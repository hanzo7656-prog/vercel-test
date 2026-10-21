# application/services/__init__.py
# ============================================================
# Services - نسخه ۳.۱
# + SelfHealer (Gemini-aware)
# ============================================================

from typing import TYPE_CHECKING


def __getattr__(name: str):
    # ===== Prediction Service =====
    if name == "PredictionService":
        from application.services.prediction_service import PredictionService
        return PredictionService
    
    # ===== Monitoring Service =====
    if name == "MonitoringService":
        from application.services.monitoring_service import MonitoringService
        return MonitoringService
    
    # ===== Prediction Router =====
    if name == "PredictionRouter":
        from application.services.prediction_router import PredictionRouter
        return PredictionRouter
    
    # ===== Self Healer (Gemini-aware) 🆕 =====
    if name == "SelfHealer":
        from application.services.self_healer import SelfHealer
        return SelfHealer
    
    # ⚠️ CommandSystem حذف شد (RuleEngine legacy)
    
    raise AttributeError(
        f"module {__name__!r} has no attribute {name!r}"
    )


__all__ = [
    "PredictionService",
    "MonitoringService",
    "PredictionRouter",
    "SelfHealer",       # 🆕
]
