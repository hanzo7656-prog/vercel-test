# application/use_cases/get_health.py
# ============================================================
# Use Case: Get Health (دریافت سلامت سیستم)
# ============================================================

import logging
from typing import Dict, Any, Optional
from datetime import datetime

from domain.interfaces.api_client import APIClient
from models.manager.model_manager import ModelManager
from core.metrics import metrics_scheduler
# ✅ اصلاح Import
from infrastructure.database import health_check as db_health_check

logger = logging.getLogger(__name__)


class GetHealthUseCase:
    """
    Use Case دریافت سلامت سیستم
    
    مسئولیت:
        - بررسی وضعیت API
        - بررسی وضعیت مدل
        - بررسی وضعیت دیتابیس‌ها
        - بررسی وضعیت متریک‌ها
    """
    
    def __init__(
        self,
        api_client: APIClient,
        model_manager: ModelManager
    ):
        self.api_client = api_client
        self.model_manager = model_manager
        
        logger.info("✅ GetHealthUseCase initialized")
    
    def execute(self) -> Dict[str, Any]:
        """
        اجرای Use Case دریافت سلامت
        
        خروجی:
            دیکشنری وضعیت سلامت
        """
        status: Dict[str, Any] = {
            'status': 'ok',
            'timestamp': datetime.now().isoformat(),
            'components': {}
        }
        
        # 1. سلامت API
        status['components']['api'] = self._check_api()
        if status['components']['api']['status'] == 'unhealthy':
            status['status'] = 'degraded'
        
        # 2. سلامت مدل
        status['components']['model'] = self._check_model()
        if status['components']['model']['status'] == 'degraded' and status['status'] == 'ok':
            status['status'] = 'degraded'
        
        # 3. سلامت دیتابیس
        status['components']['databases'] = self._check_databases()
        if status['components']['databases']['status'] == 'degraded':
            status['status'] = 'degraded'
        
        # 4. سلامت متریک‌ها
        status['components']['metrics'] = self._check_metrics()
        
        # 5. اعتبار API
        status['components']['credits'] = self._check_credits()
        
        # 6. وضعیت Threadها
        status['components']['threads'] = self._check_threads()
        
        return status
    
    def _check_api(self) -> Dict[str, Any]:
        """بررسی سلامت API"""
        try:
            api_status = self.api_client.get_status()
            if api_status and api_status.get('status') == 'ok':
                return {
                    'status': 'healthy',
                    'message': 'اتصال به API برقرار است'
                }
            else:
                return {
                    'status': 'degraded',
                    'message': 'API در دسترس نیست'
                }
        except Exception as e:
            logger.error(f"API health check error: {e}")
            return {
                'status': 'unhealthy',
                'message': f'خطا در اتصال به API: {str(e)}'
            }
    
    def _check_model(self) -> Dict[str, Any]:
        """بررسی سلامت مدل"""
        stats = self.model_manager.get_stats() if self.model_manager else {}
        loaded = stats.get('loaded', False)
        
        return {
            'status': 'healthy' if loaded else 'degraded',
            'message': 'مدل بارگذاری شده است' if loaded else 'حالت DEMO (بدون مدل)',
            'mode': 'BETA' if loaded else 'DEMO',
            'version': stats.get('version', 'unknown')
        }
    
    def _check_databases(self) -> Dict[str, Any]:
        """بررسی سلامت دیتابیس"""
        try:
            health = db_health_check()
            
            primary_ok = health.get('postgresql', {}).get('connected', False)
            cache_ok = health.get('redis', {}).get('connected', False)
            backup_ok = health.get('sqlite', {}).get('connected', False)
            
            all_ok = primary_ok and cache_ok and backup_ok
            
            return {
                'status': 'healthy' if all_ok else 'degraded',
                'primary': primary_ok,
                'cache': cache_ok,
                'backup': backup_ok
            }
        except Exception as e:
            logger.error(f"Database health check error: {e}")
            return {
                'status': 'unknown',
                'message': str(e)
            }
    
    def _check_metrics(self) -> Dict[str, Any]:
        """بررسی سلامت متریک‌ها"""
        try:
            summary = metrics_scheduler.get_summary()
            return {
                'status': 'healthy' if summary.get('status') == 'running' else 'degraded',
                'collections': summary.get('total_collections', 0),
                'errors': summary.get('errors', 0),
                'last_collection': summary.get('last_collection')
            }
        except Exception as e:
            logger.error(f"Metrics health check error: {e}")
            return {
                'status': 'unknown',
                'message': str(e)
            }
    
    def _check_credits(self) -> Dict[str, Any]:
        """بررسی اعتبار API"""
        try:
            credits = self.api_client.get_credits()
            if credits and 'remainingCredits' in credits:
                remaining = credits.get('remainingCredits', 0)
                return {
                    'status': 'healthy' if remaining > 100 else 'warning' if remaining > 10 else 'critical',
                    'remaining': remaining,
                    'total': credits.get('totalCredits'),
                    'used': credits.get('usedCredits')
                }
            return {
                'status': 'unknown',
                'message': 'No credit data available'
            }
        except Exception as e:
            logger.error(f"Credits check error: {e}")
            return {
                'status': 'unknown',
                'message': str(e)
            }
    
    def _check_threads(self) -> Dict[str, Any]:
        """بررسی وضعیت Threadها"""
        try:
            from core.threading_manager import threading_manager
            summary = threading_manager.get_summary()
            return {
                'status': 'healthy' if summary.get('errors', 0) == 0 else 'degraded',
                'total': summary.get('total_threads', 0),
                'running': summary.get('running', 0),
                'errors': summary.get('errors', 0),
                'threads': summary.get('threads', {})
            }
        except Exception as e:
            logger.error(f"Threads check error: {e}")
            return {
                'status': 'unknown',
                'message': str(e)
            }
