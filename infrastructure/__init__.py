# infrastructure/__init__.py
# ============================================================
# لایه زیرساخت (Infrastructure Layer)
# شامل API، Database، Repositories، Auth و External
# ============================================================

# ✅ استفاده از Lazy Import برای جلوگیری از Circular Import
# توابع کمکی برای دریافت سرویس‌ها

def get_coinstats_client():
    """دریافت کلاینت CoinStats (Lazy Import)"""
    from infrastructure.api.coinstats_client import coinstats_client
    return coinstats_client


def get_cache_manager():
    """دریافت Cache Manager (Lazy Import)"""
    from infrastructure.api.cache_manager import cache_manager
    return cache_manager


def get_free_crypto_client():
    """دریافت کلاینت WebSocket (Lazy Import)"""
    from infrastructure.api.free_crypto_client import create_free_crypto_client
    import os
    api_key = os.getenv("FREE_CRYPTO_API_KEY", "569szrll2wmheybya6dx")
    return create_free_crypto_client(api_key)


def get_database_primary():
    """دریافت دیتابیس اصلی (Lazy Import)"""
    from infrastructure.database import get_primary
    return get_primary()


def get_database_cache():
    """دریافت دیتابیس کش (Lazy Import)"""
    from infrastructure.database import get_cache
    return get_cache()


def get_database_backup():
    """دریافت دیتابیس پشتیبان (Lazy Import)"""
    from infrastructure.database import get_backup
    return get_backup()


def get_model_repository():
    """دریافت Repository مدل (Lazy Import)"""
    from infrastructure.repositories.model_repository import ModelRepository
    return ModelRepository()


def get_prediction_repository():
    """دریافت Repository پیش‌بینی (Lazy Import)"""
    from infrastructure.repositories.prediction_repository import PredictionRepository
    return PredictionRepository()


def get_auth_manager():
    """دریافت Auth Manager (Lazy Import)"""
    from infrastructure.auth.auth_manager import auth_manager
    return auth_manager


def get_alerter():
    """دریافت Alerter (Lazy Import)"""
    from infrastructure.external.alerter import alerter
    return alerter


__all__ = [
    # Lazy Loaders
    'get_coinstats_client',
    'get_cache_manager',
    'get_free_crypto_client',
    'get_database_primary',
    'get_database_cache',
    'get_database_backup',
    'get_model_repository',
    'get_prediction_repository',
    'get_auth_manager',
    'get_alerter',
]
