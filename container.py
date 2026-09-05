# container.py
# ============================================================
# Container - مدیریت وابستگی‌ها (Dependency Injection)
# ============================================================

import os
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class Container:
    """Container اصلی برای مدیریت وابستگی‌ها"""
    
    _instance = None
    _singletons: Dict[str, Any] = {}
    _services: Dict[str, Any] = {}
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not hasattr(self, '_initialized'):
            self._initialized = True
            logger.info("✅ Container initialized")
    
    def register(self, name: str, service: Any, singleton: bool = True) -> None:
        """ثبت سرویس در Container"""
        if singleton:
            self._singletons[name] = service
        else:
            self._services[name] = service
        logger.debug(f"✅ Service registered: {name}")
    
    def get(self, name: str) -> Any:
        """دریافت سرویس از Container"""
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
# نمونه Container
# ============================================================

container = Container()


def register_services() -> None:
    """ثبت همه سرویس‌ها در Container (با Lazy Import)"""
    logger.info("🔄 Registering services...")
    
    # ============================================================
    # ۱. سرویس‌های Infrastructure
    # ============================================================
    
    def get_api_client():
        from infrastructure.api.coinstats_client import coinstats_client
        return coinstats_client
    
    def get_cache_manager():
        from infrastructure.api.cache_manager import cache_manager
        return cache_manager
    
    def get_free_crypto_client():
        from infrastructure.api.free_crypto_client import create_free_crypto_client
        api_key = os.getenv("FREE_CRYPTO_API_KEY", "569szrll2wmheybya6dx")
        return create_free_crypto_client(api_key)
    
    container.register('api_client', get_api_client, singleton=True)
    container.register('cache_manager', get_cache_manager, singleton=True)
    container.register('free_crypto_client', get_free_crypto_client, singleton=True)
    
    # ============================================================
    # ۲. سرویس‌های Core
    # ============================================================
    
    def get_model_manager():
        from models.manager.model_manager import ModelManager
        return ModelManager(container.get('api_client'))
    
    def get_feature_engineer():
        from core.feature_engineering import FeatureEngineer
        return FeatureEngineer(container.get('api_client'))
    
    def get_user_tracker():
        from core.user_tracker import UserTracker
        return UserTracker(timeout=30)
    
    def get_price_manager():
        from core.price_manager import PriceManager
        from infrastructure.database import get_cache
        return PriceManager(
            free_client=container.get('free_crypto_client'),
            user_tracker=container.get('user_tracker'),
            cache=get_cache(),
            update_interval=10,
            fallback_interval=60
        )
    
    container.register('model_manager', get_model_manager, singleton=True)
    container.register('feature_engineer', get_feature_engineer, singleton=True)
    container.register('user_tracker', get_user_tracker, singleton=True)
    container.register('price_manager', get_price_manager, singleton=True)
    
    # ============================================================
    # ۳. سرویس‌های Application
    # ============================================================
    
    def get_predict_use_case():
        from application.use_cases.predict_coin import PredictCoinUseCase
        return PredictCoinUseCase(
            api_client=container.get('api_client'),
            model_manager=container.get('model_manager'),
            feature_engineer=container.get('feature_engineer')
        )
    
    def get_train_use_case():
        from application.use_cases.train_model import TrainModelUseCase
        from models.trainer.auto_trainer import AutoTrainer
        return TrainModelUseCase(
            api_client=container.get('api_client'),
            model_manager=container.get('model_manager'),
            trainer=AutoTrainer(
                api=container.get('api_client'),
                model_manager=container.get('model_manager')
            )
        )
    
    def get_health_use_case():
        from application.use_cases.get_health import GetHealthUseCase
        return GetHealthUseCase(
            api_client=container.get('api_client'),
            model_manager=container.get('model_manager')
        )
    
    def get_prediction_service():
        from application.services.prediction_service import PredictionService
        return PredictionService(container.get('predict_use_case'))
    
    def get_monitoring_service():
        from application.services.monitoring_service import MonitoringService
        return MonitoringService(container.get('health_use_case'))
    
    container.register('predict_use_case', get_predict_use_case, singleton=True)
    container.register('train_use_case', get_train_use_case, singleton=True)
    container.register('health_use_case', get_health_use_case, singleton=True)
    container.register('prediction_service', get_prediction_service, singleton=True)
    container.register('monitoring_service', get_monitoring_service, singleton=True)
    
    # ============================================================
    # ۴. سرویس‌های سیستم
    # ============================================================
    
    def get_metrics_scheduler():
        from core.metrics import metrics_scheduler
        return metrics_scheduler
    
    def get_threading_manager():
        from core.threading_manager import threading_manager
        return threading_manager
    
    container.register('metrics_scheduler', get_metrics_scheduler, singleton=True)
    container.register('threading_manager', get_threading_manager, singleton=True)
    
    logger.info(f"✅ {len(container._singletons) + len(container._services)} services registered")


# ============================================================
# شروع و توقف سرویس‌ها
# ============================================================

def start_services() -> None:
    """شروع همه سرویس‌های پس‌زمینه"""
    logger.info("🚀 Starting background services...")
    
    try:
        free_client = container.get('free_crypto_client')
        logger.info("✅ FreeCryptoClient started")
    except Exception as e:
        logger.error(f"❌ Failed to start FreeCryptoClient: {e}")
    
    try:
        price_manager = container.get('price_manager')
        if hasattr(price_manager, 'start'):
            price_manager.start()
            logger.info("✅ PriceManager started")
    except Exception as e:
        logger.error(f"❌ Failed to start PriceManager: {e}")
    
    logger.info("🚀 All background services started")


def stop_services() -> None:
    """توقف همه سرویس‌های پس‌زمینه"""
    logger.info("⏹️ Stopping background services...")
    
    try:
        price_manager = container.get('price_manager')
        if price_manager and hasattr(price_manager, 'stop'):
            price_manager.stop()
    except Exception as e:
        logger.error(f"❌ Error stopping PriceManager: {e}")
    
    try:
        free_client = container.get('free_crypto_client')
        if free_client and hasattr(free_client, 'stop'):
            free_client.stop()
    except Exception as e:
        logger.error(f"❌ Error stopping FreeCryptoClient: {e}")
    
    logger.info("⏹️ All background services stopped")


# ============================================================
# ثبت سرویس‌ها
# ============================================================

register_services()
