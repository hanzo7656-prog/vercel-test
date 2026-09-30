# application/services/monitoring_service.py
# ============================================================
# Service: Monitoring Service - نسخه ۴.۰
# OHLCV-aware + RuleEngine stats + لاگ کامل
# ============================================================

import logging
from datetime import datetime
from typing import Dict, Any, Optional

from domain.interfaces.api_client import APIClient
from application.use_cases.get_health import GetHealthUseCase
from core.metrics import metrics_scheduler
from core.threading_manager import threading_manager

logger = logging.getLogger(__name__)


class MonitoringService:
    """
    سرویس مانیتورینگ - نسخه ۴.۰
    
    تغییرات:
        - OHLCV stats از api_client
        - RuleEngine-aware repository stats
        - لاگ کامل
    """
    
    def __init__(self, health_use_case: GetHealthUseCase):
        self.health_use_case = health_use_case
        
        logger.info("✅ MonitoringService v4.0 initialized")
    
    # ============================================================
    # Health
    # ============================================================
    
    def get_health(self) -> Dict[str, Any]:
        """سلامت سیستم"""
        try:
            from infrastructure.database import health_check
            
            logger.debug("🔍 Monitoring: health check started")
            
            health = health_check()
            
            all_ok = all(
                info.get("connected", False)
                for info in health.values()
            )
            
            status = "ok" if all_ok else "degraded"
            logger.debug(f"✅ Monitoring: health check done ({status})")
            
            return {
                "status": status,
                "components": health,
                "timestamp": datetime.now().isoformat(),
            }
        
        except Exception as e:
            logger.error(f"❌ Monitoring health error: {e}", exc_info=True)
            return {
                "status": "error",
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            }
    
    # ============================================================
    # Metrics
    # ============================================================
    
    def get_metrics(self) -> Dict[str, Any]:
        """متریک‌های لحظه‌ای"""
        try:
            metrics = metrics_scheduler.get_metrics()
            return {
                "success": True,
                "data": metrics,
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            logger.error(f"❌ Monitoring metrics error: {e}")
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
            logger.error(f"❌ Monitoring metrics summary error: {e}")
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
            logger.error(f"❌ Monitoring dashboard metrics error: {e}")
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            }
    
    # ============================================================
    # Quota
    # ============================================================
    
    def get_quota_stats(self) -> Dict[str, Any]:
        """آمار Quota"""
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
            logger.error(f"❌ Monitoring quota stats error: {e}")
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            }
    
    # ============================================================
    # Repository Stats (RuleEngine-aware)
    # ============================================================
    
    def get_repository_stats(self) -> Dict[str, Any]:
        """آمار Repositoryها"""
        try:
            from infrastructure.repositories import repos
            
            logger.debug("🔍 Monitoring: repository stats started")
            
            model_stats: Dict[str, Any] = {}
            prediction_stats: Dict[str, Any] = {}
            rule_config_stats: Dict[str, Any] = {}
            
            try:
                model_stats = repos.model.get_stats()
            except Exception as e:
                logger.debug(f"Model stats error: {e}")
                model_stats = {"error": str(e)}
            
            try:
                prediction_stats = repos.prediction.get_stats()
            except Exception as e:
                logger.debug(f"Prediction stats error: {e}")
                prediction_stats = {"error": str(e)}
            
            try:
                rule_config_stats = repos.rule_config.get_stats()
            except Exception as e:
                logger.debug(f"RuleConfig stats error: {e}")
                rule_config_stats = {"error": str(e)}
            
            logger.debug("✅ Monitoring: repository stats done")
            
            return {
                "success": True,
                "data": {
                    "models": model_stats,
                    "predictions": prediction_stats,
                    "rule_config": rule_config_stats,
                },
                "timestamp": datetime.now().isoformat(),
            }
        
        except Exception as e:
            logger.error(f"❌ Monitoring repository stats error: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            }
    
    # ============================================================
    # API Stats (🆕 OHLCV-aware)
    # ============================================================
    
    def get_api_stats(self, api_client: APIClient) -> Dict[str, Any]:
        """
        آمار API client
        
        شامل OHLCV stats جدید
        """
        try:
            stats = api_client.get_stats()
            
            # اضافه کردن OHLCV به‌صورت جداگانه اگه هست
            ohlcv_stats = {}
            if "ohlcv_requests" in stats:
                ohlcv_stats = {
                    "ohlcv_requests": stats.get("ohlcv_requests", 0),
                    "ohlcv_candles_total": stats.get("ohlcv_candles_total", 0),
                    "ohlcv_range_caps": stats.get("ohlcv_range_caps", 0),
                    "symbol_map_cached": stats.get("symbol_map_cached", False),
                }
            
            return {
                "success": True,
                "data": {
                    **stats,
                    "ohlcv": ohlcv_stats,
                },
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            logger.error(f"❌ Monitoring API stats error: {e}")
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
            logger.error(f"❌ Monitoring thread status error: {e}")
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            }
    
    # ============================================================
    # OHLCV Health (🆕)
    # ============================================================
    
    def check_ohlcv_health(self, api_client: APIClient) -> Dict[str, Any]:
        """
        بررسی سلامت endpoint OHLCV
        
        تست ساده: BTC/USDT 4h
        """
        try:
            logger.debug("🔍 Monitoring: OHLCV health check started")
            
            if not hasattr(api_client, "get_ohlcv_candles"):
                return {
                    "success": False,
                    "status": "unavailable",
                    "error": "get_ohlcv_candles not available",
                    "timestamp": datetime.now().isoformat(),
                }
            
            result = api_client.get_ohlcv_candles(
                exchange="Binance",
                pair="BTC/USDT",
                interval="4h",
                range="1w",
                use_cache=True,
            )
            
            if result and "candles" in result:
                candle_count = len(result.get("candles", []))
                return {
                    "success": True,
                    "status": "healthy",
                    "candle_count": candle_count,
                    "pair": "BTC/USDT",
                    "interval": "4h",
                    "timestamp": datetime.now().isoformat(),
                }
            
            return {
                "success": False,
                "status": "unhealthy",
                "error": result.get("error") if result else "no response",
                "timestamp": datetime.now().isoformat(),
            }
        
        except Exception as e:
            logger.error(f"❌ Monitoring OHLCV health error: {e}")
            return {
                "success": False,
                "status": "error",
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            }
