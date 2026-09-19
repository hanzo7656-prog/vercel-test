# container.py
# ============================================================
# Container - مدیریت وابستگی‌ها (Dependency Injection)
# نسخه ۳.۱ - Repository + Database + Lifecycle + Convenience
# ============================================================

import os
import logging
from typing import Dict, Any, Optional, List, Callable
from datetime import datetime

logger = logging.getLogger(__name__)


# ============================================================
# Container
# ============================================================

class Container:
    """
    Container اصلی برای مدیریت وابستگی‌ها
    
    ویژگی‌ها:
        - Singleton
        - Lazy loading
        - Service lifecycle
        - Error handling
        - Status reporting
        - Convenience methods
    """
    
    _instance: Optional['Container'] = None
    _singletons: Dict[str, Any] = {}
    _services: Dict[str, Callable] = {}
    _init_time: Optional[datetime] = None
    
    def __new__(cls) -> 'Container':
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self) -> None:
        if hasattr(self, '_initialized'):
            return
        self._initialized = True
        self._init_time = datetime.now()
        logger.info("Container v3.1 initialized")
    
    # ============================================================
    # Register
    # ============================================================
    
    def register(
        self,
        name: str,
        service: Any,
        singleton: bool = True,
    ) -> None:
        """ثبت یک سرویس"""
        if singleton:
            self._singletons[name] = service
        else:
            self._services[name] = service
        
        logger.debug(f"Service registered: {name}")
    
    # ============================================================
    # Get
    # ============================================================
    
    def get(self, name: str) -> Any:
        """دریافت یک سرویس"""
        # Singleton
        if name in self._singletons:
            service = self._singletons[name]
            
            if callable(service) and not isinstance(service, type):
                try:
                    service = service()
                    self._singletons[name] = service
                except Exception as e:
                    logger.error(f"Failed to create '{name}': {e}")
                    raise
            
            return service
        
        # Non-singleton
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
        logger.info("Container cleared")
    
    def list_services(self) -> List[str]:
        """لیست همه سرویس‌ها"""
        return sorted(set(self._singletons.keys()) | set(self._services.keys()))
    
    # ============================================================
    # Status
    # ============================================================
    
    def get_status(self) -> Dict[str, Any]:
        """دریافت وضعیت Container"""
        return {
            "initialized": True,
            "init_time": self._init_time.isoformat() if self._init_time else None,
            "singletons_count": len(self._singletons),
            "services_count": len(self._services),
            "total": len(self.list_services()),
            "services": self.list_services(),
            "timestamp": datetime.now().isoformat(),
        }
    
    # ============================================================
    # Convenience Methods (برای سازگاری با api_routes.py)
    # ============================================================
    
    def api_client(self) -> Any:
        """دریافت API client"""
        return self.get('api_client')
    
    def cache_manager(self) -> Any:
        """دریافت cache manager"""
        return self.get('cache_manager')
    
    def model_manager(self) -> Any:
        """دریافت ModelManager"""
        return self.get('model_manager')
    
    def trainer(self) -> Any:
        """دریافت AutoTrainer"""
        return self.get('trainer')
    
    def prediction_service(self) -> Any:
        """دریافت PredictionService"""
        return self.get('prediction_service')
    
    def monitoring_service(self) -> Any:
        """دریافت MonitoringService"""
        return self.get('monitoring_service')
    
    def command_system(self) -> Any:
        """دریافت CommandSystem"""
        return self.get('command_system')
    
    def self_healer(self) -> Any:
        """دریافت SelfHealer"""
        return self.get('self_healer')
    
    def price_manager(self) -> Any:
        """دریافت PriceManager"""
        return self.get('price_manager')
    
    def user_tracker(self) -> Any:
        """دریافت UserTracker"""
        return self.get('user_tracker')
    
    def metrics_scheduler(self) -> Any:
        """دریافت MetricsScheduler"""
        return self.get('metrics_scheduler')
    
    def threading_manager(self) -> Any:
        """دریافت ThreadingManager"""
        return self.get('threading_manager')
    
    def feature_engineer(self) -> Any:
        """دریافت FeatureEngineer"""
        return self.get('feature_engineer')
    
    def indicators(self) -> Any:
        """دریافت indicators"""
        return self.get('indicators')
    
    def free_crypto_client(self) -> Any:
        """دریافت FreeCryptoClient"""
        return self.get('free_crypto_client')
    
    def db_factory(self) -> Any:
        """دریافت DatabaseFactory"""
        return self.get('db_factory')
    
    def quota_manager(self) -> Any:
        """دریافت QuotaManager"""
        return self.get('quota_manager')
    
    def database_registry(self) -> Any:
        """دریافت DatabaseRegistry"""
        return self.get('database_registry')
    
    def database_router(self) -> Any:
        """دریافت DatabaseRouter"""
        return self.get('database_router')
    
    def repo_container(self) -> Any:
        """دریافت RepositoryContainer"""
        return self.get('repo_container')
    
    def model_repository(self) -> Any:
        """دریافت ModelRepository"""
        return self.get('model_repository')
    
    def prediction_repository(self) -> Any:
        """دریافت PredictionRepository"""
        return self.get('prediction_repository')
    
    def predict_use_case(self) -> Any:
        """دریافت PredictUseCase"""
        return self.get('predict_use_case')
    
    def train_use_case(self) -> Any:
        """دریافت TrainUseCase"""
        return self.get('train_use_case')
    
    def health_use_case(self) -> Any:
        """دریافت HealthUseCase"""
        return self.get('health_use_case')
    
    def __repr__(self) -> str:
        return f"<Container services={len(self.list_services())}>"


    def binance_ws_client(self) -> Any:
        """دریافت Binance WS Client"""
        return self.get('binance_ws_client')

