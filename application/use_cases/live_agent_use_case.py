# application/use_cases/live_agent_use_case.py
# ============================================================
# Use Case: Live Agent - مدیریت ایجنت برای وب سرویس
# ============================================================

import logging
from typing import Optional, Dict, Any

from infrastructure.ai.live_agent import LiveAgent
from infrastructure.ai.agent_tools import ALL_TOOLS

logger = logging.getLogger(__name__)

class LiveAgentUseCase:
    """مدیریت چرخه حیات ایجنت Live."""

    def __init__(self, api_key: str):
        self.agent = LiveAgent(
            api_key=api_key,
            system_instruction=(
                "تو یک دستیار عملیاتی هستی. "
                "می‌توانی وضعیت سیستم را بررسی کنی، لاگ‌ها را بخوانی و قیمت ارزها را بگیری. "
                "پاسخ‌ها را به فارسی بده."
            ),
            tools=ALL_TOOLS,
        )

    async def process_text_message(self, text: str) -> str:
        """ارسال پیام متنی و دریافت پاسخ."""
        await self.agent.connect()
        try:
            await self.agent.send_text(text)
            transcript = await self.agent.receive_loop()
            return transcript
        finally:
            await self.agent.disconnect()
