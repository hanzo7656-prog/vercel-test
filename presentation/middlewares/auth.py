# presentation/middlewares/auth.py
# ============================================================
# Middleware: احراز هویت
# ============================================================

import logging
from functools import wraps
from flask import request, jsonify, current_app

from infrastructure.auth.auth_manager import get_auth

logger = logging.getLogger(__name__)


class AuthMiddleware:
    """
    Middleware احراز هویت
    
    وظیفه:
        - بررسی Session
        - اعتبارسنجی توکن
        - مدیریت دسترسی‌ها
    """
    
    @staticmethod
    def require_auth(role: str = None):
        """
        دکوراتور برای محافظت از روت‌ها
        
        پارامترها:
            role: نقش مورد نیاز (اختیاری)
        """
        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                # دریافت Session ID از Cookie
                session_id = request.cookies.get('session_id')
                
                if not session_id:
                    # بررسی Authorization Header (برای API)
                    auth_header = request.headers.get('Authorization')
                    if auth_header and auth_header.startswith('Bearer '):
                        session_id = auth_header.replace('Bearer ', '')
                
                if not session_id:
                    if request.path.startswith('/api/'):
                        return jsonify({
                            'success': False,
                            'error': 'Unauthorized',
                            'message': 'Please login first'
                        }), 401
                    return redirect('/login')
                
                # بررسی Session
                auth_manager = get_auth()
                session = auth_manager.verify_session(session_id)
                
                if not session:
                    if request.path.startswith('/api/'):
                        return jsonify({
                            'success': False,
                            'error': 'Session expired',
                            'message': 'Please login again'
                        }), 401
                    return redirect('/login')
                
                # بررسی نقش (در صورت نیاز)
                if role and session.get('role') != role and session.get('role') != 'admin':
                    if request.path.startswith('/api/'):
                        return jsonify({
                            'success': False,
                            'error': 'Forbidden',
                            'message': 'Insufficient permissions'
                        }), 403
                    return redirect('/403')
                
                # افزودن اطلاعات کاربر به request
                request.user = {
                    'username': session.get('username'),
                    'role': session.get('role')
                }
                
                return func(*args, **kwargs)
            return wrapper
        return decorator
    
    @staticmethod
    def get_current_user():
        """دریافت کاربر فعلی از Request"""
        return getattr(request, 'user', None)
