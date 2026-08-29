# config/settings.py
# ============================================================
# تنظیمات یکپارچه سیستم - نسخه ۲.۰
# ============================================================

import os
import json
import logging
from pathlib import Path
from typing import Dict, Any
from config.version import VERSION

logger = logging.getLogger(__name__)


class Settings:
    """مدیریت یکپارچه تنظیمات"""
    
    _instance = None
    _config: Dict[str, Any] = {}
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if hasattr(self, '_initialized'):
            return
        self._initialized = True
        self._load_settings()
    
    def _load_settings(self):
        """بارگذاری از فایل settings.json"""
        settings_path = Path("config/settings.json")
        
        if settings_path.exists():
            try:
                with open(settings_path, 'r', encoding='utf-8') as f:
                    self._config = json.load(f)
                logger.info("✅ Settings loaded from config/settings.json")
            except Exception as e:
                logger.error(f"❌ Settings load error: {e}")
                self._config = self._default_settings()
        else:
            logger.warning("⚠️ settings.json not found, using defaults")
            self._config = self._default_settings()
    
    def _default_settings(self) -> Dict:
        """تنظیمات پیش‌فرض"""
        return {
            "app": {
                "name": "Trading Signal System",
                "version": VERSION,
                "environment": "production",
                "debug": False,
                "timezone": "Asia/Tehran"
            },
            "cache": {
                "default_ttl": 3600,
                "prediction_ttl": 300,
                "max_size": 1000
            },
            "api": {
                "timeout": 15,
                "retry_attempts": 3,
                "retry_delay": 1
            },
            "model": {
                "version": "2.0",
                "mode": "BETA",
                "default_period": "1m",
                "auto_train_interval": 6,
                "min_data_points": 30,
                "coins": ["bitcoin", "ethereum"],
                "features": [
                    "return_1", "return_3", "return_5", "return_10",
                    "sma_5", "sma_10", "sma_20",
                    "volatility", "fear_greed",
                    "trend_5", "trend_10", "trend_20", "r2"
                ]
            },
            "scheduler": {
                "light_interval": 3,
                "medium_interval": 30,
                "heavy_interval": 300
            },
            "thresholds": {
                "ram_warning": 70,
                "ram_critical": 85,
                "cpu_warning": 70,
                "cpu_critical": 90
            }
        }
    
    def get(self, path: str, default=None):
        """دریافت مقدار با مسیر نقطه‌دار"""
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
    
    def get_all(self) -> Dict:
        return self._config.copy()


settings = Settings()


# توابع کمکی
def get_settings(path: str, default=None):
    return settings.get(path, default)


def get_model_config():
    return settings.get('model', {})


def get_cache_config():
    return settings.get('cache', {})


def get_api_config():
    return settings.get('api', {})
