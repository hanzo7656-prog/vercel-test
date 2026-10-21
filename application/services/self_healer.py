# application/services/self_healer.py
# ============================================================
# SelfHealer - نسخه ۲.۰ (Gemini-aware)
# ============================================================
# 
# تغییرات نسخه ۲.۰:
#   - _reload_engine, _recalibrate_weights, _reset_runtime_config حذف شد
#   - _clear_cache بهبود (بر اساس Redis usage نه RAM)
#   - _restart_modules حفظ
#   - _clean_quota بهبود (prediction + OHLCV)
#   - _check_gemini اضافه (فقط alert، بدون ترمیم)
# ============================================================

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Union

from domain.interfaces.api_client import APIClient
from infrastructure.database import get_cache, get_primary

logger = logging.getLogger(__name__)


class SelfHealer:
    """
    سیستم خودترمیمی - نسخه ۲.۰ (Gemini-aware)
    
    قابلیت‌ها:
        ۱. Gemini health check (alert-only)
        ۲. Cache clear (اگه Redis usage بالا)
        ۳. Restart modules (DB reconnect + API session)
        ۴. Quota cleanup (predictions + OHLCV)
    """
    
    # ============================================================
    # Constants
    # ============================================================
    
    # حداکثر تلاش
    MAX_ATTEMPTS: int = 3
    
    # Cooldown بین تلاش‌ها (دقیقه)
    COOLDOWN_MINUTES: int = 30
    
    # Cooldown برای cache clear (سخت‌گیرانه‌تر — ۱۵ دقیقه)
    CACHE_CLEAR_COOLDOWN_MINUTES: int = 15
    
    # Cooldown برای quota cleanup (۱ ساعت)
    QUOTA_CLEAN_COOLDOWN_MINUTES: int = 60
    
    # آستانه RAM برای cache clear (درصد)
    RAM_THRESHOLD: float = 85.0
    
    # آستانه Redis usage برای cache clear (درصد)
    REDIS_USAGE_THRESHOLD: float = 90.0
    
    # حداقل رکورد برای quota cleanup
    PREDICTIONS_CLEANUP_THRESHOLD: int = 100_000
    OHLCV_CLEANUP_THRESHOLD: int = 1_000_000
    
    # Retention روز برای cleanup
    PREDICTIONS_RETENTION_DAYS: int = 30
    OHLCV_RETENTION_DAYS: int = 90
    
    # ============================================================
    # Init
    # ============================================================
    
    def __init__(
        self,
        api_client: Optional[APIClient] = None,
    ) -> None:
        self.api_client = api_client
        
        # آمار healing
        self.healing_attempts: Dict[str, Dict[str, Union[int, str]]] = {}
        self.max_attempts: int = self.MAX_ATTEMPTS
        self.cooldown_minutes: int = self.COOLDOWN_MINUTES
        
        # Track startup time
        self._startup_time: datetime = datetime.now()
        
        # قفل ساده
        self._is_healing: bool = False
        
        logger.info("✅ SelfHealer v2.0 initialized (Gemini-aware)")
    
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
            "ai_status": {},
            "databases": {"postgresql": False, "redis": False, "archive": False},
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
                "gemini_alerted": False,       # 🆕 فقط alert
                "cache_cleared": False,
                "modules_restarted": [],
                "quota_cleaned": False,
                "prediction_cleaned": 0,
                "ohlcv_cleaned": 0,
            }
            
            # ۱. Gemini check (alert-only) 🆕
            if self._should_alert_gemini(metrics):
                actions["gemini_alerted"] = self._alert_gemini(metrics)
            
            # ۲. Cache
            if self._should_clear_cache(metrics):
                actions["cache_cleared"] = self._clear_cache()
            
            # ۳. Modules
            restarted = self._restart_modules(metrics)
            if restarted:
                actions["modules_restarted"] = restarted
            
            # ۴. Quota (Prediction)
            if self._should_clean_predictions(metrics):
                actions["prediction_cleaned"] = self._clean_predictions()
            
            # ۵. Quota (OHLCV) 🆕
            if self._should_clean_ohlcv(metrics):
                actions["ohlcv_cleaned"] = self._clean_ohlcv()
            
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
        if isinstance(value, int):
            return value > 0
        if isinstance(value, list):
            return len(value) > 0
        return bool(value)
    
    # ============================================================
    # Gemini (alert-only) 🆕
    # ============================================================
    
    def _should_alert_gemini(self, metrics: Dict[str, Any]) -> bool:
        """آیا Gemini نیاز به alert داره؟"""
        ai_status = metrics.get("ai_status", {})
        if not isinstance(ai_status, dict):
            return False
        
        # اگه available=False → alert
        if not ai_status.get("available", True):
            return self._check_attempts(
                "gemini_alert",
                cooldown_minutes=30,
            )
        
        return False
    
    def _alert_gemini(self, metrics: Dict[str, Any]) -> bool:
        """alert برای Gemini (بدون ترمیم)"""
        try:
            logger.warning("⚠️ Self-heal: Gemini unavailable, sending alert")
            
            from infrastructure.external.alerter import alerter
            alerter.check_and_alert({
                "level": "warning",
                "source": "self_healer",
                "message": "Gemini unavailable — check GEMINI_API_KEY",
                "component": "ai",
            })
            
            self._mark_attempt("gemini_alert")
            return True
        
        except Exception as e:
            logger.error(f"❌ Self-heal Gemini alert error: {e}")
            return False
    
    # ============================================================
    # Cache
    # ============================================================
    
    def _should_clear_cache(self, metrics: Dict[str, Any]) -> bool:
        """
        آیا cache باید پاک بشه؟
        
        دو شرط:
            - RAM > 85%
            - Redis usage > 90% (اگه cache_manager آمار بده)
        """
        ram = float(metrics.get("ram", 0))
        
        if ram > self.RAM_THRESHOLD:
            return self._check_attempts(
                "cache_clear",
                cooldown_minutes=self.CACHE_CLEAR_COOLDOWN_MINUTES,
            )
        
        # چک Redis usage 🆕
        try:
            from infrastructure.api.cache_manager import cache_manager
            stats = cache_manager.get_stats()
            usage = stats.get("command_usage_percent", 0)
            
            if usage > self.REDIS_USAGE_THRESHOLD:
                return self._check_attempts(
                    "cache_clear",
                    cooldown_minutes=self.CACHE_CLEAR_COOLDOWN_MINUTES,
                )
        except Exception as e:
            logger.debug(f"Cache usage check error: {e}")
        
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
    # Prediction Cleanup
    # ============================================================
    
    def _should_clean_predictions(self, metrics: Dict[str, Any]) -> bool:
        """آیا prediction‌ها باید پاک بشن؟"""
        try:
            from infrastructure.repositories import repos
            stats = repos.prediction.get_stats()
            total = stats.get("total", 0)
            
            if total > self.PREDICTIONS_CLEANUP_THRESHOLD:
                return self._check_attempts(
                    "prediction_clean",
                    cooldown_minutes=self.QUOTA_CLEAN_COOLDOWN_MINUTES,
                )
        except Exception as e:
            logger.debug(f"Prediction stats check error: {e}")
        
        return False
    
    def _clean_predictions(self) -> int:
        """پاک کردن prediction‌های قدیمی"""
        try:
            logger.warning("🧹 Self-heal: Cleaning old predictions...")
            
            from infrastructure.repositories import repos
            deleted = repos.prediction.delete_old(
                retention_days=self.PREDICTIONS_RETENTION_DAYS,
            )
            
            if deleted > 0:
                logger.info(f"✅ Self-heal: Deleted {deleted} old predictions")
                self._mark_attempt("prediction_clean")
                return deleted
            
            return 0
        
        except Exception as e:
            logger.error(f"❌ Self-heal prediction clean error: {e}")
            return 0
    
    # ============================================================
    # OHLCV Cleanup 🆕
    # ============================================================
    
    def _should_clean_ohlcv(self, metrics: Dict[str, Any]) -> bool:
        """آیا OHLCV باید پاک بشه؟"""
        try:
            from infrastructure.repositories import repos
            stats = repos.ohlcv.get_stats()
            total = stats.get("total_records", 0)
            
            if total > self.OHLCV_CLEANUP_THRESHOLD:
                return self._check_attempts(
                    "ohlcv_clean",
                    cooldown_minutes=self.QUOTA_CLEAN_COOLDOWN_MINUTES,
                )
        except Exception as e:
            logger.debug(f"OHLCV stats check error: {e}")
        
        return False
    
    def _clean_ohlcv(self) -> int:
        """پاک کردن OHLCV‌های قدیمی"""
        try:
            logger.warning("🧹 Self-heal: Cleaning old OHLCV...")
            
            from infrastructure.repositories import repos
            
            # قبل و بعد
            before_stats = repos.ohlcv.get_stats()
            before_count = before_stats.get("total_records", 0)
            
            repos.ohlcv.cleanup_old(
                retention_days=self.OHLCV_RETENTION_DAYS,
            )
            
            after_stats = repos.ohlcv.get_stats()
            after_count = after_stats.get("total_records", 0)
            
            deleted = before_count - after_count
            
            if deleted > 0:
                logger.info(f"✅ Self-heal: Deleted {deleted} old OHLCV records")
                self._mark_attempt("ohlcv_clean")
                return deleted
            
            return 0
        
        except Exception as e:
            logger.error(f"❌ Self-heal OHLCV clean error: {e}")
            return 0
    
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
        # ─── Gemini status ───
        gemini_status: Dict[str, Any] = {}
        try:
            from container import container
            gemini = container.get('gemini_client')
            if gemini:
                stats = gemini.get_stats()
                gemini_status = {
                    "available": gemini.is_available,
                    "total_requests": stats.get("total_requests", 0),
                    "success_rate": stats.get("success_rate", 0),
                    "last_error": stats.get("last_error"),
                }
        except Exception as e:
            logger.debug(f"Gemini status error: {e}")
        
        return {
            "attempts": self.healing_attempts,
            "max_attempts": self.max_attempts,
            "cooldown_minutes": self.cooldown_minutes,
            "cache_clear_cooldown_minutes": self.CACHE_CLEAR_COOLDOWN_MINUTES,
            "quota_clean_cooldown_minutes": self.QUOTA_CLEAN_COOLDOWN_MINUTES,
            "startup_time": self._startup_time.isoformat(),
            "gemini": gemini_status,
            "thresholds": {
                "ram": self.RAM_THRESHOLD,
                "redis_usage": self.REDIS_USAGE_THRESHOLD,
                "predictions_cleanup": self.PREDICTIONS_CLEANUP_THRESHOLD,
                "ohlcv_cleanup": self.OHLCV_CLEANUP_THRESHOLD,
            },
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
    
    def force_clear_cache(self) -> Dict[str, Any]:
        """پاک کردن اجباری cache"""
        logger.warning("🔄 Self-heal: Force cache clear requested")
        
        self.healing_attempts.pop("cache_clear", None)
        
        success = self._clear_cache()
        
        return {
            "success": success,
            "action": "cache_clear",
        }
    
    def force_clean_predictions(self) -> Dict[str, Any]:
        """پاک کردن اجباری prediction‌های قدیمی"""
        logger.warning("🔄 Self-heal: Force prediction clean requested")
        
        self.healing_attempts.pop("prediction_clean", None)
        
        deleted = self._clean_predictions()
        
        return {
            "success": deleted > 0,
            "deleted": deleted,
            "action": "prediction_clean",
        }
    
    def force_clean_ohlcv(self) -> Dict[str, Any]:
        """پاک کردن اجباری OHLCV قدیمی"""
        logger.warning("🔄 Self-heal: Force OHLCV clean requested")
        
        self.healing_attempts.pop("ohlcv_clean", None)
        
        deleted = self._clean_ohlcv()
        
        return {
            "success": deleted > 0,
            "deleted": deleted,
            "action": "ohlcv_clean",
        }
    
    def force_reconnect_databases(self) -> Dict[str, Any]:
        """reconnect اجباری همه DBها"""
        logger.warning("🔄 Self-heal: Force DB reconnect requested")
        
        try:
            from infrastructure.database.database_factory import db_factory
            result = db_factory.force_reconnect()
            
            success_count = sum(1 for v in result.values() if v)
            return {
                "success": success_count > 0,
                "reconnected": result,
                "success_count": success_count,
                "total": len(result),
            }
        except Exception as e:
            logger.error(f"❌ Force reconnect error: {e}")
            return {"success": False, "error": str(e)}


__all__ = ["SelfHealer"]
