# core/__init__.py
# ============================================================
# پکیج Core
# ============================================================

# ❌ حذف import مستقیم system برای جلوگیری از Circular Import
# from core.system import TradingSignalSystem, system
# from core.metrics import MetricsScheduler, metrics_scheduler

# ✅ فقط export names
from core.metrics import metrics_scheduler
from core.threading_manager import threading_manager
from core.feature_engineering import FeatureEngineer

# system باید به صورت lazy loaded شود
def get_system():
    """دریافت نمونه system با Lazy Loading"""
    from core.system import system
    return system

__all__ = [
    # 'TradingSignalSystem',  # ❌ حذف
    # 'system',                # ❌ حذف
    'metrics_scheduler',
    'threading_manager',
    'FeatureEngineer',
    'get_system'
]
