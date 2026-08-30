# application/services/command_system.py
# ============================================================
# سیستم دستوری - نسخه ۴.۰ (رفع Import)
# ============================================================

import logging
from datetime import datetime
from typing import Optional, Dict, Any, List, Callable

from domain.services.numeric_analyzer import NumericAnalyzer
# ✅ اصلاح Import
from infrastructure.database import get_primary

logger = logging.getLogger(__name__)


class CommandSystem:
    """
    سیستم پردازش دستورات متنی کاربر
    
    ✅ نسخه ۴.۰: انتقال به لایه Application
    """
    
    def __init__(self, analyzer: NumericAnalyzer) -> None:
        self.analyzer: NumericAnalyzer = analyzer
        self.db: Any = get_primary()
        self.default_coin: str = "bitcoin"
        
        self.commands: Dict[str, Callable[[str], str]] = {
            "/price": self._cmd_price,
            "/analyze": self._cmd_analyze,
            "/signal": self._cmd_signal,
            "/trend": self._cmd_trend,
            "/rsi": self._cmd_rsi,
            "/macd": self._cmd_macd,
            "/support": self._cmd_support,
            "/resistance": self._cmd_resistance,
            "/volatility": self._cmd_volatility,
            "/history": self._cmd_history,
            "/help": self._cmd_help,
            "/status": self._cmd_status,
            "/metrics": self._cmd_metrics,
            "/health": self._cmd_health,
        }
        
        self.aliases: Dict[str, str] = {
            "قیمت": "/price",
            "تحلیل": "/analyze",
            "آنالیز": "/analyze",
            "سیگنال": "/signal",
            "روند": "/trend",
            "help": "/help",
            "راهنما": "/help",
        }
        
        logger.info("✅ CommandSystem v4.0 initialized")

    def process_command(self, command: str, user_id: Optional[str] = None) -> str:
        """پردازش دستور"""
        if not command or not command.strip():
            return "❌ دستور وارد نشده است."
        
        command = command.strip()
        
        if command in self.aliases:
            command = self.aliases[command]
        
        cmd_parts = command.split()
        cmd_name = cmd_parts[0].lower()
        
        coin = self.default_coin
        if len(cmd_parts) > 1:
            coin = cmd_parts[1].lower()
        
        if user_id:
            self._save_history(user_id, command)
        
        if cmd_name in self.commands:
            try:
                no_coin_commands = ["/help", "/history", "/metrics", "/health", "/status"]
                if cmd_name in no_coin_commands:
                    return self.commands[cmd_name]("")
                return self.commands[cmd_name](coin)
            except Exception as e:
                logger.error(f"Error processing command {cmd_name}: {e}")
                return f"❌ خطا در پردازش دستور: {str(e)}"
        else:
            suggestions = self._find_similar_commands(cmd_name)
            if suggestions:
                return f"❌ دستور '{cmd_name}' یافت نشد.\n\n📌 دستورات مشابه:\n" + "\n".join(suggestions)
            return self._cmd_help("")

    def _find_similar_commands(self, cmd: str) -> List[str]:
        """پیدا کردن دستورات مشابه"""
        similar = []
        for known_cmd in self.commands.keys():
            if cmd in known_cmd or known_cmd in cmd:
                similar.append(f"  • {known_cmd}")
        return similar[:3]

    def _cmd_price(self, coin: str) -> str:
        """نمایش قیمت"""
        data = self.analyzer.analyze_coin(coin)
        if "error" in data:
            return f"❌ {data['error']}"
        return f"💰 قیمت {coin}: ${data['current_price']:,.2f} (تغییر: {data['price_change']}%)"

    def _cmd_analyze(self, coin: str) -> str:
        """تحلیل کامل"""
        data = self.analyzer.analyze_coin(coin)
        if "error" in data:
            return f"❌ {data['error']}"
        
        response = f"📊 **تحلیل کامل {coin}**\n"
        response += f"💰 قیمت: ${data['current_price']:,.2f}\n"
        response += f"📈 تغییر: {data['price_change']}%\n"
        response += f"📊 RSI: {data.get('rsi', 'N/A')}\n"
        response += f"📉 MACD: {data.get('macd', 'N/A')}\n"
        response += f"📈 روند: {data.get('trend', 'N/A')}\n"
        response += f"🛡️ حمایت: ${data.get('support', 'N/A')}\n"
        response += f"⚔️ مقاومت: ${data.get('resistance', 'N/A')}\n"
        response += f"📊 نوسان: {data.get('volatility', 'N/A')}\n"
        if "xgboost_signal" in data:
            response += f"🧠 سیگنال XGBoost: {data['xgboost_signal']} (اطمینان: {data['xgboost_confidence']}%)"
        return response

    def _cmd_signal(self, coin: str) -> str:
        """نمایش سیگنال"""
        data = self.analyzer.analyze_coin(coin)
        if "xgboost_signal" in data:
            return f"🧠 سیگنال {coin}: {data['xgboost_signal']} (اطمینان: {data['xgboost_confidence']}%)"
        return f"❌ سیگنالی برای {coin} موجود نیست."

    def _cmd_trend(self, coin: str) -> str:
        """نمایش روند"""
        data = self.analyzer.analyze_coin(coin)
        if "error" in data:
            return f"❌ {data['error']}"
        return f"📈 روند {coin}: {data.get('trend', 'نامشخص')}"

    def _cmd_rsi(self, coin: str) -> str:
        """نمایش RSI"""
        data = self.analyzer.analyze_coin(coin)
        if "error" in data:
            return f"❌ {data['error']}"
        return f"📊 RSI {coin}: {data.get('rsi', 'N/A')}"

    def _cmd_macd(self, coin: str) -> str:
        """نمایش MACD"""
        data = self.analyzer.analyze_coin(coin)
        if "error" in data:
            return f"❌ {data['error']}"
        macd = data.get('macd', {}).get('macd', 'N/A')
        return f"📉 MACD {coin}: {macd}"

    def _cmd_support(self, coin: str) -> str:
        """نمایش سطح حمایت"""
        data = self.analyzer.analyze_coin(coin)
        if "error" in data:
            return f"❌ {data['error']}"
        return f"🛡️ سطح حمایت {coin}: ${data.get('support', 'N/A')}"

    def _cmd_resistance(self, coin: str) -> str:
        """نمایش سطح مقاومت"""
        data = self.analyzer.analyze_coin(coin)
        if "error" in data:
            return f"❌ {data['error']}"
        return f"⚔️ سطح مقاومت {coin}: ${data.get('resistance', 'N/A')}"

    def _cmd_volatility(self, coin: str) -> str:
        """نمایش نوسان"""
        data = self.analyzer.analyze_coin(coin)
        if "error" in data:
            return f"❌ {data['error']}"
        return f"📊 نوسان {coin}: {data.get('volatility', 'N/A')}"

    def _cmd_metrics(self, _: str) -> str:
        """نمایش متریک‌ها"""
        try:
            from core.metrics import metrics_scheduler
            metrics = metrics_scheduler.get_metrics()
            cache = metrics.get('metrics', {})
            
            response = "📊 **متریک‌های سیستم**\n"
            response += f"🖥️ CPU: {cache.get('cpu', {}).get('value', 0)}%\n"
            response += f"💾 RAM: {cache.get('ram', {}).get('value', 0)}%\n"
            response += f"⏱️ آپتایم: {cache.get('uptime', {}).get('value', 'N/A')}\n"
            response += f"🔌 API: {cache.get('api_status', {}).get('value', 'unknown')}\n"
            response += f"💰 اعتبار: {cache.get('api_credits', {}).get('value', 0)}\n"
            return response
        except Exception as e:
            return f"❌ خطا در دریافت متریک: {e}"

    def _cmd_health(self, _: str) -> str:
        """نمایش وضعیت سلامت"""
        try:
            from core.metrics import metrics_scheduler
            health = metrics_scheduler.get_health()
            
            response = "🏥 **وضعیت سلامت سیستم**\n"
            response += f"📊 وضعیت کلی: {health.get('status', 'unknown')}\n"
            
            components = health.get('components', {})
            for name, info in components.items():
                status = info.get('status', 'unknown')
                emoji = "✅" if status == "healthy" else "⚠️" if status == "degraded" else "❌"
                response += f"{emoji} {name}: {status}\n"
            
            return response
        except Exception as e:
            return f"❌ خطا در دریافت سلامت: {e}"

    def _cmd_status(self, _: str) -> str:
        """نمایش وضعیت کلی"""
        try:
            from core.metrics import metrics_scheduler
            summary = metrics_scheduler.get_summary()
            
            response = "📊 **وضعیت سیستم**\n"
            response += f"🔄 وضعیت: {summary.get('status', 'unknown')}\n"
            response += f"📈 کل جمع‌آوری‌ها: {summary.get('total_collections', 0)}\n"
            response += f"❌ خطاها: {summary.get('errors', 0)}\n"
            return response
        except Exception as e:
            return f"❌ خطا در دریافت وضعیت: {e}"

    def _cmd_history(self, _: str) -> str:
        """نمایش تاریخچه"""
        try:
            if self.db and self.db.is_connected():
                result = self.db.execute(
                    "SELECT command, created_at FROM commands_log ORDER BY created_at DESC LIMIT 10"
                )
                if result:
                    response = "📋 **تاریخچه دستورات شما**\n"
                    for row in result:
                        time_str = row.get('created_at', '')
                        if time_str:
                            time_str = time_str[:16]
                        response += f"  • {row.get('command')} ({time_str})\n"
                    return response
            return "📋 تاریخچه دستورات شما خالی است."
        except Exception as e:
            logger.error(f"Error in history: {e}")
            return "⚠️ خطا در دریافت تاریخچه"

    def _cmd_help(self, _: str) -> str:
        """راهنما"""
        return """
📋 **دستورات موجود:**

💰 **قیمت و بازار**
  /price [coin]      - نمایش قیمت و تغییرات
  /analyze [coin]    - نمایش تحلیل کامل
  /signal [coin]     - نمایش سیگنال XGBoost

📈 **تحلیل تکنیکال**
  /trend [coin]      - نمایش روند
  /rsi [coin]        - نمایش شاخص RSI
  /macd [coin]       - نمایش MACD
  /support [coin]    - نمایش سطح حمایت
  /resistance [coin] - نمایش سطح مقاومت
  /volatility [coin] - نمایش نوسان

📊 **سیستم**
  /metrics           - نمایش متریک‌های سیستم
  /health            - نمایش وضعیت سلامت
  /status            - نمایش وضعیت کلی

📋 **مدیریت**
  /history           - نمایش تاریخچه دستورات شما
  /help              - نمایش این راهنما

🔹 **نکته:** ارز پیش‌فرض bitcoin است.
🔹 **مثال:** /price ethereum
"""

    def _save_history(self, user_id: str, command: str) -> None:
        """ذخیره در تاریخچه"""
        if not self.db or not self.db.is_connected():
            return
        
        try:
            self.db.execute(
                "INSERT INTO commands_log (user_id, command, created_at) VALUES (%s, %s, %s)",
                (user_id, command, datetime.now())
            )
        except Exception as e:
            logger.debug(f"Could not save history: {e}")
