# models/__init__.py
# ============================================================
# پکیج مدل - نسخه ۲.۰
# ============================================================

from typing import TYPE_CHECKING

# ============================================================
# Import مستقیم (بدون circular dependency)
# ============================================================

from models.manager import (
    ModelManager,
    TRAINING_PRESETS,
    LEARNING_STRATEGIES,
    HYPERPARAMETER_LIMITS,
    DEFAULT_HYPERPARAMETERS,
)


# ============================================================
# Lazy Import برای Trainerها
# ============================================================

def __getattr__(name):
    """
    Lazy import برای Trainerها
    
    این تابع باعث می‌شه AutoTrainer و ManualTrainer فقط
    وقتی واقعاً استفاده بشن، import بشن. اینطوری circular
    dependency پیش نمیاد.
    """
    if name == "AutoTrainer":
        from models.trainer.auto_trainer import AutoTrainer
        return AutoTrainer
    
    if name == "ManualTrainer":
        # ManualTrainer یه CLI هست، پس ماژول رو برمی‌گردونیم
        from models.trainer import manual_trainer
        return manual_trainer
    
    raise AttributeError(
        f"module {__name__!r} has no attribute {name!r}"
    )


# ============================================================
# Export
# ============================================================

__all__ = [
    # Manager
    "ModelManager",
    
    # Trainerها (lazy)
    "AutoTrainer",
    "ManualTrainer",
    
    # Constants
    "TRAINING_PRESETS",
    "LEARNING_STRATEGIES",
    "HYPERPARAMETER_LIMITS",
    "DEFAULT_HYPERPARAMETERS",
]
