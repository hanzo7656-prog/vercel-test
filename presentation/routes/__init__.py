# presentation/routes/__init__.py
# ============================================================
# Routes - مسیرهای API و Web
# ============================================================

from presentation.routes.api_routes import api_bp
from presentation.routes.web_routes import web_bp
from presentation.routes.metrics_routes import metrics_bp

__all__ = [
    'api_bp',
    'web_bp',
    'metrics_bp'
]
