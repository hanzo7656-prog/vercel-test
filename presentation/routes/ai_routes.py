# presentation/routes/ai_routes.py
# ============================================================
# AI Routes - روت‌های کامل Gemini (متنی + Live Agent)
# نسخه ۳.۰ - با اندپوینت‌های جامع
# ============================================================

import asyncio
import base64
import json
import logging
import os
from datetime import datetime, timezone

from flask import (
    Blueprint, request, jsonify, current_app,
    Response, stream_with_context,
)

from infrastructure.auth.auth_manager import require_auth

logger = logging.getLogger(__name__)

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
    response = {"success": False, "error": message}
    response.update(extra)
    response["timestamp"] = datetime.now(timezone.utc).isoformat()
    return jsonify(response), status_code


# ============================================================
# ۱. Text-based AI (Gemini Flash)
# ============================================================

@ai_bp.route("/chat", methods=["POST"])
@require_auth()
def ai_chat():
    """چت با Gemini Flash (متنی)."""
    try:
        data = request.json or {}
        message = data.get("message", "").strip()
        if not message:
            return _error("message الزامی است", 400)

        from application.use_cases.ai_chat import AIChatUseCase
        use_case = AIChatUseCase(
            gemini_service=current_app.container.get("gemini_service"),
            price_manager=current_app.container.get("price_manager"),
            coinstats_client=current_app.container.get("api_client"),
        )
        
        result = use_case.execute(
            message=message,
            history=data.get("history", []),
            include_context=bool(data.get("include_context", True)),
            temperature=float(data.get("temperature", 0.7)),
        )
        
        if not result.get("success"):
            return _error(result.get("error", "خطای چت"), 400)
        
        return _success({
            "reply": result["reply"],
            "usage": result.get("usage", {}),
            "latency_ms": result.get("latency_ms", 0),
            "model": result.get("model"),
        })
    except Exception as e:
        logger.error(f"❌ /api/ai/chat error: {e}", exc_info=True)
        return _error(str(e), 500)


