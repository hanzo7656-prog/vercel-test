# presentation/routes/web_routes.py
# ============================================================
# Web Routes - صفحات HTML
# ============================================================

from flask import Blueprint, send_from_directory, redirect, request, jsonify
from infrastructure.auth.auth_manager import require_auth, get_auth

web_bp = Blueprint('web', __name__)


# ============================================================
# ۱. صفحه اصلی
# ============================================================

@web_bp.route('/')
def home():
    """صفحه اصلی - ریدایرکت به داشبورد"""
    return redirect('/dashboard')


# ============================================================
# ۲. صفحات با احراز هویت
# ============================================================

@web_bp.route('/dashboard')
@require_auth()
def dashboard():
    """داشبورد اصلی"""
    return send_from_directory('static', 'dashboard.html')


@web_bp.route('/predict')
@require_auth()
def predict_page():
    """صفحه پیش‌بینی و تحلیل"""
    return send_from_directory('static', 'predict.html')


@web_bp.route('/database')
@require_auth()
def database_page():
    """صفحه مدیریت دیتابیس"""
    return send_from_directory('static', 'database.html')


@web_bp.route('/test-api')
@require_auth()
def test_api_page():
    """صفحه تست API"""
    return send_from_directory('static', 'test-api.html')


@web_bp.route('/settings')
@require_auth()
def settings_page():
    """صفحه تنظیمات"""
    return send_from_directory('static', 'settings.html')


@web_bp.route('/chart')
@require_auth()
def chart_page():
    """صفحه نمودار"""
    return send_from_directory('static', 'chart.html')


@web_bp.route('/debug')
@require_auth('admin')
def debug_page():
    """صفحه دیباگ (فقط ادمین)"""
    return send_from_directory('static', 'debug.html')


# ============================================================
# ۳. صفحه ورود (GET - نمایش فرم)
# ============================================================

@web_bp.route('/login', methods=['GET'])
def login_page():
    """صفحه ورود"""
    return send_from_directory('static', 'login.html')


# ============================================================
# ۴. پردازش لاگین (POST - پردازش فرم)
# ============================================================

@web_bp.route('/login', methods=['POST'])
def login_post():
    """
    پردازش فرم ورود
    
    Body:
        username: نام کاربری
        password: رمز عبور
    """
    try:
        data = request.get_json()
        if not data:
            # اگر JSON نبود، از فرم استفاده کن
            username = request.form.get('username', '').strip()
            password = request.form.get('password', '').strip()
        else:
            username = data.get('username', '').strip()
            password = data.get('password', '').strip()
        
        if not username or not password:
            return jsonify({
                'success': False,
                'error': 'لطفاً نام کاربری و رمز عبور را وارد کنید'
            }), 400
        
        auth_manager = get_auth()
        result = auth_manager.login(username, password)
        
        if result["success"]:
            response = jsonify(result)
            response.set_cookie(
                'session_id',
                result['session_id'],
                max_age=86400,
                httponly=True,
                secure=True,
                samesite='Lax',
                path='/'
            )
            return response
        
        return jsonify(result), 401
        
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Login error: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': 'خطا در پردازش درخواست'
        }), 500


# ============================================================
# ۵. خروج از حساب
# ============================================================

@web_bp.route('/logout', methods=['POST'])
def logout_post():
    """خروج از حساب"""
    session_id = request.cookies.get('session_id')
    if session_id:
        auth_manager = get_auth()
        auth_manager.logout(session_id)
    
    response = jsonify({"success": True, "message": "خروج موفق"})
    response.delete_cookie('session_id', path='/')
    return response


# ============================================================
# ۶. فایل‌های استاتیک
# ============================================================

@web_bp.route('/static/<path:filename>')
def static_files(filename):
    """سرویس فایل‌های استاتیک"""
    return send_from_directory('static', filename)


# ============================================================
# ۷. صفحات خطا
# ============================================================

@web_bp.route('/403')
def forbidden():
    """صفحه دسترسی غیرمجاز"""
    return send_from_directory('static', '403.html'), 403


@web_bp.route('/404')
def not_found():
    """صفحه پیدا نشد"""
    return send_from_directory('static', '404.html'), 404


@web_bp.route('/500')
def internal_error():
    """صفحه خطای داخلی"""
    return send_from_directory('static', '500.html'), 500
