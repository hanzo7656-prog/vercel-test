# application/__init__.py
# ============================================================
# لایه کاربرد (Application Layer) - نسخه ۳.۰
# Lazy Import - Gemini-only (RuleEngine legacy حذف شد)
# ============================================================

from typing import TYPE_CHECKING


# ============================================================
# Lazy Import
# ============================================================

def __getattr__(name: str):
    """
    Lazy loading برای همه اجزای Application Layer
    """
    
    # ============================================================
    # DTOs
    # ============================================================
    
    if name == "PredictionDTO":
        from application.dto import PredictionDTO
        return PredictionDTO
    
    if name == "PredictionRequestDTO":
        from application.dto import PredictionRequestDTO
        return PredictionRequestDTO
    
    # ⚠️ TrainRequestDTO حذف شد (RuleEngine legacy)
    # ⚠️ BatchTrainRequestDTO حذف شد (RuleEngine legacy)
    # ⚠️ CalibrateRequestDTO حذف شد (RuleEngine legacy)
    # ⚠️ ScanRequestDTO حذف شد (RuleEngine legacy)
    
    # ============================================================
    # Use Cases
    # ============================================================
    
    if name == "GetHealthUseCase":
        from application.use_cases import GetHealthUseCase
        return GetHealthUseCase
    
    if name == "AIChatUseCase":
        from application.use_cases import AIChatUseCase
        return AIChatUseCase
    
    if name == "AIAnalyzeImageUseCase":
        from application.use_cases import AIAnalyzeImageUseCase
        return AIAnalyzeImageUseCase
    
    if name == "AIExplainUseCase":
        from application.use_cases import AIExplainUseCase
        return AIExplainUseCase
    
    if name == "PredictCoinGeminiUseCase":
        from application.use_cases import PredictCoinGeminiUseCase
        return PredictCoinGeminiUseCase
    
    # ⚠️ PredictCoinUseCase حذف شد (RuleEngine legacy)
    # ⚠️ TrainModelUseCase حذف شد (RuleEngine legacy)
    # ⚠️ ScanMarketUseCase حذف شد (RuleEngine legacy)
    
    # ============================================================
    # Services
    # ============================================================
    
    if name == "PredictionService":
        from application.services import PredictionService
        return PredictionService
    
    if name == "MonitoringService":
        from application.services import MonitoringService
        return MonitoringService
    
    if name == "PredictionRouter":
        from application.services import PredictionRouter
        return PredictionRouter
    
    # ⚠️ CommandSystem حذف شد (RuleEngine legacy)
    # ⚠️ SelfHealer حذف شد (RuleEngine legacy)
    
    # ============================================================
    # Not found
    # ============================================================
    
    raise AttributeError(
        f"module {__name__!r} has no attribute {name!r}"
    )


# ============================================================
# Export
# ============================================================

__all__ = [
    # ===== DTOs =====
    "PredictionDTO",
    "PredictionRequestDTO",
    
    # ===== Use Cases =====
    "GetHealthUseCase",
    "AIChatUseCase",
    "AIAnalyzeImageUseCase",
    "AIExplainUseCase",
    "PredictCoinGeminiUseCase",
    
    # ===== Services =====
    "PredictionService",
    "MonitoringService",
    "PredictionRouter",
]
