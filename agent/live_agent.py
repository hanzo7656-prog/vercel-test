# agent/live_agent.py
# ============================================================
# Live Agent - اتصال مستقیم به Gemini Live API (بدون ADK)
# نسخه ۲.۰
# ============================================================

import logging
from typing import Callable, List, Optional

from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

class LiveAgent:
    """ایجنت Live با اتصال مستقیم به WebSocket گوگل."""

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
        self.tools_map = {tool.__name__: tool for tool in self.tools}
        self.session = None

        self.config = types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            output_audio_transcription=types.AudioTranscriptionConfig(),
            input_audio_transcription=types.AudioTranscriptionConfig(),
            system_instruction=types.Content(parts=[types.Part(text=self.system_instruction)]),
            tools=self._build_tools_declaration(),
        )

    def _build_tools_declaration(self) -> List[types.Tool]:
        """ساخت تعریف ابزارها برای مدل بر اساس داک‌استرینگ."""
        if not self.tools:
            return []

        declarations = []
        for tool in self.tools:
            declaration = types.FunctionDeclaration(
                name=tool.__name__,
                description=tool.__doc__ or "No description",
                parameters_json_schema={"type": "object", "properties": {}},
            )
            declarations.append(declaration)

        return [types.Tool(function_declarations=declarations)]

    async def connect(self):
        logger.info(f"Connecting to Live API (model={self.model})")
        self.session = await self.client.aio.live.connect(
            model=self.model, config=self.config
        ).__aenter__()
        logger.info("✅ Connected to Live API")

    async def disconnect(self):
        if self.session:
            await self.session.__aexit__(None, None, None)
            self.session = None
            logger.info("Disconnected from Live API")

    async def send_text(self, text: str):
        if not self.session:
            raise RuntimeError("Not connected")
        logger.info(f"👤 User: {text}")
        await self.session.send_realtime_input(text=text)

    async def receive_loop(self) -> str:
        """دریافت پاسخ و اجرای ابزارها."""
        if not self.session:
            raise RuntimeError("Not connected")

        full_transcript = ""

        async for response in self.session.receive():
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
                    result = self.tools_map[name](**args)
                except Exception as e:
                    logger.error(f"Tool error: {e}")
                    result = {"error": str(e)}
            else:
                result = {"error": f"Unknown tool: {name}"}

            logger.info(f"📥 Tool result: {result}")
            function_responses.append(
                types.FunctionResponse(name=name, response={"result": result})
            )

        await self.session.send_tool_response(function_responses=function_responses)
