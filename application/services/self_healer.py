# application/services/self_healer.py
# ============================================================
# سیستم خودترمیمی - نسخه ۵.۰
# رفع Circular Import + Quota Healing
# ============================================================

import os
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Union

from domain.interfaces.api_client import APIClient
from models.manager.model_manager import ModelManager
from models.trainer.auto_trainer import AutoTrainer
from infrastructure.database import get_cache, get_primary

logger = logging.getLogger(__name__)


class SelfHealer:
    """
    سیستم خودترمیمی
    
    رفع باگ‌ها:
        - Circular import با metrics (lazy)
    
    ارتقاها:
        - Quota healing
        - Better restore
        - Backup check
    """
    
    def __init__(
        self,
        model_manager: ModelManager,
        trainer: AutoTrainer,
        api_client: Optional[APIClient] = None,
    ) -> None:
        self.model_manager = model_manager
        self.trainer = trainer
        self.api_client = api_client
        
        self.healing_attempts: Dict[str, Dict[str, Union[int, str]]] = {}
        self.max_attempts: int = 3
        self.cooldown_minutes: int = 30
        
        logger.info("✅ SelfHealer v5.0 initialized")
    
    # ============================================================
    # Metrics (Lazy - بدون circular)
    # ============================================================
    
    def _get_metrics_from_scheduler(self) -> Dict[str, Any]:
        """دریافت متریک‌ها (lazy)"""
        try:
            from core.metrics import metrics_scheduler
            return metrics_scheduler.get_alert_metrics()
        except ImportError:
            logger.debug("⚠️ Metrics Scheduler not available")
            return self._get_fallback_metrics()
        except Exception as e:
            logger.error(f"Metrics error: {e}")
            return self._get_fallback_metrics()
    
    def _get_fallback_metrics(self) -> Dict[str, Any]:
        """Fallback metrics"""
        return {
            "cpu": 0,
            "ram": 0,
            "api_status": "unknown",
            "model_loaded": False,
            "model_accuracy": None,
            "databases": {"postgresql": False, "redis": False, "archive": False},
            "quota": {},
        }
    
    # ============================================================
    # Check & Heal
    # ============================================================
    
    def check_and_heal(
        self,
        metrics: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        بررسی و خودترمیمی
        
        پارامترها:
            metrics: متریک‌ها (اگه None، از Scheduler)
        
        خروجی:
            اقدامات انجام شده
        """
        if metrics is None:
            metrics = self._get_metrics_from_scheduler()
        
        actions: Dict[str, Any] = {
            "model_restored": False,
            "cache_cleared": False,
            "modules_restarted": [],
            "model_retrained": False,
            "quota_cleaned": False,  # 🆕
        }
        
        # ۱. مدل
        if self._should_restore_model(metrics):
            actions["model_restored"] = self._restore_model()
        
        # ۲. آموزش مجدد
        if self._should_retrain(metrics):
            actions["model_retrained"] = self._retrain_model()
        
        # ۳. کش
        if self._should_clear_cache(metrics):
            actions["cache_cleared"] = self._clear_cache()
        
        # ۴. ماژول‌ها
        restarted = self._restart_modules(metrics)
        if restarted:
            actions["modules_restarted"] = restarted
        
        # ۵. Quota (🆕)
        if self._should_clean_quota(metrics):
            actions["quota_cleaned"] = self._clean_quota()
        
        if any(actions.values()):
            logger.info(f"🔄 Self-healing: {actions}")
        
        return actions
    
    # ============================================================
    # Model Restore
    # ============================================================
    
    def _should_restore_model(self, metrics: Dict[str, Any]) -> bool:
        """آیا مدل باید restore بشه؟"""
        accuracy = metrics.get("model_accuracy")
        
        if accuracy is None:
            return False
        
        if accuracy < 0.50:
            key = "model_restore"
            attempts = self.healing_attempts.get(key, {}).get("count", 0)
            
            if attempts >= self.max_attempts:
                return False
            
            last = self.healing_attempts.get(key, {}).get("last_attempt")
            if last:
                try:
                    cooldown = datetime.fromisoformat(last) + timedelta(
                        minutes=self.cooldown_minutes
                    )
                    if datetime.now() < cooldown:
                        return False
                except ValueError:
                    pass
            
            return True
        
        return False
    
    def _restore_model(self) -> bool:
        """Restore مدل"""
        try:
            logger.warning("🔄 Restoring previous model...")
            
            history = self.model_manager.get_version_history(limit=5)
            
            if len(history) < 2:
                logger.warning("⚠️ No previous version")
                return False
            
            # پیدا کردن نسخه قبلی
            previous_version = None
            for item in history[1:]:
                if not item.get("is_ensemble", False):
                    previous_version = item.get("version")
                    break
            
            if not previous_version:
                return False
            
            # فعال‌سازی
            success = self.model_manager.set_active(previous_version)
            
            if success:
                logger.info(f"✅ Model restored to {previous_version}")
                
                key = "model_restore"
                if key not in self.healing_attempts:
                    self.healing_attempts[key] = {"count": 0}
                self.healing_attempts[key]["count"] += 1
                self.healing_attempts[key]["last_attempt"] = datetime.now().isoformat()
                
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"❌ Restore error: {e}", exc_info=True)
            return False
    
    # ============================================================
    # Retrain
    # ============================================================
    
    def _should_retrain(self, metrics: Dict[str, Any]) -> bool:
        """آیا آموزش مجدد لازمه؟"""
        accuracy = metrics.get("model_accuracy")
        loaded = metrics.get("model_loaded", False)
        
        if not loaded or (accuracy is not None and accuracy < 0.45):
            key = "model_retrain"
            last = self.healing_attempts.get(key, {}).get("last_attempt")
            
            if last:
                try:
                    cooldown = datetime.fromisoformat(last) + timedelta(minutes=60)
                    if datetime.now() < cooldown:
                        return False
                except ValueError:
                    pass
            
            return True
        
        return False
    
    def _retrain_model(self) -> bool:
        """آموزش مجدد مدل"""
        try:
            logger.warning("🔄 Retraining model...")
            
            if self.trainer:
                result = self.trainer.train_model(period="1m")
                
                if result.get("success"):
                    logger.info(f"✅ Model retrained: {result.get('accuracy')}")
                    
                    key = "model_retrain"
                    if key not in self.healing_attempts:
                        self.healing_attempts[key] = {}
                    self.healing_attempts[key]["last_attempt"] = datetime.now().isoformat()
                    
                    return True
                
                logger.error(f"❌ Retrain failed: {result.get('error')}")
                return False
            
            return False
            
        except Exception as e:
            logger.error(f"❌ Retrain error: {e}", exc_info=True)
            return False
    
    # ============================================================
    # Cache
    # ============================================================
    
    def _should_clear_cache(self, metrics: Dict[str, Any]) -> bool:
        """آیا کش باید پاک بشه؟"""
        ram = float(metrics.get("ram", 0))
        
        if ram > 85:
            key = "cache_clear"
            last = self.healing_attempts.get(key, {}).get("last_attempt")
            
            if last:
                try:
                    cooldown = datetime.fromisoformat(last) + timedelta(minutes=10)
                    if datetime.now() < cooldown:
                        return False
                except ValueError:
                    pass
            
            return True
        
        return False
    
    def _clear_cache(self) -> bool:
        """پاک کردن کش"""
        try:
            logger.warning("🧹 Clearing cache...")
            
            cache = get_cache()
            if cache and cache.is_connected():
                cache.flush()
                logger.info("✅ Cache cleared")
                
                key = "cache_clear"
                if key not in self.healing_attempts:
                    self.healing_attempts[key] = {}
                self.healing_attempts[key]["last_attempt"] = datetime.now().isoformat()
                
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"❌ Cache clear error: {e}")
            return False
    
    # ============================================================
    # Modules
    # ============================================================
    
    def _restart_modules(self, metrics: Dict[str, Any]) -> List[str]:
        """ری‌استارت ماژول‌های مشکل‌دار"""
        restarted = []
        
        # API
        if metrics.get("api_status") in ["error", "unhealthy"]:
            restarted.append("api_handler")
            logger.info("🔄 Restarting API handler...")
            
            if self.api_client and hasattr(self.api_client, "session"):
                try:
                    import requests
                    self.api_client.session.close()
                    self.api_client.session = requests.Session()
                    self.api_client.session.headers.update({
                        "X-API-KEY": self.api_client.api_key,
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                    })
                    logger.info("✅ API session recreated")
                except Exception as e:
                    logger.error(f"❌ API restart error: {e}")
        
        # Databases
        databases = metrics.get("databases", {})
        for name, status in databases.items():
            if not status:
                restarted.append(f"database_{name}")
                try:
                    from infrastructure.database.database_factory import db_factory
                    result = db_factory.force_reconnect(name)
                    if result.get(name, False):
                        logger.info(f"✅ Database {name} reconnected")
                except Exception as e:
                    logger.error(f"❌ DB {name} restart error: {e}")
        
        return restarted
    
    # ============================================================
    # Quota (🆕)
    # ============================================================
    
    def _should_clean_quota(self, metrics: Dict[str, Any]) -> bool:
        """آیا Quota باید پاک بشه؟"""
        quota = metrics.get("quota", {})
        
        for db_name, status in quota.items():
            if isinstance(status, dict):
                if status.get("status") == "critical":
                    key = f"quota_clean_{db_name}"
                    last = self.healing_attempts.get(key, {}).get("last_attempt")
                    
                    if last:
                        try:
                            cooldown = datetime.fromisoformat(last) + timedelta(minutes=30)
                            if datetime.now() < cooldown:
                                continue
                        except ValueError:
                            pass
                    
                    return True
        
        return False
    
    def _clean_quota(self) -> bool:
        """پاک کردن رکوردهای قدیمی برای آزاد کردن فضا"""
        try:
            logger.warning("🧹 Cleaning old records for quota...")
            
            from infrastructure.repositories import repos
            
            # حذف پیش‌بینی‌های قدیمی
            deleted = repos.prediction.delete_old(retention_days=30)
            
            if deleted > 0:
                logger.info(f"✅ Deleted {deleted} old predictions")
                
                key = "quota_clean"
                if key not in self.healing_attempts:
                    self.healing_attempts[key] = {}
                self.healing_attempts[key]["last_attempt"] = datetime.now().isoformat()
                
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"❌ Quota clean error: {e}")
            return False
    
    # ============================================================
    # Status
    # ============================================================
    
    def get_healing_status(self) -> Dict[str, Any]:
        """وضعیت خودترمیمی"""
        return {
            "attempts": self.healing_attempts,
            "max_attempts": self.max_attempts,
            "cooldown_minutes": self.cooldown_minutes,
            "timestamp": datetime.now().isoformat(),
        }
    
    def reset_attempts(self) -> None:
        """بازنشانی تلاش‌ها"""
        self.healing_attempts.clear()
        logger.info("✅ Healing attempts reset")
