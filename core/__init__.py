# core/__init__.py
# ============================================================
# پکیج Core
# ============================================================

from core.metrics import metrics_scheduler
from core.threading_manager import threading_manager
from core.feature_engineering import FeatureEngineer

def get_system():
    from core.system import system
    return system

__all__ = [
    'metrics_scheduler',
    'threading_manager',
    'FeatureEngineer',
    'get_system'
]
