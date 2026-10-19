# infrastructure/ai/gemini_client.py
# ============================================================
# Gemini Client - لایه‌ی خام روی Google Gen AI SDK
# نسخه ۱.۰
# ============================================================
# 
# مسئولیت:
#   - ساخت کلاینت SDK
#   - مدیریت API Key از env
#   - متدهای خام: generate, generate_stream, count_tokens
#   - مدیریت خطا (retry, rate limit, auth)
#   - آمار مصرف (تعداد درخواست، توکن)
# 
# توجه:
#   این لایه هیچ منطق دامنه ندارد.
#   فقط یک wrapper نازک روی SDK است.
# ============================================================

import logging
import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, AsyncIterator

from google import genai
from google.genai import types
from google.genai.errors import ClientError, ServerError, APIError

logger = logging.getLogger(__name__)


# ============================================================
# Constants
# ============================================================

# مدل‌های مجاز
DEFAULT_MODEL = "gemini-3.8-flash"
FALLBACK_MODEL = "gemini-3.8-flash"  # در صورت خطا
PRO_MODEL = "gemini-3.8-pro"

# timeout پیش‌فرض (ثانیه)
DEFAULT_TIMEOUT = 60

# حداکثر تعداد تلاش مجدد
MAX_RETRIES = 3

# تاخیر بین تلاش‌ها (ثانیه) — exponential backoff
RETRY_DELAYS = [1, 2, 4]


# ============================================================
# Errors
# ============================================================

class GeminiError(Exception):
    """خطای پایه Gemini"""
    pass


class GeminiRateLimitError(GeminiError):
    """خطای rate limit (429)"""
    pass


class GeminiAuthError(GeminiError):
    """خطای احراز هویت (401/403)"""
    pass


class GeminiTimeoutError(GeminiError):
    """timeout"""
    pass


# ============================================================
# GeminiClient
# ============================================================

