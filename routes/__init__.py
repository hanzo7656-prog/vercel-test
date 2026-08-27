# routes/__init__.py
# ============================================================
# پکیج Routes - ثبت همه روت‌های Flask
# ============================================================

from flask import Flask
from typing import Any


def register_all_routes(app: Flask, system: Any):
    """
    ثبت همه روت‌ها در Flask app
    
    پارامترها:
        app: نمونه Flask
        system: نمونه TradingSignalSystem
    """
    from routes.api_routes import register_api_routes
    from routes.web_routes import register_web_routes
    from routes.metrics_routes import register_metrics_routes
    
    # ثبت روت‌ها به ترتیب
    register_api_routes(app, system)
    register_web_routes(app)
    register_metrics_routes(app)
    
    return app


# برای راحتی کار، همه چیز رو export می‌کنیم
from routes.api_routes import register_api_routes
from routes.web_routes import register_web_routes
from routes.metrics_routes import register_metrics_routes

__all__ = [
    'register_all_routes',
    'register_api_routes',
    'register_web_routes',
    'register_metrics_routes'
]
