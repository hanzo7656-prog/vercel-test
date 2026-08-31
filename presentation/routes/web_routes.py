# presentation/routes/web_routes.py

from flask import Blueprint, send_from_directory, redirect
from infrastructure.auth.auth_manager import require_auth

web_bp = Blueprint('web', __name__)

# ============================================================
# صفحات HTML
# ============================================================

@web_bp.route('/')
def home():
    return redirect('/dashboard')

@web_bp.route('/dashboard')
@require_auth()
def dashboard():
    return send_from_directory('frontend', 'dashboard.html')

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

@web_bp.route('/chart')
@require_auth()
def chart():
    return send_from_directory('frontend', 'chart.html')

@web_bp.route('/login')
def login_page():
    return send_from_directory('frontend', 'index.html')

# ============================================================
# فایل‌های استاتیک (CSS, JS, Components)
# ============================================================

@web_bp.route('/css/<path:filename>')
def css_files(filename):
    return send_from_directory('frontend/css', filename)

@web_bp.route('/js/<path:filename>')
def js_files(filename):
    return send_from_directory('frontend/js', filename)

@web_bp.route('/components/<path:filename>')
def components_files(filename):
    return send_from_directory('frontend/components', filename)

@web_bp.route('/nav.html')
def nav():
    return send_from_directory('frontend', 'nav.html')

@web_bp.route('/<path:filename>.html')
def html_pages(filename):
    # بررسی وجود فایل
    import os
    if os.path.exists(f'static/{filename}.html'):
        return send_from_directory('frontend', f'{filename}.html')
    return redirect('/dashboard')
