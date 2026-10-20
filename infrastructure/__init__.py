# infrastructure/__init__.py
# ============================================================
# لایه زیرساخت (Infrastructure Layer)
# نسخه ۲.۰ - Gemini-only (model_repository حذف شد)
# ============================================================
# 
# شامل API، Database، Repositories، Auth، External و AI
# ============================================================

# ✅ استفاده از Lazy Import برای جلوگیری از Circular Import


# ============================================================
# API Clients
# ============================================================

def get_coinstats_client():
    """دریافت کلاینت CoinStats (Lazy Import)"""
    from infrastructure.api.coinstats_client import coinstats_client
    return coinstats_client


def get_cache_manager():
    """دریافت Cache Manager (Lazy Import)"""
    from infrastructure.api.cache_manager import cache_manager
    return cache_manager


def get_free_crypto_client():
    """دریافت کلاینت FreeCrypto (Lazy Import)"""
    from infrastructure.api.free_crypto_client import create_free_crypto_client
    import os
    api_key = os.getenv("FREE_CRYPTO_API_KEY", "569szrll2wmheybya6dx")
    return create_free_crypto_client(api_key)


def get_binance_ws_client():
    """دریافت کلاینت Binance WebSocket (Lazy Import)"""
    from infrastructure.api.binance_ws_client import binance_ws_client
    return binance_ws_client


# ============================================================
# Database
# ============================================================

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


# ============================================================
# Repositories
# ============================================================

def get_prediction_repository():
    """دریافت Repository پیش‌بینی (Lazy Import)"""
    from infrastructure.repositories.prediction_repository import PredictionRepository
    return PredictionRepository()


def get_settings_repository():
    """دریافت Repository تنظیمات (Lazy Import)"""
    from infrastructure.repositories.settings_repository import SettingsRepository
    return SettingsRepository()


# ⚠️ get_model_repository حذف شد (RuleEngine legacy)


# ============================================================
# AI (Gemini) 🆕
# ============================================================

def get_gemini_client():
    """دریافت Gemini Client (Lazy Import) 🆕"""
    from infrastructure.ai.gemini_client import gemini_client
    return gemini_client


def get_gemini_service():
    """دریافت Gemini Service (Lazy Import) 🆕"""
    from infrastructure.ai.gemini_service import gemini_service
    return gemini_service


# ============================================================
# Auth
# ============================================================

def get_auth_manager():
    """دریافت Auth Manager (Lazy Import)"""
    from infrastructure.auth.auth_manager import auth_manager
    return auth_manager


# ============================================================
# External
# ============================================================

def get_alerter():
    """دریافت Alerter (Lazy Import)"""
    from infrastructure.external.alerter import alerter
    return alerter


# ============================================================
# Export
# ============================================================

__all__ = [
    # API Clients
    'get_coinstats_client',
    'get_cache_manager',
    'get_free_crypto_client',
    'get_binance_ws_client',
    
    # Database
    'get_database_primary',
    'get_database_cache',
    'get_database_backup',
    
    # Repositories
    'get_prediction_repository',
    'get_settings_repository',
    
    # AI (Gemini) 🆕
    'get_gemini_client',
    'get_gemini_service',
    
    # Auth
    'get_auth_manager',
    
    # External
    'get_alerter',
]
