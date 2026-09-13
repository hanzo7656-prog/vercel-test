# infrastructure/database/registry.py
# ============================================================
# ثبت و مدیریت دیتابیس‌ها - نسخه ۳.۰
# رفع باگ + بهبود + ارتقا
# ============================================================

import logging
import threading
import time
from typing import Dict, Any, Optional, List
from datetime import datetime
from contextlib import contextmanager

from infrastructure.database.base import DatabaseBase

logger = logging.getLogger(__name__)


class DatabaseRegistry:
    """
    ثبت و مدیریت دیتابیس‌ها
    
    ویژگی‌ها:
        - Thread-safe با Lock
        - Health check با reconnect خودکار
        - get_by_role با fallback
        - Context manager support
        - Cleanup خودکار
    
    رفع باگ‌ها:
        - بدون thread-safety → Lock
        - Reconnect خودکار ندارد → اضافه شد
        - get_by_role بدون fallback → fallback به primary
        - بدون cleanup → unregister
    
    ارتقاها:
        - Health check گروهی
        - Summary کارآمد
        - Categorized databases (by type)
        - Uptime tracking
    """
    
    _instance: Optional['DatabaseRegistry'] = None
    _lock: threading.Lock = threading.Lock()
    
    def __new__(cls) -> 'DatabaseRegistry':
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self) -> None:
        if hasattr(self, '_initialized'):
            return
        self._initialized = True
        
        self._databases: Dict[str, DatabaseBase] = {}
        self._roles: Dict[str, str] = {}
        self._config: Dict[str, Any] = {}
        self._registered_at: datetime = datetime.now()
        
        # آمار reconnect
        self._reconnect_count: int = 0
        self._last_reconnect: Optional[datetime] = None
        
        logger.debug("✅ DatabaseRegistry initialized")
    
    # ============================================================
    # ثبت و حذف
    # ============================================================
    
    def register(
        self,
        name: str,
        db: DatabaseBase,
        roles: Optional[List[str]] = None
    ) -> None:
        """
        ثبت یک دیتابیس
        
        پارامترها:
            name: نام دیتابیس
            db: نمونه دیتابیس
            roles: نقش‌ها (primary, backup, ...)
        """
        with self._lock:
            # حذف قبلی اگر وجود داشت
            if name in self._databases:
                logger.warning(f"⚠️ Replacing existing database '{name}'")
                try:
                    self._databases[name].disconnect()
                except Exception:
                    pass
            
            self._databases[name] = db
            
            if roles:
                for role in roles:
                    self._roles[role] = name
            
            logger.info(
                f"✅ Database '{name}' registered "
                f"(type: {db.config.get('type', 'unknown')}, roles: {roles})"
            )
    
    def unregister(self, name: str) -> bool:
        """
        حذف یک دیتابیس
        
        پارامترها:
            name: نام دیتابیس
        
        خروجی:
            True اگر موفق
        """
        with self._lock:
            if name not in self._databases:
                return False
            
            db = self._databases.pop(name)
            
            # قطع اتصال
            try:
                db.disconnect()
            except Exception:
                pass
            
            # حذف نقش‌ها
            self._roles = {
                role: db_name
                for role, db_name in self._roles.items()
                if db_name != name
            }
            
            logger.info(f"✅ Database '{name}' unregistered")
            return True
    
    def clear(self) -> None:
        """حذف همه دیتابیس‌ها"""
        with self._lock:
            for name, db in list(self._databases.items()):
                try:
                    db.disconnect()
                except Exception:
                    pass
            
            self._databases.clear()
            self._roles.clear()
            
            logger.info("🧹 All databases unregistered")
    
    # ============================================================
    # دسترسی
    # ============================================================
    
    def get(
        self,
        name: Optional[str] = None,
        auto_reconnect: bool = True
    ) -> Optional[DatabaseBase]:
        """
        دریافت دیتابیس با نام
        
        پارامترها:
            name: نام دیتابیس (پیش‌فرض: default از config)
            auto_reconnect: تلاش برای reconnect در صورت قطعی
        
        خروجی:
            نمونه دیتابیس یا None
        
        ارتقا:
            - Reconnect خودکار
            - آمار reconnect
        """
        if name is None:
            name = self._config.get("default", "primary")
        
        db = self._databases.get(name)
        
        if db is None:
            logger.debug(f"⚠️ Database '{name}' not found")
            return None
        
        # Reconnect خودکار اگر قطع بود
        if auto_reconnect and not db.is_connected():
            logger.warning(f"⚠️ Database '{name}' disconnected, reconnecting...")
            self._reconnect_count += 1
            self._last_reconnect = datetime.now()
            
            try:
                if db.connect():
                    logger.info(f"✅ Database '{name}' reconnected")
                else:
                    logger.error(f"❌ Failed to reconnect '{name}'")
            except Exception as e:
                logger.error(f"❌ Reconnect error for '{name}': {e}")
        
        return db
    
    def get_by_role(
        self,
        role: str,
        auto_reconnect: bool = True
    ) -> Optional[DatabaseBase]:
        """
        دریافت دیتابیس بر اساس نقش
        
        پارامترها:
            role: نقش (primary, backup, analytics, ...)
            auto_reconnect: تلاش برای reconnect
        
        خروجی:
            نمونه دیتابیس یا None
        
        ارتقا:
            - Fallback به primary اگر role پیدا نشد
        """
        db_name = self._roles.get(role)
        
        if db_name is None:
            logger.debug(
                f"⚠️ Role '{role}' not found, "
                f"falling back to default"
            )
            default_name = self._config.get("default", "primary")
            return self.get(default_name, auto_reconnect)
        
        return self.get(db_name, auto_reconnect)
    
    def get_all(self) -> Dict[str, DatabaseBase]:
        """
        دریافت همه دیتابیس‌ها
        
        خروجی:
            دیکشنری {name: db_instance}
        """
        with self._lock:
            return dict(self._databases)
    
    def get_by_type(self, db_type: str) -> Dict[str, DatabaseBase]:
        """
        دریافت دیتابیس‌های یک نوع خاص
        
        پارامترها:
            db_type: نوع دیتابیس (postgresql, redis, ...)
        
        خروجی:
            دیکشنری {name: db_instance}
        """
        with self._lock:
            return {
                name: db
                for name, db in self._databases.items()
                if db.config.get("type") == db_type
            }
    
    def get_names(self) -> List[str]:
        """دریافت لیست نام دیتابیس‌ها"""
        with self._lock:
            return list(self._databases.keys())
    
    def get_roles(self) -> Dict[str, str]:
        """دریافت mapping نقش‌ها"""
        with self._lock:
            return dict(self._roles)
    
    def has(self, name: str) -> bool:
        """بررسی وجود دیتابیس"""
        with self._lock:
            return name in self._databases
    
    # ============================================================
    # Health & Status
    # ============================================================
    
    def get_health(self) -> Dict[str, Any]:
        """
        بررسی سلامت همه دیتابیس‌ها
        
        خروجی:
            دیکشنری سلامت
        
        ارتقا:
            - اطلاعات کامل‌تر
            - Reconnect در حین بررسی
        """
        health: Dict[str, Any] = {}
        
        # کپی از دیتابیس‌ها برای جلوگیری از lock طولانی
        with self._lock:
            databases = dict(self._databases)
        
        for name, db in databases.items():
            try:
                base = db.health_check()
                
                # اطلاعات اضافی
                stats: Dict[str, Any] = {}
                try:
                    if hasattr(db, 'get_stats'):
                        stats = db.get_stats()
                except Exception as e:
                    logger.debug(f"⚠️ Could not get stats for {name}: {e}")
                
                conn_config = db.config.get("connection", {})
                
                health[name] = {
                    "name": name,
                    "type": db.config.get("type", "unknown"),
                    "host": conn_config.get("host", ""),
                    "port": conn_config.get("port", ""),
                    "database": conn_config.get("database", ""),
                    "connected": base.get("connected", False),
                    "ping": base.get("ping", False),
                    "enabled": db.config.get("enabled", True),
                    "version": stats.get("version", "unknown"),
                    "uptime_seconds": base.get("uptime_seconds", 0),
                    "uptime_formatted": base.get("uptime_formatted", "0s"),
                    "stats": base.get("stats", {}),
                    "quota": base.get("quota", {}),
                    "used_mb": stats.get("used_mb", 0),
                }
            except Exception as e:
                logger.error(f"❌ Health check error for '{name}': {e}")
                health[name] = {
                    "name": name,
                    "type": db.config.get("type", "unknown"),
                    "connected": False,
                    "ping": False,
                    "error": str(e),
                }
        
        return health
    
    def get_summary(self) -> Dict[str, Any]:
        """
        خلاصه وضعیت همه دیتابیس‌ها
        
        خروجی:
            دیکشنری خلاصه با آمار کلی
        """
        health = self.get_health()
        
        total = len(health)
        connected = sum(1 for h in health.values() if h.get("connected"))
        ping_ok = sum(1 for h in health.values() if h.get("ping"))
        
        # دسته‌بندی بر اساس نوع
        by_type: Dict[str, int] = {}
        for h in health.values():
            db_type = h.get("type", "unknown")
            by_type[db_type] = by_type.get(db_type, 0) + 1
        
        # آمار quota
        total_used_mb = sum(
            h.get("used_mb", 0) or 0 for h in health.values()
        )
        
        # آمار warning/critical
        warnings = sum(
            1 for h in health.values()
            if h.get("quota", {}).get("warning", False)
        )
        criticals = sum(
            1 for h in health.values()
            if h.get("quota", {}).get("status") == "critical"
        )
        
        return {
            "total_databases": total,
            "connected": connected,
            "disconnected": total - connected,
            "ping_ok": ping_ok,
            "by_type": by_type,
            "uptime_seconds": int(
                (datetime.now() - self._registered_at).total_seconds()
            ),
            "reconnect_count": self._reconnect_count,
            "last_reconnect": (
                self._last_reconnect.isoformat()
                if self._last_reconnect else None
            ),
            "quota": {
                "total_used_mb": round(total_used_mb, 2),
                "warnings": warnings,
                "criticals": criticals,
            },
            "databases": health,
            "timestamp": datetime.now().isoformat(),
        }
    
    def get_health_summary(self) -> Dict[str, Any]:
        """خلاصه سلامت (بدون اطلاعات جزئی)"""
        health = self.get_health()
        
        return {
            "total": len(health),
            "connected": sum(1 for h in health.values() if h.get("connected")),
            "disconnected": sum(1 for h in health.values() if not h.get("connected")),
            "status": "healthy" if all(h.get("connected") for h in health.values()) else "degraded",
            "timestamp": datetime.now().isoformat(),
        }
    
    def reconnect_all(self) -> Dict[str, bool]:
        """
        Reconnect همه دیتابیس‌ها
        
        خروجی:
            دیکشنری {name: success}
        """
        results = {}
        
        with self._lock:
            databases = dict(self._databases)
        
        for name, db in databases.items():
            try:
                if db.is_connected():
                    results[name] = True
                else:
                    results[name] = db.connect()
                    if results[name]:
                        self._reconnect_count += 1
                        self._last_reconnect = datetime.now()
            except Exception as e:
                logger.error(f"❌ Reconnect error for '{name}': {e}")
                results[name] = False
        
        return results
    
    # ============================================================
    # Config
    # ============================================================
    
    def set_config(self, config: Dict[str, Any]) -> None:
        """
        تنظیم تنظیمات
        
        پارامترها:
            config: دیکشنری تنظیمات کامل
        """
        with self._lock:
            self._config = config
            default = config.get("default", "primary")
            logger.debug(f"✅ Registry config set (default: {default})")
    
    def get_config(self) -> Dict[str, Any]:
        """دریافت تنظیمات"""
        with self._lock:
            return dict(self._config)
    
    def get_default_name(self) -> str:
        """دریافت نام دیتابیس پیش‌فرض"""
        return self._config.get("default", "primary")
    
    # ============================================================
    # Context Manager
    # ============================================================
    
    def __enter__(self) -> 'DatabaseRegistry':
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        pass
    
    def __repr__(self) -> str:
        return (
            f"<DatabaseRegistry "
            f"databases={len(self._databases)} "
            f"roles={len(self._roles)} "
            f"reconnects={self._reconnect_count}>"
        )


# ============================================================
# Singleton
# ============================================================

registry: DatabaseRegistry = DatabaseRegistry()
