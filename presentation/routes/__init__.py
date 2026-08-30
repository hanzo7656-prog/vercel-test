# فقط API routes
from presentation.routes.api_routes import api_bp
from presentation.routes.metrics_routes import metrics_bp

__all__ = ['api_bp', 'metrics_bp']
