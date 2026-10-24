# agent/live_agent.py
# ============================================================
# Live Agent - اتصال مستقیم به Gemini Live API (بدون ADK)
# نسخه ۳.۰ - با Async Tools, Session Resumption, Compression
# ============================================================

import asyncio
import logging
from typing import Callable, List, Optional

from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

class LiveAgent:
    def __init__(
        self,
        api_key: str,
        model: str = "gemini-3.8-live",
        system_instruction: str = "تو یک دستیار هستی.",
        tools: Optional[List[Callable]] = None,
        enable_resumption: bool = True,
        enable_compression: bool = True,
    ):
        self.client = genai.Client(api_key=api_key)
        self.model = model
        self.tools = tools or []
        self.tools_map = {tool.__name__: tool for tool in self.tools}
        self.session = None
        self._resumption_handle: Optional[str] = None

        # ساخت config با پروتکل‌های قوی‌تر
        config_kwargs = {
            "response_modalities": ["AUDIO"],
            "output_audio_transcription": types.AudioTranscriptionConfig(),
            "input_audio_transcription": types.AudioTranscriptionConfig(),
            "system_instruction": types.Content(parts=[types.Part(text=system_instruction)]),
            "tools": self._build_tools_declaration(),
        }

        # Session Resumption (بازیابی session پس از قطع)
        if enable_resumption:
            config_kwargs["session_resumption"] = types.SessionResumptionConfig()

        # Context Window Compression (جلوگیری از قطع در مکالمات طولانی)
        if enable_compression:
            config_kwargs["context_window_compression"] = types.ContextWindowCompressionConfig(
                sliding_window=types.SlidingWindow()
            )

        self.config = types.LiveConnectConfig(**config_kwargs)

    def _build_tools_declaration(self) -> List[types.Tool]:
        if not self.tools:
            return []
        declarations = []
        for tool in self.tools:
            # ⭐ Async Function Calling: NON_BLOCKING برای اینکه مکالمه قطع نشود
            declaration = types.FunctionDeclaration(
                name=tool.__name__,
                description=tool.__doc__ or "No description",
                parameters_json_schema={"type": "object", "properties": {}},
                behavior="NON_BLOCKING",  # ابزار در پس‌زمینه اجرا می‌شود
            )
            declarations.append(declaration)
        return [types.Tool(function_declarations=declarations)]

    async def connect(self):
        logger.info(f"Connecting to Live API (model={self.model})")
        connect_kwargs = {"model": self.model, "config": self.config}
        if self._resumption_handle:
            connect_kwargs["config"].session_resumption = types.SessionResumptionConfig(
                handle=self._resumption_handle
            )
        self.session = await self.client.aio.live.connect(**connect_kwargs).__aenter__()
        logger.info("✅ Connected")

    async def disconnect(self):
        if self.session:
            await self.session.__aexit__(None, None, None)
            self.session = None
            logger.info("Disconnected")

    async def send_text(self, text: str):
        if not self.session:
            raise RuntimeError("Not connected")
        await self.session.send_realtime_input(text=text)

    async def send_audio(self, pcm_bytes: bytes):
        if not self.session:
            raise RuntimeError("Not connected")
        await self.session.send_realtime_input(
            audio=types.Blob(data=pcm_bytes, mime_type="audio/pcm;rate=16000")
        )

    async def receive_loop(self) -> str:
        if not self.session:
            raise RuntimeError("Not connected")

        full_transcript = ""

        async for response in self.session.receive():
            # بررسی GoAway (هشدار قبل از قطع اتصال)
            if response.go_away:
                logger.warning(f"GoAway received, time left: {response.go_away.time_left}")

            # بررسی Session Resumption Update
            if response.session_resumption_update:
                update = response.session_resumption_update
                if update.resumable and update.new_handle:
                    self._resumption_handle = update.new_handle
                    logger.debug(f"Resumption handle updated")

            if response.server_content:
                if response.server_content.output_transcription:
                    text = response.server_content.output_transcription.text
                    if text:
                        full_transcript += text

                if response.server_content.turn_complete:
                    break

            if response.tool_call:
                await self._handle_tool_call(response.tool_call)

        return full_transcript

    async def _handle_tool_call(self, tool_call):
        function_responses = []
        for fc in tool_call.function_calls:
            name = fc.name
            args = dict(fc.args or {})
            logger.info(f"🔧 Tool call: {name}({args})")

            if name in self.tools_map:
                try:
                    # اجرای ابزار (sync یا async)
                    result = self.tools_map[name](**args)
                    if asyncio.iscoroutine(result):
                        result = await result
                except Exception as e:
                    logger.error(f"Tool error: {e}")
                    result = {"error": str(e)}
            else:
                result = {"error": f"Unknown tool: {name}"}

            logger.info(f"📥 Tool result: {result}")

            # ⭐ Scheduling: نتیجه ابزار در اولین فرصت به مدل داده شود
            function_responses.append(
                types.FunctionResponse(
                    name=name,
                    response={"result": result},
                    scheduling="INTERRUPT",  # مدل فوراً نتیجه را اعلام می‌کند
                )
            )

        await self.session.send_tool_response(function_responses=function_responses)
