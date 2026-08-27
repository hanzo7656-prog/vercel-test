# models/trainer/__init__.py
# ============================================================
# پکیج آموزش مدل
# ============================================================

from models.trainer.auto_trainer import AutoTrainer
from models.trainer.manual_trainer import train_model

__all__ = [
    'AutoTrainer',
    'train_model'
]
