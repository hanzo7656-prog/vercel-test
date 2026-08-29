# infrastructure/database/registry.py
# ============================================================
# ثبت و مدیریت دیتابیس‌ها - نسخه ۲.۰ (انتقال به Infrastructure)
# ============================================================

from typing import Dict, Any, Optional, List
from infrastructure.database.base import DatabaseBase
import logging

logger = logging.getLogger(__name__)


class DatabaseRegistry:
    """ثبت و مدیریت دیتابیس‌ها"""
    
    _instance = None
    _databases: Dict[str, DatabaseBase] = {}
    _roles: Dict[str, str] = {}
    _config: Dict[str, Any] = {}
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def register(self, name: str, db: DatabaseBase, roles: List[str] = None) -> None:
        """ثبت یک دیتابیس"""
        self._databases[name] = db
        if roles:
            for role in roles:
                self._roles[role] = name
        logger.info(f"✅ دیتابیس {name} با نقش‌های {roles} ثبت شد")
    
    def get(self, name: Optional[str] = None) -> Optional[DatabaseBase]:
        """دریافت دیتابیس با نام"""
        if name is None:
            name = self._config.get("default_db", "postgresql")
        return self._databases.get(name)
    
    def get_by_role(self, role: str) -> Optional[DatabaseBase]:
        """دریافت دیتابیس بر اساس نقش"""
        db_name = self._roles.get(role)
        if db_name:
            return self._databases.get(db_name)
        return None
    
    def get_all(self) -> Dict[str, DatabaseBase]:
        """دریافت همه دیتابیس‌ها"""
        return self._databases
    
    def get_health(self) -> Dict[str, Any]:
        """بررسی سلامت همه دیتابیس‌ها با اطلاعات کامل"""
        health: Dict[str, Any] = {}
        for name, db in self._databases.items():
            base = db.health_check()
            
            stats: Dict[str, Any] = {}
            if hasattr(db, 'get_stats'):
                try:
                    stats = db.get_stats()
                except Exception:
                    pass
            
            health[name] = {
                "name": name,
                "type": db.config.get("type", "unknown"),
                "host": db.config.get("host") or db.config.get("url", ""),
                "port": db.config.get("port", ""),
                "connected": base.get("connected", False),
                "ping": base.get("ping", False),
                "enabled": db.config.get("enabled", True),
                "version": stats.get("version", "unknown"),
                "stats": stats
            }
        return health
    
    def set_config(self, config: Dict[str, Any]) -> None:
        """تنظیم تنظیمات"""
        self._config = config


registry: DatabaseRegistry = DatabaseRegistry()
