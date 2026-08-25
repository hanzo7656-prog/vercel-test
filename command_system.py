# command_system.py
# ============================================================
# سیستم دستوری - پردازش دستورات متنی کاربران
# ============================================================

from numeric_analyzer import NumericAnalyzer

class CommandSystem:
    def __init__(self, analyzer: NumericAnalyzer):
        self.analyzer = analyzer
        self.commands = {
            "/price": self._cmd_price,
            "/analyze": self._cmd_analyze,
            "/signal": self._cmd_signal,
            "/trend": self._cmd_trend,
            "/help": self._cmd_help,
        }

    def process_command(self, command: str, args: str = "") -> str:
        """پردازش دستور و بازگرداندن پاسخ"""
        cmd_parts = command.strip().split()
        if not cmd_parts:
            return "❌ دستور وارد نشده است."

        cmd_name = cmd_parts[0].lower()
        coin = cmd_parts[1] if len(cmd_parts) > 1 else "bitcoin"

        if cmd_name in self.commands:
            try:
                return self.commands[cmd_name](coin)
            except Exception as e:
                return f"❌ خطا در پردازش دستور: {e}"
        else:
            return self._cmd_help("")  # دستور ناشناخته

    # ---------- پیاده‌سازی دستورات ----------
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

    def _cmd_help(self, _) -> str:
        return """
📋 **دستورات موجود:**
/price [coin]      - نمایش قیمت و تغییرات
/analyze [coin]    - نمایش تحلیل کامل
/signal [coin]     - نمایش سیگنال XGBoost
/trend [coin]      - نمایش روند
/help              - نمایش این راهنما
"""
