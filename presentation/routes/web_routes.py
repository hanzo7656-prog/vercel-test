# presentation/routes/web_routes.py
# ============================================================
# Web Routes - صفحات HTML
# ============================================================

from flask import Blueprint, send_from_directory, redirect
from infrastructure.auth.auth_manager import require_auth

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
# ۳. صفحه ورود (بدون احراز هویت)
# ============================================================

@web_bp.route('/login')
def login_page():
    """صفحه ورود"""
    return send_from_directory('static', 'login.html')


# ============================================================
# ۴. فایل‌های استاتیک
# ============================================================

@web_bp.route('/static/<path:filename>')
def static_files(filename):
    """سرویس فایل‌های استاتیک"""
    return send_from_directory('static', filename)


# ============================================================
# ۵. صفحات خطا
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
