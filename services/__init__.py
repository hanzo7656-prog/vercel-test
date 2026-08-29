# services/__init__.py
# ============================================================
# پکیج سرویس‌ها
# ============================================================

from services.prediction_service import prediction_service, PredictionService
from services.training_service import training_service, TrainingService
from services.batch_processor import batch_processor, BatchProcessor

__all__ = [
    'prediction_service',
    'PredictionService',
    'training_service',
    'TrainingService',
    'batch_processor',
    'BatchProcessor'
]
