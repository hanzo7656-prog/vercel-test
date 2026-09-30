# models/__init__.py
# ============================================================
# پکیج مدل - نسخه ۳.۰
# RuleEngine-based
# ============================================================

from typing import TYPE_CHECKING

# ============================================================
# Import مستقیم
# ============================================================

from models.manager import ModelManager


# ============================================================
# Lazy Import برای Trainer
# ============================================================

def __getattr__(name):
    """
    Lazy import برای AutoTrainer (WeightCalibrator)
    """
    if name == "AutoTrainer":
        from models.trainer.auto_trainer import AutoTrainer
        return AutoTrainer
    
    if name == "CALIBRATION_PROFILES":
        from models.trainer.auto_trainer import CALIBRATION_PROFILES
        return CALIBRATION_PROFILES
    
    raise AttributeError(
        f"module {__name__!r} has no attribute {name!r}"
    )


# ============================================================
# Export
# ============================================================

__all__ = [
    "ModelManager",
    "AutoTrainer",
    "CALIBRATION_PROFILES",
]
