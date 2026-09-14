# providers.py
# ============================================================
# Providers - ارائه‌دهنده‌های سرویس
# نسخه ۳.۰ - Repository + Database + Application
# ============================================================

import logging
from typing import Any
from flask import current_app, has_app_context

from container import container, start_services, stop_services

logger = logging.getLogger(__name__)


# ============================================================
# Core Get Service
# ============================================================

def get_service(name: str) -> Any:
    """
    دریافت یک سرویس از Container
    
    پارامترها:
        name: نام سرویس
    
    خروجی:
        نمونه سرویس
    """
    # اگه در Flask context هستیم
    if has_app_context():
        app_container = getattr(current_app, 'container', None)
        if app_container:
            return app_container.get(name)
    
    # Global container
    return container.get(name)


# ============================================================
# Infrastructure Providers
# ============================================================

def get_api_client():
    """کلاینت API"""
    return get_service('api_client')


def get_cache_manager():
    """مدیریت کش"""
    return get_service('cache_manager')


def get_free_crypto_client():
    """FreeCryptoClient"""
    return get_service('free_crypto_client')


# ============================================================
# Database Providers 🆕
# ============================================================

def get_db_factory():
    """Database Factory"""
    return get_service('db_factory')


def get_quota_manager():
    """Quota Manager"""
    return get_service('quota_manager')


def get_database_registry():
    """Database Registry"""
    return get_service('database_registry')


def get_database_router():
    """Database Router"""
    return get_service('database_router')


# ============================================================
# Repository Providers 🆕
# ============================================================

def get_repo_container():
    """Repository Container"""
    return get_service('repo_container')


def get_model_repository():
    """Model Repository"""
    return get_service('model_repository')


def get_prediction_repository():
    """Prediction Repository"""
    return get_service('prediction_repository')


# ============================================================
# Model Providers
# ============================================================

def get_model_manager():
    """Model Manager"""
    return get_service('model_manager')


def get_trainer():
    """Auto Trainer"""
    return get_service('trainer')


# ============================================================
# Core Providers
# ============================================================

def get_feature_engineer():
    """Feature Engineer"""
    return get_service('feature_engineer')


def get_user_tracker():
    """User Tracker"""
    return get_service('user_tracker')


def get_price_manager():
    """Price Manager"""
    return get_service('price_manager')


def get_indicators():
    """Indicators"""
    return get_service('indicators')


# ============================================================
# Application Providers 🆕
# ============================================================

def get_predict_use_case():
    """Predict Use Case"""
    return get_service('predict_use_case')


def get_train_use_case():
    """Train Use Case"""
    return get_service('train_use_case')


def get_health_use_case():
    """Health Use Case"""
    return get_service('health_use_case')


def get_prediction_service():
    """Prediction Service"""
    return get_service('prediction_service')


def get_monitoring_service():
    """Monitoring Service"""
    return get_service('monitoring_service')


def get_command_system():
    """Command System"""
    return get_service('command_system')


def get_self_healer():
    """Self Healer"""
    return get_service('self_healer')


# ============================================================
# System Providers
# ============================================================

def get_metrics_scheduler():
    """Metrics Scheduler"""
    return get_service('metrics_scheduler')


def get_threading_manager():
    """Threading Manager"""
    return get_service('threading_manager')


# ============================================================
# Flask Extension
# ============================================================

def init_container(app) -> None:
    """
    راه‌اندازی Container در Flask app
    
    پارامترها:
        app: نمونه Flask
    """
    # اتصال Container به app
    app.container = container
    
    # ثبت Middlewares
    try:
        from presentation.middlewares.error_handler import ErrorHandler
        from presentation.middlewares.logging import LoggingMiddleware
        
        ErrorHandler.init_app(app)
        LoggingMiddleware.init_app(app)
        
        logger.info("✅ Middlewares registered")
    except ImportError as e:
        logger.warning(f"⚠️ Middlewares not available: {e}")
    except Exception as e:
        logger.warning(f"⚠️ Middlewares registration failed: {e}")
    
    # شروع سرویس‌های پس‌زمینه
    try:
        start_services()
        logger.info("✅ Background services started")
    except Exception as e:
        logger.error(f"❌ Failed to start services: {e}")
    
    logger.info("✅ Container initialized in Flask app")


# ============================================================
# Shutdown
# ============================================================

def shutdown_services() -> None:
    """خاموش کردن همه سرویس‌ها"""
    try:
        stop_services()
        logger.info("✅ All services shut down")
    except Exception as e:
        logger.error(f"❌ Shutdown error: {e}")


def get_container_status() -> dict:
    """وضعیت Container"""
    return container.get_status()
