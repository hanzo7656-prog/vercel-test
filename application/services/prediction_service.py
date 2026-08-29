# application/services/prediction_service.py
# ============================================================
# Service: Prediction Service (سرویس پیش‌بینی)
# ============================================================

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

from domain.entities.prediction import Prediction
from domain.interfaces.api_client import APIClient
from application.use_cases.predict_coin import PredictCoinUseCase
from application.dto.prediction_dto import PredictionDTO, PredictionRequestDTO

logger = logging.getLogger(__name__)


class PredictionService:
    """
    سرویس پیش‌بینی - Orchestrator Use Cases
    
    مسئولیت:
        - هماهنگی Use Cases پیش‌بینی
        - تبدیل DTOها
        - مدیریت خطاها
        - کش (در آینده)
    """
    
    def __init__(self, predict_use_case: PredictCoinUseCase):
        self.predict_use_case = predict_use_case
        
        # کش ساده (برای آینده)
        self._cache: Dict[str, Dict] = {}
        self._cache_ttl: int = 300  # ۵ دقیقه
        
        logger.info("✅ PredictionService initialized")
    
    def predict_single(
        self,
        coin: str = "bitcoin",
        period: str = "24h"
    ) -> PredictionDTO:
        """
        پیش‌بینی یک ارز
        
        پارامترها:
            coin: شناسه ارز
            period: بازه زمانی
        
        خروجی:
            PredictionDTO
        """
        try:
            # اعتبارسنجی
            if not coin or coin.strip() == '':
                return PredictionDTO.from_error("Coin ID cannot be empty")
            
            # اجرای Use Case
            prediction = self.predict_use_case.execute(coin, period)
            
            # تبدیل به DTO
            return PredictionDTO.from_prediction(prediction)
            
        except ValueError as e:
            logger.warning(f"Validation error in predict_single: {e}")
            return PredictionDTO.from_error(str(e))
        except Exception as e:
            logger.error(f"Error in predict_single: {e}", exc_info=True)
            return PredictionDTO.from_error(f"Prediction failed: {str(e)}")
    
    def predict_multiple(
        self,
        coins: List[str],
        period: str = "24h"
    ) -> PredictionDTO:
        """
        پیش‌بینی چند ارز
        
        پارامترها:
            coins: لیست شناسه ارزها
            period: بازه زمانی
        
        خروجی:
            PredictionDTO
        """
        try:
            if not coins:
                return PredictionDTO.from_error("Coin list cannot be empty")
            
            # اجرای Use Case
            predictions = self.predict_use_case.execute_multiple(coins, period)
            
            # تبدیل به DTO
            return PredictionDTO.from_predictions(predictions)
            
        except Exception as e:
            logger.error(f"Error in predict_multiple: {e}", exc_info=True)
            return PredictionDTO.from_error(f"Multiple prediction failed: {str(e)}")
    
    def predict_from_request(self, request: PredictionRequestDTO) -> PredictionDTO:
        """
        پیش‌بینی از روی DTO درخواست
        
        پارامترها:
            request: PredictionRequestDTO
        
        خروجی:
            PredictionDTO
        """
        if request.is_multiple():
            return self.predict_multiple(request.coins, request.period)
        else:
            return self.predict_single(request.coin, request.period)
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """دریافت آمار کش"""
        return {
            'cache_size': len(self._cache),
            'cache_ttl': self._cache_ttl,
            'timestamp': datetime.now().isoformat()
        }
    
    def clear_cache(self) -> None:
        """پاک کردن کش"""
        self._cache.clear()
        logger.info("✅ Prediction cache cleared")