class GeminiClient:
    """
    کلاینت خام Gemini
    
    استفاده:
        client = GeminiClient()
        response = client.generate(
            prompt="سلام",
            system="You are a helpful assistant.",
        )
    """
    
    _instance: Optional["GeminiClient"] = None
    
    def __new__(cls) -> "GeminiClient":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self) -> None:
        if hasattr(self, "_initialized"):
            return
        self._initialized = True
        
        # ============================================================
        # API Key
        # ============================================================
        
        api_key = os.getenv("GEMINI_API_KEY", "").strip()
        
        if not api_key:
            logger.error(
                "❌ GEMINI_API_KEY not set in environment! "
                "Gemini features will fail."
            )
            self._client: Optional[genai.Client] = None
        else:
            # لاگ امن — فقط طول و ۴ کاراکتر اول
            logger.info(
                f"✅ GEMINI_API_KEY loaded "
                f"(len={len(api_key)}, prefix={api_key[:4]}...)"
            )
            try:
                self._client = genai.Client(api_key=api_key)
            except Exception as e:
                logger.error(f"❌ Failed to create Gemini client: {e}")
                self._client = None
        
        # ============================================================
        # Stats
        # ============================================================
        
        self.stats: Dict[str, Any] = {
            "total_requests": 0,
            "successful": 0,
            "failed": 0,
            "retried": 0,
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "total_tokens": 0,
            "total_latency_ms": 0,
            "last_request_at": None,
            "last_error": None,
            "last_error_at": None,
            "started_at": datetime.now().isoformat(),
        }
        
        logger.info("✅ GeminiClient initialized")
    
    # ============================================================
    # Properties
    # ============================================================
    
    @property
    def is_available(self) -> bool:
        """آیا کلاینت آماده است؟"""
        return self._client is not None
    
    # ============================================================
    # Generate (non-streaming)
    # ============================================================
    
    def generate(
        self,
        prompt: Optional[str] = None,
        contents: Optional[List[types.Content]] = None,
        system: Optional[str] = None,
        model: str = DEFAULT_MODEL,
        temperature: float = 0.7,
        max_output_tokens: Optional[int] = None,
        top_p: Optional[float] = None,
        top_k: Optional[int] = None,
        tools: Optional[List[Any]] = None,
        timeout: int = DEFAULT_TIMEOUT,
        retries: int = MAX_RETRIES,
    ) -> Dict[str, Any]:
        """
        تولید پاسخ غیر-استریم.
        
        Args:
            prompt: پرامپت ساده (اگه contents داده نشه)
            contents: لیست Content برای multi-turn
            system: system instruction
            model: نام مدل
            temperature: 0-2
            max_output_tokens: حداکثر توکن خروجی
            top_p, top_k: پارامترهای sampling
            tools: ابزارها برای function calling
            timeout: timeout (ثانیه)
            retries: تعداد تلاش مجدد
        
        Returns:
            {
                "text": str,
                "function_calls": list,
                "finish_reason": str,
                "usage": {...},
                "model": str,
                "latency_ms": float,
            }
        
        Raises:
            GeminiAuthError, GeminiRateLimitError, GeminiError
        """
        if not self.is_available:
            raise GeminiAuthError(
                "Gemini client not available (GEMINI_API_KEY missing)"
            )
        
        # ============================================================
        # آماده‌سازی contents
        # ============================================================
        
        if contents is None:
            if not prompt:
                raise GeminiError("Either 'prompt' or 'contents' is required")
            contents = [
                types.Content(
                    role="user",
                    parts=[types.Part.from_text(text=prompt)],
                )
            ]
        
        # ============================================================
        # Config
        # ============================================================
        
        config_kwargs: Dict[str, Any] = {
            "temperature": temperature,
        }
        
        if system:
            config_kwargs["system_instruction"] = system
        
        if max_output_tokens is not None:
            config_kwargs["max_output_tokens"] = max_output_tokens
        
        if top_p is not None:
            config_kwargs["top_p"] = top_p
        
        if top_k is not None:
            config_kwargs["top_k"] = top_k
        
        if tools:
            config_kwargs["tools"] = tools
        
        config = types.GenerateContentConfig(**config_kwargs)
        
        # ============================================================
        # اجرا با retry
        # ============================================================
        
        start_time = time.time()
        last_error: Optional[Exception] = None
        
        for attempt in range(retries + 1):
            try:
                self.stats["total_requests"] += 1
                
                response = self._client.models.generate_content(
                    model=model,
                    contents=contents,
                    config=config,
                )
                
                latency_ms = (time.time() - start_time) * 1000
                self.stats["successful"] += 1
                self.stats["total_latency_ms"] += latency_ms
                self.stats["last_request_at"] = datetime.now().isoformat()
                
                # ============================================================
                # پارس پاسخ
                # ============================================================
                
                parsed = self._parse_response(response, latency_ms, model)
                
                # آمار توکن
                usage = parsed.get("usage", {})
                self.stats["total_input_tokens"] += usage.get("prompt_tokens", 0)
                self.stats["total_output_tokens"] += usage.get("candidates_tokens", 0)
                self.stats["total_tokens"] += usage.get("total_tokens", 0)
                
                logger.debug(
                    f"✅ Gemini generate OK "
                    f"({model}, {latency_ms:.0f}ms, "
                    f"tokens={usage.get('total_tokens', 0)})"
                )
                
                return parsed
            
            except ClientError as e:
                status = getattr(e, "status_code", None) or getattr(e, "code", None)
                msg = str(e)
                
                # 401/403 → auth
                if status in (401, 403):
                    self._mark_error(e)
                    raise GeminiAuthError(f"Auth failed: {msg}") from e
                
                # 429 → rate limit
                if status == 429:
                    if attempt < retries:
                        delay = RETRY_DELAYS[min(attempt, len(RETRY_DELAYS) - 1)]
                        logger.warning(
                            f"⏳ Rate limit hit, retry in {delay}s "
                            f"(attempt {attempt + 1}/{retries})"
                        )
                        self.stats["retried"] += 1
                        time.sleep(delay)
                        last_error = e
                        continue
                    self._mark_error(e)
                    raise GeminiRateLimitError(f"Rate limit: {msg}") from e
                
                # 400 → bad request (نمی‌شه retry کرد)
                if status == 400:
                    self._mark_error(e)
                    raise GeminiError(f"Bad request: {msg}") from e
                
                # بقیه
                if attempt < retries:
                    delay = RETRY_DELAYS[min(attempt, len(RETRY_DELAYS) - 1)]
                    logger.warning(f"⚠️ Client error, retry in {delay}s: {msg}")
                    self.stats["retried"] += 1
                    time.sleep(delay)
                    last_error = e
                    continue
                
                self._mark_error(e)
                raise GeminiError(f"Client error: {msg}") from e
            
            except ServerError as e:
                if attempt < retries:
                    delay = RETRY_DELAYS[min(attempt, len(RETRY_DELAYS) - 1)]
                    logger.warning(
                        f"⚠️ Server error, retry in {delay}s "
                        f"(attempt {attempt + 1}/{retries}): {e}"
                    )
                    self.stats["retried"] += 1
                    time.sleep(delay)
                    last_error = e
                    continue
                
                self._mark_error(e)
                raise GeminiError(f"Server error: {e}") from e
            
            except (APIError, Exception) as e:
                # timeout?
                if "timeout" in str(e).lower() or "timed out" in str(e).lower():
                    if attempt < retries:
                        delay = RETRY_DELAYS[min(attempt, len(RETRY_DELAYS) - 1)]
                        logger.warning(f"⏳ Timeout, retry in {delay}s")
                        self.stats["retried"] += 1
                        time.sleep(delay)
                        last_error = e
                        continue
                    self._mark_error(e)
                    raise GeminiTimeoutError(f"Timeout: {e}") from e
                
                if attempt < retries:
                    delay = RETRY_DELAYS[min(attempt, len(RETRY_DELAYS) - 1)]
                    logger.warning(f"⚠️ Error, retry in {delay}s: {e}")
                    self.stats["retried"] += 1
                    time.sleep(delay)
                    last_error = e
                    continue
                
                self._mark_error(e)
                raise GeminiError(f"Unknown error: {e}") from e
        
        # اگه به اینجا رسیدیم یعنی همه retryها fail شدن
        self._mark_error(last_error)
        raise GeminiError(f"All {retries + 1} attempts failed: {last_error}")
    
    # ============================================================
    # Generate Stream (async)
    # ============================================================
    
    async def generate_stream(
        self,
        prompt: Optional[str] = None,
        contents: Optional[List[types.Content]] = None,
        system: Optional[str] = None,
        model: str = DEFAULT_MODEL,
        temperature: float = 0.7,
        max_output_tokens: Optional[int] = None,
        tools: Optional[List[Any]] = None,
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        تولید پاسخ استریم (برای SSE / WebSocket).
        
        Yields:
            {"text": str, "is_final": bool, "usage": {...}}
        """
        if not self.is_available:
            raise GeminiAuthError(
                "Gemini client not available (GEMINI_API_KEY missing)"
            )
        
        if contents is None:
            if not prompt:
                raise GeminiError("Either 'prompt' or 'contents' is required")
            contents = [
                types.Content(
                    role="user",
                    parts=[types.Part.from_text(text=prompt)],
                )
            ]
        
        config_kwargs: Dict[str, Any] = {"temperature": temperature}
        if system:
            config_kwargs["system_instruction"] = system
        if max_output_tokens is not None:
            config_kwargs["max_output_tokens"] = max_output_tokens
        if tools:
            config_kwargs["tools"] = tools
        
        config = types.GenerateContentConfig(**config_kwargs)
        
        self.stats["total_requests"] += 1
        start_time = time.time()
        
        try:
            stream = await self._client.aio.models.generate_content_stream(
                model=model,
                contents=contents,
                config=config,
            )
            
            accumulated_text = ""
            
            async for chunk in stream:
                text = self._extract_text(chunk)
                if text:
                    accumulated_text += text
                    yield {
                        "text": text,
                        "accumulated": accumulated_text,
                        "is_final": False,
                    }
                
                # function calls در chunk
                func_calls = self._extract_function_calls(chunk)
                if func_calls:
                    yield {
                        "function_calls": func_calls,
                        "is_final": False,
                    }
            
            latency_ms = (time.time() - start_time) * 1000
            self.stats["successful"] += 1
            self.stats["total_latency_ms"] += latency_ms
            self.stats["last_request_at"] = datetime.now().isoformat()
            
            yield {
                "text": "",
                "accumulated": accumulated_text,
                "is_final": True,
                "latency_ms": latency_ms,
            }
        
        except Exception as e:
            self._mark_error(e)
            raise GeminiError(f"Stream error: {e}") from e
    
    # ============================================================
    # Count Tokens (برای تخمین هزینه)
    # ============================================================
    
    def count_tokens(
        self,
        contents: List[types.Content],
        model: str = DEFAULT_MODEL,
    ) -> int:
        """
        شمارش توکن‌ها (بدون تولید پاسخ).
        
        برای تخمین هزینه قبل از ارسال.
        """
        if not self.is_available:
            return 0
        
        try:
            result = self._client.models.count_tokens(
                model=model,
                contents=contents,
            )
            return getattr(result, "total_tokens", 0) or 0
        except Exception as e:
            logger.warning(f"⚠️ count_tokens error: {e}")
            return 0
    
    # ============================================================
    # Parse Helpers
    # ============================================================
    
    def _parse_response(
        self,
        response: Any,
        latency_ms: float,
        model: str,
    ) -> Dict[str, Any]:
        """پارس response به dict استاندارد."""
        text = self._extract_text(response)
        function_calls = self._extract_function_calls(response)
        
        finish_reason = None
        try:
            candidates = getattr(response, "candidates", None) or []
            if candidates:
                finish_reason = getattr(
                    candidates[0], "finish_reason", None
                )
                if finish_reason is not None:
                    finish_reason = str(finish_reason)
        except Exception:
            pass
        
        usage = {}
        try:
            usage_meta = getattr(response, "usage_metadata", None)
            if usage_meta:
                usage = {
                    "prompt_tokens": getattr(
                        usage_meta, "prompt_token_count", 0
                    ) or 0,
                    "candidates_tokens": getattr(
                        usage_meta, "candidates_token_count", 0
                    ) or 0,
                    "total_tokens": getattr(
                        usage_meta, "total_token_count", 0
                    ) or 0,
                }
        except Exception:
            pass
        
        return {
            "text": text,
            "function_calls": function_calls,
            "finish_reason": finish_reason,
            "usage": usage,
            "model": model,
            "latency_ms": round(latency_ms, 2),
        }
    
    @staticmethod
    def _extract_text(response: Any) -> str:
        """استخراج متن از response یا chunk."""
        try:
            if hasattr(response, "text"):
                return response.text or ""
        except Exception:
            pass
        
        try:
            candidates = getattr(response, "candidates", None) or []
            if not candidates:
                return ""
            content = getattr(candidates[0], "content", None)
            if not content:
                return ""
            parts = getattr(content, "parts", None) or []
            texts = []
            for part in parts:
                ptext = getattr(part, "text", None)
                if ptext:
                    texts.append(ptext)
            return "".join(texts)
        except Exception:
            return ""
    
    @staticmethod
    def _extract_function_calls(response: Any) -> List[Dict[str, Any]]:
        """استخراج function callها."""
        result: List[Dict[str, Any]] = []
        
        try:
            candidates = getattr(response, "candidates", None) or []
            if not candidates:
                return result
            
            content = getattr(candidates[0], "content", None)
            if not content:
                return result
            
            parts = getattr(content, "parts", None) or []
            for part in parts:
                fc = getattr(part, "function_call", None)
                if fc:
                    result.append({
                        "name": getattr(fc, "name", ""),
                        "args": dict(getattr(fc, "args", {}) or {}),
                    })
        except Exception:
            pass
        
        return result
    
    def _mark_error(self, e: Optional[Exception]) -> None:
        """ثبت خطا در آمار."""
        self.stats["failed"] += 1
        self.stats["last_error"] = str(e)[:500] if e else "unknown"
        self.stats["last_error_at"] = datetime.now().isoformat()
    
    # ============================================================
    # Stats
    # ============================================================
    
    def get_stats(self) -> Dict[str, Any]:
        """آمار کامل کلاینت."""
        total = self.stats["total_requests"]
        avg_latency = (
            self.stats["total_latency_ms"] / max(self.stats["successful"], 1)
        )
        
        return {
            **self.stats,
            "available": self.is_available,
            "success_rate": round(
                self.stats["successful"] / max(total, 1) * 100, 2
            ),
            "avg_latency_ms": round(avg_latency, 2),
            "model_default": DEFAULT_MODEL,
        }


# ============================================================
# Singleton
# ============================================================

gemini_client: GeminiClient = GeminiClient()
