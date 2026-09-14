# container.py
# ============================================================
# Container - مدیریت وابستگی‌ها (Dependency Injection)
# نسخه ۳.۰ - Repository + Database + Lifecycle
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
    
    ارتقاها:
        - Repositoryها
        - Database factory
        - Quota manager
        - Service lifecycle
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
        logger.info("✅ Container v3.0 initialized")
    
    # ============================================================
    # Register
    # ============================================================
    
    def register(
        self,
        name: str,
        service: Any,
        singleton: bool = True,
    ) -> None:
        """
        ثبت یک سرویس
        
        پارامترها:
            name: نام سرویس
            service: نمونه یا factory function
            singleton: singleton باشه؟
        """
        if singleton:
            # اگه callable بود، ذخیره می‌کنیم تا بعداً صدا بزنیم
            self._singletons[name] = service
        else:
            self._services[name] = service
        
        logger.debug(f"✅ Service registered: {name}")
    
    # ============================================================
    # Get
    # ============================================================
    
    def get(self, name: str) -> Any:
        """
        دریافت یک سرویس
        
        پارامترها:
            name: نام سرویس
        
        خروجی:
            نمونه سرویس
        
        استثناها:
            KeyError: اگه سرویس نباشه
        """
        # Singleton
        if name in self._singletons:
            service = self._singletons[name]
            
            # اگه callable هست و هنوز ساخته نشده
            if callable(service) and not isinstance(service, type):
                try:
                    service = service()
                    self._singletons[name] = service
                except Exception as e:
                    logger.error(f"❌ Failed to create '{name}': {e}")
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
        logger.info("🧹 Container cleared")
    
    def list_services(self) -> List[str]:
        """لیست همه سرویس‌ها"""
        return sorted(set(self._singletons.keys()) | set(self._services.keys()))
    
    # ============================================================
    # Status
    # ============================================================
    
    def get_status(self) -> Dict[str, Any]:
        """
        دریافت وضعیت Container
        
        خروجی:
            دیکشنری وضعیت
        """
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
# Singleton
# ============================================================

container: Container = Container()


# ============================================================
# Register Services
# ============================================================

def register_services() -> None:
    """
    ثبت همه سرویس‌ها در Container
    
    ترتیب:
        ۱. Infrastructure
        ۲. Database
        ۳. Repository
        ۴. Model
        ۵. Core
        ۶. Application
        ۷. System
    """
    logger.info("🔄 Registering services...")
    
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
        """ایجاد FreeCryptoClient"""
        from infrastructure.api.free_crypto_client import create_free_crypto_client as _create
        
        api_key = os.getenv("FREE_CRYPTO_API_KEY", "569szrll2wmheybya6dx")
        client = _create(api_key)
        logger.info("✅ FreeCryptoClient created")
        return client
    
    container.register('api_client', get_api_client, singleton=True)
    container.register('cache_manager', get_cache_manager, singleton=True)
    container.register('free_crypto_client', create_free_crypto_client, singleton=True)
    
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
    # ۳. Repository 🆕
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
            update_interval=10,
            fallback_interval=60,
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
    # ۶. Application 🆕
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
    
    logger.info(
        f"✅ {len(container.list_services())} services registered"
    )
    logger.debug(f"   Services: {container.list_services()}")


# ============================================================
# Start Services
# ============================================================

def start_services() -> None:
    """
    شروع سرویس‌های پس‌زمینه
    
    - FreeCryptoClient
    - PriceManager
    """
    logger.info("🚀 Starting background services...")
    
    # ۱. FreeCryptoClient
    try:
        free_client = container.get('free_crypto_client')
        if free_client:
            logger.info("✅ FreeCryptoClient started")
    except Exception as e:
        logger.error(f"❌ FreeCryptoClient start failed: {e}")
    
    # ۲. PriceManager
    try:
        price_manager = container.get('price_manager')
        if price_manager and hasattr(price_manager, 'start'):
            price_manager.start()
            logger.info("✅ PriceManager started")
    except Exception as e:
        logger.error(f"❌ PriceManager start failed: {e}")
    
    logger.info("✅ Background services started")


# ============================================================
# Stop Services
# ============================================================

def stop_services() -> None:
    """
    توقف سرویس‌های پس‌زمینه
    """
    logger.info("⏹️ Stopping background services...")
    
    # ۱. PriceManager
    try:
        price_manager = container.get('price_manager')
        if price_manager and hasattr(price_manager, 'stop'):
            price_manager.stop()
            logger.info("✅ PriceManager stopped")
    except Exception as e:
        logger.error(f"❌ PriceManager stop failed: {e}")
    
    # ۲. FreeCryptoClient
    try:
        free_client = container.get('free_crypto_client')
        if free_client and hasattr(free_client, 'stop'):
            free_client.stop()
            logger.info("✅ FreeCryptoClient stopped")
    except Exception as e:
        logger.error(f"❌ FreeCryptoClient stop failed: {e}")
    
    # ۳. Metrics Scheduler
    try:
        metrics = container.get('metrics_scheduler')
        if metrics and hasattr(metrics, 'stop'):
            metrics.stop()
            logger.info("✅ MetricsScheduler stopped")
    except Exception as e:
        logger.error(f"❌ MetricsScheduler stop failed: {e}")
    
    # ۴. Threading Manager
    try:
        threading = container.get('threading_manager')
        if threading and hasattr(threading, 'stop_all'):
            threading.stop_all()
            logger.info("✅ ThreadingManager stopped")
    except Exception as e:
        logger.error(f"❌ ThreadingManager stop failed: {e}")
    
    logger.info("⏹️ All background services stopped")


# ============================================================
# Auto-register on import
# ============================================================

register_services()
