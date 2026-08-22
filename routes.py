# routes.py
# ============================================================
# مدیریت صفحات HTML (فرانت‌اند)
# ============================================================

from flask import send_from_directory, render_template_string, redirect
from app import app


# ============================================================
# روت‌های صفحات استاتیک
# ============================================================

@app.route('/')
def home_page():
    """ریدایرکت به داشبورد"""
    return redirect('/dashboard')


@app.route('/dashboard')
@require_auth()
def dashboard_page():
    """داشبورد"""
    return send_from_directory('static', 'dashboard.html')


@app.route('/predict-page')
@require_auth()
def predict_page():
    """صفحه پیش‌بینی"""
    return send_from_directory('static', 'predict.html')


@app.route('/test-api-page')
@require_auth()
def test_api_page():
    """صفحه تست API"""
    return send_from_directory('static', 'test-api.html')


@app.route('/health-page')
@require_auth()
def health_page():
    """صفحه سلامت سیستم"""
    return send_from_directory('static', 'health.html')


@app.route('/settings-page')
@require_auth()
def settings_page():
    """صفحه تنظیمات و آمار"""
    return send_from_directory('static', 'settings.html')
    
@app.route('/chart-page')
@require_auth()
def chart_page():
    return send_from_directory('static', 'chart.html')


@app.route('/database-page')
@require_auth()
def database_page():
    """صفحه مدیریت دیتابیس"""
    return send_from_directory('static', 'database.html')
# ===========================================================
# سرو فایل‌های استاتیک (CSS, JS, Images)
# ============================================================

@app.route('/static/<path:filename>')
def static_files(filename):
    """سرو فایل‌های استاتیک"""
    return send_from_directory('static', filename)


# ============================================================
# صفحات خطا
# ============================================================

@app.errorhandler(404)
def not_found(error):
    """صفحه خطای ۴۰۴"""
    return send_from_directory('static', '404.html'), 404


@app.errorhandler(500)
def internal_error(error):
    """صفحه خطای ۵۰۰"""
    return send_from_directory('static', '500.html'), 500


