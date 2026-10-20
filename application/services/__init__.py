# application/services/__init__.py
# ============================================================
# Services - سرویس‌های لایه کاربرد
# نسخه ۳.۰ - Gemini-only (SelfHealer, CommandSystem حذف شدند)
# ============================================================

from typing import TYPE_CHECKING


# ============================================================
# Lazy Import (جلوگیری از Circular)
# ============================================================

def __getattr__(name: str):
    """
    Lazy loading برای سرویس‌ها
    """
    
    # ===== Prediction Service =====
    if name == "PredictionService":
        from application.services.prediction_service import PredictionService
        return PredictionService
    
    # ===== Monitoring Service =====
    if name == "MonitoringService":
        from application.services.monitoring_service import MonitoringService
        return MonitoringService
    
    # ===== Prediction Router 🆕 =====
    if name == "PredictionRouter":
        from application.services.prediction_router import PredictionRouter
        return PredictionRouter
    
    # ⚠️ CommandSystem حذف شد (RuleEngine legacy)
    # ⚠️ SelfHealer حذف شد (RuleEngine legacy)
    
    raise AttributeError(
        f"module {__name__!r} has no attribute {name!r}"
    )


# ============================================================
# Export
# ============================================================

__all__ = [
    "PredictionService",
    "MonitoringService",
    "PredictionRouter",
]
