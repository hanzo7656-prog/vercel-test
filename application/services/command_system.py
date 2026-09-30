# application/services/command_system.py
# ============================================================
# سیستم دستوری - نسخه ۶.۰
# RuleEngine Commands + Calibration + Screener + State
# ============================================================
# 
# تغییرات نسخه ۶.۰:
#   - حذف /model, /profile, /profiles, /train (XGBoost-specific)
#   - اضافه /rules, /config, /calibrate, /scan, /state
#   - اضافه /versions, /schedule
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
    
    ارتقاها (v6.0):
        - RuleEngine commands (rules, config)
        - Calibration commands
        - Screener commands (scan)
        - State commands
        - بدون XGBoost
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
            
            # ===== مدل (RuleEngine) =====
            "/model": self._cmd_model,
            "/rules": self._cmd_rules,
            "/config": self._cmd_config,
            "/versions": self._cmd_versions,
            
            # ===== کالیبراسیون =====
            "/calibrate": self._cmd_calibrate,
            "/profiles": self._cmd_profiles_list,
            "/schedule": self._cmd_schedule,
            
            # ===== اسکن =====
            "/scan": self._cmd_scan,
            "/state": self._cmd_state,
            
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
            "قوانین": "/rules",
            "تنظیمات": "/config",
            "نسخه‌ها": "/versions",
            "کالیبراسیون": "/calibrate",
            "پروفایل": "/profiles",
            "زمان‌بندی": "/schedule",
            "اسکن": "/scan",
            "وضعیت": "/state",
            "help": "/help",
            "راهنما": "/help",
            "وضعیت_سیستم": "/status",
        }
        
        logger.info("✅ CommandSystem v6.0 initialized")
    
    # ============================================================
    # Process
    # ============================================================
    
    def process_command(
        self,
        command: str,
        user_id: Optional[str] = None,
    ) -> str:
        """پردازش دستور"""
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
        if "signal" in data:
            return (
                f"🧠 سیگنال {coin}: {data['signal']} "
                f"({data.get('confidence', 0)}%)"
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
    # Model Commands (RuleEngine)
    # ============================================================
    
    def _cmd_model(self, _: str) -> str:
        """وضعیت مدل"""
        try:
            from container import container
            mm = container.get("model_manager")
            
            loaded = mm.engine is not None
            version = mm.current_version or "default"
            stats = mm.get_stats()
            engine_stats = stats.get("engine", {})
            
            return (
                f"🧠 **وضعیت مدل (RuleEngine)**\n"
                f"📦 بارگذاری: {'✅' if loaded else '❌'}\n"
                f"🏷️ نسخه: {version}\n"
                f"📋 تعداد قوانین: {stats.get('rule_count', 0)}\n"
                f"🎯 آستانه قبولی: {engine_stats.get('min_pass_score', 0.55):.2f}\n"
                f"⚙️ ترکیب: {engine_stats.get('aggregation', 'weighted_sum')}\n"
                f"📊 کل نسخه‌ها: {stats.get('total_versions', 0)}\n"
                f"🔧 Runtime config: {'✅' if stats.get('runtime_config_active') else '❌'}"
            )
        except Exception as e:
            return f"❌ خطا: {e}"
    
    def _cmd_rules(self, _: str) -> str:
        """لیست قوانین فعال"""
        try:
            from container import container
            mm = container.get("model_manager")
            
            if mm.engine is None:
                return "❌ RuleEngine بارگذاری نشده"
            
            response = "📋 **قوانین فعال:**\n\n"
            for rule in mm.engine.rules:
                status = "✅" if rule.enabled else "❌"
                response += (
                    f"{status} **{rule.name}** — وزن: {rule.weight:.2f}\n"
                )
                # پارامترهای کلیدی
                cfg = rule.config
                if rule.name == "rsi":
                    response += f"   RSI بازه: [{cfg.get('min', 25)}, {cfg.get('max', 60)}]\n"
                elif rule.name == "volume":
                    response += f"   ضریب: {cfg.get('multiplier', 1.2)}x\n"
                elif rule.name == "trend":
                    response += f"   MA: {cfg.get('ma_column', 'MA50')} ({cfg.get('vs_ma', 'above')})\n"
                elif rule.name == "momentum":
                    response += f"   MACD: {cfg.get('macd_positive', 'neutral')}\n"
            
            return response
        except Exception as e:
            return f"❌ خطا: {e}"
    
    def _cmd_config(self, _: str) -> str:
        """config فعلی"""
        try:
            from container import container
            mm = container.get("model_manager")
            config = mm.get_active_config()
            
            scoring = config.get("scoring", {})
            batch = config.get("batch", {})
            symbols = config.get("symbols", {})
            
            return (
                f"⚙️ **تنظیمات فعلی**\n\n"
                f"📊 **Scoring:**\n"
                f"   Min pass: {scoring.get('min_pass_score', 0.55)}\n"
                f"   Aggregation: {scoring.get('aggregation', 'weighted_sum')}\n\n"
                f"🔍 **Batch:**\n"
                f"   Batch size: {batch.get('batch_size', 30)}\n"
                f"   Timeframe: {batch.get('timeframe', '4h')}\n\n"
                f"🪙 **Symbols:**\n"
                f"   Count: {symbols.get('count', 30)}\n"
                f"   Exclude stables: {symbols.get('exclude_stablecoins', True)}"
            )
        except Exception as e:
            return f"❌ خطا: {e}"
    
    def _cmd_versions(self, args: str) -> str:
        """لیست نسخه‌ها"""
        try:
            from container import container
            mm = container.get("model_manager")
            
            limit = 10
            if args:
                try:
                    limit = int(args.strip())
                except ValueError:
                    pass
            
            versions = mm.get_version_history(limit=limit)
            
            if not versions:
                return "📋 هیچ نسخه‌ای ثبت نشده"
            
            response = f"📋 **آخرین {len(versions)} نسخه:**\n\n"
            for v in versions:
                active = "🟢" if v.get("is_active") else "⚪"
                acc = v.get("accuracy", 0) or 0
                version = v.get("version", "N/A")
                date = str(v.get("training_date", ""))[:19]
                response += f"{active} **{version}** — دقت: {acc:.2%} ({date})\n"
            
            return response
        except Exception as e:
            return f"❌ خطا: {e}"
    
    # ============================================================
    # Calibration Commands
    # ============================================================
    
    def _cmd_calibrate(self, args: str) -> str:
        """کالیبراسیون وزن‌ها"""
        try:
            from container import container
            trainer = container.get("trainer")
            
            profile_name = args.strip() if args else "balanced"
            
            response = f"🔄 **شروع کالیبراسیون ({profile_name})...**\n"
            result = trainer.calibrate(
                period="1m",
                profile_name=profile_name,
                save=True,
            )
            
            if result.get("success"):
                return (
                    f"✅ **کالیبراسیون موفق**\n"
                    f"🏷️ نسخه: {result.get('version', 'N/A')}\n"
                    f"🎯 بهترین امتیاز: {result.get('best_score', 0):.4f}\n"
                    f"📈 بهبود: {result.get('improvement', 0):+.4f}\n"
                    f"⏱️ زمان: {result.get('duration_seconds', 0):.1f}s\n"
                    f"⚙️ پروفایل: {profile_name}"
                )
            else:
                return f"❌ کالیبراسیون ناموفق: {result.get('error')}"
        except Exception as e:
            return f"❌ خطا: {e}"
    
    def _cmd_profiles_list(self, _: str) -> str:
        """لیست پروفایل‌های کالیبراسیون"""
        try:
            from container import container
            trainer = container.get("trainer")
            
            if hasattr(trainer, 'get_presets'):
                presets = trainer.get_presets()
            else:
                from models.trainer.auto_trainer import CALIBRATION_PROFILES
                presets = [
                    {'id': k, **v}
                    for k, v in CALIBRATION_PROFILES.items()
                ]
            
            response = "📋 **پروفایل‌های کالیبراسیون:**\n\n"
            for p in presets:
                icon = p.get('icon', '•')
                pid = p.get('id', '?')
                desc = p.get('description', '')
                est = p.get('estimated_time_seconds', '?')
                response += f"  {icon} **{pid}** — {desc} (~{est}s)\n"
            
            return response
        except Exception as e:
            return f"❌ خطا: {e}"
    
    def _cmd_schedule(self, _: str) -> str:
        """وضعیت زمان‌بندی کالیبراسیون"""
        try:
            from container import container
            trainer = container.get("trainer")
            
            stats = trainer.get_stats()
            inner = stats.get("stats", {})
            
            is_running = stats.get("is_running", False)
            status_icon = "🟢" if is_running else "⚪"
            
            return (
                f"⏰ **زمان‌بندی کالیبراسیون**\n\n"
                f"{status_icon} وضعیت: {'فعال' if is_running else 'غیرفعال'}\n"
                f"🔄 در حال کالیبراسیون: {'✅' if stats.get('is_calibrating') else '❌'}\n"
                f"📅 بازه: هر {inner.get('interval_hours', 6)} ساعت\n"
                f"📊 بازه داده: {inner.get('training_period', '1m')}\n"
                f"⚙️ پروفایل: {inner.get('profile_name', 'balanced')}\n\n"
                f"📈 آمار:\n"
                f"   کل: {inner.get('total_calibrations', 0)}\n"
                f"   موفق: {inner.get('successful_calibrations', 0)}\n"
                f"   ناموفق: {inner.get('failed_calibrations', 0)}\n"
                f"   آخرین: {inner.get('last_calibration', 'N/A')}"
            )
        except Exception as e:
            return f"❌ خطا: {e}"
    
    # ============================================================
    # Screener Commands
    # ============================================================
    
    def _cmd_scan(self, args: str) -> str:
        """اسکن بازار"""
        try:
            from container import container
            use_case = container.get("scan_market_use_case")
            
            # پارامترها
            top_n = 30
            max_results = 10
            
            if args:
                parts = args.split()
                for i, p in enumerate(parts):
                    if p == "--top" and i + 1 < len(parts):
                        try:
                            top_n = int(parts[i + 1])
                        except ValueError:
                            pass
                    elif p == "--max" and i + 1 < len(parts):
                        try:
                            max_results = int(parts[i + 1])
                        except ValueError:
                            pass
            
            result = use_case.execute(
                top_n=top_n,
                max_results=max_results,
                update_state=True,
            )
            
            if not result.results:
                return (
                    f"🔍 **اسکن کامل شد**\n"
                    f"📊 اسکن‌شده: {result.total_scanned}\n"
                    f"❌ هیچ ارزی از فیلتر رد نشد"
                )
            
            response = (
                f"🔍 **نتایج اسکن** (ID: {result.scan_id})\n"
                f"📊 اسکن‌شده: {result.total_scanned} | "
                f"قبول: {result.passed_count} | "
                f"⏱️ {result.duration_seconds:.1f}s\n\n"
            )
            
            for pred in result.results[:max_results]:
                rank_icon = "🥇" if pred.rank == 1 else "🥈" if pred.rank == 2 else "🥉" if pred.rank == 3 else "•"
                state_icon = {
                    "SETUP": "🎯",
                    "WATCHING": "👀",
                    "ACTIVE": "🔥",
                    "COOLING": "❄️",
                    "IDLE": "💤",
                }.get(pred.state.value, "•")
                
                response += (
                    f"{rank_icon} **{pred.symbol}** — "
                    f"امتیاز: {pred.score:.3f} {state_icon} {pred.state.value}\n"
                )
            
            return response
        except Exception as e:
            return f"❌ خطا: {e}"
    
    def _cmd_state(self, args: str) -> str:
        """وضعیت state"""
        try:
            from container import container
            mm = container.get("model_manager")
            sm = mm.state_machine
            
            if sm is None:
                return "❌ StateMachine در دسترس نیست"
            
            # اگه symbol داده شده
            if args:
                symbol = args.strip().upper()
                # BTC → BTC/USDT
                if "/" not in symbol:
                    if not symbol.endswith("USDT"):
                        symbol = f"{symbol}USDT"
                    symbol = f"{symbol[:-4]}/USDT"
                
                snapshot = sm.get_state(symbol)
                
                return (
                    f"📍 **{symbol}**\n"
                    f"🎯 State: **{snapshot.state.value}**\n"
                    f"📅 ورود: {snapshot.entered_at.strftime('%Y-%m-%d %H:%M')}\n"
                    f"🔔 تعداد سیگنال: {snapshot.signal_count}"
                )
            
            # خلاصه
            response = "📍 **وضعیت State Machine**\n\n"
            response += "برای دیدن جزئیات: `/state BTCUSDT`\n"
            response += "برای خلاصه: از API استفاده کن"
            
            return response
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

🧠 **مدل (RuleEngine)**
  /model             وضعیت مدل
  /rules             لیست قوانین فعال
  /config            تنظیمات فعلی
  /versions [n]      آخرین نسخه‌ها

⚙️ **کالیبراسیون**
  /calibrate [prof]  کالیبراسیون وزن‌ها
  /profiles          لیست پروفایل‌ها
  /schedule          وضعیت کالیبراسیون خودکار

🔍 **اسکن و State**
  /scan [--top N]    اسکن بازار
  /state [symbol]    وضعیت یک symbol

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
🔹 مثال: /scan --top 20 --max 5
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
