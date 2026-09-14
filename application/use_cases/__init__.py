# application/use_cases/__init__.py
# ============================================================
# Use Cases - موارد استفاده - نسخه ۲.۰
# Lazy Import
# ============================================================

from typing import TYPE_CHECKING


# ============================================================
# Lazy Import
# ============================================================

def __getattr__(name: str):
    """
    Lazy loading برای Use Caseها
    """
    
    # ===== Predict =====
    if name == "PredictCoinUseCase":
        from application.use_cases.predict_coin import PredictCoinUseCase
        return PredictCoinUseCase
    
    # ===== Train =====
    if name == "TrainModelUseCase":
        from application.use_cases.train_model import TrainModelUseCase
        return TrainModelUseCase
    
    # ===== Health =====
    if name == "GetHealthUseCase":
        from application.use_cases.get_health import GetHealthUseCase
        return GetHealthUseCase
    
    raise AttributeError(
        f"module {__name__!r} has no attribute {name!r}"
    )


# ============================================================
# Export
# ============================================================

__all__ = [
    "PredictCoinUseCase",
    "TrainModelUseCase",
    "GetHealthUseCase",
]
