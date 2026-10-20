# application/services/prediction_service.py
# ============================================================
# Service: Prediction Service - نسخه ۴.۰
# فقط Gemini - RuleEngine حذف شد
# ============================================================
# 
# تغییرات نسخه ۴.۰:
#   - predict_use_case حذف شد (RuleEngine legacy)
#   - فقط prediction_router
#   - پیام‌های خطای واضح
# ============================================================

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

from domain.entities.prediction import Prediction
from application.dto.prediction_dto import (
    PredictionDTO,
    PredictionRequestDTO,
    VALID_ENGINES,
)

logger = logging.getLogger(__name__)


# ============================================================
# PredictionService
# ============================================================

class PredictionService:
    """
    سرویس پیش‌بینی - فقط Gemini
    
    ارتقاها (v4.0):
        - RuleEngine حذف شد
        - فقط PredictionRouter با Gemini
    """
    
    def __init__(
        self,
        prediction_router: Any,
    ):
        """
        Args:
            prediction_router: PredictionRouter (فقط Gemini)
        """
        self.prediction_router = prediction_router
        
        # آمار
        self._stats = {
            "total_requests": 0,
            "successful": 0,
            "failed": 0,
            "by_engine": {
                "gemini": 0,
                "auto": 0,
            },
        }
        
        logger.info(
            f"✅ PredictionService v4.0 initialized "
            f"(router={'yes' if prediction_router else 'no'})"
        )
    
    # ============================================================
    # Predict Single
    # ============================================================
    
    def predict_single(
        self,
        coin: str = "bitcoin",
        period: str = "24h",
        save: bool = True,
        engine: str = "auto",
    ) -> PredictionDTO:
        """
        پیش‌بینی یک ارز
        
        پارامترها:
            coin: شناسه ارز
            period: بازه
            save: ذخیره بشه؟
            engine: "gemini" | "auto"
        
        خروجی:
            PredictionDTO
        """
        self._stats["total_requests"] += 1
        self._stats["by_engine"][engine] = (
            self._stats["by_engine"].get(engine, 0) + 1
        )
        
        try:
            # ============================================================
            # اعتبارسنجی
            # ============================================================
            
            request_dto = PredictionRequestDTO(
                coin=coin,
                period=period,
                engine=engine,
            )
            valid, errors = request_dto.validate()
            
            if not valid:
                self._stats["failed"] += 1
                return PredictionDTO.from_error(
                    f"Invalid request: {', '.join(errors)}"
                )
            
            # نرمال‌سازی
            request_dto = request_dto.normalized()
            
            # ============================================================
            # Router
            # ============================================================
            
            if self.prediction_router is None:
                self._stats["failed"] += 1
                return PredictionDTO.from_error(
                    "PredictionRouter در دسترس نیست"
                )
            
            prediction = self.prediction_router.predict(
                coin_id=request_dto.coin,
                period=request_dto.period,
                engine=request_dto.engine,
                save=save,
                use_cache=True,
            )
            
            self._stats["successful"] += 1
            return PredictionDTO.from_prediction(prediction)
        
        # ============================================================
        # Error handling
        # ============================================================
        
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
            return PredictionDTO.from_error(
                f"Prediction failed: {str(e)[:200]}"
            )
    
    # ============================================================
    # Predict Multiple
    # ============================================================
    
    def predict_multiple(
        self,
        coins: List[str],
        period: str = "24h",
        save: bool = True,
        engine: str = "auto",
    ) -> PredictionDTO:
        """
        پیش‌بینی چند ارز
        
        پارامترها:
            coins: لیست ارزها
            period: بازه
            save: ذخیره بشه؟
            engine: "gemini" | "auto"
        
        خروجی:
            PredictionDTO
        """
        self._stats["total_requests"] += 1
        self._stats["by_engine"][engine] = (
            self._stats["by_engine"].get(engine, 0) + 1
        )
        
        try:
            # ============================================================
            # اعتبارسنجی
            # ============================================================
            
            if not coins:
                self._stats["failed"] += 1
                return PredictionDTO.from_error("Coin list cannot be empty")
            
            if len(coins) > 20:
                self._stats["failed"] += 1
                return PredictionDTO.from_error(
                    "Too many coins (max: 20)"
                )
            
            if engine not in VALID_ENGINES:
                if engine == "rule":
                    self._stats["failed"] += 1
                    return PredictionDTO.from_error(
                        "RuleEngine حذف شده است. از engine=gemini یا "
                        "engine=auto استفاده کنید."
                    )
                self._stats["failed"] += 1
                return PredictionDTO.from_error(
                    f"Invalid engine: {engine}"
                )
            
            # ============================================================
            # اجرا (تک‌تک)
            # ============================================================
            
            results: List[Prediction] = []
            
            for coin in coins:
                try:
                    dto = self.predict_single(
                        coin=coin,
                        period=period,
                        save=save,
                        engine=engine,
                    )
                    
                    if dto.success and dto.data:
                        try:
                            pred = Prediction.from_dict(dto.data)
                            results.append(pred)
                        except Exception as e:
                            logger.warning(
                                f"⚠️ Could not parse prediction for {coin}: {e}"
                            )
                    else:
                        logger.warning(
                            f"⚠️ Prediction failed for {coin}: {dto.error}"
                        )
                
                except Exception as e:
                    logger.error(f"❌ Predict error for {coin}: {e}")
                    continue
            
            if not results:
                self._stats["failed"] += 1
                return PredictionDTO.from_error(
                    "همه پیش‌بینی‌ها شکست خوردند"
                )
            
            self._stats["successful"] += 1
            return PredictionDTO.from_predictions(results)
        
        except Exception as e:
            logger.error(f"Multiple prediction error: {e}", exc_info=True)
            self._stats["failed"] += 1
            return PredictionDTO.from_error(str(e)[:200])
    
    # ============================================================
    # From DTO
    # ============================================================
    
    def predict_from_request(
        self,
        request: PredictionRequestDTO,
    ) -> PredictionDTO:
        """پیش‌بینی از روی DTO درخواست"""
        engine = getattr(request, "engine", "auto")
        
        if request.is_multiple():
            return self.predict_multiple(
                request.coins,
                request.period,
                engine=engine,
            )
        else:
            return self.predict_single(
                request.coin,
                request.period,
                engine=engine,
            )
    
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
        
        result = {
            **self._stats,
            "success_rate": round(success_rate, 2),
            "router_available": self.prediction_router is not None,
            "timestamp": datetime.now().isoformat(),
        }
        
        # آمار router (اگه هست)
        if self.prediction_router is not None:
            try:
                result["router"] = self.prediction_router.get_stats()
            except Exception:
                pass
        
        return result


__all__ = ["PredictionService"]
