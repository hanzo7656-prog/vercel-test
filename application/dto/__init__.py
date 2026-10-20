# application/dto/__init__.py
# ============================================================
# DTOs - نسخه ۳.۰
# Gemini-only (RuleEngine DTOs حذف شدند)
# ============================================================

from typing import TYPE_CHECKING


def __getattr__(name: str):
    # ============================================================
    # Prediction DTOs
    # ============================================================
    
    if name == "PredictionDTO":
        from application.dto.prediction_dto import PredictionDTO
        return PredictionDTO
    
    if name == "PredictionRequestDTO":
        from application.dto.prediction_dto import PredictionRequestDTO
        return PredictionRequestDTO
    
    # ⚠️ CalibrateRequestDTO حذف شد (RuleEngine legacy)
    # ⚠️ ScanRequestDTO حذف شد (RuleEngine legacy)
    
    raise AttributeError(
        f"module {__name__!r} has no attribute {name!r}"
    )


__all__ = [
    "PredictionDTO",
    "PredictionRequestDTO",
]
