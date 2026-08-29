# container.py
# ============================================================
# Container - مدیریت وابستگی‌ها (Dependency Injection)
# ============================================================

import logging
from typing import Dict, Any, Optional, Type, Callable

from domain.interfaces.api_client import APIClient
from domain.interfaces.repository import Repository

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
    """
    Container اصلی برای مدیریت وابستگی‌ها (Dependency Injection)
    
    ویژگی‌ها:
        - Singleton Pattern برای دسترسی یکپارچه
        - Lazy Loading برای ایجاد سرویس‌ها در زمان نیاز
        - قابلیت Mock کردن برای تست
    """
    
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
    
    # ============================================================
    # ثبت و دریافت سرویس‌ها
    # ============================================================
    
    def register(self, name: str, service: Any, singleton: bool = True) -> None:
        """
        ثبت یک سرویس در Container
        
        پارامترها:
            name: نام سرویس
            service: نمونه سرویس یا Callable برای ساخت
            singleton: آیا به صورت Singleton باشد؟
        """
        if singleton:
            self._singletons[name] = service
        else:
            self._services[name] = service
        logger.debug(f"✅ Service registered: {name} (singleton: {singleton})")
    
    def get(self, name: str) -> Any:
        """
        دریافت یک سرویس از Container
        
        پارامترها:
            name: نام سرویس
        
        خروجی:
            نمونه سرویس
        
        استثناها:
            KeyError: اگر سرویس ثبت نشده باشد
        """
        # بررسی Singleton
        if name in self._singletons:
            service = self._singletons[name]
            # اگر Callable باشد، اجرا کن
            if callable(service) and not isinstance(service, type):
                service = service()
                self._singletons[name] = service
            return service
        
        # بررسی سرویس عادی
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
        """دریافت کلاینت API"""
        return self.get('api_client')
    
    def cache_manager(self) -> CacheManager:
        """دریافت مدیریت کش"""
        return self.get('cache_manager')
    
    def model_repository(self) -> ModelRepository:
        """دریافت Repository مدل"""
        return self.get('model_repository')
    
    def prediction_repository(self) -> PredictionRepository:
        """دریافت Repository پیش‌بینی"""
        return self.get('prediction_repository')
    
    def auth_manager(self) -> AuthManager:
        """دریافت مدیریت احراز هویت"""
        return self.get('auth_manager')
    
    # ============================================================
    # سرویس‌های لایه Core
    # ============================================================
    
    def feature_engineer(self) -> FeatureEngineer:
        """دریافت مهندس ویژگی"""
        return self.get('feature_engineer')
    
    def model_manager(self) -> ModelManager:
        """دریافت مدیریت مدل"""
        return self.get('model_manager')
    
    def trainer(self) -> AutoTrainer:
        """دریافت آموزش‌دهنده خودکار"""
        return self.get('trainer')
    
    # ============================================================
    # سرویس‌های لایه Application (Use Cases)
    # ============================================================
    
    def predict_use_case(self) -> PredictCoinUseCase:
        """دریافت Use Case پیش‌بینی"""
        return self.get('predict_use_case')
    
    def train_use_case(self) -> TrainModelUseCase:
        """دریافت Use Case آموزش"""
        return self.get('train_use_case')
    
    def health_use_case(self) -> GetHealthUseCase:
        """دریافت Use Case سلامت"""
        return self.get('health_use_case')
    
    # ============================================================
    # سرویس‌های لایه Application (Services)
    # ============================================================
    
    def prediction_service(self) -> PredictionService:
        """دریافت سرویس پیش‌بینی"""
        return self.get('prediction_service')
    
    def monitoring_service(self) -> MonitoringService:
        """دریافت سرویس مانیتورینگ"""
        return self.get('monitoring_service')
    
    # ============================================================
    # سرویس‌های سیستم
    # ============================================================
    
    def metrics_scheduler(self):
        """دریافت Scheduler متریک"""
        return self.get('metrics_scheduler')
    
    def threading_manager(self):
        """دریافت مدیریت Threadها"""
        return self.get('threading_manager')
    
    # ============================================================
    # گزارش وضعیت
    # ============================================================
    
    def get_status(self) -> Dict[str, Any]:
        """دریافت وضعیت Container"""
        return {
            'singletons': list(self._singletons.keys()),
            'services': list(self._services.keys()),
            'total': len(self._singletons) + len(self._services),
            'timestamp': datetime.now().isoformat()
        }


