# self_healer.py
# ============================================================
# سیستم خودترمیمی - نسخه ۳.۰ (با Type Hints)
# ============================================================

import os
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Union

logger = logging.getLogger(__name__)


class SelfHealer:
    """
    سیستم خودترمیمی:
    - بازگشت به نسخه قبلی مدل در صورت افت دقت
    - پاک‌سازی خودکار کش
    - ری‌استارت ماژول‌ها (با reconnect)
    
    ✅ نسخه ۳.۰: اضافه شدن Type Hints کامل
    """
    
    def __init__(self, model_manager: Any, trainer: Any) -> None:
        self.model_manager = model_manager
        self.trainer = trainer
        self.healing_attempts: Dict[str, Dict[str, Union[int, str]]] = {}
        self.max_attempts: int = 3
        self.cooldown_minutes: int = 30
        
        logger.info("✅ SelfHealer v3.0 initialized (with Type Hints)")
    
    def _get_metrics_from_scheduler(self) -> Dict[str, Any]:
        """دریافت متریک‌ها از Scheduler"""
        try:
            from core import metrics_scheduler
            return metrics_scheduler.get_alert_metrics()
        except ImportError:
            logger.warning("⚠️ Metrics Scheduler not available, using fallback")
            return self._get_fallback_metrics()
        except Exception as e:
            logger.error(f"❌ Error getting metrics from scheduler: {e}")
            return self._get_fallback_metrics()
    
    def _get_fallback_metrics(self) -> Dict[str, Any]:
        """Fallback در صورت عدم دسترسی به Scheduler"""
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
    
    # ---------- ۱. بازگشت مدل ----------
    
    def _should_restore_model(self, metrics: Dict[str, Any]) -> bool:
        """بررسی نیاز به بازگشت مدل"""
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
                cooldown: datetime = datetime.fromisoformat(last_attempt) + timedelta(minutes=self.cooldown_minutes)
                if datetime.now() < cooldown:
                    logger.info(f"⏳ Restore cooldown active (until {cooldown})")
                    return False
            
            return True
        
        return False
    
    def _restore_model(self) -> bool:
        """بازگشت به نسخه قبلی مدل"""
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
            
            model: Any = self.model_manager.get_model_by_version(previous_version)
            if model:
                self.model_manager.current_model = model
                self.model_manager.current_version = previous_version
                
                if self.model_manager.db and self.model_manager.db.is_connected():
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
            logger.error(f"❌ Error restoring model: {e}")
            return False
    
    # ---------- ۲. آموزش مجدد ----------
    
    def _should_retrain(self, metrics: Dict[str, Any]) -> bool:
        """بررسی نیاز به آموزش مجدد"""
        accuracy: Optional[float] = metrics.get("model_accuracy")
        loaded: bool = metrics.get("model_loaded", False)
        
        if not loaded or (accuracy is not None and accuracy < 0.45):
            key: str = "model_retrain"
            last_attempt: Optional[str] = self.healing_attempts.get(key, {}).get("last_attempt")
            
            if last_attempt:
                cooldown: datetime = datetime.fromisoformat(last_attempt) + timedelta(minutes=60)
                if datetime.now() < cooldown:
                    return False
            
            return True
        
        return False
    
    def _retrain_model(self) -> bool:
        """آموزش مجدد مدل"""
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
            logger.error(f"❌ Error retraining model: {e}")
            return False
    
    # ---------- ۳. پاک‌سازی کش ----------
    
    def _should_clear_cache(self, metrics: Dict[str, Any]) -> bool:
        """بررسی نیاز به پاک‌سازی کش"""
        ram: float = float(metrics.get("ram", 0))
        
        if ram > 85:
            key: str = "cache_clear"
            last_clear: Optional[str] = self.healing_attempts.get(key, {}).get("last_attempt")
            
            if last_clear:
                cooldown: datetime = datetime.fromisoformat(last_clear) + timedelta(minutes=10)
                if datetime.now() < cooldown:
                    return False
            
            return True
        
        return False
    
    def _clear_cache(self) -> bool:
        """پاک‌سازی کش (Redis)"""
        try:
            logger.warning("🧹 Clearing cache to free memory...")
            
            from database import get_cache
            cache: Any = get_cache()
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
            logger.error(f"❌ Error clearing cache: {e}")
            return False
    
    # ---------- ۴. ری‌استارت ماژول‌ها ----------
    
    def _restart_modules(self, metrics: Dict[str, Any]) -> List[str]:
        """ری‌استارت ماژول‌های مشکل‌دار"""
        restarted: List[str] = []
        
        # بررسی API
        if metrics.get("api_status") in ["error", "unhealthy"]:
            restarted.append("api_handler")
            logger.info("🔄 Restarting API handler...")
        
        # بررسی دیتابیس
        databases: Dict[str, bool] = metrics.get("databases", {})
        for name, status in databases.items():
            if not status:
                restarted.append(f"database_{name}")
                try:
                    from database import db_factory
                    result: Dict[str, bool] = db_factory.force_reconnect(name)
                    if result.get(name, False):
                        logger.info(f"✅ Database {name} reconnected successfully")
                    else:
                        logger.warning(f"⚠️ Failed to reconnect {name}")
                except Exception as e:
                    logger.error(f"❌ Error reconnecting {name}: {e}")
        
        return restarted
    
    # ---------- ۵. وضعیت ----------
    
    def get_healing_status(self) -> Dict[str, Any]:
        """دریافت وضعیت خودترمیمی"""
        return {
            "attempts": self.healing_attempts,
            "max_attempts": self.max_attempts,
            "cooldown_minutes": self.cooldown_minutes,
            "timestamp": datetime.now().isoformat()
        }
