# database/registry.py
# ============================================================
# ثبت و مدیریت دیتابیس‌ها - مانند پریز برق
# ============================================================

from typing import Dict, Any, Optional, List
from database.base import DatabaseBase


class DatabaseRegistry:
    """
    ثبت‌کننده دیتابیس‌ها
    هر دیتابیس با یک نام و نقش ثبت میشه
    """
    
    _instance = None
    _databases: Dict[str, DatabaseBase] = {}
    _roles: Dict[str, str] = {}  # نقش → نام دیتابیس
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def register(self, name: str, db: DatabaseBase, roles: List[str] = None):
        """ثبت یک دیتابیس با نقش‌های آن"""
        self._databases[name] = db
        
        if roles:
            for role in roles:
                self._roles[role] = name
        
        print(f"✅ دیتابیس {name} با نقش‌های {roles} ثبت شد")
    
    def get(self, name: str = None) -> Optional[DatabaseBase]:
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
        """بررسی سلامت همه دیتابیس‌ها"""
        health = {}
        for name, db in self._databases.items():
            health[name] = db.health_check()
        return health
    
    def set_config(self, config: Dict):
        """تنظیم پیکربندی"""
        self._config = config


# نمونه Singleton
registry = DatabaseRegistry()
