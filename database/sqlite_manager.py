# database/sqlite_manager.py
# ============================================================
# مدیریت SQLite (از طریق پروتکل PostgreSQL)
# ============================================================

import psycopg2
import psycopg2.extras
import logging
from typing import Any, Optional, Dict, List
from database.base import DatabaseBase

logger = logging.getLogger(__name__)


class SQLiteManager(DatabaseBase):
    """مدیریت SQLite از طریق پروتکل PostgreSQL"""
    
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
            logger.info(f"✅ SQLite ({self.name}) متصل شد")
            return True
        except Exception as e:
            logger.error(f"❌ خطا در اتصال SQLite ({self.name}): {e}")
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
            logger.info(f"✅ SQLite ({self.name}) قطع شد")
            return True
        except Exception as e:
            logger.error(f"❌ خطا در قطع SQLite ({self.name}): {e}")
            return False
            
    def execute(self, query: str, params: tuple = None) -> List[Dict]:
        """اجرای کوئری و برگرداندن نتایج"""
        if not self.is_connected():
            logger.warning(f"⚠️ SQLite ({self.name}) متصل نیست")
            return []
    
        try:
            with self._connection.cursor() as cursor:
                cursor.execute(query, params or ())
                if query.strip().upper().startswith("SELECT"):
                    rows = cursor.fetchall()
                    if rows:
                        columns = [desc[0] for desc in cursor.description]
                        return [dict(zip(columns, row)) for row in rows]
                    return []
                self._connection.commit()
                return []
        except Exception as e:
            logger.error(f"❌ خطا در اجرای کوئری SQLite ({self.name}): {e}")
            self._connection.rollback()
            return []
    
    def get(self, key: str) -> Optional[Any]:
        """دریافت مقدار"""
        result = self.execute("SELECT value FROM cache WHERE key = %s", (key,))
        if result:
            return result[0].get("value")
        return None
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """ذخیره مقدار"""
        try:
            self.execute(
                "INSERT OR REPLACE INTO cache (key, value) VALUES (%s, %s)",
                (key, value)
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
            self.execute("DELETE FROM cache")
            return True
        except:
            return False
            
    def get_stats(self) -> Dict[str, Any]:
        """دریافت آمار SQLite"""
        try:
            if not self.is_connected():
                return {"version": "unknown", "error": "not connected"}
        
            # دریافت ورژن SQLite
            result = self.execute("SELECT sqlite_version()")
            if result and len(result) > 0:
                version = result[0].get('sqlite_version', 'unknown')
                return {"version": version}
            return {"version": "unknown"}
        except Exception as e:
            print(f"⚠️ SQLite stats error: {e}")
            return {"version": "unknown"}
            
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
            result = self.execute("SELECT sqlite_version()")
            base["version"] = result[0].get("sqlite_version", "unknown") if result else "unknown"
        except:
            base["version"] = "error"
        return base