# ============================================================
# Singleton
# ============================================================

container: Container = Container()


# ============================================================
# Register Services
# ============================================================

def register_services() -> None:
    """ثبت همه سرویس‌ها در Container"""
    logger.info("Registering services...")
    
    # ============================================================
    # ۱. Infrastructure
    # ============================================================
    
    def get_api_client():
        from infrastructure.api.coinstats_client import coinstats_client
        return coinstats_client
    
    def get_cache_manager():
        from infrastructure.api.cache_manager import cache_manager
        return cache_manager
    
    def create_free_crypto_client():
        from infrastructure.api.free_crypto_client import create_free_crypto_client as _create
        
        api_key = os.getenv("FREE_CRYPTO_API_KEY", "569szrll2wmheybya6dx")
        client = _create(api_key)
        logger.info("FreeCryptoClient created")
        return client

    def get_binance_ws_client():
        from infrastructure.api.binance_ws_client import binance_ws_client
        return binance_ws_client
        
    container.register('api_client', get_api_client, singleton=True)
    container.register('cache_manager', get_cache_manager, singleton=True)
    container.register('free_crypto_client', create_free_crypto_client, singleton=True)
    container.register('binance_ws_client', get_binance_ws_client, singleton=True)  # 🆕
    # ============================================================
    # ۲. Database
    # ============================================================
    
    def get_db_factory():
        from infrastructure.database.database_factory import db_factory
        return db_factory
    
    def get_quota_manager():
        from infrastructure.database.quota_manager import quota_manager
        return quota_manager
    
    def get_database_registry():
        from infrastructure.database.registry import registry
        return registry
    
    def get_database_router():
        from infrastructure.database.router import router
        return router
    
    container.register('db_factory', get_db_factory, singleton=True)
    container.register('quota_manager', get_quota_manager, singleton=True)
    container.register('database_registry', get_database_registry, singleton=True)
    container.register('database_router', get_database_router, singleton=True)
    
    # ============================================================
    # ۳. Repository
    # ============================================================
    
    def get_repo_container():
        from infrastructure.repositories.init_repository import repo_container
        return repo_container
    
    def get_model_repository():
        from infrastructure.repositories.init_repository import repo_container
        return repo_container.model
    
    def get_prediction_repository():
        from infrastructure.repositories.init_repository import repo_container
        return repo_container.prediction
    
    container.register('repo_container', get_repo_container, singleton=True)
    container.register('model_repository', get_model_repository, singleton=True)
    container.register('prediction_repository', get_prediction_repository, singleton=True)
    
    # ============================================================
    # ۴. Model
    # ============================================================
    
    def get_model_manager():
        from models.manager.model_manager import ModelManager
        return ModelManager(container.get('api_client'))
    
    def get_trainer():
        from models.trainer.auto_trainer import AutoTrainer
        return AutoTrainer(
            api=container.get('api_client'),
            model_manager=container.get('model_manager'),
        )
    
    container.register('model_manager', get_model_manager, singleton=True)
    container.register('trainer', get_trainer, singleton=True)
    
    # ============================================================
    # ۵. Core
    # ============================================================
    
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
        )
    
    def get_indicators():
        from core.indicators import (
            get_all_indicators,
            calculate_rsi,
            calculate_sma,
            calculate_ema,
            calculate_macd,
        )
        return {
            'get_all_indicators': get_all_indicators,
            'calculate_rsi': calculate_rsi,
            'calculate_sma': calculate_sma,
            'calculate_ema': calculate_ema,
            'calculate_macd': calculate_macd,
        }
    
    container.register('feature_engineer', get_feature_engineer, singleton=True)
    container.register('user_tracker', get_user_tracker, singleton=True)
    container.register('price_manager', get_price_manager, singleton=True)
    container.register('indicators', get_indicators, singleton=True)
    
    # ============================================================
    # ۶. Application
    # ============================================================
    
    def get_predict_use_case():
        from application.use_cases.predict_coin import PredictCoinUseCase
        return PredictCoinUseCase(
            api_client=container.get('api_client'),
            model_manager=container.get('model_manager'),
            feature_engineer=container.get('feature_engineer'),
        )
    
    def get_train_use_case():
        from application.use_cases.train_model import TrainModelUseCase
        return TrainModelUseCase(
            api_client=container.get('api_client'),
            model_manager=container.get('model_manager'),
            trainer=container.get('trainer'),
        )
    
    def get_health_use_case():
        try:
            from application.use_cases.get_health import GetHealthUseCase
            return GetHealthUseCase(
                api_client=container.get('api_client'),
                model_manager=container.get('model_manager'),
            )
        except ImportError:
            return None
    
    def get_prediction_service():
        from application.services.prediction_service import PredictionService
        return PredictionService(container.get('predict_use_case'))
    
    def get_monitoring_service():
        from application.services.monitoring_service import MonitoringService
        return MonitoringService(container.get('health_use_case'))
    
    def get_command_system():
        try:
            from application.services.command_system import CommandSystem
            from domain.services.numeric_analyzer import NumericAnalyzer
            analyzer = NumericAnalyzer(container.get('api_client'))
            return CommandSystem(analyzer)
        except ImportError:
            return None
    
    def get_self_healer():
        from application.services.self_healer import SelfHealer
        return SelfHealer(
            model_manager=container.get('model_manager'),
            trainer=container.get('trainer'),
            api_client=container.get('api_client'),
        )
    
    container.register('predict_use_case', get_predict_use_case, singleton=True)
    container.register('train_use_case', get_train_use_case, singleton=True)
    container.register('health_use_case', get_health_use_case, singleton=True)
    container.register('prediction_service', get_prediction_service, singleton=True)
    container.register('monitoring_service', get_monitoring_service, singleton=True)
    container.register('command_system', get_command_system, singleton=True)
    container.register('self_healer', get_self_healer, singleton=True)
    
    # ============================================================
    # ۷. System
    # ============================================================
    
    def get_metrics_scheduler():
        from core.metrics import metrics_scheduler
        return metrics_scheduler
    
    def get_threading_manager():
        from core.threading_manager import threading_manager
        return threading_manager
    
    container.register('metrics_scheduler', get_metrics_scheduler, singleton=True)
    container.register('threading_manager', get_threading_manager, singleton=True)
    
    # ============================================================
    # Summary
    # ============================================================
    
    logger.info(f"{len(container.list_services())} services registered")


