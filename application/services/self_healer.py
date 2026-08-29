# application/services/self_healer.py
# ============================================================
# سیستم خودترمیمی - نسخه ۴.۰ (انتقال به Application)
# ============================================================

import os
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Union

from domain.interfaces.api_client import APIClient
from models.manager.model_manager import ModelManager
from models.trainer.auto_trainer import AutoTrainer
from infrastructure.database import get_cache

logger = logging.getLogger(__name__)


class SelfHealer:
    """
    سیستم خودترمیمی - نسخه ۴.۰
    
    ویژگی‌ها:
        - بازگشت به نسخه قبلی مدل در صورت افت دقت
        - پاک‌سازی خودکار کش
        - ری‌استارت ماژول‌ها (با reconnect)
        - یکپارچه با Metrics Scheduler
    
    ✅ نسخه ۴.۰: انتقال به لایه Application
    ✅ Type Hints کامل
    ✅ استفاده از Container
    """
    
    def __init__(
        self,
        model_manager: ModelManager,
        trainer: AutoTrainer,
        api_client: Optional[APIClient] = None
    ) -> None:
        """
        راه‌اندازی سیستم خودترمیمی
        
        پارامترها:
            model_manager: مدیریت مدل
            trainer: آموزش‌دهنده خودکار
            api_client: کلاینت API (اختیاری)
        """
        self.model_manager: ModelManager = model_manager
        self.trainer: AutoTrainer = trainer
        self.api_client: Optional[APIClient] = api_client
        
        self.healing_attempts: Dict[str, Dict[str, Union[int, str]]] = {}
        self.max_attempts: int = 3
        self.cooldown_minutes: int = 30
        
        logger.info("✅ SelfHealer v4.0 initialized (with Type Hints)")
    
    def _get_metrics_from_scheduler(self) -> Dict[str, Any]:
        """
        دریافت متریک‌ها از Scheduler
        
        خروجی:
            دیکشنری متریک‌ها
        """
        try:
            from core.metrics import metrics_scheduler
            return metrics_scheduler.get_alert_metrics()
        except ImportError:
            logger.warning("⚠️ Metrics Scheduler not available, using fallback")
            return self._get_fallback_metrics()
        except Exception as e:
            logger.error(f"❌ Error getting metrics from scheduler: {e}")
            return self._get_fallback_metrics()
    
    def _get_fallback_metrics(self) -> Dict[str, Any]:
        """
        Fallback در صورت عدم دسترسی به Scheduler
        
        خروجی:
            دیکشنری متریک‌های پیش‌فرض
        """
        return {
            "cpu": 0,
            "ram": 0,
            "api_status": "unknown",
            "model_loaded": False,
            "model_accuracy": None,
            "databases": {"postgresql": False, "redis": False, "sqlite": False}
        }
    
    def check_and_heal(self, metrics: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        بررسی و اجرای خودترمیمی در صورت نیاز
        
        پارامترها:
            metrics: اگر None باشد، از Scheduler دریافت می‌شود
        
        خروجی:
            دیکشنری از اقدامات انجام شده
        """
        if metrics is None:
            metrics = self._get_metrics_from_scheduler()
        
        actions: Dict[str, Any] = {
            "model_restored": False,
            "cache_cleared": False,
            "modules_restarted": [],
            "model_retrained": False
        }
        
        # ۱. بررسی مدل
        if self._should_restore_model(metrics):
            actions["model_restored"] = self._restore_model()
        
        # ۲. بررسی نیاز به آموزش مجدد
        if self._should_retrain(metrics):
            actions["model_retrained"] = self._retrain_model()
        
        # ۳. بررسی کش
        if self._should_clear_cache(metrics):
            actions["cache_cleared"] = self._clear_cache()
        
        # ۴. بررسی ماژول‌ها
        restarted: List[str] = self._restart_modules(metrics)
        if restarted:
            actions["modules_restarted"] = restarted
        
        # اگر اقدامی انجام شد، لاگ کن
        if any(actions.values()):
            logger.info(f"🔄 Self-healing actions: {actions}")
        
        return actions
    
    # ============================================================
    # ۱. بازگشت مدل
    # ============================================================
    
    def _should_restore_model(self, metrics: Dict[str, Any]) -> bool:
        """
        بررسی نیاز به بازگشت مدل
        
        پارامترها:
            metrics: متریک‌های سیستم
        
        خروجی:
            True اگر نیاز به بازگشت باشد
        """
        accuracy: Optional[float] = metrics.get("model_accuracy")
        
        if accuracy is None:
            return False
        
        if accuracy < 0.50:
            key: str = "model_restore"
            attempts: int = self.healing_attempts.get(key, {}).get("count", 0)
            last_attempt: Optional[str] = self.healing_attempts.get(key, {}).get("last_attempt")
            
            if attempts >= self.max_attempts:
                logger.warning(f"⚠️ Maximum restore attempts reached ({self.max_attempts})")
                return False
            
            if last_attempt:
                try:
                    cooldown: datetime = datetime.fromisoformat(last_attempt) + timedelta(minutes=self.cooldown_minutes)
                    if datetime.now() < cooldown:
                        logger.info(f"⏳ Restore cooldown active (until {cooldown})")
                        return False
                except ValueError:
                    # اگر فرمت تاریخ نامعتبر بود، ادامه بده
                    pass
            
            return True
        
        return False
    
    def _restore_model(self) -> bool:
        """
        بازگشت به نسخه قبلی مدل
        
        خروجی:
            True اگر بازگشت موفق باشد
        """
        try:
            logger.warning("🔄 Attempting to restore previous model version...")
            
            history: List[Dict[str, Any]] = self.model_manager.get_version_history(limit=5)
            
            if len(history) < 2:
                logger.warning("⚠️ No previous version found")
                return False
            
            previous_version: Optional[str] = None
            for item in history[1:]:
                if not item.get('is_ensemble', False):
                    previous_version = item.get('version')
                    break
            
            if not previous_version:
                logger.warning("⚠️ No valid previous version found")
                return False
            
            model = self.model_manager.get_model_by_version(previous_version)
            if model:
                self.model_manager.current_model = model
                self.model_manager.current_version = previous_version
                
                # به‌روزرسانی دیتابیس
                if self.model_manager.db and self.model_manager.db.is_connected():
                    try:
                        self.model_manager.db.execute(
                            "UPDATE models SET is_active = TRUE WHERE version = %s",
                            (previous_version,)
                        )
                        self.model_manager.db.execute(
                            "UPDATE models SET is_active = FALSE WHERE version != %s AND is_ensemble = FALSE",
                            (previous_version,)
                        )
                        
                        self.model_manager.db.execute(
                            """INSERT INTO model_training_history 
                               (model_id, action, reason, created_at) 
                               VALUES ((SELECT id FROM models WHERE version = %s), 'restore', %s, %s)""",
                            (previous_version, f"Auto-restored due to low accuracy", datetime.now())
                        )
                    except Exception as e:
                        logger.error(f"❌ Database update error: {e}")
                
                logger.info(f"✅ Model restored to version: {previous_version}")
                
                key: str = "model_restore"
                if key not in self.healing_attempts:
                    self.healing_attempts[key] = {"count": 0}
                self.healing_attempts[key]["count"] = self.healing_attempts[key]["count"] + 1
                self.healing_attempts[key]["last_attempt"] = datetime.now().isoformat()
                
                return True
            else:
                logger.error(f"❌ Failed to load model version: {previous_version}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error restoring model: {e}", exc_info=True)
            return False
    
    # ============================================================
    # ۲. آموزش مجدد
    # ============================================================
    
    def _should_retrain(self, metrics: Dict[str, Any]) -> bool:
        """
        بررسی نیاز به آموزش مجدد
        
        پارامترها:
            metrics: متریک‌های سیستم
        
        خروجی:
            True اگر نیاز به آموزش مجدد باشد
        """
        accuracy: Optional[float] = metrics.get("model_accuracy")
        loaded: bool = metrics.get("model_loaded", False)
        
        if not loaded or (accuracy is not None and accuracy < 0.45):
            key: str = "model_retrain"
            last_attempt: Optional[str] = self.healing_attempts.get(key, {}).get("last_attempt")
            
            if last_attempt:
                try:
                    cooldown: datetime = datetime.fromisoformat(last_attempt) + timedelta(minutes=60)
                    if datetime.now() < cooldown:
                        return False
                except ValueError:
                    pass
            
            return True
        
        return False
    
    def _retrain_model(self) -> bool:
        """
        آموزش مجدد مدل
        
        خروجی:
            True اگر آموزش موفق باشد
        """
        try:
            logger.warning("🔄 Retraining model...")
            
            if self.trainer:
                result: Dict[str, Any] = self.trainer.train_model(period="1m")
                if result.get("success"):
                    logger.info(f"✅ Model retrained successfully: {result.get('accuracy')}")
                    
                    key: str = "model_retrain"
                    if key not in self.healing_attempts:
                        self.healing_attempts[key] = {}
                    self.healing_attempts[key]["last_attempt"] = datetime.now().isoformat()
                    
                    return True
                else:
                    logger.error(f"❌ Model retrain failed: {result.get('message')}")
                    return False
            else:
                logger.warning("⚠️ Trainer not available")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error retraining model: {e}", exc_info=True)
            return False
    
    # ============================================================
    # ۳. پاک‌سازی کش
    # ============================================================
    
    def _should_clear_cache(self, metrics: Dict[str, Any]) -> bool:
        """
        بررسی نیاز به پاک‌سازی کش
        
        پارامترها:
            metrics: متریک‌های سیستم
        
        خروجی:
            True اگر نیاز به پاک‌سازی باشد
        """
        ram: float = float(metrics.get("ram", 0))
        
        if ram > 85:
            key: str = "cache_clear"
            last_clear: Optional[str] = self.healing_attempts.get(key, {}).get("last_attempt")
            
            if last_clear:
                try:
                    cooldown: datetime = datetime.fromisoformat(last_clear) + timedelta(minutes=10)
                    if datetime.now() < cooldown:
                        return False
                except ValueError:
                    pass
            
            return True
        
        return False
    
    def _clear_cache(self) -> bool:
        """
        پاک‌سازی کش (Redis)
        
        خروجی:
            True اگر پاک‌سازی موفق باشد
        """
        try:
            logger.warning("🧹 Clearing cache to free memory...")
            
            cache = get_cache()
            if cache and cache.is_connected():
                cache._client.flushdb()
                logger.info("✅ Cache cleared successfully")
                
                key: str = "cache_clear"
                if key not in self.healing_attempts:
                    self.healing_attempts[key] = {}
                self.healing_attempts[key]["last_attempt"] = datetime.now().isoformat()
                
                return True
            else:
                logger.warning("⚠️ Cache not available")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error clearing cache: {e}", exc_info=True)
            return False
    
    # ============================================================
    # ۴. ری‌استارت ماژول‌ها
    # ============================================================
    
    def _restart_modules(self, metrics: Dict[str, Any]) -> List[str]:
        """
        ری‌استارت ماژول‌های مشکل‌دار
        
        پارامترها:
            metrics: متریک‌های سیستم
        
        خروجی:
            لیست ماژول‌های ری‌استارت شده
        """
        restarted: List[str] = []
        
        # بررسی API
        if metrics.get("api_status") in ["error", "unhealthy"]:
            restarted.append("api_handler")
            logger.info("🔄 Restarting API handler...")
            
            # ری‌استارت کلاینت API
            if self.api_client:
                try:
                    # بازنشانی Session
                    if hasattr(self.api_client, 'session'):
                        self.api_client.session.close()
                        import requests
                        self.api_client.session = requests.Session()
                        self.api_client.session.headers.update({
                            "X-API-KEY": self.api_client.api_key,
                            "Content-Type": "application/json",
                            "Accept": "application/json"
                        })
                        logger.info("✅ API session recreated")
                except Exception as e:
                    logger.error(f"❌ Error restarting API: {e}")
        
        # بررسی دیتابیس
        databases: Dict[str, bool] = metrics.get("databases", {})
        for name, status in databases.items():
            if not status:
                restarted.append(f"database_{name}")
                try:
                    from infrastructure.database.database_factory import db_factory
                    result: Dict[str, bool] = db_factory.force_reconnect(name)
                    if result.get(name, False):
                        logger.info(f"✅ Database {name} reconnected successfully")
                    else:
                        logger.warning(f"⚠️ Failed to reconnect {name}")
                except ImportError:
                    logger.warning(f"⚠️ Database factory not available for {name}")
                except Exception as e:
                    logger.error(f"❌ Error reconnecting {name}: {e}")
        
        return restarted
    
    # ============================================================
    # ۵. وضعیت
    # ============================================================
    
    def get_healing_status(self) -> Dict[str, Any]:
        """
        دریافت وضعیت خودترمیمی
        
        خروجی:
            دیکشنری وضعیت
        """
        return {
            "attempts": self.healing_attempts,
            "max_attempts": self.max_attempts,
            "cooldown_minutes": self.cooldown_minutes,
            "timestamp": datetime.now().isoformat()
        }
    
    def reset_attempts(self) -> None:
        """بازنشانی همه تلاش‌ها"""
        self.healing_attempts.clear()
        logger.info("✅ Healing attempts reset")
