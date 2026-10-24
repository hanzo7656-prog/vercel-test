# presentation/routes/ai_routes.py
# ============================================================
# AI Routes - روت‌های Gemini
# نسخه ۱.۰
# ============================================================
# 
# Endpoints:
#   POST /api/ai/chat            — چت متنی
#   POST /api/ai/chat/stream     — چت استریم (SSE)
#   POST /api/ai/analyze-image   — تحلیل تصویر
#   POST /api/ai/explain         — توضیح سیگنال
#   GET  /api/ai/status          — وضعیت سرویس
#   GET  /api/ai/stats           — آمار مصرف
# ============================================================

import base64
import json
import logging
from datetime import datetime, timezone

from flask import (
    Blueprint,
    request,
    jsonify,
    current_app,
    Response,
    stream_with_context,
)
import asyncio
import os
from flask import request, jsonify
from application.use_cases.live_agent_use_case import LiveAgentUseCase

from infrastructure.auth.auth_manager import require_auth

logger = logging.getLogger(__name__)


# ============================================================
# Blueprint
# ============================================================

ai_bp = Blueprint("ai", __name__, url_prefix="/api/ai")


# ============================================================
# Helpers
# ============================================================

def _success(data=None, **extra):
    response = {"success": True}
    if data is not None:
        response["data"] = data
    response.update(extra)
    response["timestamp"] = datetime.now(timezone.utc).isoformat()
    return jsonify(response)


def _error(message: str, status_code: int = 400, **extra):
    response = {
        "success": False,
        "error": message,
    }
    response.update(extra)
    response["timestamp"] = datetime.now(timezone.utc).isoformat()
    return jsonify(response), status_code


def _get_chat_use_case():
    return current_app.container.get("ai_chat_use_case")


def _get_image_use_case():
    return current_app.container.get("ai_analyze_image_use_case")


def _get_explain_use_case():
    return current_app.container.get("ai_explain_use_case")


def _get_gemini_service():
    return current_app.container.get("gemini_service")


def _get_gemini_client():
    return current_app.container.get("gemini_client")

# ============================================================
# state
# ============================================================


@api_bp.route('/ai/stats', methods=['GET'])
@require_auth('admin')
def ai_stats_monitoring():
    container = current_app.container
    monitoring = container.monitoring_service()
    result = monitoring.get_ai_stats()
    return jsonify(result), 200 if result.get('success') else 500



# ============================================================
# Chat
# ============================================================

@ai_bp.route("/chat", methods=["POST"])
@require_auth()
def ai_chat():
    """
    چت با Gemini.
    
    Body:
        {
            "message": "بیت‌کوین چطوره؟",
            "history": [
                {"role": "user", "text": "..."},
                {"role": "model", "text": "..."}
            ],
            "include_context": true,
            "temperature": 0.7
        }
    
    Response:
        {
            "success": true,
            "data": {
                "reply": "...",
                "usage": {"prompt_tokens": 100, ...},
                "latency_ms": 1200,
                "context_included": true
            }
        }
    """
    try:
        data = request.json or {}
        
        message = data.get("message", "").strip()
        if not message:
            return _error("message الزامی است", 400)
        
        history = data.get("history") or []
        include_context = bool(data.get("include_context", True))
        temperature = float(data.get("temperature", 0.7))
        
        # محدودیت
        temperature = max(0.0, min(2.0, temperature))
        
        use_case = _get_chat_use_case()
        result = use_case.execute(
            message=message,
            history=history,
            include_context=include_context,
            temperature=temperature,
        )
        
        if not result.get("success"):
            return _error(
                result.get("error", "خطای چت"),
                400,
                details=result,
            )
        
        return _success({
            "reply": result["reply"],
            "usage": result.get("usage", {}),
            "latency_ms": result.get("latency_ms", 0),
            "model": result.get("model"),
            "context_included": result.get("context_included", False),
            "function_calls": result.get("function_calls", []),
        })
    
    except Exception as e:
        logger.error(f"❌ /api/ai/chat error: {e}", exc_info=True)
        return _error(str(e), 500)


