# database/postgresql_manager.py
# ============================================================
# مدیریت PostgreSQL
# ============================================================

import psycopg2
import psycopg2.extras
import logging
from typing import Any, Optional, Dict, List
from database.base import DatabaseBase

logger = logging.getLogger(__name__)


class PostgreSQLManager(DatabaseBase):
    """مدیریت PostgreSQL"""
    
    def __init__(self, name: str, config: Dict[str, Any]):
        super().__init__(name, config)
        self._connection = None
        self._cursor = None
    
    def connect(self) -> bool:
        try:
            self._connection = psycopg2.connect(
                host=self.config.get("host"),
                port=self.config.get("port", 5432),
                user=self.config.get("user"),
                password=self.config.get("password"),
                dbname=self.config.get("database"),
                sslmode="require" if self.config.get("ssl", True) else "disable",
                connect_timeout=10
            )
            self._cursor = self._connection.cursor()
            # تست اتصال
            self._cursor.execute("SELECT 1")
            self._cursor.fetchone()
            self._connected = True
            self._client = self._connection  # ← مهم!
            logger.info(f"✅ PostgreSQL ({self.name}) متصل شد")
            return True
        except Exception as e:
            logger.error(f"❌ خطا در اتصال PostgreSQL ({self.name}): {e}")
            self._connected = False
            self._client = None
            return False

    def disconnect(self) -> bool:
        """قطع اتصال"""
        try:
            if self._cursor:
                self._cursor.close()
            if self._connection:
                self._connection.close()
            self._connected = False
            logger.info(f"✅ PostgreSQL ({self.name}) قطع شد")
            return True
        except Exception as e:
            logger.error(f"❌ خطا در قطع PostgreSQL ({self.name}): {e}")
            return False
    
    def execute(self, query: str, params: tuple = None) -> List[Dict]:
        """اجرای کوئری و برگرداندن نتایج"""
        if not self.is_connected():
            logger.warning(f"⚠️ PostgreSQL ({self.name}) متصل نیست")
            return []
        
        try:
            self._cursor.execute(query, params or ())
            if query.strip().upper().startswith("SELECT"):
                rows = self._cursor.fetchall()
                return [dict(row) for row in rows]
            self._connection.commit()
            return []
        except Exception as e:
            logger.error(f"❌ خطا در اجرای کوئری PostgreSQL ({self.name}): {e}")
            self._connection.rollback()
            return []
    
    def get(self, key: str) -> Optional[Any]:
        """دریافت مقدار (برای سازگاری)"""
        result = self.execute("SELECT value FROM cache WHERE key = %s", (key,))
        if result:
            return result[0].get("value")
        return None
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """ذخیره مقدار (برای سازگاری)"""
        try:
            self.execute(
                "INSERT INTO cache (key, value, expires_at) VALUES (%s, %s, NOW() + INTERVAL %s SECOND) "
                "ON CONFLICT (key) DO UPDATE SET value = %s, expires_at = NOW() + INTERVAL %s SECOND",
                (key, value, ttl or 3600, value, ttl or 3600)
            )
            return True
        except:
            return False
    
    def delete(self, key: str) -> bool:
        """حذف مقدار"""
        try:
            self.execute("DELETE FROM cache WHERE key = %s", (key,))
            return True
        except:
            return False
    
    def exists(self, key: str) -> bool:
        """بررسی وجود کلید"""
        result = self.execute("SELECT 1 FROM cache WHERE key = %s", (key,))
        return len(result) > 0
    
    def flush(self) -> bool:
        """پاک کردن همه داده‌ها"""
        try:
            self.execute("TRUNCATE TABLE cache")
            return True
        except:
            return False
    def get_stats(self) -> Dict[str, Any]:
        """دریافت آمار PostgreSQL"""
        try:
            result = self.execute("SELECT version()")
            if result:
                return {
                    "version": result[0].get("version", "unknown")
                }
            return {"version": "unknown"}
        except Exception as e:
            logger.warning(f"⚠️ Could not get stats for PostgreSQL: {e}")
            return {"version": "unknown"}
            
    def create_table(self, table_name: str, schema: Dict[str, str]) -> bool:
        """ایجاد جدول جدید"""
        try:
            columns = ", ".join([f"{k} {v}" for k, v in schema.items()])
            query = f"CREATE TABLE IF NOT EXISTS {table_name} ({columns})"
            self.execute(query)
            return True
        except Exception as e:
            logger.error(f"❌ خطا در ایجاد جدول {table_name}: {e}")
            return False
    
    def ping(self) -> bool:
        """بررسی سلامت اتصال"""
        if not self._connected or not self._client:
            return False
        try:
            self._cursor.execute("SELECT 1")
            self._cursor.fetchone()
            return True
        except Exception:
            return False
    
    def health_check(self) -> Dict[str, Any]:
        """بررسی سلامت کامل"""
        base = super().health_check()
        try:
            result = self.execute("SELECT version()")
            base["version"] = result[0].get("version", "unknown") if result else "unknown"
        except:
            base["version"] = "error"
        return base
