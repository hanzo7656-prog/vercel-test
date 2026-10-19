# application/use_cases/ai_chat.py
# ============================================================
# Use Case: AI Chat - چت با Gemini
# نسخه ۱.۰
# ============================================================
# 
# مسئولیت:
#   - دریافت پیام + تاریخچه
#   - گرفتن context از بازار (اختیاری)
#   - فراخوانی GeminiService
#   - ساخت پاسخ استاندارد
# 
# نکته:
#   این use case مستقل از RuleEngine است.
#   از price_manager و coinstats_client فقط برای context استفاده می‌کنه.
# ============================================================

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from infrastructure.ai.gemini_service import (
    GeminiService,
    GeminiError,
    MAX_HISTORY_MESSAGES,
    MAX_MESSAGE_LEN,
)

logger = logging.getLogger(__name__)


# ============================================================
# Constants
# ============================================================

# ارزهای پیش‌فرض برای context
DEFAULT_CONTEXT_COINS = ["BTC", "ETH"]


# ============================================================
# AIChatUseCase
# ============================================================

class AIChatUseCase:
    """
    Use Case چت AI.
    
    استفاده:
        uc = AIChatUseCase(
            gemini_service=...,
            price_manager=...,
            coinstats_client=...,
        )
        result = uc.execute(
            message="بیت‌کوین چطوره؟",
            history=[{"role": "user", "text": "..."}, ...],
            include_context=True,
        )
    """
    
    def __init__(
        self,
        gemini_service: GeminiService,
        price_manager: Optional[Any] = None,
        coinstats_client: Optional[Any] = None,
    ) -> None:
        self.gemini_service = gemini_service
        self.price_manager = price_manager
        self.coinstats_client = coinstats_client
        
        # آمار
        self._stats = {
            "total_chats": 0,
            "successful": 0,
            "failed": 0,
            "with_context": 0,
            "without_context": 0,
        }
        
        logger.info("✅ AIChatUseCase initialized")
    
    # ============================================================
    # Execute
    # ============================================================
    
    def execute(
        self,
        message: str,
        history: Optional[List[Dict[str, str]]] = None,
        include_context: bool = True,
        context_coins: Optional[List[str]] = None,
        temperature: float = 0.7,
    ) -> Dict[str, Any]:
        """
        اجرای چت.
        
        Args:
            message: پیام کاربر
            history: [{"role": "user"|"model", "text": "..."}]
            include_context: شامل داده‌های بازار در system
            context_coins: ارزهایی که context بگیرن
            temperature: 0-2
        
        Returns:
            {
                "success": bool,
                "reply": str,
                "usage": {...},
                "latency_ms": float,
                "context_included": bool,
                "timestamp": str,
            }
        """
        self._stats["total_chats"] += 1
        
        # ============================================================
        # Validation
        # ============================================================
        
        if not message or not message.strip():
            self._stats["failed"] += 1
            return {
                "success": False,
                "error": "پیام خالی است",
                "timestamp": datetime.now().isoformat(),
            }
        
        if len(message) > MAX_MESSAGE_LEN:
            message = message[:MAX_MESSAGE_LEN]
            logger.warning(f"⚠️ Message truncated to {MAX_MESSAGE_LEN} chars")
        
        # تاریخچه
        if history is not None and not isinstance(history, list):
            self._stats["failed"] += 1
            return {
                "success": False,
                "error": "history باید لیست باشد",
                "timestamp": datetime.now().isoformat(),
            }
        
        # trim تاریخچه
        if history:
            history = history[-MAX_HISTORY_MESSAGES:]
        
        # ============================================================
        # Context (داده‌های بازار)
        # ============================================================
        
        context: Optional[Dict[str, Any]] = None
        
        if include_context:
            try:
                context = self._build_market_context(
                    coins=context_coins or DEFAULT_CONTEXT_COINS
                )
                if context:
                    self._stats["with_context"] += 1
                else:
                    self._stats["without_context"] += 1
            except Exception as e:
                logger.warning(f"⚠️ Context build error: {e}")
                self._stats["without_context"] += 1
        
        # ============================================================
        # Call Gemini
        # ============================================================
        
        try:
            result = self.gemini_service.chat(
                message=message,
                history=history,
                context=context,
                temperature=temperature,
            )
            
            self._stats["successful"] += 1
            
            return {
                "success": True,
                "reply": result.get("text", ""),
                "function_calls": result.get("function_calls", []),
                "usage": result.get("usage", {}),
                "latency_ms": result.get("latency_ms", 0),
                "model": result.get("model", "unknown"),
                "context_included": bool(context),
                "timestamp": datetime.now().isoformat(),
            }
        
        except GeminiError as e:
            self._stats["failed"] += 1
            logger.error(f"❌ AI chat error: {e}")
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            }
        
        except Exception as e:
            self._stats["failed"] += 1
            logger.error(f"❌ AI chat unexpected error: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"خطای غیرمنتظره: {str(e)[:200]}",
                "timestamp": datetime.now().isoformat(),
            }
    
    # ============================================================
    # Context Builder
    # ============================================================
    
    def _build_market_context(
        self,
        coins: List[str],
    ) -> Optional[Dict[str, Any]]:
        """
        ساخت context از داده‌های بازار.
        
        فقط چیزهایی که سریع و ارزان در دسترسن.
        """
        context: Dict[str, Any] = {}
        
        # ============================================================
        # ۱. قیمت‌های لحظه‌ای (از price_manager → Redis/WS)
        # ============================================================
        
        if self.price_manager is not None:
            try:
                prices = self.price_manager.get_prices(coins)
                if prices:
                    context["realtime_prices"] = {
                        sym: {
                            "price": p.get("price", 0),
                            "change_24h": p.get("change_24h", 0),
                        }
                        for sym, p in prices.items()
                    }
            except Exception as e:
                logger.debug(f"price_manager context error: {e}")
        
        # ============================================================
        # ۲. Fear & Greed + BTC Dominance (از CoinStats cache)
        # ============================================================
        
        if self.coinstats_client is not None:
            try:
                fg = self.coinstats_client.get_fear_greed(use_cache=True)
                if fg and "error" not in fg and "now" in fg:
                    context["fear_greed"] = {
                        "value": fg["now"].get("value", 50),
                        "classification": fg["now"].get(
                            "value_classification", "Neutral"
                        ),
                    }
            except Exception as e:
                logger.debug(f"fear_greed context error: {e}")
            
            try:
                dom = self.coinstats_client.get_btc_dominance(use_cache=True)
                if dom and "error" not in dom:
                    data_arr = dom.get("data") or []
                    if isinstance(data_arr, list) and data_arr:
                        last = data_arr[-1]
                        if isinstance(last, list) and len(last) >= 2:
                            context["btc_dominance"] = {
                                "value": float(last[1])
                            }
            except Exception as e:
                logger.debug(f"btc_dominance context error: {e}")
        
        return context if context else None
    
    # ============================================================
    # Stats
    # ============================================================
    
    def get_stats(self) -> Dict[str, Any]:
        total = self._stats["total_chats"]
        success_rate = (
            self._stats["successful"] / max(total, 1) * 100
        )
        
        return {
            **self._stats,
            "success_rate": round(success_rate, 2),
            "timestamp": datetime.now().isoformat(),
        }


__all__ = ["AIChatUseCase"]
