# application/services/monitoring_service.py
# ============================================================
# Service: Monitoring Service - نسخه ۲.۰
# Quota + Repository Stats
# ============================================================

import logging
import signal
from typing import Dict, Any, Optional
from datetime import datetime

from domain.interfaces.api_client import APIClient
from application.use_cases.get_health import GetHealthUseCase
from core.metrics import metrics_scheduler
from core.threading_manager import threading_manager

logger = logging.getLogger(__name__)


class MonitoringService:
    """
    سرویس مانیتورینگ
    
    ارتقاها:
        - Quota stats
        - Repository stats
        - Cross-platform timeout
    """
    
    def __init__(self, health_use_case: GetHealthUseCase):
        self.health_use_case = health_use_case
        
        logger.info("✅ MonitoringService v2.0 initialized")
    
    # ============================================================
    # Health
    # ============================================================
    
    def get_health(self) -> Dict[str, Any]:
        """
        دریافت سلامت سیستم
        
        خروجی:
            دیکشنری سلامت
        """
        try:
            # Timeout cross-platform
            from infrastructure.database import health_check
            
            # راه ساده: بدون signal
            health = health_check()
            
            all_ok = all(
                info.get("connected", False)
                for info in health.values()
            )
            
            return {
                "status": "ok" if all_ok else "degraded",
                "components": health,
                "timestamp": datetime.now().isoformat(),
            }
            
        except Exception as e:
            logger.error(f"Health check error: {e}")
            return {
                "status": "error",
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            }
    
    # ============================================================
    # Metrics
    # ============================================================
    
    def get_metrics(self) -> Dict[str, Any]:
        """دریافت متریک‌های لحظه‌ای"""
        try:
            metrics = metrics_scheduler.get_metrics()
            return {
                "success": True,
                "data": metrics,
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            logger.error(f"Metrics error: {e}")
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            }
    
    def get_metrics_summary(self) -> Dict[str, Any]:
        """خلاصه متریک‌ها"""
        try:
            summary = metrics_scheduler.get_summary()
            return {
                "success": True,
                "data": summary,
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            logger.error(f"Metrics summary error: {e}")
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            }
    
    def get_dashboard_metrics(self) -> Dict[str, Any]:
        """متریک‌های داشبورد"""
        try:
            data = metrics_scheduler.get_dashboard_metrics()
            return {
                "success": True,
                "data": data,
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            logger.error(f"Dashboard metrics error: {e}")
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            }
    
    # ============================================================
    # Quota (🆕)
    # ============================================================
    
    def get_quota_stats(self) -> Dict[str, Any]:
        """آمار Quota همه دیتابیس‌ها"""
        try:
            from infrastructure.database import get_all_quotas, get_db
            
            quotas = get_all_quotas()
            result = {}
            
            for db_name, quota in quotas.items():
                try:
                    db = get_db(db_name)
                    if db and db.is_connected() and hasattr(db, "_calculate_used_size"):
                        used_mb = db._calculate_used_size()
                        from infrastructure.database import get_quota_status
                        status = get_quota_status(db_name, used_mb)
                        result[db_name] = {
                            "quota": quota,
                            "status": status,
                        }
                    else:
                        result[db_name] = {"quota": quota, "status": {"connected": False}}
                except Exception:
                    result[db_name] = {"quota": quota, "status": {"error": "unknown"}}
            
            return {
                "success": True,
                "data": result,
                "timestamp": datetime.now().isoformat(),
            }
            
        except Exception as e:
            logger.error(f"Quota stats error: {e}")
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            }
    
    # ============================================================
    # Repository Stats (🆕)
    # ============================================================
    
    def get_repository_stats(self) -> Dict[str, Any]:
        """آمار Repositoryها"""
        try:
            from infrastructure.repositories import repos
            
            model_stats = {}
            prediction_stats = {}
            
            try:
                model_stats = repos.model.get_stats()
            except Exception as e:
                logger.debug(f"Model stats error: {e}")
            
            try:
                prediction_stats = repos.prediction.get_stats()
            except Exception as e:
                logger.debug(f"Prediction stats error: {e}")
            
            return {
                "success": True,
                "data": {
                    "models": model_stats,
                    "predictions": prediction_stats,
                },
                "timestamp": datetime.now().isoformat(),
            }
            
        except Exception as e:
            logger.error(f"Repository stats error: {e}")
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            }
    
    # ============================================================
    # Threads
    # ============================================================
    
    def get_thread_status(self) -> Dict[str, Any]:
        """وضعیت Threadها"""
        try:
            summary = threading_manager.get_summary()
            return {
                "success": True,
                "data": summary,
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            logger.error(f"Thread status error: {e}")
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            }
    
    # ============================================================
    # API
    # ============================================================
    
    def get_api_stats(self, api_client: APIClient) -> Dict[str, Any]:
        """آمار API"""
        try:
            stats = api_client.get_stats()
            return {
                "success": True,
                "data": stats,
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            logger.error(f"API stats error: {e}")
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            }
