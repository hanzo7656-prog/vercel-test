# application/__init__.py
# ============================================================
# لایه کاربرد (Application Layer) - نسخه ۲.۰
# Lazy Import
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
    
    if name == "TrainRequestDTO":
        from application.dto import TrainRequestDTO
        return TrainRequestDTO
    
    if name == "BatchTrainRequestDTO":
        from application.dto import BatchTrainRequestDTO
        return BatchTrainRequestDTO
    
    # ============================================================
    # Use Cases
    # ============================================================
    
    if name == "PredictCoinUseCase":
        from application.use_cases import PredictCoinUseCase
        return PredictCoinUseCase
    
    if name == "TrainModelUseCase":
        from application.use_cases import TrainModelUseCase
        return TrainModelUseCase
    
    if name == "GetHealthUseCase":
        from application.use_cases import GetHealthUseCase
        return GetHealthUseCase
    
    # ============================================================
    # Services
    # ============================================================
    
    if name == "PredictionService":
        from application.services import PredictionService
        return PredictionService
    
    if name == "MonitoringService":
        from application.services import MonitoringService
        return MonitoringService
    
    if name == "CommandSystem":
        from application.services import CommandSystem
        return CommandSystem
    
    if name == "SelfHealer":
        from application.services import SelfHealer
        return SelfHealer
    
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
    "TrainRequestDTO",
    "BatchTrainRequestDTO",
    
    # ===== Use Cases =====
    "PredictCoinUseCase",
    "TrainModelUseCase",
    "GetHealthUseCase",
    
    # ===== Services =====
    "PredictionService",
    "MonitoringService",
    "CommandSystem",
    "SelfHealer",
]
