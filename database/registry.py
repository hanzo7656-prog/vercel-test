# database/registry.py
# ============================================================
# ثبت و مدیریت دیتابیس‌ها
# ============================================================

from typing import Dict, Any, Optional, List
from database.base import DatabaseBase


class DatabaseRegistry:
    
    _instance = None
    _databases: Dict[str, DatabaseBase] = {}
    _roles: Dict[str, str] = {}
    _config: Dict = {}
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def register(self, name: str, db: DatabaseBase, roles: List[str] = None):
        self._databases[name] = db
        if roles:
            for role in roles:
                self._roles[role] = name
        print(f"✅ دیتابیس {name} با نقش‌های {roles} ثبت شد")
    
    def get(self, name: str = None) -> Optional[DatabaseBase]:
        if name is None:
            name = self._config.get("default_db", "postgresql")
        return self._databases.get(name)
    
    def get_by_role(self, role: str) -> Optional[DatabaseBase]:
        db_name = self._roles.get(role)
        if db_name:
            return self._databases.get(db_name)
        return None
    
    def get_all(self) -> Dict[str, DatabaseBase]:
        return self._databases
    
    def get_health(self) -> Dict[str, Any]:
        """بررسی سلامت همه دیتابیس‌ها با اطلاعات کامل"""
        health = {}
        for name, db in self._databases.items():
            base = db.health_check()
        
            # دریافت stats
            stats = {}
            if hasattr(db, 'get_stats'):
                try:
                    stats = db.get_stats()
                except:
                    pass
        
            health[name] = {
                "name": name,
                "type": db.config.get("type", "unknown"),
                "host": db.config.get("host") or db.config.get("url", ""),
                "port": db.config.get("port", ""),
                "password": db.config.get("password") or db.config.get("token", ""),
                "connected": base.get("connected", False),
                "ping": base.get("ping", False),
                "enabled": db.config.get("enabled", True),
                "version": stats.get("version", "unknown"),
                "stats": stats
            }
        return health
    
    def _get_db_stats(self, db) -> Dict:
        """دریافت آمار دیتابیس (اگه ممکن باشه)"""
        stats = {}
        try:
            if hasattr(db, 'get_stats'):
                stats = db.get_stats()
        except:
            pass
        return stats
    
    def set_config(self, config: Dict):
        self._config = config


registry = DatabaseRegistry()
