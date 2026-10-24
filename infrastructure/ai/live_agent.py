# infrastructure/ai/live_agent.py
# ============================================================
# Live Agent - اتصال مستقیم به Gemini Live API
# نسخه ۱.۰ - جایگزین ADK
# ============================================================

import asyncio
import base64
import json
import logging
from datetime import datetime
from typing import Callable, Dict, List, Optional

from google import genai
from google.genai import types

logger = logging.getLogger(__name__)


class LiveAgent:
    """
    ایجنت Live با اتصال مستقیم به WebSocket گوگل.
    
    ویژگی‌ها:
        - مدیریت Session
        - اجرای ابزارها (Function Calling)
        - رونویسی صوتی (Input/Output)
        - تاریخچه مکالمه
    """

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-2.5-flash-native-audio-preview-12-2025",
        system_instruction: str = "تو یک دستیار هستی.",
        tools: Optional[List[Callable]] = None,
    ):
        self.client = genai.Client(api_key=api_key)
        self.model = model
        self.system_instruction = system_instruction
        self.tools = tools or []
        
        # نقشه ابزارها: {name: callable}
        self.tools_map = {tool.__name__: tool for tool in self.tools}
        
        self.session = None
        self.history: List[types.Content] = []
        
        # تنظیمات اتصال
        self.config = types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            output_audio_transcription=types.AudioTranscriptionConfig(),
            input_audio_transcription=types.AudioTranscriptionConfig(),
            system_instruction=types.Content(parts=[types.Part(text=self.system_instruction)]),
            tools=self._build_tools_declaration(),
        )

    def _build_tools_declaration(self) -> List[types.Tool]:
        """ساخت تعریف ابزارها برای مدل."""
        if not self.tools:
            return []
        
        declarations = []
        for tool in self.tools:
            # استخراج داک‌استرینگ برای توضیحات
            description = tool.__doc__ or "No description"
            
            # ⚠️ نکته: برای سادگی، فرض می‌کنیم ابزارها بدون پارامتر هستند.
            # برای ابزارهای پارامتردار، باید JSON Schema بنویسید.
            declaration = types.FunctionDeclaration(
                name=tool.__name__,
                description=description,
                parameters_json_schema={"type": "object", "properties": {}},
            )
            declarations.append(declaration)
        
        return [types.Tool(function_declarations=declarations)]

    async def connect(self):
        """اتصال به WebSocket."""
        logger.info(f"Connecting to Live API (model={self.model})")
        self.session = await self.client.aio.live.connect(
            model=self.model, 
            config=self.config
        ).__aenter__()
        logger.info("✅ Connected to Live API")

    async def disconnect(self):
        """قطع اتصال."""
        if self.session:
            await self.session.__aexit__(None, None, None)
            self.session = None
            logger.info("Disconnected from Live API")

    async def send_text(self, text: str):
        """ارسال پیام متنی."""
        if not self.session:
            raise RuntimeError("Not connected")
        
        logger.info(f"👤 User: {text}")
        await self.session.send_realtime_input(text=text)

    async def send_audio(self, pcm_bytes: bytes):
        """ارسال بایت‌های صوتی (PCM 16kHz)."""
        if not self.session:
            raise RuntimeError("Not connected")
        
        await self.session.send_realtime_input(
            audio=types.Blob(
                data=pcm_bytes,
                mime_type="audio/pcm;rate=16000"
            )
        )

    async def receive_loop(self, on_audio: Optional[Callable[[bytes], None]] = None, on_text: Optional[Callable[[str], None]] = None):
        """
        حلقه دریافت پاسخ.
        
        Args:
            on_audio: callback برای دریافت بایت‌های صوتی (PCM 24kHz)
            on_text: callback برای دریافت متن (رونویسی)
        """
        if not self.session:
            raise RuntimeError("Not connected")
        
        full_transcript = ""
        
        async for response in self.session.receive():
            # ۱. بررسی پاسخ متنی (یا رونویسی صوتی)
            if response.server_content:
                # رونویسی خروجی
                if response.server_content.output_transcription:
                    text = response.server_content.output_transcription.text
                    if text:
                        full_transcript += text
                        if on_text:
                            on_text(text)
                
                # داده‌های صوتی
                if response.server_content.model_turn:
                    for part in response.server_content.model_turn.parts:
                        if part.inline_data:
                            if on_audio:
                                on_audio(part.inline_data.data)
                
                # پایان نوبت
                if response.server_content.turn_complete:
                    logger.info("🤖 Turn complete")
                    break
            
            # ۲. بررسی فراخوانی ابزار
            if response.tool_call:
                await self._handle_tool_call(response.tool_call)
        
        return full_transcript

    async def _handle_tool_call(self, tool_call):
        """اجرای ابزار و ارسال نتیجه به مدل."""
        function_responses = []
        
        for fc in tool_call.function_calls:
            name = fc.name
            args = dict(fc.args or {})
            
            logger.info(f"🔧 Tool call: {name}({args})")
            
            # اجرای ابزار
            if name in self.tools_map:
                try:
                    # فراخوانی تابع (فرض می‌کنیم sync است)
                    result = self.tools_map[name](**args)
                except Exception as e:
                    logger.error(f"Tool error: {e}")
                    result = {"error": str(e)}
            else:
                result = {"error": f"Unknown tool: {name}"}
            
            logger.info(f"📥 Tool result: {result}")
            
            # آماده‌سازی پاسخ
            function_responses.append(
                types.FunctionResponse(
                    name=name,
                    response={"result": result}
                )
            )
        
        # ارسال به مدل
        await self.session.send_tool_response(
            function_responses=function_responses
        )
