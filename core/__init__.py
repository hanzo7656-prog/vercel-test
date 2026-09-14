# core/__init__.py
# ============================================================
# پکیج Core - ماژول‌های اصلی سیستم
# نسخه ۲.۰ - Lazy Import
# ============================================================

from typing import TYPE_CHECKING


# ============================================================
# Lazy Import (جلوگیری از Circular)
# ============================================================

def __getattr__(name: str):
    """
    Lazy loading برای همه ماژول‌ها
    
    این تابع وقتی صدا زده می‌شه که یه attribute
    از این ماژول درخواست بشه که در global namespace نیست.
    """
    
    # ===== Metrics =====
    if name == "metrics_scheduler":
        from core.metrics import metrics_scheduler
        return metrics_scheduler
    
    if name == "MetricsScheduler":
        from core.metrics import MetricsScheduler
        return MetricsScheduler
    
    # ===== Threading =====
    if name == "threading_manager":
        from core.threading_manager import threading_manager
        return threading_manager
    
    # ===== Feature Engineering =====
    if name == "feature_engineer":
        from core.feature_engineering import feature_engineer
        return feature_engineer
    
    if name == "FeatureEngineer":
        from core.feature_engineering import FeatureEngineer
        return FeatureEngineer
    
    # ===== Parallel =====
    if name == "parallel_processor":
        from core.parallel_processor import parallel_processor
        return parallel_processor
    
    if name == "ParallelProcessor":
        from core.parallel_processor import ParallelProcessor
        return ParallelProcessor
    
    # ===== User Tracker =====
    if name == "UserTracker":
        from core.user_tracker import UserTracker
        return UserTracker
    
    # ===== Price Manager =====
    if name == "PriceManager":
        from core.price_manager import PriceManager
        return PriceManager
    
    # ===== Indicators =====
    if name == "calculate_rsi":
        from core.indicators import calculate_rsi
        return calculate_rsi
    
    if name == "calculate_sma":
        from core.indicators import calculate_sma
        return calculate_sma
    
    if name == "calculate_ema":
        from core.indicators import calculate_ema
        return calculate_ema
    
    if name == "calculate_macd":
        from core.indicators import calculate_macd
        return calculate_macd
    
    if name == "get_all_indicators":
        from core.indicators import get_all_indicators
        return get_all_indicators
    
    # ===== System =====
    if name == "system":
        from core.system import system
        return system
    
    if name == "TradingSignalSystem":
        from core.system import TradingSignalSystem
        return TradingSignalSystem
    
    # اگه پیدا نشد
    raise AttributeError(
        f"module {__name__!r} has no attribute {name!r}"
    )


# ============================================================
# Helper Functions (Lazy)
# ============================================================

def get_system():
    """
    دریافت نمونه TradingSignalSystem (Lazy)
    
    خروجی:
        TradingSignalSystem instance
    """
    from core.system import system
    return system


def get_metrics_scheduler():
    """
    دریافت MetricsScheduler (Lazy)
    
    خروجی:
        MetricsScheduler instance
    """
    from core.metrics import metrics_scheduler
    return metrics_scheduler


def get_price_manager():
    """
    دریافت PriceManager از Container
    
    خروجی:
        PriceManager instance
    """
    try:
        from container import container
        return container.get('price_manager')
    except (ImportError, KeyError) as e:
        # Fallback: ساخت مستقیم
        try:
            from core.price_manager import PriceManager
            from infrastructure.database import get_cache
            
            from infrastructure.api.free_crypto_client import (
                create_free_crypto_client
            )
            from core.user_tracker import UserTracker
            
            free_client = create_free_crypto_client()
            user_tracker = UserTracker(timeout=30)
            
            return PriceManager(
                free_client=free_client,
                user_tracker=user_tracker,
                cache=get_cache(),
                update_interval=10,
                fallback_interval=60,
            )
        except Exception as inner_e:
            raise RuntimeError(
                f"Could not create PriceManager: {e} / {inner_e}"
            )


def get_user_tracker():
    """
    دریافت UserTracker از Container
    
    خروجی:
        UserTracker instance
    """
    try:
        from container import container
        return container.get('user_tracker')
    except (ImportError, KeyError):
        # Fallback
        from core.user_tracker import UserTracker
        return UserTracker(timeout=30)


def get_threading_manager():
    """
    دریافت ThreadingManager (Lazy)
    
    خروجی:
        ThreadingManager instance
    """
    from core.threading_manager import threading_manager
    return threading_manager


def get_feature_engineer():
    """
    دریافت FeatureEngineer (Lazy)
    
    خروجی:
        FeatureEngineer instance
    """
    from core.feature_engineering import feature_engineer
    return feature_engineer


def get_parallel_processor():
    """
    دریافت ParallelProcessor (Lazy)
    
    خروجی:
        ParallelProcessor instance
    """
    from core.parallel_processor import parallel_processor
    return parallel_processor


# ============================================================
# Export
# ============================================================

__all__ = [
    # ===== Lazy Classes/Instances =====
    "metrics_scheduler",
    "MetricsScheduler",
    "threading_manager",
    "feature_engineer",
    "FeatureEngineer",
    "parallel_processor",
    "ParallelProcessor",
    "UserTracker",
    "PriceManager",
    
    # ===== Indicators =====
    "calculate_rsi",
    "calculate_sma",
    "calculate_ema",
    "calculate_macd",
    "get_all_indicators",
    
    # ===== System =====
    "system",
    "TradingSignalSystem",
    
    # ===== Helper Functions =====
    "get_system",
    "get_metrics_scheduler",
    "get_price_manager",
    "get_user_tracker",
    "get_threading_manager",
    "get_feature_engineer",
    "get_parallel_processor",
]
