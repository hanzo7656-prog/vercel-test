# application/use_cases/live_agent_use_case.py
import logging
from agent.live_agent import LiveAgent
from agent.tools import ALL_TOOLS

logger = logging.getLogger(__name__)

class LiveAgentUseCase:
    def __init__(self, api_key: str):
        self.agent = LiveAgent(
            api_key=api_key,
            system_instruction=(
                "تو یک دستیار عملیاتی هستی. "
                "می‌توانی وضعیت سیستم را بررسی کنی، لاگ‌ها را بخوانی، "
                "قیمت ارزها را بگیری، پیش‌بینی کنی و دیتابیس را ببینی. "
                "پاسخ‌ها را به فارسی بده."
            ),
            tools=ALL_TOOLS,
        )

    async def process_text_message(self, text: str) -> str:
        await self.agent.connect()
        try:
            await self.agent.send_text(text)
            return await self.agent.receive_loop()
        finally:
            await self.agent.disconnect()