# ============================================================
# ایجاد نمونه و ثبت سرویس‌ها
# ============================================================

from datetime import datetime

container = Container()


def register_services() -> None:
    """
    ثبت همه سرویس‌ها در Container
    این تابع باید در زمان راه‌اندازی برنامه اجرا شود
    """
    
    logger.info("🔄 Registering services...")
    
    # ============================================================
    # ۱. سرویس‌های Infrastructure
    # ============================================================
    
    # API Client (Singleton)
    container.register('api_client', coinstats_client, singleton=True)
    
    # Cache Manager (Singleton)
    container.register('cache_manager', cache_manager, singleton=True)
    
    # Repositories (Singleton)
    container.register('model_repository', ModelRepository, singleton=True)
    container.register('prediction_repository', PredictionRepository, singleton=True)
    
    # Auth Manager (Singleton)
    container.register('auth_manager', auth_manager, singleton=True)
    
    # ============================================================
    # ۲. سرویس‌های Core
    # ============================================================
    
    # Feature Engineer (با وابستگی به API Client)
    def create_feature_engineer():
        return FeatureEngineer(container.api_client())
    container.register('feature_engineer', create_feature_engineer, singleton=True)
    
    # Model Manager (با وابستگی به API Client)
    def create_model_manager():
        return ModelManager(container.api_client())
    container.register('model_manager', create_model_manager, singleton=True)
    
    # Auto Trainer (با وابستگی به API Client و Model Manager)
    def create_trainer():
        return AutoTrainer(container.api_client(), container.model_manager())
    container.register('trainer', create_trainer, singleton=True)
    
    # ============================================================
    # ۳. سرویس‌های Application (Use Cases)
    # ============================================================
    
    # Predict Coin Use Case
    def create_predict_use_case():
        return PredictCoinUseCase(
            api_client=container.api_client(),
            model_manager=container.model_manager(),
            feature_engineer=container.feature_engineer()
        )
    container.register('predict_use_case', create_predict_use_case, singleton=True)
    
    # Train Model Use Case
    def create_train_use_case():
        return TrainModelUseCase(
            api_client=container.api_client(),
            model_manager=container.model_manager(),
            trainer=container.trainer()
        )
    container.register('train_use_case', create_train_use_case, singleton=True)
    
    # Get Health Use Case
    def create_health_use_case():
        return GetHealthUseCase(
            api_client=container.api_client(),
            model_manager=container.model_manager()
        )
    container.register('health_use_case', create_health_use_case, singleton=True)
    
    # ============================================================
    # ۴. سرویس‌های Application (Services)
    # ============================================================
    
    # Prediction Service
    def create_prediction_service():
        return PredictionService(container.predict_use_case())
    container.register('prediction_service', create_prediction_service, singleton=True)
    
    # Monitoring Service
    def create_monitoring_service():
        return MonitoringService(container.health_use_case())
    container.register('monitoring_service', create_monitoring_service, singleton=True)
    
    # ============================================================
    # ۵. سرویس‌های سیستم
    # ============================================================
    
    # Metrics Scheduler
    container.register('metrics_scheduler', metrics_scheduler, singleton=True)
    
    # Threading Manager
    container.register('threading_manager', threading_manager, singleton=True)
    
    logger.info(f"✅ {len(container._singletons) + len(container._services)} services registered")


# اجرای ثبت سرویس‌ها
register_services()
