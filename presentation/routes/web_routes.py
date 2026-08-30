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
    return send_from_directory('static', 'dashboard.html')


@web_bp.route('/chart-page')
@require_auth()
def chart_page():
    return send_from_directory('static', 'chart.html')


@web_bp.route('/predict-page')
@require_auth()
def predict_page():
    return send_from_directory('static', 'predict.html')


@web_bp.route('/database-page')
@require_auth()
def database_page():
    return send_from_directory('static', 'database.html')


@web_bp.route('/test-api-page')
@require_auth()
def test_api_page():
    return send_from_directory('static', 'test-api.html')


@web_bp.route('/settings-page')
@require_auth()
def settings_page():
    return send_from_directory('static', 'settings.html')


@web_bp.route('/debug-page')
@require_auth('admin')
def debug_page():
    return send_from_directory('static', 'debug.html')


# ============================================================
# ۳. مسیرهای کوتاه (برای راحتی)
# ============================================================

@web_bp.route('/chart')
@require_auth()
def chart_short():
    return send_from_directory('static', 'chart.html')


@web_bp.route('/predict')
@require_auth()
def predict_short():
    return send_from_directory('static', 'predict.html')


@web_bp.route('/database')
@require_auth()
def database_short():
    return send_from_directory('static', 'database.html')


@web_bp.route('/test-api')
@require_auth()
def test_api_short():
    return send_from_directory('static', 'test-api.html')


@web_bp.route('/settings')
@require_auth()
def settings_short():
    return send_from_directory('static', 'settings.html')


@web_bp.route('/debug')
@require_auth('admin')
def debug_short():
    return send_from_directory('static', 'debug.html')


# ============================================================
# ۴. صفحه ورود (GET - نمایش فرم)
# ============================================================

@web_bp.route('/login', methods=['GET'])
def login_page():
    return send_from_directory('static', 'login.html')


# ============================================================
# ۵. پردازش لاگین (POST)
# ============================================================

@web_bp.route('/login', methods=['POST'])
def login_post():
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
            response.set_cookie('session_id', result['session_id'], max_age=86400, httponly=True, secure=True, samesite='Lax', path='/')
            return response
        
        return jsonify(result), 401
        
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Login error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': 'خطا در پردازش درخواست'}), 500


# ============================================================
# ۶. خروج از حساب
# ============================================================

@web_bp.route('/logout', methods=['POST'])
def logout_post():
    session_id = request.cookies.get('session_id')
    if session_id:
        auth_manager = get_auth()
        auth_manager.logout(session_id)
    
    response = jsonify({"success": True, "message": "خروج موفق"})
    response.delete_cookie('session_id', path='/')
    return response


# ============================================================
# ۷. فایل‌های استاتیک
# ============================================================

@web_bp.route('/static/<path:filename>')
def static_files(filename):
    return send_from_directory('static', filename)


# ============================================================
# ۸. صفحات خطا
# ============================================================

@web_bp.route('/403')
def forbidden():
    return send_from_directory('static', '403.html'), 403


@web_bp.route('/404')
def not_found():
    return send_from_directory('static', '404.html'), 404


@web_bp.route('/500')
def internal_error():
    return send_from_directory('static', '500.html'), 500
