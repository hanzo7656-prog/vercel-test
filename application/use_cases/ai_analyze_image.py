# application/use_cases/ai_analyze_image.py
# ============================================================
# Use Case: AI Analyze Image - تحلیل چارت تصویری
# نسخه ۱.۰
# ============================================================

import logging
from datetime import datetime
from typing import Any, Dict, Optional

from infrastructure.ai.gemini_service import (
    GeminiService,
    GeminiError,
    MAX_IMAGE_MB,
)

logger = logging.getLogger(__name__)


# ============================================================
# MIME Types مجاز
# ============================================================

VALID_MIME_TYPES = {
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/webp",
    "image/heic",
    "image/heif",
}


# ============================================================
# AIAnalyzeImageUseCase
# ============================================================

class AIAnalyzeImageUseCase:
    """
    Use Case تحلیل تصویر چارت.
    
    استفاده:
        uc = AIAnalyzeImageUseCase(gemini_service=..., coinstats_client=...)
        result = uc.execute(
            image_bytes=data,
            mime_type="image/png",
            prompt="این چارت بیت‌کوین است، تحلیل کن.",
            include_context=True,
        )
    """
    
    def __init__(
        self,
        gemini_service: GeminiService,
        coinstats_client: Optional[Any] = None,
    ) -> None:
        self.gemini_service = gemini_service
        self.coinstats_client = coinstats_client
        
        self._stats = {
            "total_analyses": 0,
            "successful": 0,
            "failed": 0,
        }
        
        logger.info("✅ AIAnalyzeImageUseCase initialized")
    
    # ============================================================
    # Execute
    # ============================================================
    
    def execute(
        self,
        image_bytes: bytes,
        mime_type: str = "image/jpeg",
        prompt: Optional[str] = None,
        include_context: bool = True,
    ) -> Dict[str, Any]:
        """
        اجرای تحلیل تصویر.
        
        Args:
            image_bytes: بایت‌های تصویر
            mime_type: نوع MIME
            prompt: سوال کاربر
            include_context: شامل داده‌های بازار
        
        Returns:
            {
                "success": bool,
                "analysis": str,
                "usage": {...},
                "latency_ms": float,
                "timestamp": str,
            }
        """
        self._stats["total_analyses"] += 1
        
        # ============================================================
        # Validation
        # ============================================================
        
        if not image_bytes:
            self._stats["failed"] += 1
            return {
                "success": False,
                "error": "تصویر خالی است",
                "timestamp": datetime.now().isoformat(),
            }
        
        if len(image_bytes) > MAX_IMAGE_MB * 1024 * 1024:
            self._stats["failed"] += 1
            return {
                "success": False,
                "error": f"تصویر بزرگ است (حداکثر {MAX_IMAGE_MB}MB)",
                "timestamp": datetime.now().isoformat(),
            }
        
        mime_type = (mime_type or "").lower().strip()
        if mime_type == "image/jpg":
            mime_type = "image/jpeg"
        
        if mime_type not in VALID_MIME_TYPES:
            self._stats["failed"] += 1
            return {
                "success": False,
                "error": (
                    f"نوع تصویر مجاز نیست: {mime_type}. "
                    f"مجاز: {sorted(VALID_MIME_TYPES)}"
                ),
                "timestamp": datetime.now().isoformat(),
            }
        
        # ============================================================
        # Context
        # ============================================================
        
        context: Optional[Dict[str, Any]] = None
        
        if include_context and self.coinstats_client is not None:
            try:
                context = self._build_context()
            except Exception as e:
                logger.debug(f"Image context error: {e}")
        
        # ============================================================
        # Call
        # ============================================================
        
        try:
            result = self.gemini_service.analyze_image(
                image_bytes=image_bytes,
                mime_type=mime_type,
                prompt=prompt,
                context=context,
            )
            
            self._stats["successful"] += 1
            
            return {
                "success": True,
                "analysis": result.get("text", ""),
                "usage": result.get("usage", {}),
                "latency_ms": result.get("latency_ms", 0),
                "model": result.get("model", "unknown"),
                "context_included": bool(context),
                "timestamp": datetime.now().isoformat(),
            }
        
        except GeminiError as e:
            self._stats["failed"] += 1
            logger.error(f"❌ Image analysis error: {e}")
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            }
        
        except Exception as e:
            self._stats["failed"] += 1
            logger.error(f"❌ Image analysis unexpected: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"خطای غیرمنتظره: {str(e)[:200]}",
                "timestamp": datetime.now().isoformat(),
            }
    
    # ============================================================
    # Context
    # ============================================================
    
    def _build_context(self) -> Optional[Dict[str, Any]]:
        """ساخت context ساده از CoinStats."""
        context: Dict[str, Any] = {}
        
        try:
            fg = self.coinstats_client.get_fear_greed(use_cache=True)
            if fg and "error" not in fg and "now" in fg:
                context["fear_greed"] = {
                    "value": fg["now"].get("value", 50),
                    "classification": fg["now"].get(
                        "value_classification", "Neutral"
                    ),
                }
        except Exception:
            pass
        
        try:
            btc = self.coinstats_client.get_coin("bitcoin")
            if btc and "error" not in btc:
                context["btc"] = {
                    "price": btc.get("price", 0),
                    "change_24h": btc.get("priceChange1d", 0),
                }
        except Exception:
            pass
        
        return context if context else None
    
    # ============================================================
    # Stats
    # ============================================================
    
    def get_stats(self) -> Dict[str, Any]:
        return {
            **self._stats,
            "timestamp": datetime.now().isoformat(),
        }


__all__ = ["AIAnalyzeImageUseCase"]
