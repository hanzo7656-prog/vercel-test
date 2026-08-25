# command_system.py
# ============================================================
# سیستم دستوری - نسخه کامل با تاریخچه و پاسخ‌های پیشرفته
# ============================================================

from datetime import datetime
from database import get_primary

class CommandSystem:
    def __init__(self, analyzer):
        self.analyzer = analyzer
        self.db = get_primary()
        self.commands = {
            "/price": self._cmd_price,
            "/analyze": self._cmd_analyze,
            "/signal": self._cmd_signal,
            "/trend": self._cmd_trend,
            "/rsi": self._cmd_rsi,
            "/support": self._cmd_support,
            "/resistance": self._cmd_resistance,
            "/help": self._cmd_help,
            "/history": self._cmd_history,
        }
        self.default_coin = "bitcoin"

    def process_command(self, command: str, user_id: str = None) -> str:
        """پردازش دستور و ذخیره در تاریخچه"""
        cmd_parts = command.strip().split()
        if not cmd_parts:
            return "❌ دستور وارد نشده است."

        cmd_name = cmd_parts[0].lower()
        coin = cmd_parts[1] if len(cmd_parts) > 1 else self.default_coin

        # ذخیره در تاریخچه (اگر user_id وجود داشته باشد)
        if user_id:
            self._save_history(user_id, command)

        if cmd_name in self.commands:
            try:
                response = self.commands[cmd_name](coin)
                return response
            except Exception as e:
                return f"❌ خطا در پردازش دستور: {e}"
        else:
            return self._cmd_help("")

    # ---------- دستورات ----------
    
    def _cmd_price(self, coin: str) -> str:
        data = self.analyzer.analyze_coin(coin)
        if "error" in data:
            return f"❌ {data['error']}"
        return f"💰 قیمت {coin}: ${data['current_price']:,.2f} (تغییر: {data['price_change']}%)"

    def _cmd_analyze(self, coin: str) -> str:
        data = self.analyzer.analyze_coin(coin)
        if "error" in data:
            return f"❌ {data['error']}"
        
        response = f"📊 **تحلیل کامل {coin}**\n"
        response += f"💰 قیمت: ${data['current_price']:,.2f}\n"
        response += f"📈 تغییر: {data['price_change']}%\n"
        response += f"📊 RSI: {data.get('rsi', 'N/A')}\n"
        response += f"📉 MACD: {data.get('macd', 'N/A')}\n"
        response += f"📈 روند: {data.get('trend', 'N/A')}\n"
        response += f"🛡️ حمایت: {data.get('support', 'N/A')}\n"
        response += f"⚔️ مقاومت: {data.get('resistance', 'N/A')}\n"
        if "xgboost_signal" in data:
            response += f"🧠 سیگنال XGBoost: {data['xgboost_signal']} (اطمینان: {data['xgboost_confidence']}%)"
        return response

    def _cmd_signal(self, coin: str) -> str:
        data = self.analyzer.analyze_coin(coin)
        if "xgboost_signal" in data:
            return f"🧠 سیگنال {coin}: {data['xgboost_signal']} (اطمینان: {data['xgboost_confidence']}%)"
        return f"❌ سیگنالی برای {coin} موجود نیست."

    def _cmd_trend(self, coin: str) -> str:
        data = self.analyzer.analyze_coin(coin)
        if "error" in data:
            return f"❌ {data['error']}"
        return f"📈 روند {coin}: {data.get('trend', 'نامشخص')}"

    def _cmd_rsi(self, coin: str) -> str:
        data = self.analyzer.analyze_coin(coin)
        if "error" in data:
            return f"❌ {data['error']}"
        return f"📊 RSI {coin}: {data.get('rsi', 'N/A')}"

    def _cmd_support(self, coin: str) -> str:
        data = self.analyzer.analyze_coin(coin)
        if "error" in data:
            return f"❌ {data['error']}"
        return f"🛡️ سطح حمایت {coin}: ${data.get('support', 'N/A')}"

    def _cmd_resistance(self, coin: str) -> str:
        data = self.analyzer.analyze_coin(coin)
        if "error" in data:
            return f"❌ {data['error']}"
        return f"⚔️ سطح مقاومت {coin}: ${data.get('resistance', 'N/A')}"

    def _cmd_history(self, _) -> str:
        # نمایش تاریخچه دستورات کاربر
        return "📋 تاریخچه دستورات شما در حال بارگذاری..."

    def _cmd_help(self, _) -> str:
        return """
📋 **دستورات موجود:**

💰 **قیمت و بازار**
  /price [coin]      - نمایش قیمت و تغییرات
  /analyze [coin]    - نمایش تحلیل کامل
  /signal [coin]     - نمایش سیگنال XGBoost

📈 **تحلیل تکنیکال**
  /trend [coin]      - نمایش روند
  /rsi [coin]        - نمایش شاخص RSI
  /support [coin]    - نمایش سطح حمایت
  /resistance [coin] - نمایش سطح مقاومت

📋 **مدیریت**
  /history           - نمایش تاریخچه دستورات شما
  /help              - نمایش این راهنما

🔹 **نکته:** ارز پیش‌فرض bitcoin است.
🔹 **مثال:** /price ethereum
"""

    # ---------- ذخیره تاریخچه ----------
    def _save_history(self, user_id: str, command: str):
        """ذخیره دستور در دیتابیس"""
        if not self.db or not self.db.is_connected():
            return
        
        try:
            self.db.execute(
                """INSERT INTO commands_log (user_id, command, created_at) 
                   VALUES (%s, %s, %s)""",
                (user_id, command, datetime.now())
            )
        except Exception as e:
            print(f"⚠️ خطا در ذخیره تاریخچه: {e}")
