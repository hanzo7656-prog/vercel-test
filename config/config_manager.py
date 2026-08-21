# config/config_manager.py
# ============================================================
# مدیریت تنظیمات - یکپارچه
# ============================================================

import os
import json
import logging
from typing import Any, Dict, Optional
from pathlib import Path
from functools import lru_cache

logger = logging.getLogger(__name__)


class ConfigManager:
    """مدیریت یکپارچه تنظیمات سیستم"""
    
    _instance = None
    _settings: Dict[str, Any] = {}
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not hasattr(self, '_initialized'):
            self._initialized = True
            self._load_settings()
            self._override_from_env()
    
    def _load_settings(self):
        """بارگذاری تنظیمات از فایل"""
        settings_path = Path("config/settings.json")
        
        if not settings_path.exists():
            logger.warning("⚠️ config/settings.json یافت نشد، استفاده از تنظیمات پیش‌فرض")
            self._settings = self._get_default_settings()
            return
        
        try:
            with open(settings_path, 'r', encoding='utf-8') as f:
                self._settings = json.load(f)
            logger.info("✅ تنظیمات عمومی بارگذاری شد")
        except Exception as e:
            logger.error(f"❌ خطا در بارگذاری تنظیمات: {e}")
            self._settings = self._get_default_settings()
    
    def _get_default_settings(self) -> Dict:
        """تنظیمات پیش‌فرض"""
        return {
            "app": {
                "name": "Trading Signal System",
                "version": "5.0",
                "environment": "production",
                "debug": False,
                "timezone": "Asia/Tehran"
            },
            "cache": {
                "default_ttl": 3600,
                "max_size": 1000,
                "cleanup_interval": 300
            },
            "api": {
                "timeout": 15,
                "retry_attempts": 3,
                "retry_delay": 1
            },
            "model": {
                "default_period": "1m",
                "auto_train_interval": 6,
                "min_data_points": 30
            },
            "system": {
                "max_tasks": 50,
                "task_ttl": 300,
                "num_workers": 1
            },
            "thresholds": {
                "ram_warning": 70,
                "ram_critical": 85,
                "credit_warning": 15,
                "credit_critical": 5
            },
            "logging": {
                "level": "INFO",
                "max_logs": 500
            }
        }
    
    def _override_from_env(self):
        """جایگزینی با متغیرهای محیطی"""
        env_mappings = {
            "APP_ENVIRONMENT": "app.environment",
            "APP_DEBUG": "app.debug",
            "CACHE_TTL": "cache.default_ttl",
            "API_TIMEOUT": "api.timeout",
            "API_RETRY_ATTEMPTS": "api.retry_attempts",
            "MODEL_AUTO_TRAIN_INTERVAL": "model.auto_train_interval",
            "SYSTEM_MAX_TASKS": "system.max_tasks",
            "LOG_LEVEL": "logging.level"
        }
        
        for env_var, config_path in env_mappings.items():
            value = os.getenv(env_var)
            if value is not None:
                # تبدیل نوع
                if value.lower() == 'true':
                    value = True
                elif value.lower() == 'false':
                    value = False
                elif value.isdigit():
                    value = int(value)
                elif value.replace('.', '').isdigit():
                    value = float(value)
                
                self._set_nested(config_path, value)
                logger.debug(f"✅ {env_var} → {config_path} = {value}")
    
    def _set_nested(self, path: str, value: Any):
        """تنظیم مقدار در مسیر تو در تو (مثل 'app.environment')"""
        keys = path.split('.')
        target = self._settings
        
        for key in keys[:-1]:
            if key not in target:
                target[key] = {}
            target = target[key]
        
        target[keys[-1]] = value
    
    @lru_cache(maxsize=128)
    def get(self, path: str, default: Any = None) -> Any:
        """دریافت مقدار با مسیر (مثل 'app.environment')"""
        keys = path.split('.')
        target = self._settings
        
        try:
            for key in keys:
                target = target[key]
            return target
        except (KeyError, TypeError):
            return default
    
    def get_all(self) -> Dict[str, Any]:
        """دریافت همه تنظیمات"""
        return self._settings.copy()
    
    def reload(self):
        """بارگذاری مجدد تنظیمات"""
        self._settings = {}
        self._load_settings()
        self._override_from_env()
        # پاک کردن کش
        self.get.cache_clear()
        logger.info("🔄 تنظیمات بارگذاری مجدد شد")
    
    def get_section(self, section: str) -> Dict[str, Any]:
        """دریافت یک بخش کامل"""
        return self.get(section, {})
    
    def update(self, path: str, value: Any):
        """به‌روزرسانی یک مقدار (و ذخیره در فایل)"""
        self._set_nested(path, value)
        self._save_to_file()
        self.get.cache_clear()
        logger.info(f"✅ تنظیمات {path} = {value} ذخیره شد")
    
    def _save_to_file(self):
        """ذخیره تنظیمات در فایل"""
        try:
            settings_path = Path("config/settings.json")
            settings_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(settings_path, 'w', encoding='utf-8') as f:
                json.dump(self._settings, f, indent=4, ensure_ascii=False)
        except Exception as e:
            logger.error(f"❌ خطا در ذخیره تنظیمات: {e}")


# ============================================================
# نمونه Singleton و راهنماها
# ============================================================

config = ConfigManager()


def get_config(path: str, default: Any = None) -> Any:
    """راهنمای سریع برای دریافت تنظیمات"""
    return config.get(path, default)


def get_app_config() -> Dict:
    """دریافت تنظیمات اپلیکیشن"""
    return config.get_section("app")


def get_cache_config() -> Dict:
    """دریافت تنظیمات کش"""
    return config.get_section("cache")


def get_api_config() -> Dict:
    """دریافت تنظیمات API"""
    return config.get_section("api")


def get_model_config() -> Dict:
    """دریافت تنظیمات مدل"""
    return config.get_section("model")


def get_system_config() -> Dict:
    """دریافت تنظیمات سیستم"""
    return config.get_section("system")


def get_thresholds() -> Dict:
    """دریافت آستانه‌ها"""
    return config.get_section("thresholds")
