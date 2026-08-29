# container.py
# ============================================================
# Container - مدیریت وابستگی‌ها (Dependency Injection)
# ============================================================

import logging
from typing import Dict, Any, Optional

from domain.interfaces.api_client import APIClient

# ✅ Import مستقیم از مسیرهای درست (بدون Circular Import)
from infrastructure.api.coinstats_client import coinstats_client, CoinStatsClient
from infrastructure.api.cache_manager import cache_manager, CacheManager
from infrastructure.database import get_primary, get_cache, get_backup
from infrastructure.repositories.model_repository import ModelRepository
from infrastructure.repositories.prediction_repository import PredictionRepository
from infrastructure.auth.auth_manager import auth_manager, AuthManager

from core.feature_engineering import FeatureEngineer
from core.metrics import metrics_scheduler
from core.threading_manager import threading_manager

from models.manager.model_manager import ModelManager
from models.trainer.auto_trainer import AutoTrainer

from application.use_cases.predict_coin import PredictCoinUseCase
from application.use_cases.train_model import TrainModelUseCase
from application.use_cases.get_health import GetHealthUseCase
from application.services.prediction_service import PredictionService
from application.services.monitoring_service import MonitoringService

logger = logging.getLogger(__name__)


class Container:
    """Container اصلی برای مدیریت وابستگی‌ها (Dependency Injection)"""
    
    _instance = None
    _services: Dict[str, Any] = {}
    _singletons: Dict[str, Any] = {}
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self) -> None:
        if not hasattr(self, '_initialized'):
            self._initialized = True
            self._services = {}
            self._singletons = {}
            logger.info("✅ Container initialized")
    
    def register(self, name: str, service: Any, singleton: bool = True) -> None:
        """ثبت یک سرویس در Container"""
        if singleton:
            self._singletons[name] = service
        else:
            self._services[name] = service
        logger.debug(f"✅ Service registered: {name} (singleton: {singleton})")
    
    def get(self, name: str) -> Any:
        """دریافت یک سرویس از Container"""
        if name in self._singletons:
            service = self._singletons[name]
            if callable(service) and not isinstance(service, type):
                service = service()
                self._singletons[name] = service
            return service
        
        if name in self._services:
            service = self._services[name]
            if callable(service):
                return service()
            return service
        
        raise KeyError(f"Service '{name}' not found in container")
    
    def has(self, name: str) -> bool:
        """بررسی وجود سرویس"""
        return name in self._singletons or name in self._services
    
    def clear(self) -> None:
        """پاک کردن همه سرویس‌ها"""
        self._singletons.clear()
        self._services.clear()
        logger.info("🧹 Container cleared")
    
    # ============================================================
    # سرویس‌های لایه Infrastructure
    # ============================================================
    
    def api_client(self) -> APIClient:
        return self.get('api_client')
    
    def cache_manager(self) -> CacheManager:
        return self.get('cache_manager')
    
    def model_repository(self) -> ModelRepository:
        return self.get('model_repository')
    
    def prediction_repository(self) -> PredictionRepository:
        return self.get('prediction_repository')
    
    def auth_manager(self) -> AuthManager:
        return self.get('auth_manager')
    
    # ============================================================
    # سرویس‌های لایه Core
    # ============================================================
    
    def feature_engineer(self) -> FeatureEngineer:
        return self.get('feature_engineer')
    
    def model_manager(self) -> ModelManager:
        return self.get('model_manager')
    
    def trainer(self) -> AutoTrainer:
        return self.get('trainer')
    
    # ============================================================
    # سرویس‌های لایه Application
    # ============================================================
    
    def predict_use_case(self) -> PredictCoinUseCase:
        return self.get('predict_use_case')
    
    def train_use_case(self) -> TrainModelUseCase:
        return self.get('train_use_case')
    
    def health_use_case(self) -> GetHealthUseCase:
        return self.get('health_use_case')
    
    def prediction_service(self) -> PredictionService:
        return self.get('prediction_service')
    
    def monitoring_service(self) -> MonitoringService:
        return self.get('monitoring_service')
    
    # ============================================================
    # سرویس‌های سیستم
    # ============================================================
    
    def metrics_scheduler(self):
        return self.get('metrics_scheduler')
    
    def threading_manager(self):
        return self.get('threading_manager')
    
    def get_status(self) -> Dict[str, Any]:
        """دریافت وضعیت Container"""
        from datetime import datetime
        return {
            'singletons': list(self._singletons.keys()),
            'services': list(self._services.keys()),
            'total': len(self._singletons) + len(self._services),
            'timestamp': datetime.now().isoformat()
        }


# ============================================================
# ایجاد نمونه و ثبت سرویس‌ها
# ============================================================

container = Container()


def register_services() -> None:
    """ثبت همه سرویس‌ها در Container"""
    logger.info("🔄 Registering services...")
    
    # ============================================================
    # ۱. سرویس‌های Infrastructure
    # ============================================================
    container.register('api_client', coinstats_client, singleton=True)
    container.register('cache_manager', cache_manager, singleton=True)
    container.register('model_repository', ModelRepository, singleton=True)
    container.register('prediction_repository', PredictionRepository, singleton=True)
    container.register('auth_manager', auth_manager, singleton=True)
    
    # ============================================================
    # ۲. سرویس‌های Core (با Lazy Loading)
    # ============================================================
    def create_feature_engineer():
        return FeatureEngineer(container.api_client())
    container.register('feature_engineer', create_feature_engineer, singleton=True)
    
    def create_model_manager():
        return ModelManager(container.api_client())
    container.register('model_manager', create_model_manager, singleton=True)
    
    def create_trainer():
        return AutoTrainer(container.api_client(), container.model_manager())
    container.register('trainer', create_trainer, singleton=True)
    
    # ============================================================
    # ۳. سرویس‌های Application
    # ============================================================
    def create_predict_use_case():
        return PredictCoinUseCase(
            api_client=container.api_client(),
            model_manager=container.model_manager(),
            feature_engineer=container.feature_engineer()
        )
    container.register('predict_use_case', create_predict_use_case, singleton=True)
    
    def create_train_use_case():
        return TrainModelUseCase(
            api_client=container.api_client(),
            model_manager=container.model_manager(),
            trainer=container.trainer()
        )
    container.register('train_use_case', create_train_use_case, singleton=True)
    
    def create_health_use_case():
        return GetHealthUseCase(
            api_client=container.api_client(),
            model_manager=container.model_manager()
        )
    container.register('health_use_case', create_health_use_case, singleton=True)
    
    def create_prediction_service():
        return PredictionService(container.predict_use_case())
    container.register('prediction_service', create_prediction_service, singleton=True)
    
    def create_monitoring_service():
        return MonitoringService(container.health_use_case())
    container.register('monitoring_service', create_monitoring_service, singleton=True)
    
    # ============================================================
    # ۴. سرویس‌های سیستم
    # ============================================================
    container.register('metrics_scheduler', metrics_scheduler, singleton=True)
    container.register('threading_manager', threading_manager, singleton=True)
    
    logger.info(f"✅ {len(container._singletons) + len(container._services)} services registered")


# اجرای ثبت سرویس‌ها
register_services()
