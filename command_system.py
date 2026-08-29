# command_system.py
# ============================================================
# سیستم دستوری - نسخه ۳.۰ (با Type Hints کامل)
# ============================================================

import logging
from datetime import datetime
from typing import Optional, Dict, Any, List, Callable, Union

from database import get_primary
from numeric_analyzer import NumericAnalyzer

logger = logging.getLogger(__name__)


class CommandSystem:
    """
    سیستم پردازش دستورات متنی کاربر
    
    ✅ نسخه ۳.۰: اضافه شدن Type Hints کامل
    """
    
    def __init__(self, analyzer: NumericAnalyzer) -> None:
        self.analyzer: NumericAnalyzer = analyzer
        self.db: Any = get_primary()
        self.default_coin: str = "bitcoin"
        
        # دیکشنری دستورات
        self.commands: Dict[str, Callable[[str], str]] = {
            # دستورات اصلی
            "/price": self._cmd_price,
            "/analyze": self._cmd_analyze,
            "/signal": self._cmd_signal,
            "/trend": self._cmd_trend,
            
            # شاخص‌های تکنیکال
            "/rsi": self._cmd_rsi,
            "/macd": self._cmd_macd,
            "/support": self._cmd_support,
            "/resistance": self._cmd_resistance,
            "/volatility": self._cmd_volatility,
            
            # مدیریت
            "/history": self._cmd_history,
            "/help": self._cmd_help,
            "/status": self._cmd_status,
            
            # دستورات سیستم
            "/metrics": self._cmd_metrics,
            "/health": self._cmd_health,
        }
        
        # مترادف‌ها
        self.aliases: Dict[str, str] = {
            "قیمت": "/price",
            "تحلیل": "/analyze",
            "آنالیز": "/analyze",
            "سیگنال": "/signal",
            "روند": "/trend",
            "help": "/help",
            "راهنما": "/help",
        }
        
        # ثبت در Scheduler
        self._register_with_scheduler()
        
        logger.info("✅ CommandSystem v3.0 initialized")
    
    def _register_with_scheduler(self) -> None:
        """ثبت در Scheduler"""
        try:
            from core import metrics_scheduler
            logger.info("✅ CommandSystem registered with Metrics Scheduler")
        except ImportError:
            pass
        except Exception as e:
            logger.debug(f"Could not register with scheduler: {e}")

    def process_command(self, command: str, user_id: Optional[str] = None) -> str:
        """
        پردازش دستور و ذخیره در تاریخچه
        
        پارامترها:
            command: دستور ورودی
            user_id: شناسه کاربر (اختیاری)
        
        خروجی:
            پاسخ دستور به صورت متن
        """
        if not command or not command.strip():
            return "❌ دستور وارد نشده است."
        
        command = command.strip()
        
        # بررسی alias
        if command in self.aliases:
            command = self.aliases[command]
        
        cmd_parts: List[str] = command.split()
        cmd_name: str = cmd_parts[0].lower()
        
        # استخراج کوین (اگر وجود داشته باشد)
        coin: str = self.default_coin
        if len(cmd_parts) > 1:
            coin = cmd_parts[1].lower()
        
        # ذخیره در تاریخچه (اگر user_id وجود داشته باشد)
        if user_id:
            self._save_history(user_id, command)
        
        # پردازش دستور
        if cmd_name in self.commands:
            try:
                # برخی دستورات به کوین نیاز ندارند
                no_coin_commands: List[str] = ["/help", "/history", "/metrics", "/health", "/status"]
                if cmd_name in no_coin_commands:
                    response: str = self.commands[cmd_name]("")
                else:
                    response = self.commands[cmd_name](coin)
                return response
            except Exception as e:
                logger.error(f"❌ Error processing command {cmd_name}: {e}")
                return f"❌ خطا در پردازش دستور: {str(e)}"
        else:
            # پیشنهاد دستورات مشابه
            suggestions: List[str] = self._find_similar_commands(cmd_name)
            if suggestions:
                return f"❌ دستور '{cmd_name}' یافت نشد.\n\n📌 دستورات مشابه:\n" + "\n".join(suggestions)
            return self._cmd_help("")

    def _find_similar_commands(self, cmd: str) -> List[str]:
        """پیدا کردن دستورات مشابه"""
        similar: List[str] = []
        for known_cmd in self.commands.keys():
            if cmd in known_cmd or known_cmd in cmd:
                similar.append(f"  • {known_cmd}")
        return similar[:3]  # حداکثر ۳ مورد

    # ============================================================
    #
