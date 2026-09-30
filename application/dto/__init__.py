# application/dto/__init__.py
# ============================================================
# DTOs - نسخه ۲.۰
# ============================================================

from typing import TYPE_CHECKING


def __getattr__(name: str):
    if name == "PredictionDTO":
        from application.dto.prediction_dto import PredictionDTO
        return PredictionDTO
    
    if name == "PredictionRequestDTO":
        from application.dto.prediction_dto import PredictionRequestDTO
        return PredictionRequestDTO
    
    if name == "CalibrateRequestDTO":
        from application.dto.prediction_dto import CalibrateRequestDTO
        return CalibrateRequestDTO
    
    if name == "ScanRequestDTO":
        from application.dto.prediction_dto import ScanRequestDTO
        return ScanRequestDTO
    
    raise AttributeError(
        f"module {__name__!r} has no attribute {name!r}"
    )


__all__ = [
    "PredictionDTO",
    "PredictionRequestDTO",
    "CalibrateRequestDTO",
    "ScanRequestDTO",
]
