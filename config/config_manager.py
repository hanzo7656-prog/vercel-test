# config/config_manager.py
# ============================================================
# مدیریت تنظیمات سیستم - نسخه ۲.۰ (یکپارچه با دیتابیس)
# ============================================================

import os
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime

logger = logging.getLogger(__name__)


class ConfigManager:
    """
    مدیریت یکپارچه تنظیمات سیستم
    
    ویژگی‌ها:
    - بارگذاری از فایل JSON
    - ذخیره خودکار تغییرات
    - دسترسی به تنظیمات با مسیر (مثل 'auto_trainer.interval_hours')
    - پشتیبانی از پیش‌فرض
    - قابلیت reload
    """
    
    _instance = None
    _config: Dict[str, Any] = {}
    _config_path: Path = Path("config/metrics_config.json")
    _last_loaded: Optional[datetime] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not hasattr(self, '_initialized'):
            self._initialized = True
            self._load_config()
            logger.info("✅ ConfigManager initialized")
    
    # ============================================================
    # بارگذاری و ذخیره
    # ============================================================
    
    def _load_config(self):
        """بارگذاری تنظیمات از فایل"""
        try:
            # ایجاد پوشه config اگر وجود ندارد
            self._config_path.parent.mkdir(parents=True, exist_ok=True)
            
            if self._config_path.exists():
                with open(self._config_path, 'r', encoding='utf-8') as f:
                    self._config = json.load(f)
                self._last_loaded = datetime.now()
                logger.info(f"✅ تنظیمات از {self._config_path} بارگذاری شد")
            else:
                logger.warning(f"⚠️ فایل {self._config_path} یافت نشد، استفاده از پیش‌فرض")
                self._config = self._get_default_config()
                self._save_config()
                
        except Exception as e:
            logger.error(f"❌ خطا در بارگذاری تنظیمات: {e}")
            self._config = self._get_default_config()
    
    def _save_config(self):
        """ذخیره تنظیمات در فایل"""
        try:
            self._config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._config_path, 'w', encoding='utf-8') as f:
                json.dump(self._config, f, indent=4, ensure_ascii=False)
            logger.info(f"✅ تنظیمات در {self._config_path} ذخیره شد")
        except Exception as e:
            logger.error(f"❌ خطا در ذخیره تنظیمات: {e}")
            raise
    
    def _get_default_config(self) -> Dict[str, Any]:
        """تنظیمات پیش‌فرض کامل"""
        return {
            # ============================================================
            # AutoTrainer
            # ============================================================
            "auto_trainer": {
                "enabled": True,
                "interval_hours": 6,
                "start_hours": [2, 8, 14, 20],
                "coins": ["bitcoin", "ethereum", "solana"],
                "period": "1m",
                "incremental": True,
                "min_credits": 100
            },
            
            # ============================================================
            # تعداد نقاط تاریخی
            # ============================================================
            "historical_points": {
                "fear_greed": 5,
                "btc_dominance": 5,
                "global_market": 3,
                "chart": 31
            },
            
            # ============================================================
            # Dashboard (زمان‌بندی درخواست‌ها)
            # ============================================================
            "dashboard": {
                "price_interval": 15,          # ثانیه
                "credits_interval": 300,        # ثانیه (۵ دقیقه)
                "status_interval": 180,         # ثانیه (۳ دقیقه)
                "fear_greed_interval": 300,     # ثانیه (۵ دقیقه)
                "btc_dominance_interval": 300,  # ثانیه (۵ دقیقه)
                "news_interval": 600,           # ثانیه (۱۰ دقیقه)
                "alerts_interval": 60           # ثانیه (۱ دقیقه)
            },
            
            # ============================================================
            # کش (TTL)
            # ============================================================
            "cache": {
                "price_ttl": 15,                # ثانیه
                "fear_greed_ttl": 300,          # ثانیه (۵ دقیقه)
                "btc_dominance_ttl": 300,       # ثانیه (۵ دقیقه)
                "news_ttl": 600,                # ثانیه (۱۰ دقیقه)
                "credits_ttl": 300,             # ثانیه (۵ دقیقه)
                "status_ttl": 180,              # ثانیه (۳ دقیقه)
                "chart_ttl": 3600               # ثانیه (۱ ساعت)
            },
            
            # ============================================================
            # دیتابیس
            # ============================================================
            "database": {
                "history_retention_days": 30,   # نگهداری تاریخچه به روز
                "cleanup_interval_hours": 24,   # پاکسازی هر ۲۴ ساعت
                "max_history_records": 10000    # حداکثر رکوردهای تاریخچه
            },
            
            # ============================================================
            # لاگینگ
            # ============================================================
            "logging": {
                "level": "INFO",
                "max_logs": 500,
                "log_interval_seconds": 60
            },
            
            # ============================================================
            # Scheduler
            # ============================================================
            "scheduler": {
                "check_interval": 1,            # ثانیه
                "light_interval": 3,            # ثانیه (CPU, RAM)
                "medium_interval": 30,          # ثانیه (API, Model)
                "heavy_interval": 300           # ثانیه (Database, Disk)
            }
        }
    
    # ============================================================
    # دسترسی به تنظیمات
    # ============================================================
    
    def get(self, path: str, default: Any = None) -> Any:
        """
        دریافت مقدار با مسیر (مثل 'auto_trainer.interval_hours')
        
        مثال:
            config.get('auto_trainer.interval_hours')  # 6
            config.get('dashboard.price_interval')     # 15
        """
        keys = path.split('.')
        value = self._config
        
        for key in keys:
            if isinstance(value, dict):
                value = value.get(key)
                if value is None:
                    return default
            else:
                return default
        
        return value
    
    def set(self, path: str, value: Any):
        """
        تنظیم مقدار با مسیر و ذخیره خودکار
        
        مثال:
            config.set('auto_trainer.interval_hours', 12)
            config.set('historical_points.fear_greed', 10)
        """
        keys = path.split('.')
        target = self._config
        
        for key in keys[:-1]:
            if key not in target:
                target[key] = {}
            target = target[key]
        
        target[keys[-1]] = value
        self._save_config()
    
    def get_section(self, section: str) -> Dict[str, Any]:
        """دریافت یک بخش کامل"""
        return self._config.get(section, {})
    
    def get_all(self) -> Dict[str, Any]:
        """دریافت همه تنظیمات"""
        return self._config.copy()
    
    def reload(self):
        """بارگذاری مجدد تنظیمات از فایل"""
        self._load_config()
        logger.info("🔄 تنظیمات بارگذاری مجدد شد")
    
    # ============================================================
    # توابع کمکی برای بخش‌های خاص
    # ============================================================
    
    def get_historical_points(self, name: str) -> int:
        """دریافت تعداد نقاط تاریخی برای یک اندپوینت"""
        return self.get(f"historical_points.{name}", 5)
    
    def set_historical_points(self, name: str, count: int):
        """تنظیم تعداد نقاط تاریخی برای یک اندپوینت"""
        valid_names = ["fear_greed", "btc_dominance", "global_market", "chart"]
        if name not in valid_names:
            raise ValueError(f"name باید یکی از {valid_names} باشد")
        if count < 1 or count > 50:
            raise ValueError("count باید بین ۱ تا ۵۰ باشد")
        self.set(f"historical_points.{name}", count)
    
    def get_auto_trainer_config(self) -> Dict[str, Any]:
        """دریافت تنظیمات AutoTrainer"""
        return self.get_section("auto_trainer")
    
    def get_dashboard_config(self) -> Dict[str, Any]:
        """دریافت تنظیمات Dashboard"""
        return self.get_section("dashboard")
    
    def get_cache_config(self) -> Dict[str, Any]:
        """دریافت تنظیمات کش"""
        return self.get_section("cache")
    
    def get_database_config(self) -> Dict[str, Any]:
        """دریافت تنظیمات دیتابیس"""
        return self.get_section("database")
    
    def get_scheduler_config(self) -> Dict[str, Any]:
        """دریافت تنظیمات Scheduler"""
        return self.get_section("scheduler")
    
    # ============================================================
    # مدیریت تنظیمات از طریق API
    # ============================================================
    
    def to_dict(self) -> Dict[str, Any]:
        """تبدیل به دیکشنری برای پاسخ API"""
        return {
            "auto_trainer": self.get_auto_trainer_config(),
            "historical_points": self.get_section("historical_points"),
            "dashboard": self.get_dashboard_config(),
            "cache": self.get_cache_config(),
            "database": self.get_database_config(),
            "scheduler": self.get_scheduler_config(),
            "last_loaded": self._last_loaded.isoformat() if self._last_loaded else None
        }
    
    def update_from_dict(self, updates: Dict[str, Any]):
        """به‌روزرسانی از دیکشنری"""
        for key, value in updates.items():
            if isinstance(value, dict):
                for sub_key, sub_value in value.items():
                    self.set(f"{key}.{sub_key}", sub_value)
            else:
                self.set(key, value)


