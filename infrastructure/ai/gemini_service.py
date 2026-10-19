# infrastructure/ai/gemini_service.py
# ============================================================
# Gemini Service - لایه‌ی سطح بالا (دامنه‌ای)
# نسخه ۱.۰
# ============================================================
# 
# مسئولیت:
#   - ساخت contents با تاریخچه
#   - ترکیب system + context
#   - متدهای دامنه‌ای:
#       chat: چت با تاریخچه
#       analyze_image: تحلیل تصویر چارت
#       explain_signal: توضیح سیگنال
#       analyze_text: تحلیل متن (خبر)
# 
# توجه:
#   این لایه مستقل از RuleEngine قدیمی است.
#   ولی می‌تونه از داده‌های بازار (price, ohlcv) استفاده کنه.
# ============================================================

import base64
import json
import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from google.genai import types

from infrastructure.ai.gemini_client import (
    GeminiClient,
    GeminiError,
    DEFAULT_MODEL,
    gemini_client,
)
from prompts.system_prompt import (
    SYSTEM_PROMPT_MAIN,
    SYSTEM_PROMPT_CHART,
    SYSTEM_PROMPT_SIGNAL,
    SYSTEM_PROMPT_NEWS,
)

logger = logging.getLogger(__name__)


# ============================================================
# Constants
# ============================================================

# حداکثر طول تاریخچه (پیام‌ها)
MAX_HISTORY_MESSAGES = 20

# حداکثر حجم تصویر (MB)
MAX_IMAGE_MB = 10

# حداکثر طول متن پیام
MAX_MESSAGE_LEN = 8000


# ============================================================
# GeminiService
# ============================================================

