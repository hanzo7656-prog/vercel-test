# database/router.py
# ============================================================
# مسیریاب داده - مشخص میکنه هر داده به کدام دیتابیس بره
# ============================================================

from typing import Any, Optional, Dict
from database.registry import registry


class DatabaseRouter:
    """
    مسیریاب داده
    بر اساس نوع داده، دیتابیس مناسب را انتخاب میکنه
    """
    
    _instance = None
    _routing: Dict[str, str] = {}
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def set_routing(self, routing: Dict[str, str]):
        """تنظیم مسیریابی"""
        self._routing = routing
        print(f"✅ مسیریابی با {len(routing)} قانون تنظیم شد")
    
    def get_db_for(self, data_type: str) -> Optional[Any]:
        """
        دریافت دیتابیس مناسب برای نوع داده
        مثال: get_db_for("users") → PostgreSQL
        """
        db_name = self._routing.get(data_type)
        if db_name:
            return registry.get(db_name)
        
        # Fallback به پیش‌فرض
        return registry.get()
    
    def get_db_for_role(self, role: str) -> Optional[Any]:
        """دریافت دیتابیس بر اساس نقش"""
        return registry.get_by_role(role)
    
    def get_cache_db(self):
        """دریافت دیتابیس کش (Redis)"""
        return self.get_db_for_role("cache")
    
    def get_primary_db(self):
        """دریافت دیتابیس اصلی (PostgreSQL)"""
        return self.get_db_for_role("primary")
    
    def get_backup_db(self):
        """دریافت دیتابیس پشتیبان (SQLite)"""
        return self.get_db_for_role("backup")


# نمونه Singleton
router = DatabaseRouter()
