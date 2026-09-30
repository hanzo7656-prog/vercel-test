# application/services/self_healer.py
# ============================================================
# SelfHealer - نسخه ۷.۰
# OHLCV-aware + لاگ کامل + Recalibrate
# ============================================================

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Union

from domain.interfaces.api_client import APIClient
from models.manager.model_manager import ModelManager
from models.trainer.auto_trainer import AutoTrainer
from infrastructure.database import get_cache, get_primary

logger = logging.getLogger(__name__)


class SelfHealer:
    """
    سیستم خودترمیمی - نسخه ۷.۰
    
    تغییرات نسبت به ۶.۰:
        - لاگ کامل هر اقدام
        - Rate limit برای recalibrate (جلوگیری از loop)
        - تشخیص دقیق‌تر مشکل OHLCV
        - Disable موقت در صورت خطای مکرر
    """
    
    # ============================================================
    # Constants
    # ============================================================
    
    # حداکثر تلاش
    MAX_ATTEMPTS: int = 3
    
    # Cooldown بین تلاش‌ها (دقیقه)
    COOLDOWN_MINUTES: int = 30
    
    # Cooldown برای recalibrate (سخت‌گیرانه‌تر — ۲ ساعت)
    RECALIBRATE_COOLDOWN_MINUTES: int = 120
    
    # حداقل دقت قابل قبول
    MIN_ACCEPTABLE_ACCURACY: float = 0.45
    
    # اگه accuracy = 0 → احتمالاً engine load نشده
    ZERO_ACCURACY_GRACE_PERIOD: int = 60  # ثانیه
    
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
        self.max_attempts: int = self.MAX_ATTEMPTS
        self.cooldown_minutes: int = self.COOLDOWN_MINUTES
        
        # Track startup time
        self._startup_time: datetime = datetime.now()
        
        # قفل ساده برای جلوگیری از loop
        self._is_healing: bool = False
        
        logger.info("✅ SelfHealer v7.0 initialized")
    
    # ============================================================
    # Metrics
    # ============================================================
    
    def _get_metrics_from_scheduler(self) -> Dict[str, Any]:
        """دریافت متریک‌ها"""
        try:
            from core.metrics import metrics_scheduler
            return metrics_scheduler.get_alert_metrics()
        except ImportError:
            logger.debug("⚠️ Metrics Scheduler not available")
            return self._get_fallback_metrics()
        except Exception as e:
            logger.error(f"❌ Metrics error: {e}")
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
        
        لاگ کامل + جلوگیری از loop
        """
        # جلوگیری از اجرای همزمان
        if self._is_healing:
            logger.debug("⏭️ Self-healing already in progress, skipping")
            return {"skipped": True, "reason": "already_healing"}
        
        self._is_healing = True
        
        try:
            if metrics is None:
                metrics = self._get_metrics_from_scheduler()
            
            logger.debug("🔍 Self-healing check started")
            
            actions: Dict[str, Any] = {
                "engine_reloaded": False,
                "weights_recalibrated": False,
                "cache_cleared": False,
                "modules_restarted": [],
                "quota_cleaned": False,
                "config_reset": False,
            }
            
            # ۱. Engine
            if self._should_reload_engine(metrics):
                actions["engine_reloaded"] = self._reload_engine()
            
            # ۲. Recalibrate
            if self._should_recalibrate(metrics):
                actions["weights_recalibrated"] = self._recalibrate_weights()
            
            # ۳. Cache
            if self._should_clear_cache(metrics):
                actions["cache_cleared"] = self._clear_cache()
            
            # ۴. Modules
            restarted = self._restart_modules(metrics)
            if restarted:
                actions["modules_restarted"] = restarted
            
            # ۵. Quota
            if self._should_clean_quota(metrics):
                actions["quota_cleaned"] = self._clean_quota()
            
            # ۶. Config
            if self._should_reset_config(metrics):
                actions["config_reset"] = self._reset_runtime_config()
            
            # لاگ
            has_action = any(self._has_action(v) for v in actions.values())
            if has_action:
                logger.warning(f"🔄 Self-healing actions: {actions}")
            else:
                logger.debug("✅ Self-healing: no action needed")
            
            return actions
        
        finally:
            self._is_healing = False
    
    @staticmethod
    def _has_action(value: Any) -> bool:
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
        engine_loaded = self.model_manager.engine is not None
        
        # اگه engine نیست ولی version داریم → reload
        if not engine_loaded and self.model_manager.current_version:
            return self._check_attempts("engine_reload")
        
        return False
    
    def _reload_engine(self) -> bool:
        """بارگذاری مجدد RuleEngine"""
        try:
            logger.warning("🔄 Self-heal: Reloading RuleEngine...")
            
            self.model_manager._initialize_engine()
            
            if self.model_manager.engine is not None:
                rule_count = len(self.model_manager.engine.rules)
                logger.info(f"✅ Self-heal: RuleEngine reloaded ({rule_count} rules)")
                self._mark_attempt("engine_reload")
                return True
            
            logger.error("❌ Self-heal: RuleEngine reload failed")
            return False
        
        except Exception as e:
            logger.error(f"❌ Self-heal engine reload error: {e}", exc_info=True)
            return False
    
    # ============================================================
    # Recalibrate
    # ============================================================
    
    def _should_recalibrate(self, metrics: Dict[str, Any]) -> bool:
        """
        آیا کالیبراسیون مجدد لازمه؟
        
        فقط اگه:
            - engine بارگذاری شده
            - از startup حداقل ۵ دقیقه گذشته
            - accuracy صفر نیست یا اگه صفر شد ولی OHLCV کار می‌کنه
            - cooldown ۲ ساعته گذشته
        """
        # ۱. engine باید باشه
        if self.model_manager.engine is None:
            return False
        
        # ۲. اگه از startup کمتر از ۵ دقیقه گذشته، صبر کن
        time_since_startup = (datetime.now() - self._startup_time).total_seconds()
        if time_since_startup < 300:  # ۵ دقیقه
            logger.debug(
                f"⏳ Recalibrate skipped (startup grace: "
                f"{int(time_since_startup)}s < 300s)"
            )
            return False
        
        # ۳. چک accuracy
        accuracy = metrics.get("model_accuracy")
        
        if accuracy is None:
            return False
        
        # ۴. اگه accuracy = 0 → شاید مشکل DB یا engine
        if accuracy == 0.0:
            # اگه بار اوله، صبر کن
            key = "recalibrate_zero_accuracy"
            if not self._check_attempts(key, cooldown_minutes=60):
                return False
            
            logger.warning(
                "⚠️ accuracy=0 detected, might need recalibration"
            )
        
        elif accuracy >= self.MIN_ACCEPTABLE_ACCURACY:
            return False
        
        # ۵. چک cooldown (سخت‌گیرانه: ۲ ساعت)
        return self._check_attempts(
            "recalibrate",
            cooldown_minutes=self.RECALIBRATE_COOLDOWN_MINUTES,
        )
    
    def _recalibrate_weights(self) -> bool:
        """کالیبراسیون مجدد"""
        try:
            logger.warning("🔄 Self-heal: Starting recalibration (fast profile)...")
            
            result = self.trainer.calibrate(
                period="1m",
                profile_name="fast",
                save=True,
            )
            
            if result.get("success"):
                best_score = result.get("best_score", 0)
                improvement = result.get("improvement", 0)
                
                logger.info(
                    f"✅ Self-heal: Recalibration succeeded "
                    f"(score={best_score:.4f}, improvement={improvement:+.4f})"
                )
                
                self._mark_attempt("recalibrate")
                return True
            
            error = result.get("error", "unknown")
            logger.error(f"❌ Self-heal: Recalibration failed: {error}")
            
            self._mark_attempt("recalibrate")
            return False
        
        except Exception as e:
            logger.error(f"❌ Self-heal recalibrate error: {e}", exc_info=True)
            self._mark_attempt("recalibrate")
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
            logger.warning("🧹 Self-heal: Clearing cache...")
            
            cache = get_cache()
            if cache and cache.is_connected():
                cache.flush()
                logger.info("✅ Self-heal: Cache cleared")
                self._mark_attempt("cache_clear")
                return True
            
            return False
        
        except Exception as e:
            logger.error(f"❌ Self-heal cache clear error: {e}")
            return False
    
    # ============================================================
    # Modules
    # ============================================================
    
    def _restart_modules(self, metrics: Dict[str, Any]) -> List[str]:
        """ری‌استارت ماژول‌ها"""
        restarted: List[str] = []
        
        # API
        if metrics.get("api_status") in ["error", "unhealthy"]:
            restarted.append("api_handler")
            logger.info("🔄 Self-heal: Restarting API handler...")
            
            if self.api_client and hasattr(self.api_client, "session"):
                try:
                    import requests
                    self.api_client.session.close()
                    self.api_client.session = requests.Session()
                    
                    api_key = getattr(self.api_client, "api_key", None)
                    if api_key:
                        self.api_client.session.headers.update({
                            "X-API-KEY": api_key,
                            "Content-Type": "application/json",
                            "Accept": "application/json",
                        })
                    
                    logger.info("✅ Self-heal: API session recreated")
                except Exception as e:
                    logger.error(f"❌ Self-heal API restart error: {e}")
        
        # Databases
        databases = metrics.get("databases", {})
        for name, status in databases.items():
            if not status:
                restarted.append(f"database_{name}")
                try:
                    from infrastructure.database.database_factory import db_factory
                    result = db_factory.force_reconnect(name)
                    if result.get(name, False):
                        logger.info(f"✅ Self-heal: DB {name} reconnected")
                except Exception as e:
                    logger.error(f"❌ Self-heal DB {name} error: {e}")
        
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
            logger.warning("🧹 Self-heal: Cleaning old records...")
            
            from infrastructure.repositories import repos
            
            deleted = repos.prediction.delete_old(retention_days=30)
            
            if deleted > 0:
                logger.info(f"✅ Self-heal: Deleted {deleted} old predictions")
                self._mark_attempt("quota_clean")
                return True
            
            return False
        
        except Exception as e:
            logger.error(f"❌ Self-heal quota clean error: {e}")
            return False
    
    # ============================================================
    # Runtime Config Reset
    # ============================================================
    
    def _should_reset_config(self, metrics: Dict[str, Any]) -> bool:
        """آیا runtime config باید reset بشه؟"""
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
            logger.warning("🔄 Self-heal: Resetting runtime config...")
            
            result = self.model_manager.reset_runtime_config()
            
            if result.get("success"):
                logger.info("✅ Self-heal: Runtime config reset")
                self._mark_attempt("config_reset")
                return True
            
            return False
        
        except Exception as e:
            logger.error(f"❌ Self-heal reset config error: {e}")
            return False
    
    # ============================================================
    # Attempts Management
    # ============================================================
    
    def _check_attempts(
        self,
        key: str,
        cooldown_minutes: Optional[int] = None,
    ) -> bool:
        """بررسی امکان تلاش مجدد"""
        cooldown = cooldown_minutes or self.cooldown_minutes
        
        entry = self.healing_attempts.get(key, {})
        count = entry.get("count", 0)
        
        if count >= self.max_attempts:
            logger.debug(f"⏭️ {key}: max attempts reached ({count})")
            return False
        
        last = entry.get("last_attempt")
        if last:
            try:
                last_dt = datetime.fromisoformat(last)
                next_attempt = last_dt + timedelta(minutes=cooldown)
                
                if datetime.now() < next_attempt:
                    remaining = (next_attempt - datetime.now()).total_seconds()
                    logger.debug(
                        f"⏭️ {key}: cooldown ({int(remaining)}s remaining)"
                    )
                    return False
            except (ValueError, TypeError):
                pass
        
        return True
    
    def _mark_attempt(self, key: str) -> None:
        """ثبت تلاش"""
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
            "recalibrate_cooldown_minutes": self.RECALIBRATE_COOLDOWN_MINUTES,
            "startup_time": self._startup_time.isoformat(),
            "trainer": trainer_stats,
            "model": model_stats,
            "timestamp": datetime.now().isoformat(),
        }
    
    def reset_attempts(self) -> None:
        """بازنشانی تلاش‌ها"""
        self.healing_attempts.clear()
        self._startup_time = datetime.now()
        logger.info("✅ Self-heal: All attempts reset")
    
    # ============================================================
    # Manual Healing (API)
    # ============================================================
    
    def force_recalibrate(
        self,
        profile_name: str = "fast",
        period: str = "1m",
    ) -> Dict[str, Any]:
        """کالیبراسیون اجباری"""
        logger.warning(
            f"🔄 Self-heal: Force recalibrate requested "
            f"(profile={profile_name}, period={period})"
        )
        
        # reset attempts
        self.healing_attempts.pop("recalibrate", None)
        self.healing_attempts.pop("recalibrate_zero_accuracy", None)
        
        result = self.trainer.calibrate(
            period=period,
            profile_name=profile_name,
            save=True,
        )
        
        if result.get("success"):
            self._mark_attempt("recalibrate")
            logger.info(
                f"✅ Self-heal: Force recalibrate succeeded "
                f"(score={result.get('best_score', 0):.4f})"
            )
        else:
            logger.error(
                f"❌ Self-heal: Force recalibrate failed: "
                f"{result.get('error', 'unknown')}"
            )
        
        return result
    
    def force_reload_engine(self) -> Dict[str, Any]:
        """بارگذاری اجباری engine"""
        logger.warning("🔄 Self-heal: Force engine reload requested")
        
        self.healing_attempts.pop("engine_reload", None)
        
        success = self._reload_engine()
        
        result = {
            "success": success,
            "engine_loaded": self.model_manager.engine is not None,
            "version": self.model_manager.current_version,
        }
        
        if success:
            logger.info("✅ Self-heal: Force reload succeeded")
        else:
            logger.error("❌ Self-heal: Force reload failed")
        
        return result


__all__ = ["SelfHealer"]
