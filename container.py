# container.py
# ============================================================
# Container - مدیریت وابستگی‌ها (Dependency Injection)
# نسخه ۶.۰ - فقط Gemini (RuleEngine legacy حذف شد)
# ============================================================
# 
# تغییرات نسخه ۶.۰:
#   - model_manager, trainer حذف شدند
#   - predict_use_case, scan_market_use_case حذف شدند
#   - rule_config_repository, model_repository حذف شدند
#   - command_system, self_healer حذف شدند
#   - feature_engineer حذف شد
#   - فقط Gemini + PredictionRouter
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
        logger.info("Container v6.0 initialized (Gemini-only)")
    
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
    # Convenience Methods - Infrastructure
    # ============================================================
    
    def api_client(self) -> Any:
        return self.get('api_client')
    
    def cache_manager(self) -> Any:
        return self.get('cache_manager')
    
    def free_crypto_client(self) -> Any:
        return self.get('free_crypto_client')
    
    def binance_ws_client(self) -> Any:
        return self.get('binance_ws_client')
    
    # ============================================================
    # Convenience Methods - Database
    # ============================================================
    
    def db_factory(self) -> Any:
        return self.get('db_factory')
    
    def quota_manager(self) -> Any:
        return self.get('quota_manager')
    
    def database_registry(self) -> Any:
        return self.get('database_registry')
    
    def database_router(self) -> Any:
        return self.get('database_router')
    
    # ============================================================
    # Convenience Methods - Repositories
    # ============================================================
    
    def repo_container(self) -> Any:
        return self.get('repo_container')
    
    def prediction_repository(self) -> Any:
        return self.get('prediction_repository')
    
    # ⚠️ model_repository, rule_config_repository حذف شدند
    
    # ============================================================
    # Convenience Methods - Core
    # ============================================================
    
    def indicators(self) -> Any:
        return self.get('indicators')
    
    def user_tracker(self) -> Any:
        return self.get('user_tracker')
    
    def price_manager(self) -> Any:
        return self.get('price_manager')
    
    def metrics_scheduler(self) -> Any:
        return self.get('metrics_scheduler')
    
    def threading_manager(self) -> Any:
        return self.get('threading_manager')
    
    # ⚠️ feature_engineer حذف شد
    
    # ============================================================
    # Convenience Methods - AI (Gemini)
    # ============================================================
    
    def gemini_client(self) -> Any:
        return self.get('gemini_client')
    
    def gemini_service(self) -> Any:
        return self.get('gemini_service')
    
    def ai_chat_use_case(self) -> Any:
        return self.get('ai_chat_use_case')
    
    def ai_analyze_image_use_case(self) -> Any:
        return self.get('ai_analyze_image_use_case')
    
    def ai_explain_use_case(self) -> Any:
        return self.get('ai_explain_use_case')
    
    def predict_coin_gemini_use_case(self) -> Any:
        return self.get('predict_coin_gemini_use_case')
    
    def prediction_router(self) -> Any:
        return self.get('prediction_router')
    
    # ============================================================
    # Convenience Methods - Application
    # ============================================================
    
    def prediction_service(self) -> Any:
        return self.get('prediction_service')
    
    def monitoring_service(self) -> Any:
        return self.get('monitoring_service')
    
    def health_use_case(self) -> Any:
        return self.get('health_use_case')
    
    def self_healer(self) -> Any:
        return self.get('self_healer')
        
    def __repr__(self) -> str:
        return f"<Container services={len(self.list_services())}>"


# ============================================================
# Singleton
# ============================================================

container: Container = Container()


# ============================================================
# Register Services
# ============================================================

