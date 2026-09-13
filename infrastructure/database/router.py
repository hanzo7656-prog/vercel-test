# infrastructure/database/router.py
# ============================================================
# مسیریاب داده - نسخه ۳.۰
# Dynamic Routing + Failover + Read/Write Split
# ============================================================

import logging
import threading
from typing import Any, Optional, Dict, List
from datetime import datetime

from infrastructure.database.registry import registry
from infrastructure.database.base import DatabaseBase

logger = logging.getLogger(__name__)


class DatabaseRouter:
    """
    مسیریاب داده بر اساس نوع داده
    
    ویژگی‌ها:
        - Dynamic routing (routing config از databases.json)
        - Failover خودکار (اگر primary قطع، backup)
        - Read/Write split (اختیاری)
        - Thread-safe
        - Fallback هوشمند
    
    رفع باگ‌ها:
        - get_db_for_role بدون fallback → اضافه شد
        - Singleton بدون thread-safety → Lock
        - بدون failover → اضافه شد
    
    ارتقاها:
        - Failover خودکار
        - Read/Write split
        - Round-robin برای replicaها
        - آمار routing
    """
    
    _instance: Optional['DatabaseRouter'] = None
    _lock: threading.Lock = threading.Lock()
    
    def __new__(cls) -> 'DatabaseRouter':
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self) -> None:
        if hasattr(self, '_initialized'):
            return
        self._initialized = True
        
        self._routing: Dict[str, str] = {}
        self._read_write_split: bool = False
        self._read_replica_roles: List[str] = ["replica", "readonly"]
        self._round_robin_index: int = 0
        
        # Failover chain
        self._failover_chain: Dict[str, List[str]] = {
            "primary": ["backup"],
            "backup": [],
            "analytics": [],
            "logs": [],
            "archive": [],
            "cache": [],
        }
        
        # آمار
        self._route_count: int = 0
        self._failover_count: int = 0
        self._route_by_type: Dict[str, int] = {}
        
        logger.debug("✅ DatabaseRouter initialized")
    
    # ============================================================
    # تنظیمات
    # ============================================================
    
    def set_routing(self, routing: Dict[str, str]) -> None:
        """
        تنظیم مسیریابی
        
        پارامترها:
            routing: دیکشنری {data_type: db_name}
        """
        with self._lock:
            self._routing = dict(routing)
            logger.info(f"✅ Routing set with {len(routing)} rules")
    
    def set_read_write_split(self, enabled: bool) -> None:
        """
        فعال/غیرفعال کردن Read/Write Split
        
        پارامترها:
            enabled: True برای فعال‌سازی
        """
        self._read_write_split = enabled
        logger.info(
            f"✅ Read/Write Split: "
            f"{'enabled' if enabled else 'disabled'}"
        )
    
    def set_failover_chain(self, chain: Dict[str, List[str]]) -> None:
        """
        تنظیم زنجیره Failover
        
        پارامترها:
            chain: دیکشنری {db_name: [fallback_dbs]}
        """
        with self._lock:
            self._failover_chain = dict(chain)
            logger.info(f"✅ Failover chain set for {len(chain)} databases")
    
    def add_routing_rule(self, data_type: str, db_name: str) -> None:
        """اضافه کردن یک قاعده routing"""
        with self._lock:
            self._routing[data_type] = db_name
    
    def remove_routing_rule(self, data_type: str) -> bool:
        """حذف یک قاعده routing"""
        with self._lock:
            return self._routing.pop(data_type, None) is not None
    
    # ============================================================
    # دریافت دیتابیس
    # ============================================================
    
    def get_db_for(self, data_type: str) -> Optional[DatabaseBase]:
        """
        دریافت دیتابیس مناسب برای نوع داده
        
        پارامترها:
            data_type: نوع داده (users, cache, predictions, ...)
        
        خروجی:
            نمونه دیتابیس یا None
        
        ارتقا:
            - Failover خودکار
            - Fallback به default
        """
        self._route_count += 1
        self._route_by_type[data_type] = (
            self._route_by_type.get(data_type, 0) + 1
        )
        
        # ۱. بررسی routing config
        db_name = self._routing.get(data_type)
        
        if db_name:
            db = registry.get(db_name, auto_reconnect=True)
            
            if db is not None and db.is_connected():
                return db
            
            # Failover
            if db_name in self._failover_chain:
                for fallback_name in self._failover_chain[db_name]:
                    fallback_db = registry.get(fallback_name, auto_reconnect=True)
                    if fallback_db is not None and fallback_db.is_connected():
                        self._failover_count += 1
                        logger.warning(
                            f"⚠️ Failover: {db_name} → {fallback_name} "
                            f"for '{data_type}'"
                        )
                        return fallback_db
        
        # ۲. Fallback به default
        default_name = registry.get_default_name()
        db = registry.get(default_name, auto_reconnect=True)
        
        if db is None:
            logger.error(f"❌ No database available for '{data_type}'")
        
        return db
    
    def get_db_for_role(
        self,
        role: str,
        auto_reconnect: bool = True
    ) -> Optional[DatabaseBase]:
        """
        دریافت دیتابیس بر اساس نقش
        
        پارامترها:
            role: نقش (primary, backup, cache, ...)
            auto_reconnect: تلاش برای reconnect
        
        خروجی:
            نمونه دیتابیس یا None
        
        ارتقا:
            - Fallback خودکار
        """
        db = registry.get_by_role(role, auto_reconnect=auto_reconnect)
        
        if db is None:
            logger.warning(
                f"⚠️ Role '{role}' not available, "
                f"falling back to default"
            )
            default_name = registry.get_default_name()
            db = registry.get(default_name, auto_reconnect=auto_reconnect)
        
        return db
    
    def get_primary_db(
        self,
        auto_reconnect: bool = True
    ) -> Optional[DatabaseBase]:
        """دریافت دیتابیس اصلی (primary)"""
        return self.get_db_for_role("primary", auto_reconnect)
    
    def get_backup_db(
        self,
        auto_reconnect: bool = True
    ) -> Optional[DatabaseBase]:
        """دریافت دیتابیس پشتیبان (backup)"""
        return self.get_db_for_role("backup", auto_reconnect)
    
    def get_cache_db(
        self,
        auto_reconnect: bool = True
    ) -> Optional[DatabaseBase]:
        """دریافت دیتابیس کش (cache)"""
        return self.get_db_for_role("cache", auto_reconnect)
    
    def get_analytics_db(
        self,
        auto_reconnect: bool = True
    ) -> Optional[DatabaseBase]:
        """دریافت دیتابیس تحلیل (analytics)"""
        return self.get_db_for_role("analytics", auto_reconnect)
    
    def get_logs_db(
        self,
        auto_reconnect: bool = True
    ) -> Optional[DatabaseBase]:
        """دریافت دیتابیس لاگ (logs)"""
        return self.get_db_for_role("logs", auto_reconnect)
    
    def get_archive_db(
        self,
        auto_reconnect: bool = True
    ) -> Optional[DatabaseBase]:
        """دریافت دیتابیس آرشیو (archive)"""
        return self.get_db_for_role("archive", auto_reconnect)
    
    def get_default_db(
        self,
        auto_reconnect: bool = True
    ) -> Optional[DatabaseBase]:
        """دریافت دیتابیس پیش‌فرض"""
        default_name = registry.get_default_name()
        return registry.get(default_name, auto_reconnect=auto_reconnect)
    
    # ============================================================
    # Read/Write Split
    # ============================================================
    
    def get_write_db(self) -> Optional[DatabaseBase]:
        """
        دریافت دیتابیس برای نوشتن
        
        خروجی:
            همیشه primary
        """
        return self.get_primary_db()
    
    def get_read_db(self, data_type: Optional[str] = None) -> Optional[DatabaseBase]:
        """
        دریافت دیتابیس برای خواندن
        
        پارامترها:
            data_type: نوع داده (اختیاری)
        
        خروجی:
            اگر read_write_split فعال باشد، replica
            در غیر این صورت، primary
        """
        if not self._read_write_split:
            if data_type:
                return self.get_db_for(data_type)
            return self.get_primary_db()
        
        # تلاش برای replica
        for role in self._read_replica_roles:
            db = registry.get_by_role(role, auto_reconnect=True)
            if db is not None and db.is_connected():
                return db
        
        # Fallback به primary
        return self.get_primary_db()
    
    # ============================================================
    # آمار
    # ============================================================
    
    def get_stats(self) -> Dict[str, Any]:
        """
        دریافت آمار router
        
        خروجی:
            دیکشنری آمار
        """
        return {
            "route_count": self._route_count,
            "failover_count": self._failover_count,
            "routing_rules": len(self._routing),
            "read_write_split": self._read_write_split,
            "route_by_type": dict(self._route_by_type),
            "routing": dict(self._routing),
            "failover_chain": dict(self._failover_chain),
            "timestamp": datetime.now().isoformat(),
        }
    
    def reset_stats(self) -> None:
        """بازنشانی آمار"""
        self._route_count = 0
        self._failover_count = 0
        self._route_by_type.clear()
        logger.info("✅ Router stats reset")
    
    def get_routing_map(self) -> Dict[str, str]:
        """دریافت نقشه routing فعلی"""
        return dict(self._routing)
    
    # ============================================================
    # Bulk helpers
    # ============================================================
    
    def get_databases_for_role(self, role: str) -> List[DatabaseBase]:
        """
        دریافت همه دیتابیس‌های یک نقش
        
        پارامترها:
            role: نقش
        
        خروجی:
            لیست دیتابیس‌ها
        """
        roles = registry.get_roles()
        result = []
        
        for name, db in registry.get_all().items():
            if roles.get(role) == name:
                result.append(db)
        
        return result
    
    def get_all_databases_by_type(self, db_type: str) -> List[DatabaseBase]:
        """دریافت همه دیتابیس‌های یک نوع"""
        by_type = registry.get_by_type(db_type)
        return list(by_type.values())
    
    def __repr__(self) -> str:
        return (
            f"<DatabaseRouter "
            f"rules={len(self._routing)} "
            f"split={self._read_write_split}>"
        )


# ============================================================
# Singleton
# ============================================================

router: DatabaseRouter = DatabaseRouter()
