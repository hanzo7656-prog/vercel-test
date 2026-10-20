# application/services/prediction_router.py
# ============================================================
# Prediction Router - فقط Gemini
# نسخه ۲.۰ - RuleEngine حذف شد
# ============================================================
# 
# تغییرات نسخه ۲.۰:
#   - فقط Gemini
#   - rule_use_case حذف شد (فقط برای پیام خطا)
#   - auto = gemini
# ============================================================

import logging
from datetime import datetime
from typing import Any, Dict, Optional

from domain.entities.prediction import Prediction as PredictionEntity

logger = logging.getLogger(__name__)


# ============================================================
# Constants
# ============================================================

# ⚠️ "rule" هنوز توی لیست هست ولی کار نمی‌کنه (پیام واضح می‌ده)
VALID_ENGINES = ["gemini", "auto"]


# ============================================================
# PredictionRouter
# ============================================================

class PredictionRouter:
    """
    Router - فقط Gemini.
    
    استفاده:
        router = PredictionRouter(gemini_use_case=...)
        entity = router.predict("bitcoin", "24h", engine="auto")
    """
    
    def __init__(
        self,
        gemini_use_case: Any,
    ) -> None:
        self.gemini_use_case = gemini_use_case
        
        # آمار
        self._stats: Dict[str, Any] = {
            "total_calls": 0,
            "by_engine": {"gemini": 0, "auto": 0},
            "successful": 0,
            "failed": 0,
            "rule_requests_rejected": 0,  # 🆕 درخواست‌های rule که رد شدن
        }
        
        logger.info(
            f"✅ PredictionRouter v2.0 initialized "
            f"(gemini={'yes' if gemini_use_case else 'no'})"
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
        اجرای پیش‌بینی با Gemini.
        
        Args:
            coin_id: "bitcoin"
            period: "24h" | "1w" | "1m" | "3m" | "6m"
            engine: "gemini" | "auto" (هر دو به Gemini می‌رن)
            save: ذخیره در DB
            use_cache: استفاده از cache
        
        Returns:
            PredictionEntity
        
        Raises:
            ValueError: پارامتر نامعتبر
            RuntimeError: Gemini در دسترس نیست یا خطا داد
        """
        engine = (engine or "auto").lower().strip()
        
        # ============================================================
        # Validation
        # ============================================================
        
        if engine not in VALID_ENGINES:
            # اگه engine=rule بود، پیام واضح
            if engine == "rule":
                self._stats["rule_requests_rejected"] += 1
                raise RuntimeError(
                    "RuleEngine حذف شده است. لطفاً از engine=gemini یا "
                    "engine=auto استفاده کنید."
                )
            
            raise ValueError(
                f"Invalid engine: {engine}. Must be one of {VALID_ENGINES}"
            )
        
        # ============================================================
        # Gemini availability
        # ============================================================
        
        if self.gemini_use_case is None:
            raise RuntimeError(
                "Gemini engine not available. "
                "Check GEMINI_API_KEY environment variable."
            )
        
        self._stats["total_calls"] += 1
        self._stats["by_engine"][engine] += 1
        
        # ============================================================
        # Execute
        # ============================================================
        
        try:
            logger.debug(f"🔄 {engine} → gemini ({coin_id})")
            
            result = self.gemini_use_case.execute(
                coin_id=coin_id,
                period=period,
                save=save,
                use_cache=use_cache,
            )
            
            self._stats["successful"] += 1
            return result
        
        except Exception:
            self._stats["failed"] += 1
            raise
    
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
            "valid_engines": VALID_ENGINES,
            "success_rate": round(success_rate, 2),
            "timestamp": datetime.now().isoformat(),
        }


__all__ = ["PredictionRouter", "VALID_ENGINES"]
