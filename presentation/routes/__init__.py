# presentation/__init__.py
# ============================================================
# لایه ارائه (Presentation Layer)
# ============================================================

from presentation.routes.api_routes import api_bp
from presentation.routes.metrics_routes import metrics_bp
from presentation.routes.web_routes import web_bp  # ✅ اضافه کنید

__all__ = [
    'api_bp',
    'metrics_bp',
    'web_bp' 
]
