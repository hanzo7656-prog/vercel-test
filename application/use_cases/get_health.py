# application/use_cases/get_health.py
# ============================================================
# Use Case: Get Health - نسخه ۲.۰
# RuleEngine-aware + Full component check
# ============================================================
# 
# تغییرات نسخه ۲.۰:
#   - _check_model: چک RuleEngine (نه XGBoost)
#   - اضافه کردن وضعیت RuleConfig
#   - حفظ بقیه ساختار
# ============================================================

import logging
from typing import Dict, Any, Optional
from datetime import datetime

from domain.interfaces.api_client import APIClient
from models.manager.model_manager import ModelManager
from core.metrics import metrics_scheduler
from infrastructure.database import health_check as db_health_check

logger = logging.getLogger(__name__)


class GetHealthUseCase:
    """
    Use Case دریافت سلامت سیستم
    
    مسئولیت:
        - بررسی وضعیت API
        - بررسی وضعیت مدل (RuleEngine)
        - بررسی وضعیت دیتابیس‌ها
        - بررسی وضعیت متریک‌ها
        - بررسی Threadها
    """
    
    def __init__(
        self,
        api_client: APIClient,
        model_manager: ModelManager,
    ) -> None:
        self.api_client = api_client
        self.model_manager = model_manager
        
        logger.info("✅ GetHealthUseCase v2.0 initialized")
    
    # ============================================================
    # Main Execute
    # ============================================================
    
    def execute(self) -> Dict[str, Any]:
        """
        اجرای Use Case دریافت سلامت
        
        Returns:
            دیکشنری وضعیت سلامت
        """
        status: Dict[str, Any] = {
            "status": "ok",
            "timestamp": datetime.now().isoformat(),
            "components": {},
        }
        
        # ۱. API
        status["components"]["api"] = self._check_api()
        if status["components"]["api"]["status"] == "unhealthy":
            status["status"] = "degraded"
        
        # ۲. Model (RuleEngine)
        status["components"]["model"] = self._check_model()
        if (
            status["components"]["model"]["status"] == "degraded"
            and status["status"] == "ok"
        ):
            status["status"] = "degraded"
        
        # ۳. Databases
        status["components"]["databases"] = self._check_databases()
        if status["components"]["databases"]["status"] == "degraded":
            status["status"] = "degraded"
        
        # ۴. Metrics
        status["components"]["metrics"] = self._check_metrics()
        
        # ۵. Credits
        status["components"]["credits"] = self._check_credits()
        
        # ۶. Threads
        status["components"]["threads"] = self._check_threads()
        
        # ۷. 🆕 Rule Config
        status["components"]["rule_config"] = self._check_rule_config()
        
        return status
    
    # ============================================================
    # API
    # ============================================================
    
    def _check_api(self) -> Dict[str, Any]:
        """بررسی سلامت API"""
        try:
            api_status = self.api_client.get_status()
            if api_status and api_status.get("status") == "ok":
                return {
                    "status": "healthy",
                    "message": "اتصال به API برقرار است",
                }
            else:
                return {
                    "status": "degraded",
                    "message": "API در دسترس نیست",
                }
        except Exception as e:
            logger.error(f"API health check error: {e}")
            return {
                "status": "unhealthy",
                "message": f"خطا در اتصال به API: {str(e)[:100]}",
            }
    
    # ============================================================
    # Model (RuleEngine-aware)
    # ============================================================
    
    def _check_model(self) -> Dict[str, Any]:
        """
        بررسی سلامت مدل (RuleEngine)
        
        تغییرات v2.0:
            - چک RuleEngine (نه XGBoost)
            - اضافه کردن rule_count
            - اضافه کردن state
        """
        try:
            stats = self.model_manager.get_stats() if self.model_manager else {}
            
            engine_loaded = stats.get("loaded", False)
            engine_stats = stats.get("engine", {})
            rule_count = stats.get("rule_count", 0)
            
            return {
                "status": "healthy" if engine_loaded else "degraded",
                "message": (
                    f"RuleEngine بارگذاری شده ({rule_count} rule)"
                    if engine_loaded
                    else "RuleEngine بارگذاری نشده"
                ),
                "mode": "RULE_ENGINE",
                "version": stats.get("version", "default"),
                "rule_count": rule_count,
                "aggregation": engine_stats.get("aggregation", "weighted_sum"),
                "min_pass_score": engine_stats.get("min_pass_score", 0.55),
                "runtime_config_active": stats.get("runtime_config_active", False),
            }
        except Exception as e:
            logger.error(f"Model health check error: {e}")
            return {
                "status": "unknown",
                "message": f"خطا: {str(e)[:100]}",
            }
    
    # ============================================================
    # Databases
    # ============================================================
    
    def _check_databases(self) -> Dict[str, Any]:
        """بررسی سلامت دیتابیس"""
        try:
            health = db_health_check()
            
            primary_ok = health.get("postgresql", {}).get("connected", False)
            cache_ok = health.get("redis", {}).get("connected", False)
            backup_ok = health.get("sqlite", {}).get("connected", False)
            
            all_ok = primary_ok and cache_ok and backup_ok
            
            return {
                "status": "healthy" if all_ok else "degraded",
                "primary": primary_ok,
                "cache": cache_ok,
                "backup": backup_ok,
            }
        except Exception as e:
            logger.error(f"Database health check error: {e}")
            return {
                "status": "unknown",
                "message": str(e)[:100],
            }
    
    # ============================================================
    # Metrics
    # ============================================================
    
    def _check_metrics(self) -> Dict[str, Any]:
        """بررسی سلامت متریک‌ها"""
        try:
            summary = metrics_scheduler.get_summary()
            return {
                "status": (
                    "healthy"
                    if summary.get("status") == "running"
                    else "degraded"
                ),
                "collections": summary.get("total_collections", 0),
                "errors": summary.get("errors", 0),
                "last_collection": summary.get("last_collection"),
            }
        except Exception as e:
            logger.error(f"Metrics health check error: {e}")
            return {
                "status": "unknown",
                "message": str(e)[:100],
            }
    
    # ============================================================
    # Credits
    # ============================================================
    
    def _check_credits(self) -> Dict[str, Any]:
        """بررسی اعتبار API"""
        try:
            credits = self.api_client.get_credits()
            if credits and "remainingCredits" in credits:
                remaining = credits.get("remainingCredits", 0)
                
                if remaining > 100:
                    status = "healthy"
                elif remaining > 10:
                    status = "warning"
                else:
                    status = "critical"
                
                return {
                    "status": status,
                    "remaining": remaining,
                    "total": credits.get("totalCredits"),
                    "used": credits.get("usedCredits"),
                }
            
            return {
                "status": "unknown",
                "message": "No credit data available",
            }
        except Exception as e:
            logger.error(f"Credits check error: {e}")
            return {
                "status": "unknown",
                "message": str(e)[:100],
            }
    
    # ============================================================
    # Threads
    # ============================================================
    
    def _check_threads(self) -> Dict[str, Any]:
        """بررسی وضعیت Threadها"""
        try:
            from core.threading_manager import threading_manager
            summary = threading_manager.get_summary()
            
            errors = summary.get("errors", 0)
            
            return {
                "status": "healthy" if errors == 0 else "degraded",
                "total": summary.get("total_threads", 0),
                "running": summary.get("running", 0),
                "errors": errors,
                "threads": summary.get("threads", {}),
            }
        except Exception as e:
            logger.error(f"Threads check error: {e}")
            return {
                "status": "unknown",
                "message": str(e)[:100],
            }
    
    # ============================================================
    # Rule Config (🆕)
    # ============================================================
    
    def _check_rule_config(self) -> Dict[str, Any]:
        """
        بررسی سلامت RuleConfig Repository
        
        جدید در v2.0
        """
        try:
            from infrastructure.repositories import repos
            
            stats = repos.rule_config.get_stats()
            
            connected = stats.get("connected", False)
            override_count = stats.get("override_count", 0)
            
            return {
                "status": "healthy" if connected else "degraded",
                "connected": connected,
                "override_count": override_count,
                "table": stats.get("table", "rule_config_overrides"),
            }
        except Exception as e:
            logger.debug(f"RuleConfig check error: {e}")
            return {
                "status": "unknown",
                "message": str(e)[:100],
            }
