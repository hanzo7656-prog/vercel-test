# application/use_cases/ai_explain.py
# ============================================================
# Use Case: AI Explain - توضیح سیگنال با Gemini
# نسخه ۱.۰
# ============================================================

import logging
from datetime import datetime
from typing import Any, Dict, Optional

from infrastructure.ai.gemini_service import GeminiService, GeminiError

logger = logging.getLogger(__name__)


class AIExplainUseCase:
    """
    Use Case توضیح سیگنال.
    
    ورودی: داده‌ی سیگنال از هر منبعی (Gemini، RuleEngine، ...)
    خروجی: توضیح به زبان طبیعی
    """
    
    def __init__(
        self,
        gemini_service: GeminiService,
        coinstats_client: Optional[Any] = None,
    ) -> None:
        self.gemini_service = gemini_service
        self.coinstats_client = coinstats_client
        
        self._stats = {
            "total_explains": 0,
            "successful": 0,
            "failed": 0,
        }
        
        logger.info("✅ AIExplainUseCase initialized")
    
    def execute(
        self,
        coin: str,
        signal_data: Dict[str, Any],
        include_market_context: bool = True,
    ) -> Dict[str, Any]:
        """
        اجرای توضیح.
        
        Args:
            coin: "bitcoin"
            signal_data: {
                "signal_type": "BUY",
                "confidence": 72,
                "score": 0.72,
                "reasons": [...],
                "current_price": 65000,
            }
            include_market_context: شامل fear_greed و ...
        
        Returns:
            {"success": bool, "explanation": str, "usage": {...}, ...}
        """
        self._stats["total_explains"] += 1
        
        if not coin:
            self._stats["failed"] += 1
            return {
                "success": False,
                "error": "coin لازم است",
                "timestamp": datetime.now().isoformat(),
            }
        
        if not isinstance(signal_data, dict):
            self._stats["failed"] += 1
            return {
                "success": False,
                "error": "signal_data باید dict باشد",
                "timestamp": datetime.now().isoformat(),
            }
        
        # ============================================================
        # Market context
        # ============================================================
        
        market_context: Optional[Dict[str, Any]] = None
        
        if include_market_context and self.coinstats_client is not None:
            try:
                market_context = self._build_market_context(coin)
            except Exception as e:
                logger.debug(f"Market context error: {e}")
        
        # ============================================================
        # Call
        # ============================================================
        
        try:
            result = self.gemini_service.explain_signal(
                coin=coin,
                signal_data=signal_data,
                market_context=market_context,
            )
            
            self._stats["successful"] += 1
            
            return {
                "success": True,
                "explanation": result.get("text", ""),
                "usage": result.get("usage", {}),
                "latency_ms": result.get("latency_ms", 0),
                "model": result.get("model", "unknown"),
                "coin": coin,
                "timestamp": datetime.now().isoformat(),
            }
        
        except GeminiError as e:
            self._stats["failed"] += 1
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            }
        
        except Exception as e:
            self._stats["failed"] += 1
            logger.error(f"❌ Explain error: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"خطای غیرمنتظره: {str(e)[:200]}",
                "timestamp": datetime.now().isoformat(),
            }
    
    # ============================================================
    # Market context
    # ============================================================
    
    def _build_market_context(self, coin: str) -> Optional[Dict[str, Any]]:
        context: Dict[str, Any] = {}
        
        try:
            fg = self.coinstats_client.get_fear_greed(use_cache=True)
            if fg and "error" not in fg and "now" in fg:
                context["fear_greed"] = fg["now"].get("value", 50)
                context["fear_greed_label"] = fg["now"].get(
                    "value_classification", "Neutral"
                )
        except Exception:
            pass
        
        try:
            dom = self.coinstats_client.get_btc_dominance(use_cache=True)
            if dom and "error" not in dom:
                data_arr = dom.get("data") or []
                if isinstance(data_arr, list) and data_arr:
                    last = data_arr[-1]
                    if isinstance(last, list) and len(last) >= 2:
                        context["btc_dominance"] = float(last[1])
        except Exception:
            pass
        
        return context if context else None
    
    def get_stats(self) -> Dict[str, Any]:
        return {
            **self._stats,
            "timestamp": datetime.now().isoformat(),
        }


__all__ = ["AIExplainUseCase"]
