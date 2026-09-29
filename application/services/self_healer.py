# application/services/self_healer.py
# ============================================================
# سیستم خودترمیمی - نسخه ۶.۰
# Recalibrate جای Retrain + Quota Healing
# ============================================================
# 
# تغییرات نسخه ۶.۰:
#   - _retrain_model → _recalibrate_weights
#   - _should_retrain → _should_recalibrate
#   - حذف منطق XGBoost
#   - اتکا به AutoTrainer.calibrate()
#   - منطق RuleEngine-specific در detect مشکل
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


# ============================================================
# SelfHealer v6.0
# ============================================================

class SelfHealer:
    """
    سیستم خودترمیمی
    
    مسئولیت‌ها:
        ۱. تشخیص مشکل (مدل، cache، DB، API)
        ۲. اقدام ترمیمی مناسب
        ۳. کالیبراسیون مجدد وزن‌ها (اگه لازم)
        ۴. پاک‌سازی quota
    
    تغییرات نسبت به نسخه ۵.۰:
        - retrain → recalibrate
        - بدون XGBoost
        - منطق RuleEngine
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
        
        # آمار healing
        self.healing_attempts: Dict[str, Dict[str, Union[int, str]]] = {}
        self.max_attempts: int = 3
        self.cooldown_minutes: int = 30
        
        logger.info("✅ SelfHealer v6.0 initialized")
    
    # ============================================================
    # Metrics (Lazy)
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
    # Check & Heal (Main)
    # ============================================================
    
    def check_and_heal(
        self,
        metrics: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        بررسی و خودترمیمی
        
        Args:
            metrics: متریک‌ها (اگه None، از Scheduler)
        
        Returns:
            اقدامات انجام شده
        """
        if metrics is None:
            metrics = self._get_metrics_from_scheduler()
        
        actions: Dict[str, Any] = {
            "engine_reloaded": False,
            "weights_recalibrated": False,
            "cache_cleared": False,
            "modules_restarted": [],
            "quota_cleaned": False,
            "config_reset": False,
        }
        
        # ۱. Engine — اگه بارگذاری نشده یا score افتاده
        if self._should_reload_engine(metrics):
            actions["engine_reloaded"] = self._reload_engine()
        
        # ۲. کالیبراسیون مجدد (اگه score افتاده)
        if self._should_recalibrate(metrics):
            actions["weights_recalibrated"] = self._recalibrate_weights()
        
        # ۳. Cache
        if self._should_clear_cache(metrics):
            actions["cache_cleared"] = self._clear_cache()
        
        # ۴. ماژول‌ها (API، DB)
        restarted = self._restart_modules(metrics)
        if restarted:
            actions["modules_restarted"] = restarted
        
        # ۵. Quota
        if self._should_clean_quota(metrics):
            actions["quota_cleaned"] = self._clean_quota()
        
        # ۶. Config (اگه runtime_config مشکلی ایجاد کرده)
        if self._should_reset_config(metrics):
            actions["config_reset"] = self._reset_runtime_config()
        
        # لاگ
        if any(self._has_action(v) for v in actions.values()):
            logger.info(f"🔄 Self-healing actions: {actions}")
        
        return actions
    
    @staticmethod
    def _has_action(value: Any) -> bool:
        """آیا action انجام شده؟"""
        if isinstance(value, bool):
            return value
        if isinstance(value, list):
            return len(value) > 0
        return bool(value)
    
    # ============================================================
    # Engine Reload
    # ============================================================
    
    def _should_reload_engine(self, metrics: Dict[str, Any]) -> bool:
        """آیا engine باید reload بشه؟"""
        # اگه engine بارگذاری نشده ولی version فعال داریم
        engine_loaded = self.model_manager.engine is not None
        has_version = self.model_manager.current_version is not None
        
        if not engine_loaded and has_version:
            return self._check_attempts("engine_reload")
        
        # اگه model_loaded از metrics False ولی ما engine داریم
        metrics_loaded = metrics.get("model_loaded", True)
        if not metrics_loaded and engine_loaded:
            # تناقض — احتمالاً engine مرده
            return self._check_attempts("engine_reload")
        
        return False
    
    def _reload_engine(self) -> bool:
        """بارگذاری مجدد RuleEngine"""
        try:
            logger.warning("🔄 Reloading RuleEngine...")
            
            self.model_manager._initialize_engine()
            
            if self.model_manager.engine is not None:
                logger.info("✅ RuleEngine reloaded")
                self._mark_attempt("engine_reload")
                return True
            
            logger.error("❌ RuleEngine reload failed")
            return False
        
        except Exception as e:
            logger.error(f"❌ Engine reload error: {e}", exc_info=True)
            return False
    
    # ============================================================
    # Recalibrate (جای Retrain)
    # ============================================================
    
    def _should_recalibrate(self, metrics: Dict[str, Any]) -> bool:
        """
        آیا کالیبراسیون مجدد لازمه؟
        
        معیارها:
            - score < threshold
            - یا engine بارگذاری نشده
        """
        engine_loaded = self.model_manager.engine is not None
        
        # اگه engine نیست، نمی‌تونیم calibrate کنیم
        if not engine_loaded:
            return False
        
        # چک improvement افتضاح
        accuracy = metrics.get("model_accuracy")
        
        if accuracy is not None:
            # اگه accuracy < 0.45 (خیلی افتضاح)
            if accuracy < 0.45:
                return self._check_attempts("recalibrate")
        
        # چک آخرین کالیبراسیون (اگه خیلی قدیمیه)
        try:
            stats = self.trainer.get_stats()
            inner = stats.get("stats", {})
            last = inner.get("last_calibration")
            
            if last:
                try:
                    last_dt = datetime.fromisoformat(last)
                    # اگه بیش از ۷ روز گذشته
                    if datetime.now() - last_dt > timedelta(days=7):
                        return self._check_attempts("recalibrate")
                except (ValueError, TypeError):
                    pass
        except Exception as e:
            logger.debug(f"Could not check last calibration: {e}")
        
        return False
    
    def _recalibrate_weights(self) -> bool:
        """
        کالیبراسیون مجدد وزن‌ها
        
        با profile="fast" برای سرعت
        """
        try:
            logger.warning("🔄 Recalibrating weights (fast profile)...")
            
            result = self.trainer.calibrate(
                period="1m",
                profile_name="fast",
                save=True,
            )
            
            if result.get("success"):
                logger.info(
                    f"✅ Weights recalibrated: "
                    f"score={result.get('best_score', 0):.3f}, "
                    f"improvement={result.get('improvement', 0):+.3f}"
                )
                self._mark_attempt("recalibrate")
                return True
            
            logger.error(f"❌ Recalibration failed: {result.get('error')}")
            return False
        
        except Exception as e:
            logger.error(f"❌ Recalibrate error: {e}", exc_info=True)
            return False
    
    # ============================================================
    # Cache
    # ============================================================
    
    def _should_clear_cache(self, metrics: Dict[str, Any]) -> bool:
        """آیا cache باید پاک بشه؟"""
        ram = float(metrics.get("ram", 0))
        
        if ram > 85:
            return self._check_attempts("cache_clear", cooldown_minutes=10)
        
        return False
    
    def _clear_cache(self) -> bool:
        """پاک کردن cache"""
        try:
            logger.warning("🧹 Clearing cache...")
            
            cache = get_cache()
            if cache and cache.is_connected():
                cache.flush()
                logger.info("✅ Cache cleared")
                self._mark_attempt("cache_clear")
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
        restarted: List[str] = []
        
        # API
        if metrics.get("api_status") in ["error", "unhealthy"]:
            restarted.append("api_handler")
            logger.info("🔄 Restarting API handler...")
            
            if self.api_client and hasattr(self.api_client, "session"):
                try:
                    import requests
                    self.api_client.session.close()
                    self.api_client.session = requests.Session()
                    
                    # API key از config
                    api_key = getattr(self.api_client, "api_key", None)
                    if api_key:
                        self.api_client.session.headers.update({
                            "X-API-KEY": api_key,
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
    # Quota
    # ============================================================
    
    def _should_clean_quota(self, metrics: Dict[str, Any]) -> bool:
        """آیا Quota باید پاک بشه؟"""
        quota = metrics.get("quota", {})
        
        for db_name, status in quota.items():
            if isinstance(status, dict):
                if status.get("status") == "critical":
                    if self._check_attempts(
                        f"quota_clean_{db_name}",
                        cooldown_minutes=30,
                    ):
                        return True
        
        return False
    
    def _clean_quota(self) -> bool:
        """پاک کردن رکوردهای قدیمی"""
        try:
            logger.warning("🧹 Cleaning old records for quota...")
            
            from infrastructure.repositories import repos
            
            # حذف پیش‌بینی‌های قدیمی
            deleted = repos.prediction.delete_old(retention_days=30)
            
            if deleted > 0:
                logger.info(f"✅ Deleted {deleted} old predictions")
                self._mark_attempt("quota_clean")
                return True
            
            return False
        
        except Exception as e:
            logger.error(f"❌ Quota clean error: {e}")
            return False
    
    # ============================================================
    # Runtime Config Reset
    # ============================================================
    
    def _should_reset_config(self, metrics: Dict[str, Any]) -> bool:
        """
        آیا runtime_config باید reset بشه؟
        
        اگه:
            - runtime_config فعاله
            - و score افت کرده
        """
        try:
            has_runtime = bool(self.model_manager.runtime_config)
        except Exception:
            has_runtime = False
        
        if not has_runtime:
            return False
        
        accuracy = metrics.get("model_accuracy")
        if accuracy is not None and accuracy < 0.40:
            return self._check_attempts(
                "config_reset",
                cooldown_minutes=60,
            )
        
        return False
    
    def _reset_runtime_config(self) -> bool:
        """پاک کردن runtime_config"""
        try:
            logger.warning("🔄 Resetting runtime config...")
            
            result = self.model_manager.reset_runtime_config()
            
            if result.get("success"):
                logger.info("✅ Runtime config reset")
                self._mark_attempt("config_reset")
                return True
            
            return False
        
        except Exception as e:
            logger.error(f"❌ Reset config error: {e}")
            return False
    
    # ============================================================
    # Attempts Management
    # ============================================================
    
    def _check_attempts(
        self,
        key: str,
        cooldown_minutes: Optional[int] = None,
    ) -> bool:
        """
        بررسی اینکه آیا می‌تونیم دوباره تلاش کنیم
        
        Returns:
            True اگه:
                - تعداد attempts < max
                - و از آخرین تلاش، cooldown گذشته
        """
        cooldown = cooldown_minutes or self.cooldown_minutes
        
        entry = self.healing_attempts.get(key, {})
        count = entry.get("count", 0)
        
        if count >= self.max_attempts:
            return False
        
        last = entry.get("last_attempt")
        if last:
            try:
                last_dt = datetime.fromisoformat(last)
                if datetime.now() < last_dt + timedelta(minutes=cooldown):
                    return False
            except (ValueError, TypeError):
                pass
        
        return True
    
    def _mark_attempt(self, key: str) -> None:
        """ثبت یک تلاش"""
        if key not in self.healing_attempts:
            self.healing_attempts[key] = {"count": 0}
        
        self.healing_attempts[key]["count"] = (
            self.healing_attempts[key].get("count", 0) + 1
        )
        self.healing_attempts[key]["last_attempt"] = datetime.now().isoformat()
    
    # ============================================================
    # Status
    # ============================================================
    
    def get_healing_status(self) -> Dict[str, Any]:
        """وضعیت خودترمیمی"""
        # آمار Trainer
        trainer_stats = {}
        try:
            stats = self.trainer.get_stats()
            inner = stats.get("stats", {})
            trainer_stats = {
                "total_calibrations": inner.get("total_calibrations", 0),
                "successful_calibrations": inner.get("successful_calibrations", 0),
                "failed_calibrations": inner.get("failed_calibrations", 0),
                "last_calibration": inner.get("last_calibration"),
                "last_score": inner.get("last_score"),
                "last_improvement": inner.get("last_improvement"),
            }
        except Exception as e:
            logger.debug(f"Trainer stats error: {e}")
        
        # آمار ModelManager
        model_stats = {}
        try:
            engine = self.model_manager.engine
            model_stats = {
                "engine_loaded": engine is not None,
                "current_version": self.model_manager.current_version,
                "rule_count": len(engine.rules) if engine else 0,
                "runtime_config_active": bool(self.model_manager.runtime_config),
            }
        except Exception as e:
            logger.debug(f"Model stats error: {e}")
        
        return {
            "attempts": self.healing_attempts,
            "max_attempts": self.max_attempts,
            "cooldown_minutes": self.cooldown_minutes,
            "trainer": trainer_stats,
            "model": model_stats,
            "timestamp": datetime.now().isoformat(),
        }
    
    def reset_attempts(self) -> None:
        """بازنشانی تلاش‌ها"""
        self.healing_attempts.clear()
        logger.info("✅ Healing attempts reset")
    
    # ============================================================
    # Manual Healing
    # ============================================================
    
    def force_recalibrate(
        self,
        profile_name: str = "fast",
        period: str = "1m",
    ) -> Dict[str, Any]:
        """
        کالیبراسیون اجباری (برای API)
        
        Args:
            profile_name: profile (fast/balanced/accurate)
            period: بازه
        
        Returns:
            نتیجه کالیبراسیون
        """
        logger.info(
            f"🔄 Force recalibrate requested "
            f"(profile={profile_name}, period={period})"
        )
        
        # ریست attempts تا بتونیم
        self.healing_attempts.pop("recalibrate", None)
        
        result = self.trainer.calibrate(
            period=period,
            profile_name=profile_name,
            save=True,
        )
        
        if result.get("success"):
            self._mark_attempt("recalibrate")
        
        return result
    
    def force_reload_engine(self) -> Dict[str, Any]:
        """بارگذاری اجباری engine"""
        logger.info("🔄 Force engine reload requested")
        
        self.healing_attempts.pop("engine_reload", None)
        
        success = self._reload_engine()
        
        return {
            "success": success,
            "engine_loaded": self.model_manager.engine is not None,
            "version": self.model_manager.current_version,
        }


__all__ = ["SelfHealer"]
