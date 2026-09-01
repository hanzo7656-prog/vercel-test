# presentation/routes/web_routes.py
# ============================================================
# Web Routes - صفحات HTML (با مسیر frontend/)
# ============================================================

from flask import Blueprint, send_from_directory, redirect, request, jsonify
from infrastructure.auth.auth_manager import require_auth, get_auth
import os

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
    return send_from_directory('frontend', 'dashboard.html')


@web_bp.route('/chart')
@require_auth()
def chart():
    return send_from_directory('frontend', 'chart.html')


@web_bp.route('/analyzer')
@require_auth()
def analyzer():
    return send_from_directory('frontend', 'analyzer.html')


@web_bp.route('/model')
@require_auth()
def model():
    return send_from_directory('frontend', 'model.html')


@web_bp.route('/database')
@require_auth()
def database():
    return send_from_directory('frontend', 'database.html')


@web_bp.route('/alerts')
@require_auth()
def alerts():
    return send_from_directory('frontend', 'alerts.html')


@web_bp.route('/debug')
@require_auth('admin')
def debug():
    return send_from_directory('frontend', 'debug.html')


@web_bp.route('/settings')
@require_auth()
def settings():
    return send_from_directory('frontend', 'settings.html')


# ============================================================
# ۳. صفحه ورود (بدون احراز هویت)
# ============================================================

@web_bp.route('/login')
def login_page():
    """صفحه ورود"""
    return send_from_directory('frontend', 'index.html')


# ============================================================
# ۴. صفحات خطا (با منو)
# ============================================================

@web_bp.route('/403')
def page_403():
    """صفحه دسترسی غیرمجاز"""
    return send_from_directory('frontend', '403.html'), 403


@web_bp.route('/404')
def page_404():
    """صفحه پیدا نشد"""
    return send_from_directory('frontend', '404.html'), 404


@web_bp.route('/500')
def page_500():
    """صفحه خطای داخلی سرور"""
    return send_from_directory('frontend', '500.html'), 500


# ============================================================
# ۵. فایل‌های استاتیک (CSS, JS, Components)
# ============================================================

@web_bp.route('/css/<path:filename>')
def css_files(filename):
    """سرویس فایل‌های CSS"""
    return send_from_directory('frontend/css', filename)


@web_bp.route('/js/<path:filename>')
def js_files(filename):
    """سرویس فایل‌های JavaScript"""
    return send_from_directory('frontend/js', filename)


@web_bp.route('/components/<path:filename>')
def components_files(filename):
    """سرویس فایل‌های کامپوننت"""
    return send_from_directory('frontend/components', filename)


@web_bp.route('/nav.html')
def nav():
    """سرویس فایل منو"""
    return send_from_directory('frontend', 'nav.html')


@web_bp.route('/<path:filename>.html')
def html_pages(filename):
    """سرویس صفحات HTML دلخواه"""
    if os.path.exists(f'frontend/{filename}.html'):
        return send_from_directory('frontend', f'{filename}.html')
    return redirect('/404')


# ============================================================
# ۶. پردازش لاگین (POST)
# ============================================================

@web_bp.route('/login', methods=['POST'])
def login_post():
    """پردازش لاگین از طریق فرم یا JSON"""
    try:
        data = request.get_json()
        if not data:
            username = request.form.get('username', '').strip()
            password = request.form.get('password', '').strip()
        else:
            username = data.get('username', '').strip()
            password = data.get('password', '').strip()
        
        if not username or not password:
            return jsonify({'success': False, 'error': 'لطفاً نام کاربری و رمز عبور را وارد کنید'}), 400
        
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
        return jsonify({'success': False, 'error': 'خطا در پردازش درخواست'}), 500


# ============================================================
# ۷. خروج از حساب
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
# ۸. Error Handlers (برای نمایش صفحات خطا)
# ============================================================

@web_bp.app_errorhandler(403)
def handle_403(error):
    """هندلر خطای ۴۰۳"""
    return send_from_directory('frontend', '403.html'), 403


@web_bp.app_errorhandler(404)
def handle_404(error):
    """هندلر خطای ۴۰۴"""
    return send_from_directory('frontend', '404.html'), 404


@web_bp.app_errorhandler(500)
def handle_500(error):
    """هندلر خطای ۵۰۰"""
    return send_from_directory('frontend', '500.html'), 500