def register_services() -> None:
    """ثبت همه سرویس‌ها در Container"""
    logger.info("Registering services (Gemini-only)...")
    
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
    container.register('binance_ws_client', get_binance_ws_client, singleton=True)
    
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
    
    def get_prediction_repository():
        from infrastructure.repositories.init_repository import repo_container
        return repo_container.prediction
    
    container.register('repo_container', get_repo_container, singleton=True)
    container.register('prediction_repository', get_prediction_repository, singleton=True)
    
    # ⚠️ model_repository, rule_config_repository حذف شدند
    
    # ============================================================
    # ۴. AI (Gemini)
    # ============================================================
    
    def get_gemini_client():
        from infrastructure.ai.gemini_client import gemini_client
        return gemini_client
    
    def get_gemini_service():
        from infrastructure.ai.gemini_service import gemini_service
        return gemini_service
    
    def get_ai_chat_use_case():
        from application.use_cases.ai_chat import AIChatUseCase
        return AIChatUseCase(
            gemini_service=container.get('gemini_service'),
            price_manager=container.get('price_manager'),
            coinstats_client=container.get('api_client'),
        )
    
    def get_ai_analyze_image_use_case():
        from application.use_cases.ai_analyze_image import AIAnalyzeImageUseCase
        return AIAnalyzeImageUseCase(
            gemini_service=container.get('gemini_service'),
            coinstats_client=container.get('api_client'),
        )
    
    def get_ai_explain_use_case():
        from application.use_cases.ai_explain import AIExplainUseCase
        return AIExplainUseCase(
            gemini_service=container.get('gemini_service'),
            coinstats_client=container.get('api_client'),
        )
    
    def get_predict_coin_gemini_use_case():
        from application.use_cases.predict_coin_gemini import PredictCoinGeminiUseCase
        from infrastructure.database import get_cache
        return PredictCoinGeminiUseCase(
            gemini_service=container.get('gemini_service'),
            api_client=container.get('api_client'),
            cache=get_cache(),
        )
        
    def get_live_agent_use_case():
        from application.use_cases.live_agent_use_case import LiveAgentUseCase
        import os
        api_key = os.getenv("GEMINI_API_KEY", "")
        return LiveAgentUseCase(api_key=api_key)

    container.register('live_agent_use_case', get_live_agent_use_case, singleton=True)
    container.register('gemini_client', get_gemini_client, singleton=True)
    container.register('gemini_service', get_gemini_service, singleton=True)
    container.register('ai_chat_use_case', get_ai_chat_use_case, singleton=True)
    container.register('ai_analyze_image_use_case', get_ai_analyze_image_use_case, singleton=True)
    container.register('ai_explain_use_case', get_ai_explain_use_case, singleton=True)
    container.register('predict_coin_gemini_use_case', get_predict_coin_gemini_use_case, singleton=True)
    
    # ============================================================
    # ۵. Core
    # ============================================================
    
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
    
    container.register('user_tracker', get_user_tracker, singleton=True)
    container.register('price_manager', get_price_manager, singleton=True)
    container.register('indicators', get_indicators, singleton=True)
    
    # ⚠️ feature_engineer حذف شد
    
    # ============================================================
    # ۶. Application - Use Cases
    # ============================================================
    
    def get_health_use_case():
        try:
            from application.use_cases.get_health import GetHealthUseCase
            return GetHealthUseCase(
                api_client=container.get('api_client'),
            )
        except ImportError:
            return None
    
    container.register('health_use_case', get_health_use_case, singleton=True)
    
    # ⚠️ predict_use_case, scan_market_use_case حذف شدند
    
    # ============================================================
    # ۷. Prediction Router (فقط Gemini)
    # ============================================================
    
    def get_prediction_router():
        from application.services.prediction_router import PredictionRouter
        
        try:
            gemini_uc = container.get('predict_coin_gemini_use_case')
        except Exception as e:
            logger.warning(f"⚠️ Gemini use case not available: {e}")
            gemini_uc = None
        
        return PredictionRouter(gemini_use_case=gemini_uc)
    
    container.register('prediction_router', get_prediction_router, singleton=True)
    
    # ============================================================
    # ۸. Application - Services
    # ============================================================
    
    def get_prediction_service():
        from application.services.prediction_service import PredictionService
        
        router = None
        try:
            router = container.get('prediction_router')
        except Exception as e:
            logger.warning(f"⚠️ Prediction router not available: {e}")
        
        return PredictionService(prediction_router=router)
    
    def get_monitoring_service():
        from application.services.monitoring_service import MonitoringService
        return MonitoringService(container.get('health_use_case'))
    
    container.register('prediction_service', get_prediction_service, singleton=True)
    container.register('monitoring_service', get_monitoring_service, singleton=True)s


    # ============================================================
    # ۸.b SelfHealer (Gemini-aware) 🆕
    # ============================================================

    def get_self_healer():
        from application.services.self_healer import SelfHealer
        return SelfHealer(
            api_client=container.get('api_client'),
        )

    container.register('self_healer', get_self_healer, singleton=True)
    # ============================================================
    # ۹. System
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
    
    logger.info(f"{len(container.list_services())} services registered (Gemini-only)")


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

    # ۳. Binance WS Client
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
    
    # ۴. Gemini warmup
    try:
        gemini = container.get('gemini_client')
        if gemini and gemini.is_available:
            logger.info("✅ Gemini client ready")
        else:
            logger.warning("⚠️ Gemini client NOT available (check GEMINI_API_KEY)")
    except Exception as e:
        logger.warning(f"⚠️ Gemini warmup skipped: {e}")
    
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

    # ۲. Binance WS Client
    try:
        binance_ws = container.get('binance_ws_client')
        if binance_ws and hasattr(binance_ws, 'stop'):
            binance_ws.stop()
            print("[Container] ✅ BinanceWSClient stopped", flush=True)
    except Exception as e:
        print(f"[Container] ❌ BinanceWSClient stop failed: {e}", flush=True)
 
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
