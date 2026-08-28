# config/__init__.py
# ============================================================
# پکیج تنظیمات - نسخه ۲.۱ (با همه توابع مورد نیاز)
# ============================================================

from config.config_manager import (
    ConfigManager,
    config,
    get_config,
    set_config,
    get_historical_points,
    set_historical_points,
    get_auto_trainer_config,
    get_dashboard_config,
    get_cache_config,
    get_scheduler_config,
    get_app_config,
    get_model_config,
    get_system_config,
    get_thresholds,
    get_database_config,
    reload_config,
    get_all_config
)

__all__ = [
    'ConfigManager',
    'config',
    'get_config',
    'set_config',
    'get_historical_points',
    'set_historical_points',
    'get_auto_trainer_config',
    'get_dashboard_config',
    'get_cache_config',
    'get_scheduler_config',
    'get_app_config',
    'get_model_config',
    'get_system_config',
    'get_thresholds',
    'get_database_config',
    'reload_config',
    'get_all_config'
]
