# models/manager/__init__.py
# ============================================================
# پکیج مدیریت مدل - نسخه ۲.۰
# ============================================================

from models.manager.model_manager import (
    ModelManager,
    TRAINING_PRESETS,
    LEARNING_STRATEGIES,
    HYPERPARAMETER_LIMITS,
    DEFAULT_HYPERPARAMETERS,
)

__all__ = [
    # Class اصلی
    'ModelManager',
    
    # Constants - Presets
    'TRAINING_PRESETS',
    'LEARNING_STRATEGIES',
    'HYPERPARAMETER_LIMITS',
    'DEFAULT_HYPERPARAMETERS',
]
