# presentation/middlewares/error_handler.py
# ============================================================
# Middleware: مدیریت خطا
# ============================================================

import logging
import traceback
from flask import jsonify, request, current_app
from werkzeug.exceptions import HTTPException

logger = logging.getLogger(__name__)


class ErrorHandler:
    """
    Middleware مدیریت خطا
    
    وظیفه:
        - مدیریت یکپارچه خطاها
        - تبدیل خطاها به پاسخ JSON
        - لاگ‌گیری خطاها
    """
    
    @staticmethod
    def handle_error(error):
        """
        مدیریت خطا و بازگرداندن پاسخ مناسب
        
        پارامترها:
            error: خطای رخ داده
        """
        # لاگ خطا
        logger.error(f"Error: {error}")
        logger.error(traceback.format_exc())
        
        # خطاهای HTTP
        if isinstance(error, HTTPException):
            return jsonify({
                'success': False,
                'error': error.name,
                'message': error.description,
                'code': error.code,
                'timestamp': datetime.now().isoformat()
            }), error.code
        
        # خطاهای اعتبارسنجی
        if isinstance(error, ValueError):
            return jsonify({
                'success': False,
                'error': 'ValidationError',
                'message': str(error),
                'code': 400,
                'timestamp': datetime.now().isoformat()
            }), 400
        
        # خطاهای دیتابیس
        if 'database' in str(error).lower() or 'db' in str(error).lower():
            return jsonify({
                'success': False,
                'error': 'DatabaseError',
                'message': 'Database operation failed',
                'code': 503,
                'timestamp': datetime.now().isoformat()
            }), 503
        
        # خطاهای API
        if 'api' in str(error).lower() or 'timeout' in str(error).lower():
            return jsonify({
                'success': False,
                'error': 'APIError',
                'message': 'External API error',
                'code': 502,
                'timestamp': datetime.now().isoformat()
            }), 502
        
        # خطاهای ناشناخته
        return jsonify({
            'success': False,
            'error': 'InternalServerError',
            'message': 'An unexpected error occurred',
            'code': 500,
            'timestamp': datetime.now().isoformat()
        }), 500
    
    @staticmethod
    def init_app(app):
        """ثبت Error Handler در Flask app"""
        app.errorhandler(Exception)(ErrorHandler.handle_error)
        logger.info("✅ ErrorHandler registered")