class GeminiService:
    """
    سرویس سطح بالا برای Gemini.
    
    استفاده:
        svc = GeminiService()
        reply = svc.chat("سلام، بیت‌کوین چطوره؟", history=[])
    """
    
    _instance: Optional["GeminiService"] = None
    
    def __new__(cls) -> "GeminiService":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self) -> None:
        if hasattr(self, "_initialized"):
            return
        self._initialized = True
        
        self.client: GeminiClient = gemini_client
        
        self.stats: Dict[str, Any] = {
            "chats": 0,
            "images_analyzed": 0,
            "signals_explained": 0,
            "texts_analyzed": 0,
            "errors": 0,
            "started_at": datetime.now().isoformat(),
        }
        
        logger.info("✅ GeminiService initialized")
    
    @property
    def is_available(self) -> bool:
        return self.client.is_available
    
    # ============================================================
    # 1. Chat (multi-turn)
    # ============================================================
    
    def chat(
        self,
        message: str,
        history: Optional[List[Dict[str, str]]] = None,
        system: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        model: str = DEFAULT_MODEL,
        temperature: float = 0.7,
    ) -> Dict[str, Any]:
        """
        چت با تاریخچه.
        
        Args:
            message: پیام جدید کاربر
            history: [{"role": "user"|"model", "text": "..."}]
            system: system override
            context: داده‌های زمینه (قیمت، شاخص‌ها) که به system اضافه می‌شه
            model: نام مدل
            temperature: 0-2
        
        Returns:
            {
                "text": str,
                "usage": {...},
                "latency_ms": float,
                "model": str,
            }
        """
        if not message or not message.strip():
            raise GeminiError("Empty message")
        
        if len(message) > MAX_MESSAGE_LEN:
            message = message[:MAX_MESSAGE_LEN] + "..."
        
        # ============================================================
        # System
        # ============================================================
        
        final_system = system or SYSTEM_PROMPT_MAIN
        
        if context:
            ctx_text = self._format_context(context)
            if ctx_text:
                final_system = (
                    f"{final_system}\n\n"
                    f"## داده‌های فعلی بازار\n{ctx_text}"
                )
        
        # ============================================================
        # Contents
        # ============================================================
        
        contents = self._build_contents(message, history)
        
        # ============================================================
        # Call
        # ============================================================
        
        try:
            result = self.client.generate(
                contents=contents,
                system=final_system,
                model=model,
                temperature=temperature,
            )
            
            self.stats["chats"] += 1
            
            return {
                "text": result.get("text", ""),
                "function_calls": result.get("function_calls", []),
                "finish_reason": result.get("finish_reason"),
                "usage": result.get("usage", {}),
                "latency_ms": result.get("latency_ms", 0),
                "model": result.get("model", model),
            }
        
        except Exception as e:
            self.stats["errors"] += 1
            logger.error(f"❌ chat error: {e}")
            raise
    
    # ============================================================
    # 2. Analyze Image (چارت)
    # ============================================================
    
    def analyze_image(
        self,
        image_bytes: bytes,
        mime_type: str = "image/jpeg",
        prompt: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        model: str = DEFAULT_MODEL,
    ) -> Dict[str, Any]:
        """
        تحلیل تصویر (چارت کندل‌استیک).
        
        Args:
            image_bytes: بایت‌های تصویر
            mime_type: image/jpeg | image/png | image/webp
            prompt: سوال کاربر (پیش‌فرض: تحلیل کلی چارت)
            context: داده‌های بازار
            model: نام مدل
        
        Returns:
            {"text": str, "usage": {...}, ...}
        """
        if not image_bytes:
            raise GeminiError("Empty image")
        
        if len(image_bytes) > MAX_IMAGE_MB * 1024 * 1024:
            raise GeminiError(
                f"Image too large (max {MAX_IMAGE_MB}MB)"
            )
        
        # ============================================================
        # System
        # ============================================================
        
        final_system = SYSTEM_PROMPT_CHART
        
        if context:
            ctx_text = self._format_context(context)
            if ctx_text:
                final_system = (
                    f"{final_system}\n\n"
                    f"## داده‌های فعلی بازار\n{ctx_text}"
                )
        
        # ============================================================
        # Contents
        # ============================================================
        
        user_prompt = prompt or (
            "این چارت کندل‌استیک را تحلیل کن. شامل:\n"
            "۱. روند فعلی\n"
            "۲. سطوح حمایت و مقاومت کلیدی\n"
            "۳. الگوهای تکنیکال (اگر هست)\n"
            "۴. سیگنال خرید/فروش (اگر هست)\n"
            "پاسخ به فارسی و مختصر باشد."
        )
        
        contents = [
            types.Content(
                role="user",
                parts=[
                    types.Part.from_text(text=user_prompt),
                    types.Part.from_bytes(
                        data=image_bytes,
                        mime_type=mime_type,
                    ),
                ],
            )
        ]
        
        # ============================================================
        # Call
        # ============================================================
        
        try:
            result = self.client.generate(
                contents=contents,
                system=final_system,
                model=model,
                temperature=0.4,
            )
            
            self.stats["images_analyzed"] += 1
            
            return {
                "text": result.get("text", ""),
                "usage": result.get("usage", {}),
                "latency_ms": result.get("latency_ms", 0),
                "model": result.get("model", model),
            }
        
        except Exception as e:
            self.stats["errors"] += 1
            logger.error(f"❌ analyze_image error: {e}")
            raise
    
    # ============================================================
    # 3. Explain Signal (توضیح سیگنال)
    # ============================================================
    
    def explain_signal(
        self,
        coin: str,
        signal_data: Dict[str, Any],
        market_context: Optional[Dict[str, Any]] = None,
        model: str = DEFAULT_MODEL,
    ) -> Dict[str, Any]:
        """
        توضیح یک سیگنال/تحلیل به زبان طبیعی.
        
        Args:
            coin: شناسه ارز (bitcoin)
            signal_data: {
                "signal_type": "BUY" | "SELL" | "NEUTRAL",
                "confidence": 72,
                "score": 0.72,
                "reasons": [...],
                "current_price": 65000,
            }
            market_context: {
                "fear_greed": 60,
                "btc_dominance": 52,
                "rsi": 45,
                "trend": "uptrend",
            }
            model: نام مدل
        
        Returns:
            {"text": str, "usage": {...}, ...}
        """
        # ============================================================
        # ساخت پرامپت
        # ============================================================
        
        signal_type = signal_data.get("signal_type", "NEUTRAL")
        confidence = signal_data.get("confidence", 0)
        score = signal_data.get("score", 0.5)
        current_price = signal_data.get("current_price", 0)
        reasons = signal_data.get("reasons", [])
        
        prompt_parts = [
            f"سیگنال برای {coin}:",
            f"- نوع: {signal_type}",
            f"- اطمینان: {confidence}%",
            f"- امتیاز: {score:.3f}",
            f"- قیمت فعلی: ${current_price:,.2f}",
        ]
        
        if reasons:
            prompt_parts.append("- دلایل:")
            for r in reasons[:10]:
                prompt_parts.append(f"  • {r}")
        
        if market_context:
            prompt_parts.append("\nداده‌های بازار:")
            for k, v in market_context.items():
                prompt_parts.append(f"- {k}: {v}")
        
        prompt_parts.append(
            "\n\nاین سیگنال را برای کاربر توضیح بده:\n"
            "۱. چرا این سیگنال صادر شده (دلایل تکنیکال)\n"
            "۲. ریسک‌ها و موارد احتیاط\n"
            "۳. سناریوهای احتمالی\n"
            "پاسخ به فارسی، مختصر و حرفه‌ای باشد."
        )
        
        prompt = "\n".join(prompt_parts)
        
        # ============================================================
        # Call
        # ============================================================
        
        try:
            result = self.client.generate(
                prompt=prompt,
                system=SYSTEM_PROMPT_SIGNAL,
                model=model,
                temperature=0.5,
            )
            
            self.stats["signals_explained"] += 1
            
            return {
                "text": result.get("text", ""),
                "usage": result.get("usage", {}),
                "latency_ms": result.get("latency_ms", 0),
                "model": result.get("model", model),
            }
        
        except Exception as e:
            self.stats["errors"] += 1
            logger.error(f"❌ explain_signal error: {e}")
            raise
    
    # ============================================================
    # 4. Analyze Text (خبر / sentiment)
    # ============================================================
    
    def analyze_text(
        self,
        text: str,
        context: Optional[str] = None,
        model: str = DEFAULT_MODEL,
    ) -> Dict[str, Any]:
        """
        تحلیل متن (خبر، توییت، ...).
        
        Args:
            text: متن خبر
            context: زمینه اضافی
            model: نام مدل
        
        Returns:
            {"text": str, "usage": {...}, ...}
        """
        if not text:
            raise GeminiError("Empty text")
        
        prompt = f"متن زیر را تحلیل کن:\n\n{text}"
        if context:
            prompt += f"\n\nزمینه: {context}"
        
        try:
            result = self.client.generate(
                prompt=prompt,
                system=SYSTEM_PROMPT_NEWS,
                model=model,
                temperature=0.5,
            )
            
            self.stats["texts_analyzed"] += 1
            
            return {
                "text": result.get("text", ""),
                "usage": result.get("usage", {}),
                "latency_ms": result.get("latency_ms", 0),
                "model": result.get("model", model),
            }
        
        except Exception as e:
            self.stats["errors"] += 1
            raise
    
    # ============================================================
    # Helpers
    # ============================================================
    
    def _build_contents(
        self,
        message: str,
        history: Optional[List[Dict[str, str]]],
    ) -> List[types.Content]:
        """
        ساخت contents از history + message جدید.
        
        history item: {"role": "user"|"model", "text": "..."}
        """
        contents: List[types.Content] = []
        
        if history:
            # آخرین MAX_HISTORY_MESSAGES پیام
            trimmed = history[-MAX_HISTORY_MESSAGES:]
            
            for msg in trimmed:
                role = msg.get("role", "user")
                text = msg.get("text", "")
                if not text:
                    continue
                
                # نقش "model" در SDK Gemini "model" است
                sdk_role = "model" if role == "model" else "user"
                
                contents.append(
                    types.Content(
                        role=sdk_role,
                        parts=[types.Part.from_text(text=text)],
                    )
                )
        
        # پیام جدید
        contents.append(
            types.Content(
                role="user",
                parts=[types.Part.from_text(text=message)],
            )
        )
        
        return contents
    
    @staticmethod
    def _format_context(context: Dict[str, Any]) -> str:
        """فرمت کردن context به متن."""
        if not context:
            return ""
        
        lines = []
        for key, value in context.items():
            if value is None:
                continue
            if isinstance(value, (dict, list)):
                lines.append(f"- {key}: {json.dumps(value, ensure_ascii=False)}")
            else:
                lines.append(f"- {key}: {value}")
        
        return "\n".join(lines)
    
    # ============================================================
    # Stats
    # ============================================================
    
    def get_stats(self) -> Dict[str, Any]:
        """آمار کامل."""
        return {
            **self.stats,
            "available": self.is_available,
            "client_stats": self.client.get_stats(),
        }


# ============================================================
# Singleton
# ============================================================

gemini_service: GeminiService = GeminiService()
