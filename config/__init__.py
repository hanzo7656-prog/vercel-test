# config/__init__.py
# ============================================================
# پکیج تنظیمات - نسخه ۲.۰
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
    'reload_config',
    'get_all_config'
]
