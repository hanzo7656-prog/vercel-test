# routes/web_routes.py
# ============================================================
# روت‌های صفحات HTML - فرانت‌اند
# ============================================================

from flask import send_from_directory, redirect
from auth_manager import require_auth


def register_web_routes(app):
    """ثبت روت‌های صفحات HTML در Flask app"""
    
    # ============================================================
    # ۱. صفحه اصلی
    # ============================================================
    
    @app.route('/')
    def home_page():
        return redirect('/dashboard')

    # ============================================================
    # ۲. صفحات اصلی (نیاز به احراز هویت)
    # ============================================================
    
    @app.route('/dashboard')
    @require_auth()
    def dashboard_page():
        """داشبورد جامع"""
        return send_from_directory('static', 'dashboard.html')

    @app.route('/predict-page')
    @require_auth()
    def predict_page():
        """صفحه تحلیلگر (چت + وضعیت مدل)"""
        return send_from_directory('static', 'predict.html')

    @app.route('/database-page')
    @require_auth()
    def database_page():
        """صفحه مدیریت دیتابیس"""
        return send_from_directory('static', 'database.html')

    @app.route('/test-api-page')
    @require_auth()
    def test_api_page():
        """صفحه تست API"""
        return send_from_directory('static', 'test-api.html')

    @app.route('/settings-page')
    @require_auth()
    def settings_page():
        """صفحه تنظیمات"""
        return send_from_directory('static', 'settings.html')

    @app.route('/chart-page')
    @require_auth()
    def chart_page():
        """صفحه نمودار"""
        return send_from_directory('static', 'chart.html')

    @app.route('/debug-page')
    @require_auth()
    def debug_page():
        """صفحه دیباگ"""
        return send_from_directory('static', 'debug.html')

    # ============================================================
    # ۳. صفحه ورود (بدون احراز هویت)
    # ============================================================
    
    @app.route('/login')
    def login_page():
        """صفحه ورود"""
        return send_from_directory('static', 'login.html')

    # ============================================================
    # ۴. صفحات خطا
    # ============================================================
    
    @app.route('/403')
    def forbidden_page():
        return send_from_directory('static', '403.html'), 403

    # ============================================================
    # ۵. فایل‌های استاتیک
    # ============================================================
    
    @app.route('/static/<path:filename>')
    def static_files(filename):
        return send_from_directory('static', filename)

    # ============================================================
    # ۶. Error Handlers
    # ============================================================
    
    @app.errorhandler(404)
    def not_found(error):
        return send_from_directory('static', '404.html'), 404

    @app.errorhandler(403)
    def forbidden(error):
        return send_from_directory('static', '403.html'), 403

    @app.errorhandler(500)
    def internal_error(error):
        return send_from_directory('static', '500.html'), 500

    @app.errorhandler(Exception)
    def handle_exception(error):
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Unhandled exception: {error}")
        return send_from_directory('static', '500.html'), 500
