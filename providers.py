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
    """دریافت کلاینت API"""
    return get_service('api_client')


def get_cache_manager():
    """دریافت مدیریت کش"""
    return get_service('cache_manager')


def get_model_repository():
    """دریافت Repository مدل"""
    return get_service('model_repository')


def get_prediction_repository():
    """دریافت Repository پیش‌بینی"""
    return get_service('prediction_repository')


def get_auth_manager():
    """دریافت مدیریت احراز هویت"""
    return get_service('auth_manager')


def get_feature_engineer():
    """دریافت مهندس ویژگی"""
    return get_service('feature_engineer')


def get_model_manager():
    """دریافت مدیریت مدل"""
    return get_service('model_manager')


def get_trainer():
    """دریافت آموزش‌دهنده خودکار"""
    return get_service('trainer')


def get_predict_use_case():
    """دریافت Use Case پیش‌بینی"""
    return get_service('predict_use_case')


def get_train_use_case():
    """دریافت Use Case آموزش"""
    return get_service('train_use_case')


def get_health_use_case():
    """دریافت Use Case سلامت"""
    return get_service('health_use_case')


def get_prediction_service():
    """دریافت سرویس پیش‌بینی"""
    return get_service('prediction_service')


def get_monitoring_service():
    """دریافت سرویس مانیتورینگ"""
    return get_service('monitoring_service')


def get_metrics_scheduler():
    """دریافت Scheduler متریک"""
    return get_service('metrics_scheduler')


def get_threading_manager():
    """دریافت مدیریت Threadها"""
    return get_service('threading_manager')


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
    
    logger.info("✅ Container initialized in Flask app")


# ============================================================
# تابع کمکی برای تست
# ============================================================

def get_container_status() -> dict:
    """دریافت وضعیت Container"""
    return container.get_status()
