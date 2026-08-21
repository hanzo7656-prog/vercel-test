# config/__init__.py
# ============================================================
# پکیج تنظیمات
# ============================================================

from config.config_manager import (
    ConfigManager,
    config,
    get_config,
    get_app_config,
    get_cache_config,
    get_api_config,
    get_model_config,
    get_system_config,
    get_thresholds
)

__all__ = [
    'ConfigManager',
    'config',
    'get_config',
    'get_app_config',
    'get_cache_config',
    'get_api_config',
    'get_model_config',
    'get_system_config',
    'get_thresholds'
]
