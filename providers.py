# providers.py
# ============================================================
# Providers - ارائه‌دهنده‌های سرویس (برای استفاده در Flask)
# ============================================================

import logging
from typing import Any, Optional
from flask import current_app, has_app_context

from container import container

logger = logging.getLogger(__name__)


def get_service(name: str) -> Any:
    """
    دریافت یک سرویس از Container (با پشتیبانی از Flask Context)
    
    پارامترها:
        name: نام سرویس
    
    خروجی:
        نمونه سرویس
    
    استثناها:
        RuntimeError: اگر Container در دسترس نباشد
    """
    # اگر در Context Flask هستیم، از Container برنامه استفاده کن
    if has_app_context():
        app_container = getattr(current_app, 'container', None)
        if app_container:
            return app_container.get(name)
    
    # استفاده از Container سراسری
    return container.get(name)


# ============================================================
# Provider Functions - دسترسی آسان به سرویس‌ها
# ============================================================

def get_api_client():
    return get_service('api_client')


def get_cache_manager():
    return get_service('cache_manager')


def get_model_repository():
    return get_service('model_repository')


def get_prediction_repository():
    return get_service('prediction_repository')


def get_auth_manager():
    return get_service('auth_manager')


def get_feature_engineer():
    return get_service('feature_engineer')


def get_model_manager():
    return get_service('model_manager')


def get_trainer():
    return get_service('trainer')


def get_predict_use_case():
    return get_service('predict_use_case')


def get_train_use_case():
    return get_service('train_use_case')


def get_health_use_case():
    return get_service('health_use_case')


def get_prediction_service():
    return get_service('prediction_service')


def get_monitoring_service():
    return get_service('monitoring_service')


def get_metrics_scheduler():
    return get_service('metrics_scheduler')


def get_threading_manager():
    return get_service('threading_manager')


# ============================================================
# ✅ Provider Functions جدید برای WebSocket
# ============================================================

def get_free_crypto_client():
    """دریافت کلاینت WebSocket FreeCryptoAPI"""
    return get_service('free_crypto_client')


def get_user_tracker():
    """دریافت UserTracker"""
    return get_service('user_tracker')


def get_price_manager():
    """دریافت PriceManager"""
    return get_service('price_manager')


# ============================================================
# Flask Extension - برای اتصال به برنامه
# ============================================================

def init_container(app) -> None:
    """
    راه‌اندازی Container در Flask app
    
    پارامترها:
        app: نمونه Flask
    """
    # اتصال Container به app
    app.container = container
    
    # ثبت Middlewareها
    from presentation.middlewares.auth import AuthMiddleware
    from presentation.middlewares.error_handler import ErrorHandler
    from presentation.middlewares.logging import LoggingMiddleware
    
    # ثبت Error Handler
    ErrorHandler.init_app(app)
    
    # ثبت Logging Middleware
    LoggingMiddleware.init_app(app)
    
    # ✅ شروع سرویس‌های پس‌زمینه
    container.start_services()
    
    logger.info("✅ Container initialized in Flask app with background services")


# ============================================================
# تابع کمکی برای تست
# ============================================================

def get_container_status() -> dict:
    """دریافت وضعیت Container"""
    return container.get_status()


# ============================================================
# تابع خاموش‌سازی
# ============================================================

def shutdown_services() -> None:
    """خاموش کردن همه سرویس‌ها"""
    container.stop_services()
    logger.info("✅ All services shut down")
