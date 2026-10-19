# application/services/prediction_service.py
# ============================================================
# Service: Prediction Service - نسخه ۳.۰
# Cache + Validation + Error Handling + Engine Selection
# ============================================================
# 
# تغییرات نسخه ۳.۰:
#   - پارامتر engine (gemini | rule | auto)
#   - پشتیبانی از PredictionRouter
#   - fallback به rule استفاده قدیمی اگه router نبود
#   - آمار per-engine
# ============================================================

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

from domain.entities.prediction import Prediction
from application.use_cases.predict_coin import PredictCoinUseCase
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
    سرویس پیش‌بینی - Orchestrator
    
    ارتقاها (v3.0):
        - DTO validation
        - Engine selection (gemini | rule | auto)
        - PredictionRouter support
        - آمار per-engine
    """
    
    def __init__(
        self,
        predict_use_case: Optional[PredictCoinUseCase] = None,
        prediction_router: Optional[Any] = None,
    ):
        """
        Args:
            predict_use_case: PredictCoinUseCase قدیمی (RuleEngine)
                             می‌تونه None باشه اگه RuleEngine حذف شده
            prediction_router: PredictionRouter (gemini + rule)
        """
        self.predict_use_case = predict_use_case
        self.prediction_router = prediction_router
        
        # آمار
        self._stats = {
            "total_requests": 0,
            "successful": 0,
            "failed": 0,
            "by_engine": {
                "gemini": 0,
                "rule": 0,
                "auto": 0,
            },
        }
        
        logger.info(
            f"✅ PredictionService v3.0 initialized "
            f"(rule={'yes' if predict_use_case else 'no'}, "
            f"router={'yes' if prediction_router else 'no'})"
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
            engine: موتور (gemini | rule | auto)
        
        خروجی:
            PredictionDTO
        """
        self._stats["total_requests"] += 1
        self._stats["by_engine"][engine] = (
            self._stats["by_engine"].get(engine, 0) + 1
        )
        
        try:
            # ============================================================
            # اعتبارسنجی با DTO
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
            # مسیر ۱: PredictionRouter (جدید)
            # ============================================================
            
            if self.prediction_router is not None:
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
            # مسیر ۲: fallback به RuleEngine قدیمی
            # ============================================================
            
            if self.predict_use_case is not None:
                # اگه کاربر engine=gemini خواسته ولی router نیست، خطا
                if request_dto.engine == "gemini":
                    self._stats["failed"] += 1
                    return PredictionDTO.from_error(
                        "Gemini engine not available (prediction_router missing)"
                    )
                
                prediction = self.predict_use_case.execute(
                    request_dto.coin,
                    request_dto.period,
                    save=save,
                )
                
                self._stats["successful"] += 1
                return PredictionDTO.from_prediction(prediction)
            
            # ============================================================
            # هیچ موتوری نیست
            # ============================================================
            
            self._stats["failed"] += 1
            return PredictionDTO.from_error(
                "هیچ موتوری در دسترس نیست"
            )
        
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
            engine: موتور (gemini | rule | auto)
        
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
                self._stats["failed"] += 1
                return PredictionDTO.from_error(
                    f"Invalid engine: {engine}"
                )
            
            # ============================================================
            # اجرا (تک‌تک، چون router predict_multiple نداره)
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
                        # ساخت Prediction از dict
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
            "rule_available": self.predict_use_case is not None,
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
