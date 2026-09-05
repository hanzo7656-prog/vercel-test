# core/__init__.py
# ============================================================
# پکیج Core - ماژول‌های اصلی سیستم
# ============================================================

from core.metrics import metrics_scheduler
from core.threading_manager import threading_manager
from core.feature_engineering import FeatureEngineer, feature_engineer
from core.parallel_processor import parallel_processor, ParallelProcessor
from core.user_tracker import UserTracker
from core.price_manager import PriceManager


def get_system():
    """دریافت نمونه TradingSignalSystem (Lazy Loading)"""
    from core.system import system
    return system


def get_price_manager():
    """دریافت نمونه PriceManager (از Container استفاده کنید)"""
    # این تابع فقط برای راحتی است، اما توصیه می‌شود از Container استفاده کنید
    from container import Container
    return Container().price_manager()


def get_user_tracker():
    """دریافت نمونه UserTracker (از Container استفاده کنید)"""
    from container import Container
    return Container().user_tracker()


__all__ = [
    # ماژول‌های قبلی
    'metrics_scheduler',
    'threading_manager',
    'FeatureEngineer',
    'feature_engineer',
    'get_system',
    
    # ماژول‌های جدید
    'parallel_processor',
    'ParallelProcessor',
    'UserTracker',
    'PriceManager',
    'get_price_manager',
    'get_user_tracker',
]
