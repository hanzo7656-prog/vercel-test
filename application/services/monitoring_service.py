# application/services/monitoring_service.py
# ============================================================
# Service: Monitoring Service (سرویس مانیتورینگ)
# ============================================================

import logging
from typing import Dict, Any, Optional
from datetime import datetime

from domain.interfaces.api_client import APIClient
from application.use_cases.get_health import GetHealthUseCase
from core.metrics import metrics_scheduler
from core.threading_manager import threading_manager

logger = logging.getLogger(__name__)


class MonitoringService:
    """
    سرویس مانیتورینگ - Orchestrator Use Cases
    
    مسئولیت:
        - دریافت سلامت سیستم
        - دریافت متریک‌ها
        - مدیریت وضعیت
    """
    
    def __init__(self, health_use_case: GetHealthUseCase):
        self.health_use_case = health_use_case
        
        logger.info("✅ MonitoringService initialized")
    
    # application/services/monitoring_service.py
    def get_health(self):
        try:
            # بررسی دیتابیس‌ها با timeout
            from infrastructure.database import health_check
            health = health_check()
            return {
                'status': 'ok' if all(info.get('connected') for info in health.values()) else 'degraded',
                'components': health
            }
        except Exception as e:
            return {'status': 'error', 'error': str(e)}
    
    def get_metrics(self) -> Dict[str, Any]:
        """
        دریافت متریک‌های لحظه‌ای
        
        خروجی:
            دیکشنری متریک‌ها
        """
        try:
            metrics = metrics_scheduler.get_metrics()
            return {
                'success': True,
                'data': metrics,
                'timestamp': datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"Error getting metrics: {e}")
            return {
                'success': False,
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }
    
    def get_metrics_summary(self) -> Dict[str, Any]:
        """
        دریافت خلاصه متریک‌ها
        
        خروجی:
            دیکشنری خلاصه متریک‌ها
        """
        try:
            summary = metrics_scheduler.get_summary()
            return {
                'success': True,
                'data': summary,
                'timestamp': datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"Error getting metrics summary: {e}")
            return {
                'success': False,
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }
    
    def get_dashboard_metrics(self) -> Dict[str, Any]:
        """
        دریافت متریک‌های داشبورد
        
        خروجی:
            دیکشنری متریک‌های داشبورد
        """
        try:
            data = metrics_scheduler.get_dashboard_metrics()
            return {
                'success': True,
                'data': data,
                'timestamp': datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"Error getting dashboard metrics: {e}")
            return {
                'success': False,
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }
    
    def get_thread_status(self) -> Dict[str, Any]:
        """
        دریافت وضعیت Threadها
        
        خروجی:
            دیکشنری وضعیت Threadها
        """
        try:
            summary = threading_manager.get_summary()
            return {
                'success': True,
                'data': summary,
                'timestamp': datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"Error getting thread status: {e}")
            return {
                'success': False,
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }
    
    def get_api_stats(self, api_client: APIClient) -> Dict[str, Any]:
        """
        دریافت آمار API
        
        پارامترها:
            api_client: کلاینت API
        
        خروجی:
            دیکشنری آمار API
        """
        try:
            stats = api_client.get_stats()
            return {
                'success': True,
                'data': stats,
                'timestamp': datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"Error getting API stats: {e}")
            return {
                'success': False,
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }
