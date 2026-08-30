# presentation/middlewares/logging.py
# ============================================================
# Middleware: لاگ‌گیری
# ============================================================

import logging
import time
from flask import request, g

logger = logging.getLogger(__name__)


class LoggingMiddleware:
    """
    Middleware لاگ‌گیری
    
    وظیفه:
        - لاگ درخواست‌ها
        - اندازه‌گیری زمان پاسخ
        - لاگ خطاها
    """
    
    @staticmethod
    def before_request():
        """قبل از هر درخواست"""
        g.start_time = time.time()
        
        # لاگ درخواست
        logger.info(f"📥 {request.method} {request.path} - {request.remote_addr}")
        
        # لاگ پارامترها (در صورت Debug)
        if request.args:
            logger.debug(f"   Query: {dict(request.args)}")
        
        # ✅ اصلاح - بررسی Content-Type قبل از دسترسی به request.json
        if request.is_json:
            try:
                logger.debug(f"   Body: {request.json}")
            except Exception:
                pass
    
    @staticmethod
    def after_request(response):
        """بعد از هر درخواست"""
        elapsed = time.time() - g.start_time
        
        # لاگ پاسخ
        logger.info(f"📤 {request.method} {request.path} - {response.status_code} - {elapsed*1000:.2f}ms")
        
        return response
    
    @staticmethod
    def init_app(app):
        """ثبت Middleware در Flask app"""
        app.before_request(LoggingMiddleware.before_request)
        app.after_request(LoggingMiddleware.after_request)
        logger.info("✅ LoggingMiddleware registered")
