# infrastructure/database/sqlite_manager.py
# ============================================================
# مدیریت SQLite (Layerbase) - نسخه ۳.۰
# رفع باگ + بهبود + ارتقا + Archive Quota
# ============================================================

import psycopg2
import psycopg2.extras
import psycopg2.pool
import logging
import time
import re
import threading
from typing import Any, Optional, Dict, List, Generator
from contextlib import contextmanager
from datetime import datetime

from infrastructure.database.base import DatabaseBase, retry_on_error
from infrastructure.database.quota_manager import quota_manager

logger = logging.getLogger(__name__)


class SQLiteManager(DatabaseBase):
    """
    مدیریت SQLite via Layerbase
    
    توجه: Layerbase SQLite 3 را از طریق پروتکل PostgreSQL ارائه می‌دهد
    (مشابه Turso)
    
    ویژگی‌ها:
        - همان API PostgreSQLManager
        - محدودیت‌های SQLite (بدون JSONB, ARRAY, INTERVAL)
        - Single writer
        - Archive-focused
        - Quota Integration
    
    رفع باگ‌ها:
        - کل فایل قبلی اشتباه بود (PostgreSQL بود نه SQLite)
        - استفاده از INTERVAL که در SQLite پشتیبانی نمی‌شود
        - بدون در نظر گرفتن محدودیت‌های SQLite
    
    ارتقاها:
        - پشتیبانی از محدودیت‌های SQLite
        - Helper برای تبدیل تاریخ‌ها
        - Quota integration
        - Archive-focused helpers
    """
    
    def __init__(self, name: str, config: Dict[str, Any]) -> None:
        super().__init__(name, config)
        
        self._pool: Optional[psycopg2.pool.ThreadedConnectionPool] = None
        self._lock: threading.Lock = threading.Lock()
        self._reconnect_attempts: int = 0
        
        # کش نسخه
        self._cached_version: Optional[str] = None
        self._version_cache_time: float = 0
        self._version_cache_ttl: float = 300
        
        # تنظیمات Retry
        retry_config = config.get("retry", {})
        self._max_reconnect_attempts: int = retry_config.get("max_attempts", 5)
        self._retry_base_delay: float = retry_config.get("base_delay", 2.0)
        self._retry_max_delay: float = retry_config.get("max_delay", 30.0)
        
        # تنظیمات Pool
        pool_config = config.get("pool", {})
        self._pool_min: int = pool_config.get("min_connections", 1)
        self._pool_max: int = pool_config.get("max_connections", 3)
        self._connect_timeout: int = pool_config.get("connect_timeout", 10)
        
        # محدودیت‌های SQLite
        features = config.get("features", {})
        self._supports_interval: bool = features.get("supports_interval", False)
        self._supports_jsonb: bool = features.get("supports_jsonb", False)
        self._supports_arrays: bool = features.get("supports_arrays", False)
        self._single_writer: bool = features.get("single_writer", True)
        
        logger.debug(f"✅ SQLiteManager '{name}' initialized")
    
    # ============================================================
    # Connection Management
    # ============================================================
    
    def connect(self) -> bool:
        """برقراری اتصال با Pool"""
        with self._lock:
            try:
                self._close_pool()
                
                conn_config = self.config.get("connection", {})
                
                self._pool = psycopg2.pool.ThreadedConnectionPool(
                    minconn=self._pool_min,
                    maxconn=self._pool_max,
                    host=conn_config.get("host"),
                    port=conn_config.get("port", 5432),
                    user=conn_config.get("user"),
                    password=conn_config.get("password"),
                    dbname=conn_config.get("database"),
                    sslmode=conn_config.get("sslmode", "require"),
                    application_name=conn_config.get(
                        "application_name", "layerbase-sqlite"
                    ),
                    connect_timeout=self._connect_timeout,
                )
                
                # تست
                conn = self._pool.getconn()
                try:
                    cursor = conn.cursor()
                    cursor.execute("SELECT 1")
                    cursor.fetchone()
                    cursor.close()
                finally:
                    self._pool.putconn(conn)
                
                self._connected = True
                self._client = self._pool
                self._reconnect_attempts = 0
                
                logger.info(
                    f"✅ SQLite (Layerbase) '{self.name}' connected "
                    f"(pool: {self._pool_min}-{self._pool_max})"
                )
                return True
                
            except psycopg2.OperationalError as e:
                logger.error(f"❌ Operational error for '{self.name}': {e}")
                self._connected = False
                return False
            except Exception as e:
                logger.error(f"❌ Connection error for '{self.name}': {e}")
                self._connected = False
                return False
    
    def _close_pool(self) -> None:
        """بستن Pool"""
        if self._pool:
            try:
                self._pool.closeall()
            except Exception:
                pass
            finally:
                self._pool = None
    
    def disconnect(self) -> bool:
        """قطع اتصال"""
        with self._lock:
            try:
                self._close_pool()
                self._connected = False
                self._client = None
                logger.info(f"✅ SQLite '{self.name}' disconnected")
                return True
            except Exception as e:
                logger.error(f"❌ Disconnect error: {e}")
                return False
    
    def is_connected(self) -> bool:
        """بررسی اتصال"""
        if not self._connected or self._pool is None:
            return False
        
        try:
            conn = self._pool.getconn()
            try:
                cursor = conn.cursor()
                cursor.execute("SELECT 1")
                cursor.fetchone()
                cursor.close()
                return True
            finally:
                self._pool.putconn(conn)
        except Exception:
            self._connected = False
            return False
    
    def ensure_connection(self) -> bool:
        """اطمینان از اتصال سالم"""
        if self.is_connected():
            return True
        
        logger.warning(f"⚠️ SQLite '{self.name}' disconnected, reconnecting...")
        self.disconnect()
        
        for attempt in range(self._max_reconnect_attempts):
            if self.connect():
                logger.info(
                    f"✅ '{self.name}' reconnected "
                    f"(attempt {attempt + 1}/{self._max_reconnect_attempts})"
                )
                return True
            
            delay = min(
                self._retry_base_delay * (2 ** attempt),
                self._retry_max_delay
            )
            logger.warning(f"⏳ Retry in {delay:.1f}s...")
            time.sleep(delay)
        
        logger.error(f"❌ '{self.name}' reconnect failed")
        return False
    
    # ============================================================
    # Execute
    # ============================================================
    
    def execute(
        self,
        query: str,
        params: tuple = None
    ) -> List[Dict[str, Any]]:
        """اجرای کوئری"""
        if not self.ensure_connection():
            logger.error(f"❌ '{self.name}' not connected")
            return []
        
        conn = None
        cursor = None
        query_upper = query.strip().upper()
        is_write = not (
            query_upper.startswith("SELECT") or
            query_upper.startswith("WITH") or
            query_upper.startswith("EXPLAIN") or
            query_upper.startswith("PRAGMA")
        )
        
        try:
            conn = self._pool.getconn()
            conn.autocommit = True
            
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cursor.execute(query, params or ())
            
            self._query_count += 1
            if is_write:
                self._write_count += 1
            else:
                self._read_count += 1
            
            if not is_write:
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
            
            return []
            
        except (psycopg2.OperationalError, psycopg2.InterfaceError) as e:
            logger.warning(f"⚠️ Connection error on '{self.name}': {e}")
            self._connected = False
            self._error_count += 1
            return []
        except Exception as e:
            self._error_count += 1
            logger.error(f"❌ Query error on '{self.name}': {e}")
            return []
        finally:
            if cursor is not None:
                try:
                    cursor.close()
                except Exception:
                    pass
            if conn is not None and self._pool is not None:
                try:
                    self._pool.putconn(conn)
                except Exception:
                    pass
    
    def execute_many(
        self,
        query: str,
        params_list: List[tuple]
    ) -> int:
        """اجرای bulk"""
        if not self.ensure_connection():
            return 0
        
        conn = None
        cursor = None
        
        try:
            conn = self._pool.getconn()
            conn.autocommit = False
            cursor = conn.cursor()
            
            cursor.executemany(query, params_list)
            affected = cursor.rowcount
            conn.commit()
            
            self._query_count += len(params_list)
            self._write_count += len(params_list)
            return affected
            
        except Exception as e:
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
            logger.error(f"❌ execute_many error: {e}")
            return 0
        finally:
            if cursor is not None:
                try:
                    cursor.close()
                except Exception:
                    pass
            if conn is not None and self._pool is not None:
                try:
                    conn.autocommit = True
                    self._pool.putconn(conn)
                except Exception:
                    pass
    
    # ============================================================
    # Key-Value Operations (با محدودیت SQLite)
    # ============================================================
    
    def get(self, key: str) -> Optional[Any]:
        """
        دریافت مقدار از cache
        
        توجه: SQLite از INTERVAL پشتیبانی نمی‌کند،
        پس از مقایسه مستقیم datetime استفاده می‌کنیم
        """
        result = self.execute(
            "SELECT value FROM cache WHERE key = %s AND "
            "(expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)",
            (key,)
        )
        if result:
            return result[0].get("value")
        return None
    
    def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None
    ) -> bool:
        """
        ذخیره مقدار در cache
        
        توجه: به جای INTERVAL از datetime استفاده می‌کنیم
        چون SQLite از INTERVAL پشتیبانی نمی‌کند
        """
        try:
            if ttl:
                # محاسبه expires_at در Python
                from datetime import timedelta
                expires_at = datetime.now() + timedelta(seconds=ttl)
                
                self.execute(
                    """
                    INSERT INTO cache (key, value, expires_at)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (key) DO UPDATE
                    SET value = EXCLUDED.value,
                        expires_at = EXCLUDED.expires_at
                    """,
                    (key, str(value), expires_at.isoformat())
                )
            else:
                self.execute(
                    """
                    INSERT INTO cache (key, value, expires_at)
                    VALUES (%s, %s, NULL)
                    ON CONFLICT (key) DO UPDATE
                    SET value = EXCLUDED.value,
                        expires_at = NULL
                    """,
                    (key, str(value))
                )
            return True
        except Exception as e:
            logger.error(f"❌ Set error: {e}")
            return False
    
    def delete(self, key: str) -> bool:
        """حذف"""
        try:
            self.execute("DELETE FROM cache WHERE key = %s", (key,))
            return True
        except Exception as e:
            logger.error(f"❌ Delete error: {e}")
            return False
    
    def exists(self, key: str) -> bool:
        """بررسی وجود"""
        result = self.execute(
            "SELECT 1 FROM cache WHERE key = %s AND "
            "(expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)",
            (key,)
        )
        return len(result) > 0
    
    def flush(self) -> bool:
        """پاک کردن"""
        try:
            self.execute("DELETE FROM cache")
            return True
        except Exception as e:
            logger.error(f"❌ Flush error: {e}")
            return False
    
    # ============================================================
    # Archive Helpers
    # ============================================================
    
    def archive_batch(
        self,
        table_name: str,
        columns: List[str],
        rows: List[tuple],
        batch_size: int = 100
    ) -> int:
        """
        آرشیو batch از داده‌ها
        
        پارامترها:
            table_name: نام جدول
            columns: لیست ستون‌ها
            rows: لیست رکوردها
            batch_size: اندازه batch
        
        خروجی:
            تعداد رکوردهای ذخیره‌شده
        """
        if not rows:
            return 0
        
        try:
            # ساخت کوئری INSERT
            columns_str = ", ".join(columns)
            placeholders = ", ".join(["%s"] * len(columns))
            query = f"INSERT INTO {table_name} ({columns_str}) VALUES ({placeholders})"
            
            total = 0
            for i in range(0, len(rows), batch_size):
                batch = rows[i:i + batch_size]
                affected = self.execute_many(query, batch)
                total += affected
            
            logger.info(f"✅ Archived {total} rows to {table_name}")
            quota_manager.mark_cleanup_done(self.name, table_name)
            return total
            
        except Exception as e:
            logger.error(f"❌ archive_batch error: {e}")
            return 0
    
    def get_table_count(self, table_name: str) -> int:
        """دریافت تعداد رکوردهای یک جدول"""
        try:
            result = self.execute(f"SELECT COUNT(*) as count FROM {table_name}")
            return result[0].get("count", 0) if result else 0
        except Exception as e:
            logger.error(f"❌ count error: {e}")
            return 0
    
    def cleanup_old_records(
        self,
        table_name: str,
        date_column: str,
        retention_days: int
    ) -> int:
        """
        پاک کردن رکوردهای قدیمی
        
        پارامترها:
            table_name: نام جدول
            date_column: نام ستون تاریخ
            retention_days: مدت نگهداری
        
        خروجی:
            تعداد رکوردهای حذف شده
        """
        try:
            from datetime import timedelta
            cutoff = datetime.now() - timedelta(days=retention_days)
            
            # ابتدا شمارش
            count_result = self.execute(
                f"SELECT COUNT(*) as count FROM {table_name} "
                f"WHERE {date_column} < %s",
                (cutoff.isoformat(),)
            )
            count = count_result[0].get("count", 0) if count_result else 0
            
            if count == 0:
                return 0
            
            # حذف
            self.execute(
                f"DELETE FROM {table_name} WHERE {date_column} < %s",
                (cutoff.isoformat(),)
            )
            
            logger.info(
                f"✅ Cleaned {count} old records from "
                f"{table_name} (retention: {retention_days}d)"
            )
            quota_manager.mark_cleanup_done(self.name, table_name)
            return count
            
        except Exception as e:
            logger.error(f"❌ cleanup_old_records error: {e}")
            return 0
    
    # ============================================================
    # Transaction
    # ============================================================
    
    @contextmanager
    def transaction(self) -> Generator[None, None, None]:
        """Context manager برای transaction"""
        conn = None
        
        try:
            if not self.ensure_connection():
                raise RuntimeError(f"'{self.name}' not connected")
            
            conn = self._pool.getconn()
            conn.autocommit = False
            
            yield
            
            conn.commit()
            
        except Exception as e:
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
            logger.error(f"❌ Transaction failed: {e}")
            raise
        finally:
            if conn is not None and self._pool is not None:
                try:
                    conn.autocommit = True
                    self._pool.putconn(conn)
                except Exception:
                    pass
    
    # ============================================================
    # Stats & Quota
    # ============================================================
    
    def _calculate_used_size(self) -> float:
        """محاسبه حجم (تخمینی برای SQLite)"""
        if not self.is_connected():
            return 0.0
        
        try:
            # برای SQLite، از pg_database_size استفاده می‌کنیم
            # (چون از طریق PostgreSQL ارائه می‌شود)
            conn_config = self.config.get("connection", {})
            db_name = conn_config.get("database", "")
            
            result = self.execute(
                "SELECT pg_database_size(%s) AS size_bytes",
                (db_name,)
            )
            
            if result:
                size_bytes = result[0].get("size_bytes", 0) or 0
                return round(size_bytes / (1024 * 1024), 2)
            
            return 0.0
            
        except Exception as e:
            logger.debug(f"⚠️ Could not calculate size: {e}")
            return 0.0
    
    def _get_quota_summary(self) -> Dict[str, Any]:
        """خلاصه Quota"""
        used_mb = self._calculate_used_size()
        return quota_manager.check_quota(self.name, used_mb)
    
    def get_stats(self) -> Dict[str, Any]:
        """دریافت آمار"""
        now = time.time()
        if (
            self._cached_version
            and (now - self._version_cache_time) < self._version_cache_ttl
        ):
            return self._build_stats_response(self._cached_version)
        
        if not self.ensure_connection():
            return {
                "version": self._cached_version or "unknown",
                "connected": False,
                "name": self.name,
                "type": "sqlite",
            }
        
        # SQLite نسخه‌اش از طریق SQLite query می‌آید
        for attempt in range(3):
            try:
                result = self.execute("SELECT sqlite_version() AS version")
                if result:
                    version = result[0].get("version", "unknown")
                    self._cached_version = version
                    self._version_cache_time = now
                    return self._build_stats_response(version)
                break
            except Exception as e:
                logger.debug(f"⚠️ Version attempt {attempt + 1}: {e}")
                if attempt < 2:
                    time.sleep(0.5)
        
        return self._build_stats_response(self._cached_version or "unknown")
    
    def _build_stats_response(self, version: str) -> Dict[str, Any]:
        """ساخت پاسخ آمار"""
        used_mb = self._calculate_used_size()
        quota = quota_manager.check_quota(self.name, used_mb)
        
        return {
            "version": version,
            "connected": self.is_connected(),
            "name": self.name,
            "type": "sqlite",
            "engine": "sqlite3",
            "pool": {
                "min": self._pool_min,
                "max": self._pool_max,
            },
            "features": {
                "supports_interval": self._supports_interval,
                "supports_jsonb": self._supports_jsonb,
                "supports_arrays": self._supports_arrays,
                "single_writer": self._single_writer,
            },
            "query_count": self._query_count,
            "read_count": self._read_count,
            "write_count": self._write_count,
            "error_count": self._error_count,
            "used_mb": used_mb,
            "quota": quota,
        }
    
    def get_table_sizes(self) -> List[Dict[str, Any]]:
        """دریافت حجم جداول"""
        if not self.is_connected():
            return []
        
        try:
            # برای SQLite، لیست جداول
            tables_result = self.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
            
            result = []
            for row in tables_result:
                table_name = row.get("name", "")
                try:
                    count_result = self.execute(
                        f"SELECT COUNT(*) as count FROM {table_name}"
                    )
                    count = count_result[0].get("count", 0) if count_result else 0
                    
                    # تخمین حجم
                    estimated_mb = count * 0.001  # تخمینی
                    
                    result.append({
                        "table_name": table_name,
                        "size_mb": round(estimated_mb, 2),
                        "row_count": count,
                    })
                except Exception:
                    continue
            
            return result
            
        except Exception as e:
            logger.error(f"❌ Table sizes error: {e}")
            return []
    
    def can_write(self, estimated_size_mb: float = 0) -> bool:
        """بررسی امکان نوشتن"""
        if self._single_writer:
            # برای SQLite، writer تک است
            # می‌توانیم lock بگیریم یا فقط اجازه بدهیم
            pass
        
        return super().can_write(estimated_size_mb)
    
    def ping(self) -> bool:
        """بررسی سلامت"""
        return self.is_connected()
    
    def health_check(self) -> Dict[str, Any]:
        """بررسی سلامت کامل"""
        base = super().health_check()
        
        try:
            stats = self.get_stats()
            base["version"] = stats.get("version", "unknown")
            base["pool"] = stats.get("pool", {})
            base["used_mb"] = stats.get("used_mb", 0)
            base["quota"] = stats.get("quota", {})
            base["features"] = stats.get("features", {})
        except Exception:
            base["version"] = "unknown"
        
        return base
