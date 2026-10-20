# application/use_cases/get_health.py
# ============================================================
# Use Case: Get Health - نسخه ۳.۰
# Gemini-aware + بدون RuleEngine
# ============================================================
# 
# تغییرات نسخه ۳.۰:
#   - _check_model حذف شد (RuleEngine legacy)
#   - _check_rule_config حذف شد
#   - _check_ai اضافه شد (Gemini health)
#   - فقط اجزای واقعی: api, gemini, databases, metrics, credits, threads
# ============================================================

import logging
from typing import Dict, Any, Optional
from datetime import datetime

from domain.interfaces.api_client import APIClient
from core.metrics import metrics_scheduler
from infrastructure.database import health_check as db_health_check

logger = logging.getLogger(__name__)


class GetHealthUseCase:
    """
    Use Case دریافت سلامت سیستم
    
    مسئولیت:
        - بررسی وضعیت API (CoinStats)
        - بررسی وضعیت Gemini
        - بررسی وضعیت دیتابیس‌ها
        - بررسی وضعیت متریک‌ها
        - بررسی Threadها
        - بررسی اعتبار API
    """
    
    def __init__(
        self,
        api_client: APIClient,
    ) -> None:
        self.api_client = api_client
        
        logger.info("✅ GetHealthUseCase v3.0 initialized (Gemini-aware)")
    
    # ============================================================
    # Main Execute
    # ============================================================
    
    def execute(self) -> Dict[str, Any]:
        """اجرای Use Case دریافت سلامت"""
        status: Dict[str, Any] = {
            "status": "ok",
            "timestamp": datetime.now().isoformat(),
            "components": {},
        }
        
        # ۱. API (CoinStats)
        status["components"]["api"] = self._check_api()
        if status["components"]["api"]["status"] == "unhealthy":
            status["status"] = "degraded"
        
        # ۲. AI (Gemini) 🆕
        status["components"]["ai"] = self._check_ai()
        ai_status = status["components"]["ai"].get("status")
        if ai_status == "unhealthy" and status["status"] == "ok":
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
        
        return status
    
    # ============================================================
    # API (CoinStats)
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
    # AI (Gemini) 🆕
    # ============================================================
    
    def _check_ai(self) -> Dict[str, Any]:
        """بررسی سلامت Gemini"""
        try:
            from container import container
            
            gemini_client = container.get('gemini_client')
            if gemini_client is None:
                return {
                    "status": "unhealthy",
                    "message": "Gemini client not initialized",
                }
            
            if not gemini_client.is_available:
                return {
                    "status": "unhealthy",
                    "message": "GEMINI_API_KEY missing or invalid",
                }
            
            stats = gemini_client.get_stats()
            
            return {
                "status": "healthy",
                "message": "Gemini client ready",
                "model_default": stats.get("model_default", "gemini-3.8-flash"),
                "total_requests": stats.get("total_requests", 0),
                "success_rate": stats.get("success_rate", 0),
                "last_request_at": stats.get("last_request_at"),
            }
        
        except Exception as e:
            logger.error(f"AI health check error: {e}")
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
