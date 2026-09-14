# application/services/prediction_service.py
# ============================================================
# Service: Prediction Service - نسخه ۲.۰
# Cache + Validation + Error Handling
# ============================================================

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

from domain.entities.prediction import Prediction
from application.use_cases.predict_coin import PredictCoinUseCase
from application.dto.prediction_dto import (
    PredictionDTO,
    PredictionRequestDTO,
)

logger = logging.getLogger(__name__)


class PredictionService:
    """
    سرویس پیش‌بینی - Orchestrator Use Cases
    
    ارتقاها:
        - DTO validation
        - Better error handling
        - Cache در سطح service (لایه بالای use case)
    """
    
    def __init__(self, predict_use_case: PredictCoinUseCase):
        self.predict_use_case = predict_use_case
        
        # آمار
        self._stats = {
            "total_requests": 0,
            "successful": 0,
            "failed": 0,
        }
        
        logger.info("✅ PredictionService v2.0 initialized")
    
    # ============================================================
    # Predict Single
    # ============================================================
    
    def predict_single(
        self,
        coin: str = "bitcoin",
        period: str = "24h",
        save: bool = True,
    ) -> PredictionDTO:
        """
        پیش‌بینی یک ارز
        
        پارامترها:
            coin: شناسه ارز
            period: بازه
            save: ذخیره بشه؟
        
        خروجی:
            PredictionDTO
        """
        self._stats["total_requests"] += 1
        
        try:
            # اعتبارسنجی با DTO
            request_dto = PredictionRequestDTO(coin=coin, period=period)
            valid, errors = request_dto.validate()
            
            if not valid:
                self._stats["failed"] += 1
                return PredictionDTO.from_error(
                    f"Invalid request: {', '.join(errors)}"
                )
            
            # نرمال‌سازی
            request_dto = request_dto.normalized()
            
            # اجرا
            prediction = self.predict_use_case.execute(
                request_dto.coin,
                request_dto.period,
                save=save,
            )
            
            self._stats["successful"] += 1
            return PredictionDTO.from_prediction(prediction)
            
        except ValueError as e:
            logger.warning(f"Validation error: {e}")
            self._stats["failed"] += 1
            return PredictionDTO.from_error(str(e))
        
        except RuntimeError as e:
            logger.warning(f"Runtime error: {e}")
            self._stats["failed"] += 1
            return PredictionDTO.from_error(str(e))
        
        except Exception as e:
            logger.error(f"Prediction error: {e}", exc_info=True)
            self._stats["failed"] += 1
            return PredictionDTO.from_error(f"Prediction failed: {str(e)}")
    
    # ============================================================
    # Predict Multiple
    # ============================================================
    
    def predict_multiple(
        self,
        coins: List[str],
        period: str = "24h",
        save: bool = True,
    ) -> PredictionDTO:
        """
        پیش‌بینی چند ارز
        
        پارامترها:
            coins: لیست ارزها
            period: بازه
            save: ذخیره بشه؟
        
        خروجی:
            PredictionDTO
        """
        self._stats["total_requests"] += 1
        
        try:
            # اعتبارسنجی
            if not coins:
                self._stats["failed"] += 1
                return PredictionDTO.from_error("Coin list cannot be empty")
            
            if len(coins) > 20:
                self._stats["failed"] += 1
                return PredictionDTO.from_error(
                    "Too many coins (max: 20)"
                )
            
            # اجرا
            predictions = self.predict_use_case.execute_multiple(
                coins, period, save=save,
            )
            
            self._stats["successful"] += 1
            return PredictionDTO.from_predictions(predictions)
            
        except Exception as e:
            logger.error(f"Multiple prediction error: {e}", exc_info=True)
            self._stats["failed"] += 1
            return PredictionDTO.from_error(str(e))
    
    # ============================================================
    # From DTO
    # ============================================================
    
    def predict_from_request(
        self,
        request: PredictionRequestDTO,
    ) -> PredictionDTO:
        """پیش‌بینی از روی DTO درخواست"""
        if request.is_multiple():
            return self.predict_multiple(request.coins, request.period)
        else:
            return self.predict_single(request.coin, request.period)
    
    # ============================================================
    # Stats
    # ============================================================
    
    def get_stats(self) -> Dict[str, Any]:
        """آمار سرویس"""
        total = self._stats["total_requests"]
        success_rate = (
            self._stats["successful"] / total * 100
            if total > 0 else 0
        )
        
        return {
            **self._stats,
            "success_rate": round(success_rate, 2),
            "timestamp": datetime.now().isoformat(),
        }
