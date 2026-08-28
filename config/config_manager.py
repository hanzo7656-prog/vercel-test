# config/config_manager.py
# ============================================================
# مدیریت تنظیمات سیستم - نسخه ۲.۱ (با همه توابع)
# ============================================================

import os
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime

logger = logging.getLogger(__name__)


class ConfigManager:
    """مدیریت یکپارچه تنظیمات سیستم"""
    
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
            "app": {
                "name": "Trading Signal System",
                "version": "7.0",
                "environment": "production",
                "debug": False,
                "timezone": "Asia/Tehran"
            },
            "auto_trainer": {
                "enabled": False,
                "interval_hours": 6,
                "start_hours": [2, 8, 14, 20],
                "coins": ["bitcoin", "ethereum"],
                "period": "1m",
                "incremental": True,
                "min_credits": 100
            },
            "historical_points": {
                "fear_greed": 3,
                "btc_dominance": 3,
                "global_market": 3,
                "chart": 31
            },
            "dashboard": {
                "price_interval": 15,
                "credits_interval": 300,
                "status_interval": 180,
                "fear_greed_interval": 300,
                "btc_dominance_interval": 300,
                "news_interval": 600,
                "alerts_interval": 60,
                "full_update_interval": 60
            },
            "cache": {
                "price_ttl": 60,
                "fear_greed_ttl": 300,
                "btc_dominance_ttl": 300,
                "news_ttl": 600,
                "credits_ttl": 300,
                "status_ttl": 180,
                "chart_ttl": 3600
            },
            "model": {
                "version": "1.0",
                "mode": "DEMO",
                "last_training": None,
                "accuracy": None,
                "default_period": "1m",
                "auto_train_interval": 6,
                "min_data_points": 30,
                "features": [
                    "return_1", "return_3", "return_5", "return_10",
                    "sma_5", "sma_10", "sma_20",
                    "volatility", "fear_greed",
                    "trend_5", "trend_10", "trend_20", "r2"
                ]
            },
            "thresholds": {
                "ram_warning": 70,
                "ram_critical": 85,
                "credit_warning": 15,
                "credit_critical": 5,
                "cpu_warning": 70,
                "cpu_critical": 90
            },
            "system": {
                "health_check_interval": 30,
                "metrics_collection": True
            },
            "database": {
                "history_retention_days": 30,
                "cleanup_interval_hours": 24,
                "max_history_records": 10000
            },
            "logging": {
                "level": "INFO",
                "max_logs": 500,
                "log_interval_seconds": 60
            },
            "scheduler": {
                "check_interval": 1,
                "light_interval": 3,
                "medium_interval": 30,
                "heavy_interval": 300
            }
        }
    
    # ============================================================
    # دسترسی به تنظیمات
    # ============================================================
    
    def get(self, path: str, default: Any = None) -> Any:
        """دریافت مقدار با مسیر"""
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
        """تنظیم مقدار با مسیر و ذخیره خودکار"""
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
        return self.get(f"historical_points.{name}", 3)
    
    def set_historical_points(self, name: str, count: int):
        valid_names = ["fear_greed", "btc_dominance", "global_market", "chart"]
        if name not in valid_names:
            raise ValueError(f"name باید یکی از {valid_names} باشد")
        if count < 1 or count > 50:
            raise ValueError("count باید بین ۱ تا ۵۰ باشد")
        self.set(f"historical_points.{name}", count)
    
    def get_auto_trainer_config(self) -> Dict[str, Any]:
        return self.get_section("auto_trainer")
    
    def get_dashboard_config(self) -> Dict[str, Any]:
        return self.get_section("dashboard")
    
    def get_cache_config(self) -> Dict[str, Any]:
        return self.get_section("cache")
    
    def get_model_config(self) -> Dict[str, Any]:
        return self.get_section("model")
    
    def get_system_config(self) -> Dict[str, Any]:
        return self.get_section("system")
    
    def get_thresholds(self) -> Dict[str, Any]:
        return self.get_section("thresholds")
    
    def get_app_config(self) -> Dict[str, Any]:
        return self.get_section("app")
    
    def get_database_config(self) -> Dict[str, Any]:
        return self.get_section("database")
    
    def get_scheduler_config(self) -> Dict[str, Any]:
        return self.get_section("scheduler")
    
    # ============================================================
    # مدیریت تنظیمات از طریق API
    # ============================================================
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "app": self.get_app_config(),
            "auto_trainer": self.get_auto_trainer_config(),
            "historical_points": self.get_section("historical_points"),
            "dashboard": self.get_dashboard_config(),
            "cache": self.get_cache_config(),
            "model": self.get_model_config(),
            "thresholds": self.get_thresholds(),
            "system": self.get_system_config(),
            "database": self.get_database_config(),
            "scheduler": self.get_scheduler_config(),
            "last_loaded": self._last_loaded.isoformat() if self._last_loaded else None
        }
    
    def update_from_dict(self, updates: Dict[str, Any]):
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
    return config.get(path, default)


def set_config(path: str, value: Any):
    config.set(path, value)


def get_historical_points(name: str) -> int:
    return config.get_historical_points(name)


def set_historical_points(name: str, count: int):
    config.set_historical_points(name, count)


def get_auto_trainer_config() -> Dict[str, Any]:
    return config.get_auto_trainer_config()


def get_dashboard_config() -> Dict[str, Any]:
    return config.get_dashboard_config()


def get_cache_config() -> Dict[str, Any]:
    return config.get_cache_config()


def get_app_config() -> Dict[str, Any]:
    return config.get_app_config()


def get_model_config() -> Dict[str, Any]:
    return config.get_model_config()


def get_system_config() -> Dict[str, Any]:
    return config.get_system_config()


def get_thresholds() -> Dict[str, Any]:
    return config.get_thresholds()


def get_database_config() -> Dict[str, Any]:
    return config.get_database_config()


def get_scheduler_config() -> Dict[str, Any]:
    return config.get_scheduler_config()


def reload_config():
    config.reload()


def get_all_config() -> Dict[str, Any]:
    return config.get_all()
