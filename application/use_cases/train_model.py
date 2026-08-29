# application/use_cases/train_model.py
# ============================================================
# Use Case: Train Model (آموزش مدل)
# ============================================================

import logging
from typing import Optional, Dict, Any, List
from datetime import datetime

from domain.interfaces.api_client import APIClient
from models.manager.model_manager import ModelManager
from models.trainer.auto_trainer import AutoTrainer

logger = logging.getLogger(__name__)


class TrainModelUseCase:
    """
    Use Case آموزش مدل
    
    مسئولیت:
        - دریافت داده‌ها از API
        - آموزش مدل با AutoTrainer
        - ذخیره مدل در دیتابیس
    """
    
    def __init__(
        self,
        api_client: APIClient,
        model_manager: ModelManager,
        trainer: AutoTrainer
    ):
        self.api_client = api_client
        self.model_manager = model_manager
        self.trainer = trainer
        
        logger.info("✅ TrainModelUseCase initialized")
    
    def execute(
        self,
        period: str = "1m",
        coins: Optional[List[str]] = None,
        incremental: bool = False
    ) -> Dict[str, Any]:
        """
        اجرای Use Case آموزش
        
        پارامترها:
            period: بازه زمانی
            coins: لیست ارزها (پیش‌فرض: ['bitcoin', 'ethereum'])
            incremental: آیا آموزش افزایشی است؟
        
        خروجی:
            نتیجه آموزش
        """
        if coins is None:
            coins = ['bitcoin', 'ethereum']
        
        logger.info(f"🔄 Starting training (period: {period}, coins: {coins}, incremental: {incremental})")
        
        try:
            if incremental and self.model_manager.current_model is not None:
                # آموزش افزایشی
                result = self.trainer.incremental_train(period=period)
            else:
                # آموزش کامل
                result = self.trainer.train_model(period=period)
            
            # افزودن اطلاعات اضافی
            result['timestamp'] = datetime.now().isoformat()
            result['coins_used'] = coins
            result['period'] = period
            
            logger.info(f"✅ Training completed: {result.get('success', False)}")
            
            return result
            
        except Exception as e:
            logger.error(f"❌ Training failed: {e}", exc_info=True)
            return {
                'success': False,
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }
    
    def execute_auto(self, interval_hours: int = 6, period: str = "1m") -> Dict[str, Any]:
        """
        شروع آموزش خودکار
        
        پارامترها:
            interval_hours: فاصله زمانی (ساعت)
            period: بازه زمانی
        
        خروجی:
            نتیجه شروع آموزش خودکار
        """
        result = self.trainer.start_auto_train(
            interval_hours=interval_hours,
            period=period
        )
        
        result['timestamp'] = datetime.now().isoformat()
        
        return result
    
    def stop_auto(self) -> Dict[str, Any]:
        """متوقف کردن آموزش خودکار"""
        result = self.trainer.stop_auto_train()
        result['timestamp'] = datetime.now().isoformat()
        return result
    
    def get_status(self) -> Dict[str, Any]:
        """دریافت وضعیت آموزش"""
        stats = self.trainer.get_stats() if hasattr(self.trainer, 'get_stats') else {}
        
        return {
            'is_training': stats.get('is_training', False),
            'is_running': stats.get('is_running', False),
            'model_loaded': self.model_manager.current_model is not None,
            'model_version': self.model_manager.current_version,
            'last_score': stats.get('stats', {}).get('last_score'),
            'total_trainings': stats.get('stats', {}).get('total_trainings', 0),
            'timestamp': datetime.now().isoformat()
        }
