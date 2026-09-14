# application/services/command_system.py
# ============================================================
# سیستم دستوری - نسخه ۵.۰
# Model Commands + Profile Support
# ============================================================

import logging
from datetime import datetime
from typing import Optional, Dict, Any, List, Callable

from domain.services.numeric_analyzer import NumericAnalyzer
from infrastructure.database import get_primary

logger = logging.getLogger(__name__)


class CommandSystem:
    """
    سیستم پردازش دستورات متنی
    
    ارتقاها:
        - Model commands (train, profile)
        - Repository stats
        - Better help
    """
    
    def __init__(self, analyzer: NumericAnalyzer) -> None:
        self.analyzer = analyzer
        self.db = get_primary()
        self.default_coin = "bitcoin"
        
        # ============================================================
        # Commands
        # ============================================================
        
        self.commands: Dict[str, Callable[[str], str]] = {
            # ===== قیمت و تحلیل =====
            "/price": self._cmd_price,
            "/analyze": self._cmd_analyze,
            "/signal": self._cmd_signal,
            "/trend": self._cmd_trend,
            "/rsi": self._cmd_rsi,
            "/macd": self._cmd_macd,
            "/support": self._cmd_support,
            "/resistance": self._cmd_resistance,
            "/volatility": self._cmd_volatility,
            
            # ===== مدل =====
            "/model": self._cmd_model,
            "/profile": self._cmd_profile,
            "/profiles": self._cmd_profiles_list,
            "/train": self._cmd_train,
            
            # ===== سیستم =====
            "/history": self._cmd_history,
            "/help": self._cmd_help,
            "/status": self._cmd_status,
            "/metrics": self._cmd_metrics,
            "/health": self._cmd_health,
            "/quota": self._cmd_quota,
        }
        
        # ============================================================
        # Aliases
        # ============================================================
        
        self.aliases: Dict[str, str] = {
            "قیمت": "/price",
            "تحلیل": "/analyze",
            "آنالیز": "/analyze",
            "سیگنال": "/signal",
            "روند": "/trend",
            "مدل": "/model",
            "پروفایل": "/profile",
            "آموزش": "/train",
            "help": "/help",
            "راهنما": "/help",
            "وضعیت": "/status",
        }
        
        logger.info("✅ CommandSystem v5.0 initialized")
    
    # ============================================================
    # Process
    # ============================================================
    
    def process_command(
        self,
        command: str,
        user_id: Optional[str] = None,
    ) -> str:
        """
        پردازش دستور
        
        پارامترها:
            command: دستور
            user_id: شناسه کاربر
        
        خروجی:
            پاسخ
        """
        if not command or not command.strip():
            return "❌ دستور وارد نشده"
        
        command = command.strip()
        
        # Alias
        if command in self.aliases:
            command = self.aliases[command]
        
        # Parse
        parts = command.split()
        cmd_name = parts[0].lower()
        args = parts[1:] if len(parts) > 1 else []
        
        # ذخیره در تاریخچه
        if user_id:
            self._save_history(user_id, command)
        
        # اجرا
        if cmd_name in self.commands:
            try:
                return self.commands[cmd_name](" ".join(args))
            except Exception as e:
                logger.error(f"Command error {cmd_name}: {e}")
                return f"❌ خطا: {str(e)}"
        else:
            suggestions = self._find_similar(cmd_name)
            if suggestions:
                return (
                    f"❌ دستور '{cmd_name}' یافت نشد.\n\n"
                    f"📌 دستورات مشابه:\n" + "\n".join(suggestions)
                )
            return self._cmd_help("")
    
    def _find_similar(self, cmd: str) -> List[str]:
        """پیدا کردن دستورات مشابه"""
        similar = []
        for known in self.commands.keys():
            if cmd in known or known in cmd:
                similar.append(f"  • {known}")
        return similar[:3]
    
    # ============================================================
    # Price Commands
    # ============================================================
    
    def _cmd_price(self, coin: str) -> str:
        coin = coin or self.default_coin
        data = self.analyzer.analyze_coin(coin)
        if "error" in data:
            return f"❌ {data['error']}"
        return f"💰 {coin}: ${data['current_price']:,.2f} ({data['price_change']}%)"
    
    def _cmd_analyze(self, coin: str) -> str:
        coin = coin or self.default_coin
        data = self.analyzer.analyze_coin(coin)
        if "error" in data:
            return f"❌ {data['error']}"
        
        return (
            f"📊 **تحلیل {coin}**\n"
            f"💰 ${data['current_price']:,.2f} ({data['price_change']}%)\n"
            f"📊 RSI: {data.get('rsi', 'N/A')}\n"
            f"📉 MACD: {data.get('macd', {}).get('macd', 'N/A')}\n"
            f"📈 روند: {data.get('trend', 'N/A')}\n"
            f"🛡️ حمایت: ${data.get('support', 'N/A')}\n"
            f"⚔️ مقاومت: ${data.get('resistance', 'N/A')}\n"
            f"📊 نوسان: {data.get('volatility', 'N/A')}"
        )
    
    def _cmd_signal(self, coin: str) -> str:
        coin = coin or self.default_coin
        data = self.analyzer.analyze_coin(coin)
        if "xgboost_signal" in data:
            return (
                f"🧠 سیگنال {coin}: {data['xgboost_signal']} "
                f"({data['xgboost_confidence']}%)"
            )
        return f"❌ سیگنالی برای {coin} نیست"
    
    def _cmd_trend(self, coin: str) -> str:
        coin = coin or self.default_coin
        data = self.analyzer.analyze_coin(coin)
        return f"📈 روند {coin}: {data.get('trend', 'نامشخص')}"
    
    def _cmd_rsi(self, coin: str) -> str:
        coin = coin or self.default_coin
        data = self.analyzer.analyze_coin(coin)
        return f"📊 RSI {coin}: {data.get('rsi', 'N/A')}"
    
    def _cmd_macd(self, coin: str) -> str:
        coin = coin or self.default_coin
        data = self.analyzer.analyze_coin(coin)
        macd = data.get("macd", {})
        return f"📉 MACD {coin}: {macd.get('macd', 'N/A') if isinstance(macd, dict) else macd}"
    
    def _cmd_support(self, coin: str) -> str:
        coin = coin or self.default_coin
        data = self.analyzer.analyze_coin(coin)
        return f"🛡️ حمایت {coin}: ${data.get('support', 'N/A')}"
    
    def _cmd_resistance(self, coin: str) -> str:
        coin = coin or self.default_coin
        data = self.analyzer.analyze_coin(coin)
        return f"⚔️ مقاومت {coin}: ${data.get('resistance', 'N/A')}"
    
    def _cmd_volatility(self, coin: str) -> str:
        coin = coin or self.default_coin
        data = self.analyzer.analyze_coin(coin)
        return f"📊 نوسان {coin}: {data.get('volatility', 'N/A')}"
    
    # ============================================================
    # Model Commands
    # ============================================================
    
    def _cmd_model(self, _: str) -> str:
        """وضعیت مدل"""
        try:
            from container import container
            mm = container.get("model_manager")
            
            loaded = mm.current_model is not None
            version = mm.current_version or "N/A"
            stats = mm.get_stats()
            
            return (
                f"🧠 **وضعیت مدل**\n"
                f"📦 بارگذاری: {'✅' if loaded else '❌'}\n"
                f"🏷️ نسخه: {version}\n"
                f"🎯 دقت: {stats.get('max_accuracy', 0):.2%}\n"
                f"📊 کل نسخه‌ها: {stats.get('total_versions', 0)}\n"
                f"⚙️ پروفایل فعال: {stats.get('active_profile', 'N/A')}"
            )
        except Exception as e:
            return f"❌ خطا: {e}"
    
    def _cmd_profile(self, args: str) -> str:
        """اطلاعات پروفایل"""
        try:
            from container import container
            mm = container.get("model_manager")
            
            if args:
                result = mm.load_profile(args.strip())
                if not result.get("success"):
                    return f"❌ پروفایل '{args}' یافت نشد"
                profile = result["profile"]
            else:
                profile = mm.get_current_profile()
            
            hp = profile.get("hyperparameters", {})
            
            return (
                f"⚙️ **پروفایل: {profile.get('name', 'custom')}**\n"
                f"📝 {profile.get('description', '')}\n"
                f"🔄 استراتژی: {profile.get('learning_strategy', 'full')}\n"
                f"🌲 n_estimators: {hp.get('n_estimators', 'N/A')}\n"
                f"📏 max_depth: {hp.get('max_depth', 'N/A')}\n"
                f"📚 learning_rate: {hp.get('learning_rate', 'N/A')}"
            )
        except Exception as e:
            return f"❌ خطا: {e}"
    
    def _cmd_profiles_list(self, _: str) -> str:
        """لیست پروفایل‌ها"""
        try:
            from container import container
            mm = container.get("model_manager")
            
            presets = mm.get_presets()
            
            result = "📋 **پروفایل‌های آماده:**\n"
            for p in presets:
                result += f"  {p.get('icon', '•')} {p['id']}: {p.get('description', '')}\n"
            
            return result
        except Exception as e:
            return f"❌ خطا: {e}"
    
    def _cmd_train(self, args: str) -> str:
        """آموزش مدل"""
        try:
            from container import container
            trainer = container.get("trainer")
            
            profile_name = args.strip() if args else "balanced"
            
            result = trainer.train_model(
                period="1m",
                profile_name=profile_name,
            )
            
            if result.get("success"):
                return (
                    f"✅ **آموزش موفق**\n"
                    f"🏷️ نسخه: {result.get('version')}\n"
                    f"🎯 دقت: {result.get('accuracy', 0):.2%}\n"
                    f"⚙️ پروفایل: {profile_name}"
                )
            else:
                return f"❌ آموزش ناموفق: {result.get('error')}"
        except Exception as e:
            return f"❌ خطا: {e}"
    
    # ============================================================
    # System Commands
    # ============================================================
    
    def _cmd_status(self, _: str) -> str:
        """وضعیت سیستم"""
        try:
            from core.metrics import metrics_scheduler
            summary = metrics_scheduler.get_summary()
            
            return (
                f"📊 **وضعیت سیستم**\n"
                f"🔄 وضعیت: {summary.get('status', 'unknown')}\n"
                f"📈 Collections: {summary.get('total_collections', 0)}\n"
                f"❌ خطاها: {summary.get('errors', 0)}\n"
                f"🔧 Healing: {summary.get('healing_actions', 0)}"
            )
        except Exception as e:
            return f"❌ خطا: {e}"
    
    def _cmd_metrics(self, _: str) -> str:
        """متریک‌ها"""
        try:
            from core.metrics import metrics_scheduler
            metrics = metrics_scheduler.get_metrics()
            cache = metrics.get("metrics", {})
            
            return (
                f"📊 **متریک‌ها**\n"
                f"🖥️ CPU: {cache.get('cpu', {}).get('value', 0)}%\n"
                f"💾 RAM: {cache.get('ram', {}).get('value', 0)}%\n"
                f"⏱️ Uptime: {cache.get('uptime', {}).get('value', 'N/A')}\n"
                f"🔌 API: {cache.get('api_status', {}).get('value', 'unknown')}\n"
                f"💰 Credits: {cache.get('api_credits', {}).get('value', 0)}"
            )
        except Exception as e:
            return f"❌ خطا: {e}"
    
    def _cmd_health(self, _: str) -> str:
        """سلامت سیستم"""
        try:
            from core.metrics import metrics_scheduler
            health = metrics_scheduler.get_health()
            
            response = f"🏥 **سلامت**: {health.get('status', 'unknown')}\n"
            
            components = health.get("components", {})
            for name, info in components.items():
                status = info.get("status", "unknown")
                emoji = "✅" if status == "healthy" else "⚠️" if status == "degraded" else "❌"
                response += f"{emoji} {name}: {status}\n"
            
            return response
        except Exception as e:
            return f"❌ خطا: {e}"
    
    def _cmd_quota(self, _: str) -> str:
        """وضعیت Quota"""
        try:
            from infrastructure.database import get_all_quotas
            quotas = get_all_quotas()
            
            response = "💾 **وضعیت Quota:**\n"
            for name, quota in quotas.items():
                total = quota.get("total_mb", 0)
                response += f"  • {name}: {total} MB\n"
            
            return response
        except Exception as e:
            return f"❌ خطا: {e}"
    
    def _cmd_history(self, _: str) -> str:
        """تاریخچه دستورات"""
        try:
            if self.db and self.db.is_connected():
                result = self.db.execute(
                    "SELECT command, created_at FROM commands_log "
                    "ORDER BY created_at DESC LIMIT 10"
                )
                
                if result:
                    response = "📋 **تاریخچه:**\n"
                    for row in result:
                        time_str = str(row.get("created_at", ""))[:16]
                        response += f"  • {row.get('command')} ({time_str})\n"
                    return response
            
            return "📋 تاریخچه خالی"
        except Exception as e:
            logger.error(f"History error: {e}")
            return "⚠️ خطا در دریافت تاریخچه"
    
    def _cmd_help(self, _: str) -> str:
        """راهنما"""
        return """📋 **دستورات موجود:**

💰 **بازار**
  /price [coin]      قیمت
  /analyze [coin]    تحلیل
  /signal [coin]     سیگنال
  /trend [coin]      روند
  /rsi [coin]        RSI
  /macd [coin]       MACD
  /support [coin]    حمایت
  /resistance [coin] مقاومت
  /volatility [coin] نوسان

🧠 **مدل**
  /model             وضعیت مدل
  /profile [name]    اطلاعات پروفایل
  /profiles          لیست پروفایل‌ها
  /train [profile]   آموزش

📊 **سیستم**
  /status            وضعیت
  /metrics           متریک‌ها
  /health            سلامت
  /quota             فضای DB
  /history           تاریخچه

📖 **کمکی**
  /help              راهنما

🔹 پیش‌فرض ارز: bitcoin
🔹 مثال: /price ethereum
"""
    
    # ============================================================
    # History
    # ============================================================
    
    def _save_history(self, user_id: str, command: str) -> None:
        """ذخیره در تاریخچه"""
        if not self.db or not self.db.is_connected():
            return
        
        try:
            self.db.execute(
                "INSERT INTO commands_log (user_id, command, created_at) "
                "VALUES (%s, %s, %s)",
                (user_id, command, datetime.now()),
            )
        except Exception as e:
            logger.debug(f"Save history error: {e}")
