# presentation/__init__.py
# ============================================================
# لایه ارائه (Presentation Layer)
# نسخه ۲.۰ - Gemini-only (model_bp حذف شد)
# ============================================================

from presentation.routes.api_routes import api_bp
from presentation.routes.metrics_routes import metrics_bp
from presentation.routes.web_routes import web_bp
from presentation.routes.ai_routes import ai_bp          # 🆕

# ⚠️ model_bp حذف شد (RuleEngine legacy)


__all__ = [
    'api_bp',
    'metrics_bp',
    'web_bp',
    'ai_bp',          # 🆕
]