# ============================================================
# نمونه Singleton
# ============================================================

config = ConfigManager()


# ============================================================
# توابع کمکی برای دسترسی آسان
# ============================================================

def get_config(path: str, default: Any = None) -> Any:
    """دریافت تنظیمات با مسیر"""
    return config.get(path, default)


def set_config(path: str, value: Any):
    """تنظیم مقدار و ذخیره"""
    config.set(path, value)


def get_historical_points(name: str) -> int:
    """دریافت تعداد نقاط تاریخی"""
    return config.get_historical_points(name)


def set_historical_points(name: str, count: int):
    """تنظیم تعداد نقاط تاریخی"""
    config.set_historical_points(name, count)


def get_auto_trainer_config() -> Dict[str, Any]:
    """دریافت تنظیمات AutoTrainer"""
    return config.get_auto_trainer_config()


def get_dashboard_config() -> Dict[str, Any]:
    """دریافت تنظیمات Dashboard"""
    return config.get_dashboard_config()


def get_cache_config() -> Dict[str, Any]:
    """دریافت تنظیمات کش"""
    return config.get_cache_config()


def get_scheduler_config() -> Dict[str, Any]:
    """دریافت تنظیمات Scheduler"""
    return config.get_scheduler_config()


def reload_config():
    """بارگذاری مجدد تنظیمات"""
    config.reload()


def get_all_config() -> Dict[str, Any]:
    """دریافت همه تنظیمات"""
    return config.get_all()


# ============================================================
# راه‌اندازی اولیه (ایجاد فایل تنظیمات اگر وجود نداشته باشد)
# ============================================================

if __name__ == "__main__":
    # تست
    print("📋 تنظیمات فعلی:")
    print(json.dumps(config.get_all(), indent=2, ensure_ascii=False))
    
    print("\n📊 تعداد نقاط ترس و طمع:", get_historical_points("fear_greed"))
    print("📊 تعداد نقاط سلطه بیت‌کوین:", get_historical_points("btc_dominance"))
    print("📊 تعداد نقاط بازار جهانی:", get_historical_points("global_market"))
    
    print("\n⏱️ فاصله آموزش AutoTrainer:", get_config("auto_trainer.interval_hours"), "ساعت")
    print("⏱️ فاصله قیمت در Dashboard:", get_config("dashboard.price_interval"), "ثانیه")
