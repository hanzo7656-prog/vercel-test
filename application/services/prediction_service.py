# application/services/prediction_router.py
# ============================================================
# Prediction Router - انتخاب بین RuleEngine و Gemini
# نسخه ۱.۰
# ============================================================
# 
# مسئولیت:
#   - انتخاب موتور بر اساس پارامتر (gemini | rule | auto)
#   - fallback به RuleEngine اگه Gemini شکست خورد
#   - آمار استفاده از هر موتور
# ============================================================

import logging
from datetime import datetime
from typing import Any, Dict, Optional

from domain.entities.prediction import Prediction as PredictionEntity

logger = logging.getLogger(__name__)


# ============================================================
# Constants
# ============================================================

VALID_ENGINES = ["gemini", "rule", "auto"]


# ============================================================
# PredictionRouter
# ============================================================

class PredictionRouter:
    """
    Router بین دو موتور: Gemini و RuleEngine.
    
    استفاده:
        router = PredictionRouter(
            gemini_use_case=...,
            rule_use_case=...,  # می‌تونه None باشه (بعد از حذف RuleEngine)
        )
        entity = router.predict("bitcoin", "24h", engine="auto")
    """
    
    def __init__(
        self,
        gemini_use_case: Any,
        rule_use_case: Optional[Any] = None,
    ) -> None:
        self.gemini_use_case = gemini_use_case
        self.rule_use_case = rule_use_case
        
        # آمار
        self._stats: Dict[str, Any] = {
            "total_calls": 0,
            "by_engine": {"gemini": 0, "rule": 0, "auto": 0},
            "fallbacks_to_rule": 0,
            "successful": 0,
            "failed": 0,
        }
        
        logger.info(
            f"✅ PredictionRouter initialized "
            f"(gemini={'yes' if gemini_use_case else 'no'}, "
            f"rule={'yes' if rule_use_case else 'no'})"
        )
    
    # ============================================================
    # Predict
    # ============================================================
    
    def predict(
        self,
        coin_id: str,
        period: str = "24h",
        engine: str = "auto",
        save: bool = True,
        use_cache: bool = True,
    ) -> PredictionEntity:
        """
        اجرای پیش‌بینی با موتور انتخاب‌شده.
        
        Args:
            coin_id: "bitcoin"
            period: "24h" | "1w" | "1m" | "3m" | "6m"
            engine: "gemini" | "rule" | "auto"
            save: ذخیره در DB
            use_cache: استفاده از cache
        
        Returns:
            PredictionEntity
        
        Raises:
            ValueError: پارامتر نامعتبر
            RuntimeError: موتور در دسترس نیست یا خطا داد
        """
        engine = (engine or "auto").lower().strip()
        
        if engine not in VALID_ENGINES:
            raise ValueError(
                f"Invalid engine: {engine}. Must be one of {VALID_ENGINES}"
            )
        
        self._stats["total_calls"] += 1
        self._stats["by_engine"][engine] += 1
        
        try:
            result = self._dispatch(
                coin_id=coin_id,
                period=period,
                engine=engine,
                save=save,
                use_cache=use_cache,
            )
            self._stats["successful"] += 1
            return result
        
        except Exception:
            self._stats["failed"] += 1
            raise
    
    # ============================================================
    # Dispatch
    # ============================================================
    
    def _dispatch(
        self,
        coin_id: str,
        period: str,
        engine: str,
        save: bool,
        use_cache: bool,
    ) -> PredictionEntity:
        """مسیریابی به موتور مناسب."""
        
        # ============================================================
        # Auto: Gemini اول، بعد Rule (اگه Gemini خطا داد)
        # ============================================================
        
        if engine == "auto":
            if self.gemini_use_case is not None:
                try:
                    logger.debug(f"🔄 auto → gemini ({coin_id})")
                    return self.gemini_use_case.execute(
                        coin_id=coin_id,
                        period=period,
                        save=save,
                        use_cache=use_cache,
                    )
                except Exception as e:
                    logger.warning(
                        f"⚠️ Gemini failed in auto mode: {e}"
                    )
                    # fallback
                    if self.rule_use_case is not None:
                        self._stats["fallbacks_to_rule"] += 1
                        logger.info("🔄 Falling back to RuleEngine")
            
            if self.rule_use_case is not None:
                logger.debug(f"🔄 auto → rule ({coin_id})")
                return self.rule_use_case.execute(
                    coin_id, period, save=save
                )
            
            raise RuntimeError(
                "هیچ موتوری در دسترس نیست (نه Gemini نه RuleEngine)"
            )
        
        # ============================================================
        # Gemini
        # ============================================================
        
        if engine == "gemini":
            if self.gemini_use_case is None:
                raise RuntimeError(
                    "Gemini engine not available. "
                    "Check GEMINI_API_KEY environment variable."
                )
            logger.debug(f"🔄 gemini ({coin_id})")
            return self.gemini_use_case.execute(
                coin_id=coin_id,
                period=period,
                save=save,
                use_cache=use_cache,
            )
        
        # ============================================================
        # Rule
        # ============================================================
        
        if engine == "rule":
            if self.rule_use_case is None:
                raise RuntimeError(
                    "RuleEngine not available. "
                    "It may have been removed in a recent update."
                )
            logger.debug(f"🔄 rule ({coin_id})")
            return self.rule_use_case.execute(
                coin_id, period, save=save
            )
        
        # نباید به اینجا برسیم (بالاتر validate شد)
        raise RuntimeError(f"Unhandled engine: {engine}")
    
    # ============================================================
    # Stats
    # ============================================================
    
    def get_stats(self) -> Dict[str, Any]:
        """آمار استفاده از router."""
        total = self._stats["total_calls"]
        success_rate = (
            self._stats["successful"] / max(total, 1) * 100
        )
        
        return {
            **self._stats,
            "gemini_available": self.gemini_use_case is not None,
            "rule_available": self.rule_use_case is not None,
            "valid_engines": VALID_ENGINES,
            "success_rate": round(success_rate, 2),
            "timestamp": datetime.now().isoformat(),
        }


__all__ = ["PredictionRouter", "VALID_ENGINES"]
