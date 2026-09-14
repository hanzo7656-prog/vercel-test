# application/services/__init__.py
# ============================================================
# Services - سرویس‌های لایه کاربرد
# نسخه ۲.۰ - Lazy Import
# ============================================================

from typing import TYPE_CHECKING


# ============================================================
# Lazy Import (جلوگیری از Circular)
# ============================================================

def __getattr__(name: str):
    """
    Lazy loading برای سرویس‌ها
    
    این تابع وقتی صدا زده می‌شه که یه attribute
    از این ماژول درخواست بشه که در global namespace نیست.
    """
    
    # ===== Prediction Service =====
    if name == "PredictionService":
        from application.services.prediction_service import PredictionService
        return PredictionService
    
    # ===== Monitoring Service =====
    if name == "MonitoringService":
        from application.services.monitoring_service import MonitoringService
        return MonitoringService
    
    # ===== Command System =====
    if name == "CommandSystem":
        from application.services.command_system import CommandSystem
        return CommandSystem
    
    # ===== Self Healer =====
    if name == "SelfHealer":
        from application.services.self_healer import SelfHealer
        return SelfHealer
    
    raise AttributeError(
        f"module {__name__!r} has no attribute {name!r}"
    )


# ============================================================
# Export
# ============================================================

__all__ = [
    "PredictionService",
    "MonitoringService",
    "CommandSystem",
    "SelfHealer",
]
