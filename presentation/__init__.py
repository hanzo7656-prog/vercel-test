# presentation/__init__.py
# ============================================================
# لایه ارائه (Presentation Layer)
# شامل Routes، Middlewareها و Schemas
# ============================================================

from presentation.routes.api_routes import api_bp
from presentation.routes.web_routes import web_bp
from presentation.routes.metrics_routes import metrics_bp
from presentation.middlewares.auth import AuthMiddleware
from presentation.middlewares.error_handler import ErrorHandler
from presentation.middlewares.logging import LoggingMiddleware
#a
__all__ = [
    'api_bp',
    'web_bp',
    'metrics_bp',
    'AuthMiddleware',
    'ErrorHandler',
    'LoggingMiddleware'
]