@ai_bp.route("/chat/stream", methods=["POST"])
@require_auth()
def ai_chat_stream():
    """چت استریم (SSE) با Gemini Flash."""
    try:
        data = request.json or {}
        message = data.get("message", "").strip()
        if not message:
            return _error("message الزامی است", 400)

        gemini_service = current_app.container.get("gemini_service")
        if not gemini_service:
            return _error("Gemini service not available", 500)

        def generate():
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                async def _run():
                    from prompts.system_prompt import SYSTEM_PROMPT_MAIN
                    contents = gemini_service._build_contents(message, data.get("history", []))
                    
                    async for chunk in gemini_service.client.generate_stream(
                        contents=contents,
                        system=SYSTEM_PROMPT_MAIN,
                        temperature=float(data.get("temperature", 0.7)),
                    ):
                        yield chunk
                
                gen = _run()
                while True:
                    try:
                        chunk = loop.run_until_complete(gen.__anext__())
                        yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
                        if chunk.get("is_final"):
                            break
                    except StopAsyncIteration:
                        break
                loop.close()
            except Exception as e:
                yield f"data: {json.dumps({'error': str(e), 'is_final': True}, ensure_ascii=False)}\n\n"
        
        return Response(
            stream_with_context(generate()),
            mimetype="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
    except Exception as e:
        logger.error(f"❌ /api/ai/chat/stream error: {e}", exc_info=True)
        return _error(str(e), 500)


# ============================================================
# ۲. Vision AI (تحلیل تصویر)
# ============================================================

@ai_bp.route("/analyze-image", methods=["POST"])
@require_auth()
def ai_analyze_image():
    """تحلیل تصویر چارت با Gemini Flash."""
    try:
        image_bytes = None
        mime_type = "image/jpeg"
        prompt = None
        include_context = True

        if request.files and "image" in request.files:
            file = request.files["image"]
            image_bytes = file.read()
            mime_type = file.mimetype or "image/jpeg"
            prompt = request.form.get("prompt")
            include_context = request.form.get("include_context", "true").lower() == "true"
        else:
            data = request.json or {}
            img_b64 = data.get("image_base64", "").strip()
            if not img_b64:
                return _error("image_base64 یا فایل multipart الزامی است", 400)
            
            if img_b64.startswith("data:"):
                parts = img_b64.split(",", 1)
                if len(parts) == 2:
                    img_b64 = parts[1]
            
            image_bytes = base64.b64decode(img_b64)
            mime_type = data.get("mime_type", mime_type)
            prompt = data.get("prompt")
            include_context = bool(data.get("include_context", True))

        from application.use_cases.ai_analyze_image import AIAnalyzeImageUseCase
        use_case = AIAnalyzeImageUseCase(
            gemini_service=current_app.container.get("gemini_service"),
            coinstats_client=current_app.container.get("api_client"),
        )
        
        result = use_case.execute(
            image_bytes=image_bytes,
            mime_type=mime_type,
            prompt=prompt,
            include_context=include_context,
        )
        
        if not result.get("success"):
            return _error(result.get("error", "خطای تحلیل"), 400)
        
        return _success({
            "analysis": result["analysis"],
            "usage": result.get("usage", {}),
            "latency_ms": result.get("latency_ms", 0),
        })
    except Exception as e:
        logger.error(f"❌ /api/ai/analyze-image error: {e}", exc_info=True)
        return _error(str(e), 500)


# ============================================================
# ۳. Signal Explanation (توضیح سیگنال)
# ============================================================

@ai_bp.route("/explain", methods=["POST"])
@require_auth()
def ai_explain():
    """توضیح یک سیگنال با Gemini Flash."""
    try:
        data = request.json or {}
        coin = data.get("coin", "").strip()
        signal_data = data.get("signal_data")
        
        if not coin or not signal_data:
            return _error("coin و signal_data الزامی هستند", 400)

        from application.use_cases.ai_explain import AIExplainUseCase
        use_case = AIExplainUseCase(
            gemini_service=current_app.container.get("gemini_service"),
            coinstats_client=current_app.container.get("api_client"),
        )
        
        result = use_case.execute(
            coin=coin,
            signal_data=signal_data,
            include_market_context=bool(data.get("include_market_context", True)),
        )
        
        if not result.get("success"):
            return _error(result.get("error", "خطای توضیح"), 400)
        
        return _success({
            "explanation": result["explanation"],
            "coin": result.get("coin", coin),
            "usage": result.get("usage", {}),
            "latency_ms": result.get("latency_ms", 0),
        })
    except Exception as e:
        logger.error(f"❌ /api/ai/explain error: {e}", exc_info=True)
        return _error(str(e), 500)


# ============================================================
# ۴. Live Agent (Gemini Live)
# ============================================================

@ai_bp.route("/agent/chat", methods=["POST"])
@require_auth()
def agent_chat():
    """چت با ایجنت Live."""
    try:
        data = request.json or {}
        message = data.get("message", "").strip()
        if not message:
            return _error("message الزامی است", 400)

        api_key = os.getenv("GEMINI_API_KEY", "")
        if not api_key:
            return _error("GEMINI_API_KEY در environment تنظیم نشده است", 500)

        from application.use_cases.live_agent_use_case import LiveAgentUseCase
        use_case = LiveAgentUseCase(api_key=api_key)
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            reply = loop.run_until_complete(use_case.process_text_message(message))
        finally:
            loop.close()

        return _success({"reply": reply, "agent": "live"})
    except Exception as e:
        logger.error(f"❌ /api/ai/agent/chat error: {e}", exc_info=True)
        return _error(str(e), 500)


@ai_bp.route("/agent/status", methods=["GET"])
def agent_status():
    """وضعیت ایجنت Live و ابزارهایش."""
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
# ۵. Status & Stats
# ============================================================

@ai_bp.route("/status", methods=["GET"])
def ai_status():
    """وضعیت کلی سرویس‌های AI."""
    try:
        gemini_client = current_app.container.get("gemini_client")
        from agent.tools import ALL_TOOLS
        
        return _success({
            "text_model": {
                "available": gemini_client.is_available if gemini_client else False,
                "model": "gemini-3.8-flash",
            },
            "live_agent": {
                "available": bool(os.getenv("GEMINI_API_KEY")),
                "model": "gemini-3.8-live",
                "tools_count": len(ALL_TOOLS),
            },
            "features": {
                "chat": True,
                "vision": True,
                "explain": True,
                "streaming": True,
                "live_agent": bool(os.getenv("GEMINI_API_KEY")),
            },
        })
    except Exception as e:
        logger.error(f"❌ /api/ai/status error: {e}", exc_info=True)
        return _error(str(e), 500)


# ============================================================
# ۶. Debug (فقط برای admin)
# ============================================================

@ai_bp.route("/debug/tools", methods=["GET"])
@require_auth("admin")
def debug_tools():
    """لیست همه ابزارهای ایجنت (برای دیباگ)."""
    try:
        from agent.tools import ALL_TOOLS
        return _success({
            "count": len(ALL_TOOLS),
            "tools": [
                {"name": t.__name__, "doc": t.__doc__}
                for t in ALL_TOOLS
            ],
        })
    except Exception as e:
        return _error(str(e), 500)


@ai_bp.route("/debug/test-tool", methods=["POST"])
@require_auth("admin")
def debug_test_tool():
    """تست یک ابزار خاص (بدون نیاز به مدل)."""
    try:
        data = request.json or {}
        tool_name = data.get("tool_name")
        kwargs = data.get("kwargs", {})
        
        if not tool_name:
            return _error("tool_name الزامی است", 400)
        
        from agent.tools import ALL_TOOLS
        tools_map = {t.__name__: t for t in ALL_TOOLS}
        
        if tool_name not in tools_map:
            return _error(f"ابزار ناشناخته: {tool_name}", 404)
        
        result = tools_map[tool_name](**kwargs)
        return _success({"tool": tool_name, "result": result})
    except Exception as e:
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
        "version": "3.0.0",
        "endpoints": {
            "text": {
                "chat": "POST /api/ai/chat",
                "chat_stream": "POST /api/ai/chat/stream",
            },
            "vision": {
                "analyze_image": "POST /api/ai/analyze-image",
            },
            "explain": {
                "explain": "POST /api/ai/explain",
            },
            "agent": {
                "chat": "POST /api/ai/agent/chat",
                "status": "GET /api/ai/agent/status",
            },
            "debug": {
                "tools": "GET /api/ai/debug/tools",
                "test_tool": "POST /api/ai/debug/test-tool",
            },
            "meta": {
                "status": "GET /api/ai/status",
            },
        },
    })


__all__ = ["ai_bp"]