@ai_bp.route("/chat/stream", methods=["POST"])
@require_auth()
def ai_chat_stream():
    """
    چت استریم (SSE).
    
    Body: مثل /chat
    
    Response: text/event-stream
        data: {"text": "...", "is_final": false}
        data: {"text": "", "is_final": true}
    """
    try:
        data = request.json or {}
        message = data.get("message", "").strip()
        
        if not message:
            return _error("message الزامی است", 400)
        
        history = data.get("history") or []
        include_context = bool(data.get("include_context", True))
        temperature = float(data.get("temperature", 0.7))
        
        chat_uc = _get_chat_use_case()
        gemini_service = _get_gemini_service()
        
        # ساخت context از use case
        context = None
        if include_context:
            try:
                context = chat_uc._build_market_context(
                    coins=["BTC", "ETH"]
                )
            except Exception:
                context = None
        
        def generate():
            try:
                import asyncio
                
                async def _run():
                    from prompts.system_prompt import SYSTEM_PROMPT_MAIN
                    system = SYSTEM_PROMPT_MAIN
                    if context:
                        ctx_text = gemini_service._format_context(context)
                        system = f"{system}\n\n## داده‌های فعلی بازار\n{ctx_text}"
                    
                    contents = gemini_service._build_contents(message, history)
                    
                    async for chunk in gemini_service.client.generate_stream(
                        contents=contents,
                        system=system,
                        temperature=temperature,
                    ):
                        yield chunk
                
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    gen = _run()
                    while True:
                        try:
                            chunk = loop.run_until_complete(gen.__anext__())
                            yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
                            if chunk.get("is_final"):
                                break
                        except StopAsyncIteration:
                            break
                finally:
                    loop.close()
            
            except Exception as e:
                logger.error(f"❌ stream error: {e}", exc_info=True)
                yield f"data: {json.dumps({'error': str(e), 'is_final': True}, ensure_ascii=False)}\n\n"
        
        return Response(
            stream_with_context(generate()),
            mimetype="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )
    
    except Exception as e:
        logger.error(f"❌ /api/ai/chat/stream error: {e}", exc_info=True)
        return _error(str(e), 500)


# ============================================================
# Analyze Image
# ============================================================

@ai_bp.route("/analyze-image", methods=["POST"])
@require_auth()
def ai_analyze_image():
    """
    تحلیل تصویر چارت.
    
    دو روش:
    
    روش ۱ (multipart/form-data):
        - فیلد "image": فایل
        - فیلد "prompt": (اختیاری)
        - فیلد "include_context": "true"/"false"
    
    روش ۲ (application/json):
        {
            "image_base64": "...",
            "mime_type": "image/png",
            "prompt": "تحلیل کن",
            "include_context": true
        }
    
    Response:
        {
            "success": true,
            "data": {
                "analysis": "...",
                "usage": {...},
                "latency_ms": 2000
            }
        }
    """
    try:
        image_bytes = None
        mime_type = "image/jpeg"
        prompt = None
        include_context = True
        
        # ============================================================
        # تشخیص نوع درخواست
        # ============================================================
        
        if request.files and "image" in request.files:
            # multipart
            file = request.files["image"]
            image_bytes = file.read()
            mime_type = file.mimetype or "image/jpeg"
            prompt = request.form.get("prompt")
            include_context = (
                request.form.get("include_context", "true").lower() == "true"
            )
        else:
            # json
            data = request.json or {}
            img_b64 = data.get("image_base64", "").strip()
            
            if not img_b64:
                return _error(
                    "image_base64 یا فایل multipart الزامی است", 400
                )
            
            # پشتیبانی از data URL
            if img_b64.startswith("data:"):
                parts = img_b64.split(",", 1)
                if len(parts) == 2:
                    header = parts[0]
                    if "image/" in header:
                        try:
                            mime_type = header.split(";")[0].split(":")[1]
                        except Exception:
                            mime_type = "image/jpeg"
                    img_b64 = parts[1]
            
            try:
                image_bytes = base64.b64decode(img_b64)
            except Exception as e:
                return _error(f"base64 نامعتبر: {e}", 400)
            
            mime_type = data.get("mime_type", mime_type)
            prompt = data.get("prompt")
            include_context = bool(data.get("include_context", True))
        
        # ============================================================
        # اجرا
        # ============================================================
        
        use_case = _get_image_use_case()
        result = use_case.execute(
            image_bytes=image_bytes,
            mime_type=mime_type,
            prompt=prompt,
            include_context=include_context,
        )
        
        if not result.get("success"):
            return _error(
                result.get("error", "خطای تحلیل"),
                400,
                details=result,
            )
        
        return _success({
            "analysis": result["analysis"],
            "usage": result.get("usage", {}),
            "latency_ms": result.get("latency_ms", 0),
            "model": result.get("model"),
            "context_included": result.get("context_included", False),
        })
    
    except Exception as e:
        logger.error(f"❌ /api/ai/analyze-image error: {e}", exc_info=True)
        return _error(str(e), 500)


# ============================================================
# Explain
# ============================================================

@ai_bp.route("/explain", methods=["POST"])
@require_auth()
def ai_explain():
    """
    توضیح یک سیگنال با Gemini.
    
    Body:
        {
            "coin": "bitcoin",
            "signal_data": {
                "signal_type": "BUY",
                "confidence": 72,
                "score": 0.72,
                "reasons": ["RSI oversold", "Volume spike"],
                "current_price": 65000
            },
            "include_market_context": true
        }
    """
    try:
        data = request.json or {}
        
        coin = data.get("coin", "").strip()
        if not coin:
            return _error("coin الزامی است", 400)
        
        signal_data = data.get("signal_data") or {}
        if not signal_data:
            return _error("signal_data الزامی است", 400)
        
        include_market_context = bool(
            data.get("include_market_context", True)
        )
        
        use_case = _get_explain_use_case()
        result = use_case.execute(
            coin=coin,
            signal_data=signal_data,
            include_market_context=include_market_context,
        )
        
        if not result.get("success"):
            return _error(
                result.get("error", "خطای توضیح"),
                400,
                details=result,
            )
        
        return _success({
            "explanation": result["explanation"],
            "coin": result.get("coin", coin),
            "usage": result.get("usage", {}),
            "latency_ms": result.get("latency_ms", 0),
            "model": result.get("model"),
        })
    
    except Exception as e:
        logger.error(f"❌ /api/ai/explain error: {e}", exc_info=True)
        return _error(str(e), 500)

# ============================================================
# 🆕 Agent Live Endpoints
# ============================================================

@ai_bp.route("/agent/chat", methods=["POST"])
@require_auth()
def agent_chat():
    """
    چت با ایجنت Live.
    Body: {"message": "وضعیت سیستم چطوره؟"}
    """
    try:
        data = request.json or {}
        message = data.get("message", "").strip()
        if not message:
            return _error("message الزامی است", 400)

        api_key = os.getenv("GEMINI_API_KEY", "")
        if not api_key:
            return _error("GEMINI_API_KEY در environment تنظیم نشده است", 500)

        use_case = LiveAgentUseCase(api_key=api_key)
        
        # اجرای async در محیط sync Flask
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            reply = loop.run_until_complete(use_case.process_text_message(message))
        finally:
            loop.close()

        return _success({"reply": reply, "agent": "live"})

    except Exception as e:
        logger.error(f"❌ Agent chat error: {e}", exc_info=True)
        return _error(str(e), 500)


@ai_bp.route("/agent/status", methods=["GET"])
def agent_status():
    """بررسی وضعیت ایجنت و ابزارهایش."""
    try:
        from agent.tools import ALL_TOOLS
        return _success({
            "available": bool(os.getenv("GEMINI_API_KEY")),
            "model": "gemini-3.8-live",
            "tools_count": len(ALL_TOOLS),
            "tools": [t.__name__ for t in ALL_TOOLS],
        })
    except Exception as e:
        return _error(str(e), 500)
# ============================================================
# Status & Stats
# ============================================================

@ai_bp.route("/status", methods=["GET"])
def ai_status():
    """
    وضعیت سرویس Gemini (public — برای health check).
    """
    try:
        gemini_client = _get_gemini_client()
        gemini_service = _get_gemini_service()
        
        return _success({
            "available": gemini_client.is_available,
            "model_default": "gemini-3.8-flash",
            "features": {
                "chat": True,
                "vision": True,
                "explain": True,
                "streaming": True,
                "live_audio": False,  # فاز ۵
                "function_calling": False,  # فاز ۶
            },
            "service_stats": gemini_service.get_stats() if gemini_service else {},
        })
    
    except Exception as e:
        logger.error(f"❌ /api/ai/status error: {e}", exc_info=True)
        return _error(str(e), 500)


@ai_bp.route("/stats", methods=["GET"])
@require_auth("admin")
def ai_stats():
    """
    آمار مصرف Gemini (نیاز به admin).
    """
    try:
        gemini_client = _get_gemini_client()
        chat_uc = _get_chat_use_case()
        image_uc = _get_image_use_case()
        explain_uc = _get_explain_use_case()
        
        return _success({
            "client": gemini_client.get_stats(),
            "chat": chat_uc.get_stats() if chat_uc else {},
            "image": image_uc.get_stats() if image_uc else {},
            "explain": explain_uc.get_stats() if explain_uc else {},
        })
    
    except Exception as e:
        logger.error(f"❌ /api/ai/stats error: {e}", exc_info=True)
        return _error(str(e), 500)


# ============================================================
# Home
# ============================================================

@ai_bp.route("", methods=["GET"])
@ai_bp.route("/", methods=["GET"])
@require_auth()
def ai_home():
    """لیست endpointها."""
    return _success({
        "name": "AI API",
        "version": "1.0.0",
        "engine": "Gemini",
        "endpoints": {
            "chat": {
                "chat": "POST /api/ai/chat",
                "chat_stream": "POST /api/ai/chat/stream",
            },
            "image": {
                "analyze": "POST /api/ai/analyze-image",
            },
            "explain": {
                "explain": "POST /api/ai/explain",
            },
            "meta": {
                "status": "GET /api/ai/status",
                "stats": "GET /api/ai/stats",
            },
        },
    })


__all__ = ["ai_bp"]
