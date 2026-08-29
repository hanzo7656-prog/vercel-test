# infrastructure/database/sqlite_manager.py
# ============================================================
# مدیریت SQLite - نسخه ۲.۱
# ============================================================

import psycopg2
import psycopg2.extras
import logging
import time
from typing import Any, Optional, Dict, List
from infrastructure.database.base import DatabaseBase

logger = logging.getLogger(__name__)


class SQLiteManager(DatabaseBase):
    """مدیریت SQLite (از طریق PostgreSQL برای LayerBase)"""
    
    def __init__(self, name: str, config: Dict[str, Any]):
        super().__init__(name, config)
        self._connection = None
        self._cursor = None
        self._cached_version = None
        self._version_cache_time = 0
        self._version_cache_ttl = 300
    
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
            self._connection.autocommit = True
            self._cursor = self._connection.cursor()
            self._cursor.execute("SELECT 1")
            self._cursor.fetchone()
            self._connected = True
            self._client = self._connection
            logger.info(f"✅ SQLite ({self.name}) متصل شد")
            return True
        except Exception as e:
            logger.error(f"❌ خطا در اتصال SQLite ({self.name}): {e}")
            self._connected = False
            self._client = None
            return False

    def disconnect(self) -> bool:
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
        if not self.is_connected():
            if self.connect():
                logger.info(f"✅ SQLite ({self.name}) reconnect successful")
            else:
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
        result = self.execute("SELECT value FROM cache WHERE key = %s", (key,))
        if result:
            return result[0].get("value")
        return None
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        try:
            self.execute(
                "INSERT OR REPLACE INTO cache (key, value) VALUES (%s, %s)",
                (key, value)
            )
            return True
        except:
            return False
    
    def delete(self, key: str) -> bool:
        try:
            self.execute("DELETE FROM cache WHERE key = %s", (key,))
            return True
        except:
            return False
    
    def exists(self, key: str) -> bool:
        result = self.execute("SELECT 1 FROM cache WHERE key = %s", (key,))
        return len(result) > 0
    
    def flush(self) -> bool:
        try:
            self.execute("DELETE FROM cache")
            return True
        except:
            return False
    
    def get_stats(self) -> Dict[str, Any]:
        now = time.time()
        if self._cached_version and (now - self._version_cache_time) < self._version_cache_ttl:
            return {"version": self._cached_version}
        
        if not self.is_connected():
            if not self.connect():
                return {"version": self._cached_version or "unknown", "error": "not connected"}
        
        for attempt in range(3):
            try:
                result = self.execute("SELECT sqlite_version()")
                if result and len(result) > 0:
                    version = result[0].get('sqlite_version', 'unknown')
                    if version and version != 'unknown':
                        self._cached_version = version
                        self._version_cache_time = now
                        return {"version": version}
                break
            except Exception as e:
                logger.warning(f"⚠️ Attempt {attempt+1} to get SQLite version failed: {e}")
                if attempt < 2:
                    time.sleep(0.5 * (attempt + 1))
        
        return {"version": self._cached_version or "unknown"}
    
    def ping(self) -> bool:
        if not self._connected or not self._client:
            return False
        try:
            self._cursor.execute("SELECT 1")
            self._cursor.fetchone()
            return True
        except Exception:
            return False
    
    def health_check(self) -> Dict[str, Any]:
        base = super().health_check()
        try:
            stats = self.get_stats()
            base["version"] = stats.get("version", "unknown")
        except:
            base["version"] = "unknown"
        return base
