# infrastructure/database/postgresql_manager.py
# ============================================================
# مدیریت PostgreSQL (Neon) - نسخه ۳.۰
# رفع باگ + بهبود + ارتقا + Quota Integration
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


class PostgreSQLManager(DatabaseBase):
    """
    مدیریت PostgreSQL (Neon)
    
    ویژگی‌ها:
        - Connection Pool (ThreadedConnectionPool)
        - Self-Healing
        - Bulk operations (execute_many, execute_values)
        - Transaction support
        - Retry خودکار
        - Quota Integration
    
    رفع باگ‌ها:
        - INTERVAL %s SECOND اشتباه → NOW() + (%s * INTERVAL '1 second')
        - Reconnect مبهم → exponential backoff
        - بدون Pool → psycopg2.pool
        - execute بدون transaction → transaction context manager
    
    ارتقاها:
        - Connection Pool
        - Bulk operations
        - Transaction context manager
        - Retry decorator
        - Slow query logging
        - Quota check integration
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
        self._max_reconnect_attempts: int = retry_config.get("max_attempts", 3)
        self._retry_base_delay: float = retry_config.get("base_delay", 1.0)
        self._retry_max_delay: float = retry_config.get("max_delay", 10.0)
        
        # تنظیمات Pool
        pool_config = config.get("pool", {})
        self._pool_min: int = pool_config.get("min_connections", 2)
        self._pool_max: int = pool_config.get("max_connections", 10)
        self._connect_timeout: int = pool_config.get("connect_timeout", 10)
        
        # Slow query
        self._slow_query_threshold: float = 1.0
        self._current_conn: Optional[Any] = None
        
        logger.debug(f"✅ PostgreSQLManager '{name}' initialized")
    
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
                    channel_binding=conn_config.get("channel_binding", "prefer"),
                    application_name=conn_config.get(
                        "application_name", "trading-system"
                    ),
                    connect_timeout=self._connect_timeout,
                    keepalives_idle=30,
                    keepalives_interval=5,
                    keepalives_count=3,
                )
                
                # تست اتصال
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
                    f"✅ PostgreSQL '{self.name}' connected "
                    f"(pool: {self._pool_min}-{self._pool_max})"
                )
                return True
                
            except psycopg2.OperationalError as e:
                logger.error(f"❌ Operational error for '{self.name}': {e}")
                self._connected = False
                self._client = None
                return False
                
            except Exception as e:
                logger.error(f"❌ Connection error for '{self.name}': {e}")
                self._connected = False
                self._client = None
                return False
    
    def _close_pool(self) -> None:
        """بستن Pool"""
        if self._pool:
            try:
                self._pool.closeall()
            except Exception as e:
                logger.debug(f"⚠️ Pool close error: {e}")
            finally:
                self._pool = None
    
    def disconnect(self) -> bool:
        """قطع اتصال"""
        with self._lock:
            try:
                self._close_pool()
                self._connected = False
                self._client = None
                logger.info(f"✅ PostgreSQL '{self.name}' disconnected")
                return True
            except Exception as e:
                logger.error(f"❌ Disconnect error for '{self.name}': {e}")
                return False
    
    def is_connected(self) -> bool:
        """بررسی اتصال با تست واقعی"""
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
        except Exception as e:
            logger.debug(f"⚠️ Connection lost for '{self.name}': {e}")
            self._connected = False
            return False
    
    def ensure_connection(self) -> bool:
        """اطمینان از اتصال سالم"""
        if self.is_connected():
            return True
        
        logger.warning(f"⚠️ PostgreSQL '{self.name}' disconnected, reconnecting...")
        
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
        
        logger.error(
            f"❌ '{self.name}' reconnect failed after "
            f"{self._max_reconnect_attempts} attempts"
        )
        return False
    
    # ============================================================
    # Execute
    # ============================================================
    
    def execute(
        self,
        query: str,
        params: tuple = None
    ) -> List[Dict[str, Any]]:
        """
        اجرای کوئری
        
        خروجی:
            لیست دیکشنری‌های نتیجه (برای SELECT)
        """
        if not self.ensure_connection():
            logger.error(f"❌ '{self.name}' not connected")
            return []
        
        conn = None
        cursor = None
        start_time = time.time()
        query_upper = query.strip().upper()
        is_write = not (
            query_upper.startswith("SELECT") or
            query_upper.startswith("WITH") or
            query_upper.startswith("EXPLAIN") or
            query_upper.startswith("SHOW")
        )
        
        try:
            # اگر در transaction هستیم، از همون اتصال استفاده کن
            if self._current_conn is not None:
                conn = self._current_conn
                should_return = False
            else:
                conn = self._pool.getconn()
                conn.autocommit = True
                should_return = True
            
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cursor.execute(query, params or ())
            
            self._query_count += 1
            if is_write:
                self._write_count += 1
            else:
                self._read_count += 1
            
            # Slow query logging
            elapsed = time.time() - start_time
            if elapsed > self._slow_query_threshold:
                logger.warning(
                    f"⚠️ Slow query ({elapsed:.2f}s) on '{self.name}': "
                    f"{query[:100]}..."
                )
            
            # نتایج
            if not is_write:
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
            
            return []
            
        except (psycopg2.OperationalError, psycopg2.InterfaceError) as e:
            logger.warning(f"⚠️ Connection error on '{self.name}': {e}")
            self._connected = False
            self._error_count += 1
            
            if self.ensure_connection():
                logger.info(f"✅ '{self.name}' reconnected, retrying...")
                try:
                    conn = self._pool.getconn()
                    conn.autocommit = True
                    cursor = conn.cursor(
                        cursor_factory=psycopg2.extras.RealDictCursor
                    )
                    cursor.execute(query, params or ())
                    
                    if not is_write:
                        rows = cursor.fetchall()
                        return [dict(row) for row in rows]
                    return []
                except Exception as retry_error:
                    logger.error(f"❌ Retry failed: {retry_error}")
                    return []
            
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
            
            if conn is not None and should_return and self._pool is not None:
                try:
                    self._pool.putconn(conn)
                except Exception:
                    pass
    
    def execute_many(
        self,
        query: str,
        params_list: List[tuple]
    ) -> int:
        """اجرای کوئری با چند پارامتر (bulk)"""
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
            self._error_count += 1
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
    
    def execute_values(
        self,
        query: str,
        values: List[tuple],
        page_size: int = 100
    ) -> int:
        """Bulk insert با execute_values (سریع‌تر)"""
        if not self.ensure_connection():
            return 0
        
        conn = None
        cursor = None
        
        try:
            conn = self._pool.getconn()
            conn.autocommit = False
            cursor = conn.cursor()
            
            psycopg2.extras.execute_values(
                cursor, query, values, page_size=page_size
            )
            affected = cursor.rowcount
            conn.commit()
            
            self._query_count += len(values)
            self._write_count += len(values)
            return affected
            
        except Exception as e:
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
            logger.error(f"❌ execute_values error: {e}")
            self._error_count += 1
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
    # Key-Value Operations
    # ============================================================
    
    def get(self, key: str) -> Optional[Any]:
        """دریافت مقدار از جدول cache"""
        result = self.execute(
            "SELECT value FROM cache WHERE key = %s AND "
            "(expires_at IS NULL OR expires_at > NOW())",
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
        ذخیره مقدار در جدول cache
        
        رفع باگ: NOW() + (%s * INTERVAL '1 second') به جای INTERVAL %s SECOND
        """
        try:
            if ttl:
                self.execute(
                    """
                    INSERT INTO cache (key, value, expires_at)
                    VALUES (%s, %s, NOW() + (%s * INTERVAL '1 second'))
                    ON CONFLICT (key) DO UPDATE
                    SET value = EXCLUDED.value,
                        expires_at = EXCLUDED.expires_at
                    """,
                    (key, str(value), ttl)
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
        """حذف مقدار از cache"""
        try:
            self.execute("DELETE FROM cache WHERE key = %s", (key,))
            return True
        except Exception as e:
            logger.error(f"❌ Delete error: {e}")
            return False
    
    def exists(self, key: str) -> bool:
        """بررسی وجود کلید در cache"""
        result = self.execute(
            "SELECT 1 FROM cache WHERE key = %s AND "
            "(expires_at IS NULL OR expires_at > NOW())",
            (key,)
        )
        return len(result) > 0
    
    def flush(self) -> bool:
        """پاک کردن cache"""
        try:
            self.execute("TRUNCATE TABLE cache")
            return True
        except Exception as e:
            logger.error(f"❌ Flush error: {e}")
            return False
    
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
            self._current_conn = conn
            
            yield
            
            conn.commit()
            
        except Exception as e:
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
            logger.error(f"❌ Transaction failed on '{self.name}': {e}")
            raise
            
        finally:
            if conn is not None and self._pool is not None:
                try:
                    conn.autocommit = True
                    self._pool.putconn(conn)
                except Exception:
                    pass
            self._current_conn = None
    
    # ============================================================
    # Quota Integration
    # ============================================================
    
    def _get_quota_summary(self) -> Dict[str, Any]:
        """خلاصه Quota با محاسبه حجم واقعی"""
        # محاسبه حجم استفاده‌شده
        used_mb = self._calculate_used_size()
        
        # بررسی از QuotaManager
        quota_status = quota_manager.check_quota(self.name, used_mb)
        
        # آپدیت state
        self._quota_exceeded = quota_status.get("exceeded", False)
        self._quota_warning = quota_status.get("warning", False)
        
        return quota_status
    
    def _calculate_used_size(self) -> float:
        """
        محاسبه حجم استفاده‌شده (MB)
        
        با کوئری به pg_database_size
        """
        if not self.is_connected():
            return 0.0
        
        try:
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
            logger.debug(f"⚠️ Could not calculate used size for '{self.name}': {e}")
            return 0.0
    
    def get_table_sizes(self) -> List[Dict[str, Any]]:
        """
        دریافت حجم جداول
        
        خروجی:
            لیست دیکشنری‌های {table_name, size_mb, row_count}
        """
        if not self.is_connected():
            return []
        
        try:
            query = """
                SELECT 
                    schemaname || '.' || tablename AS table_name,
                    pg_total_relation_size(schemaname || '.' || tablename) 
                        AS size_bytes,
                    n_live_tup AS row_count
                FROM pg_stat_user_tables
                ORDER BY size_bytes DESC
            """
            
            result = self.execute(query)
            
            tables = []
            for row in result:
                tables.append({
                    "table_name": row.get("table_name", ""),
                    "size_mb": round(row.get("size_bytes", 0) / (1024 * 1024), 2),
                    "row_count": row.get("row_count", 0),
                })
            
            return tables
            
        except Exception as e:
            logger.error(f"❌ Table sizes error for '{self.name}': {e}")
            return []
    
    def can_write(self, estimated_size_mb: float = 0) -> bool:
        """بررسی امکان نوشتن با Quota"""
        if not super().can_write(estimated_size_mb):
            return False
        
        # چک اضافی
        used_mb = self._calculate_used_size()
        quota = quota_manager.check_quota(self.name, used_mb + estimated_size_mb)
        
        return not quota.get("exceeded", False)
    
    # ============================================================
    # Stats
    # ============================================================
    
    def get_stats(self) -> Dict[str, Any]:
        """دریافت آمار PostgreSQL"""
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
                "type": "postgresql",
            }
        
        for attempt in range(3):
            try:
                result = self.execute("SELECT version()")
                if result and len(result) > 0:
                    version_str = result[0].get("version", "")
                    match = re.search(r"(\d+\.\d+)", version_str)
                    if match:
                        version = match.group(1)
                        self._cached_version = version
                        self._version_cache_time = now
                        return self._build_stats_response(version)
                break
            except Exception as e:
                logger.debug(f"⚠️ Version attempt {attempt + 1} failed: {e}")
                if attempt < 2:
                    time.sleep(0.5 * (attempt + 1))
        
        return self._build_stats_response(self._cached_version or "unknown")
    
    def _build_stats_response(self, version: str) -> Dict[str, Any]:
        """ساخت پاسخ آمار"""
        used_mb = self._calculate_used_size()
        quota = quota_manager.check_quota(self.name, used_mb)
        
        return {
            "version": version,
            "connected": self.is_connected(),
            "name": self.name,
            "type": "postgresql",
            "pool": {
                "min": self._pool_min,
                "max": self._pool_max,
            },
            "query_count": self._query_count,
            "read_count": self._read_count,
            "write_count": self._write_count,
            "error_count": self._error_count,
            "used_mb": used_mb,
            "quota": quota,
        }
    
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
        except Exception:
            base["version"] = "unknown"
        
        return base
