# application/__init__.py
# ============================================================
# لایه کاربرد - نسخه ۳.۱
# + SelfHealer (Gemini-aware)
# ============================================================

from typing import TYPE_CHECKING


def __getattr__(name: str):
    # ============================================================
    # DTOs
    # ============================================================
    
    if name == "PredictionDTO":
        from application.dto import PredictionDTO
        return PredictionDTO
    
    if name == "PredictionRequestDTO":
        from application.dto import PredictionRequestDTO
        return PredictionRequestDTO
    
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
    
    if name == "SelfHealer":
        from application.services import SelfHealer
        return SelfHealer
    
    raise AttributeError(
        f"module {__name__!r} has no attribute {name!r}"
    )


__all__ = [
    # DTOs
    "PredictionDTO",
    "PredictionRequestDTO",
    
    # Use Cases
    "GetHealthUseCase",
    "AIChatUseCase",
    "AIAnalyzeImageUseCase",
    "AIExplainUseCase",
    "PredictCoinGeminiUseCase",
    
    # Services
    "PredictionService",
    "MonitoringService",
    "PredictionRouter",
    "SelfHealer",       # 🆕
]
