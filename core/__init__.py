# core/__init__.py
# ============================================================
# پکیج Core - ماژول‌های اصلی سیستم
# نسخه ۳.۰ - Gemini-only (system, feature_engineering حذف شدند)
# ============================================================

from typing import TYPE_CHECKING


# ============================================================
# Lazy Import (جلوگیری از Circular)
# ============================================================

def __getattr__(name: str):
    """
    Lazy loading برای همه ماژول‌ها
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
    
    # ⚠️ feature_engineer, FeatureEngineer حذف شدند (RuleEngine legacy)
    
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
    
    # ⚠️ system, TradingSignalSystem حذف شدند (وابسته به RuleEngine/XGBoost)
    
    raise AttributeError(
        f"module {__name__!r} has no attribute {name!r}"
    )


# ============================================================
# Helper Functions (Lazy)
# ============================================================

def get_metrics_scheduler():
    """دریافت MetricsScheduler (Lazy)"""
    from core.metrics import metrics_scheduler
    return metrics_scheduler


def get_price_manager():
    """دریافت PriceManager از Container"""
    try:
        from container import container
        return container.get('price_manager')
    except (ImportError, KeyError) as e:
        try:
            from core.price_manager import PriceManager
            from infrastructure.database import get_cache
            from infrastructure.api.free_crypto_client import create_free_crypto_client
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
    """دریافت UserTracker از Container"""
    try:
        from container import container
        return container.get('user_tracker')
    except (ImportError, KeyError):
        from core.user_tracker import UserTracker
        return UserTracker(timeout=30)


def get_threading_manager():
    """دریافت ThreadingManager (Lazy)"""
    from core.threading_manager import threading_manager
    return threading_manager


def get_parallel_processor():
    """دریافت ParallelProcessor (Lazy)"""
    from core.parallel_processor import parallel_processor
    return parallel_processor


# ⚠️ get_system, get_feature_engineer حذف شدند


# ============================================================
# Export
# ============================================================

__all__ = [
    # ===== Lazy Classes/Instances =====
    "metrics_scheduler",
    "MetricsScheduler",
    "threading_manager",
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
    
    # ===== Helper Functions =====
    "get_metrics_scheduler",
    "get_price_manager",
    "get_user_tracker",
    "get_threading_manager",
    "get_parallel_processor",
]
