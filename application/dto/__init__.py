# application/dto/__init__.py
# ============================================================
# Data Transfer Objects - نسخه ۲.۰
# ============================================================

from typing import TYPE_CHECKING


# ============================================================
# Lazy Import
# ============================================================

def __getattr__(name: str):
    """
    Lazy loading برای DTOها
    """
    
    # ===== Prediction DTOs =====
    if name == "PredictionDTO":
        from application.dto.prediction_dto import PredictionDTO
        return PredictionDTO
    
    if name == "PredictionRequestDTO":
        from application.dto.prediction_dto import PredictionRequestDTO
        return PredictionRequestDTO
    
    # ===== Trainer DTOs (🆕) =====
    if name == "TrainRequestDTO":
        from application.dto.prediction_dto import TrainRequestDTO
        return TrainRequestDTO
    
    if name == "BatchTrainRequestDTO":
        from application.dto.prediction_dto import BatchTrainRequestDTO
        return BatchTrainRequestDTO
    
    raise AttributeError(
        f"module {__name__!r} has no attribute {name!r}"
    )


# ============================================================
# Export
# ============================================================

__all__ = [
    # Prediction
    "PredictionDTO",
    "PredictionRequestDTO",
    
    # Trainer (🆕)
    "TrainRequestDTO",
    "BatchTrainRequestDTO",
]