# ============================================================
# Start/Stop Services
# ============================================================

def start_services() -> None:
    """شروع سرویس‌های پس‌زمینه"""
    logger.info("Starting background services...")
    
    # ۱. FreeCryptoClient
    try:
        free_client = container.get('free_crypto_client')
        if free_client:
            logger.info("FreeCryptoClient started")
    except Exception as e:
        logger.error(f"FreeCryptoClient start failed: {e}")
    
    # ۲. PriceManager
    try:
        price_manager = container.get('price_manager')
        if price_manager and hasattr(price_manager, 'start'):
            price_manager.start()
            logger.info("PriceManager started")
    except Exception as e:
        logger.error(f"PriceManager start failed: {e}")

    # ۳. Binance WS Client 🆕
    try:
        binance_ws = container.get('binance_ws_client')
        if binance_ws and hasattr(binance_ws, 'start'):
            result = binance_ws.start()
            if result:
                logger.info("✅ BinanceWSClient started")
            else:
                logger.warning("⚠️ BinanceWSClient start() returned False")
    except Exception as e:
        logger.error(f"❌ BinanceWSClient start failed: {e}")
    logger.info("✅ Background services started")
    

def stop_services() -> None:
    """توقف سرویس‌های پس‌زمینه"""
    logger.info("Stopping background services...")
    
    # ۱. PriceManager
    try:
        price_manager = container.get('price_manager')
        if price_manager and hasattr(price_manager, 'stop'):
            price_manager.stop()
            logger.info("PriceManager stopped")
    except Exception as e:
        logger.error(f"PriceManager stop failed: {e}")


    # ۲. Binance WS Client 🆕
    try:
        binance_ws = container.get('binance_ws_client')
        if binance_ws and hasattr(binance_ws, 'stop'):
            binance_ws.stop()
            logger.info("✅ BinanceWSClient stopped")
    except Exception as e:
        logger.error(f"❌ BinanceWSClient stop failed: {e}")
 
    # ۳. FreeCryptoClient
    try:
        free_client = container.get('free_crypto_client')
        if free_client and hasattr(free_client, 'stop'):
            free_client.stop()
            logger.info("FreeCryptoClient stopped")
    except Exception as e:
        logger.error(f"FreeCryptoClient stop failed: {e}")
    
    logger.info("All background services stopped")


# ============================================================
# Auto-register
# ============================================================

register_services()
