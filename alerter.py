# alerter.py
# ============================================================
# سیستم هشدار و اعلان - نسخه ۳.۰ (با Type Hints)
# ============================================================

import os
import json
import logging
import requests
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Union
from pathlib import Path

logger = logging.getLogger(__name__)


class Alerter:
    """
    مدیریت هشدارها و اعلان‌ها
    پشتیبانی از: کنسول، لاگ
    
    ✅ نسخه ۳.۰: اضافه شدن Type Hints و کامنت شدن تلگرام
    """
    
    def __init__(self) -> None:
        self.alerts: List[Dict[str, Any]] = []
        self.max_alerts: int = 100
        self.alert_rules: Dict[str, Any] = self._load_rules()
        
        # ============================================================
        # ⚠️ بخش تلگرام - کامنت شده (غیرفعال)
        # ============================================================
        # # تنظیمات تلگرام (از محیط)
        # self.telegram_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
        # self.telegram_chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "")
        # self.telegram_enabled: bool = bool(self.telegram_token and self.telegram_chat_id)
        
        # آخرین وضعیت برای جلوگیری از هشدار تکراری
        self.last_status: Dict[str, Optional[Union[str, float, int]]] = {
            "cpu": None,
            "ram": None,
            "api": None,
            "model": None,
            "database": None
        }
        
        # ✅ جدید: استفاده از Scheduler برای دریافت متریک
        self._metrics_cache: Dict[str, Any] = {}
        self._last_metrics_update: Optional[datetime] = None
        
        # if self.telegram_enabled:
        #     logger.info("✅ Telegram alerts enabled")
        # else:
        #     logger.info("ℹ️ Telegram alerts disabled (set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)")
        
        logger.info("✅ Alerter v3.0 initialized (Telegram disabled)")
    
    def _load_rules(self) -> Dict[str, Any]:
        """بارگذاری قوانین هشدار از فایل یا پیش‌فرض"""
        rules_path: Path = Path("config/alert_rules.json")
        
        default_rules: Dict[str, Any] = {
            "cpu": {
                "warning": 70,
                "critical": 85,
                "cooldown": 60
            },
            "ram": {
                "warning": 70,
                "critical": 85,
                "cooldown": 60
            },
            "api": {
                "error_threshold": 3,
                "cooldown": 120
            },
            "model": {
                "min_accuracy": 0.50,
                "no_update_hours": 24,
                "cooldown": 300
            },
            "database": {
                "max_disconnect": 2,
                "cooldown": 60
            }
            # ============================================================
            # ⚠️ بخش تلگرام - کامنت شده
            # ============================================================
            # "telegram": {
            #     "enabled": False,
            #     "bot_token": "",
            #     "chat_id": ""
            # }
        }
        
        if rules_path.exists():
            try:
                with open(rules_path, 'r', encoding='utf-8') as f:
                    rules: Dict[str, Any] = json.load(f)
                    logger.info("✅ Alert rules loaded from file")
                    return rules
            except Exception as e:
                logger.error(f"❌ Error loading rules: {e}")
        
        # ذخیره قوانین پیش‌فرض
        try:
            rules_path.parent.mkdir(parents=True, exist_ok=True)
            with open(rules_path, 'w', encoding='utf-8') as f:
                json.dump(default_rules, f, indent=4, ensure_ascii=False)
            logger.info("✅ Default alert rules created")
        except Exception:
            pass
        
        return default_rules
    
    def _get_metrics_from_scheduler(self) -> Dict[str, Any]:
        """دریافت متریک‌ها از Scheduler"""
        try:
            from core import metrics_scheduler
            return metrics_scheduler.get_alert_metrics()
        except ImportError:
            logger.warning("⚠️ Metrics Scheduler not available, using fallback")
            return self._get_fallback_metrics()
        except Exception as e:
            logger.error(f"❌ Error getting metrics from scheduler: {e}")
            return self._get_fallback_metrics()
    
    def _get_fallback_metrics(self) -> Dict[str, Any]:
        """Fallback در صورت عدم دسترسی به Scheduler"""
        return {
            "cpu": 0,
            "ram": 0,
            "api_status": "unknown",
            "api_credits": 0,
            "model_loaded": False,
            "model_accuracy": None,
            "databases": {"postgresql": False, "redis": False, "sqlite": False},
            "uptime": "0s",
            "last_update": datetime.now().isoformat()
        }
    
    def check_and_alert(self, metrics: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        بررسی متریک‌ها و صدور هشدار در صورت نیاز
        
        پارامترها:
            metrics: اگر None باشد، از Scheduler دریافت می‌شود
        
        خروجی:
            لیستی از هشدارهای جدید
        """
        if metrics is None:
            metrics = self._get_metrics_from_scheduler()
        
        new_alerts: List[Dict[str, Any]] = []
        
        # ۱. بررسی CPU
        cpu_alert: Optional[Dict[str, Any]] = self._check_cpu(metrics)
        if cpu_alert:
            new_alerts.append(cpu_alert)
        
        # ۲. بررسی RAM
        ram_alert: Optional[Dict[str, Any]] = self._check_ram(metrics)
        if ram_alert:
            new_alerts.append(ram_alert)
        
        # ۳. بررسی API
        api_alert: Optional[Dict[str, Any]] = self._check_api(metrics)
        if api_alert:
            new_alerts.append(api_alert)
        
        # ۴. بررسی مدل
        model_alert: Optional[Dict[str, Any]] = self._check_model(metrics)
        if model_alert:
            new_alerts.append(model_alert)
        
        # ۵. بررسی دیتابیس
        db_alert: Optional[Dict[str, Any]] = self._check_database(metrics)
        if db_alert:
            new_alerts.append(db_alert)
        
        # ذخیره و ارسال هشدارها
        for alert in new_alerts:
            self.alerts.append(alert)
            if len(self.alerts) > self.max_alerts:
                self.alerts = self.alerts[-self.max_alerts:]
            
            # ارسال هشدار
            self._send_alert(alert)
        
        return new_alerts
    
    # ---------- بررسی‌های اختصاصی ----------
    
    def _check_cpu(self, metrics: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """بررسی مصرف CPU"""
        cpu: float = float(metrics.get("cpu", 0))
        rules: Dict[str, Any] = self.alert_rules.get("cpu", {})
        
        if self.last_status.get("cpu") == cpu and cpu < rules.get("warning", 70):
            return None
        
        if cpu >= rules.get("critical", 85):
            self.last_status["cpu"] = cpu
            return self._create_alert(
                "CRITICAL",
                f"🚨 مصرف CPU بسیار بالا: {cpu}%",
                {"cpu": cpu, "threshold": rules.get("critical")},
                "cpu"
            )
        elif cpu >= rules.get("warning", 70):
            self.last_status["cpu"] = cpu
            return self._create_alert(
                "WARNING",
                f"⚠️ مصرف CPU بالا: {cpu}%",
                {"cpu": cpu, "threshold": rules.get("warning")},
                "cpu"
            )
        return None
    
    def _check_ram(self, metrics: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """بررسی مصرف RAM"""
        ram: float = float(metrics.get("ram", 0))
        rules: Dict[str, Any] = self.alert_rules.get("ram", {})
        
        if self.last_status.get("ram") == ram and ram < rules.get("warning", 70):
            return None
        
        if ram >= rules.get("critical", 85):
            self.last_status["ram"] = ram
            return self._create_alert(
                "CRITICAL",
                f"🚨 مصرف RAM بسیار بالا: {ram}%",
                {"ram": ram, "threshold": rules.get("critical")},
                "ram"
            )
        elif ram >= rules.get("warning", 70):
            self.last_status["ram"] = ram
            return self._create_alert(
                "WARNING",
                f"⚠️ مصرف RAM بالا: {ram}%",
                {"ram": ram, "threshold": rules.get("warning")},
                "ram"
            )
        return None
    
    def _check_api(self, metrics: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """بررسی وضعیت API"""
        api_status: str = metrics.get("api_status", "unknown")
        
        if self.last_status.get("api") == api_status:
            return None
        
        if api_status in ["error", "unhealthy"]:
            self.last_status["api"] = api_status
            return self._create_alert(
                "CRITICAL",
                f"🚨 API در دسترس نیست! وضعیت: {api_status}",
                {"status": api_status},
                "api"
            )
        elif api_status == "degraded":
            self.last_status["api"] = api_status
            return self._create_alert(
                "WARNING",
                f"⚠️ API با کیفیت پایین: {api_status}",
                {"status": api_status},
                "api"
            )
        return None
    
    def _check_model(self, metrics: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """بررسی وضعیت مدل"""
        accuracy: Optional[float] = metrics.get("model_accuracy")
        loaded: bool = metrics.get("model_loaded", False)
        rules: Dict[str, Any] = self.alert_rules.get("model", {})
        
        # بررسی دقت
        if accuracy is not None and accuracy < rules.get("min_accuracy", 0.50):
            if self.last_status.get("model") != "low_accuracy":
                self.last_status["model"] = "low_accuracy"
                return self._create_alert(
                    "CRITICAL",
                    f"🚨 دقت مدل پایین است: {accuracy*100:.1f}%",
                    {"accuracy": accuracy, "threshold": rules.get("min_accuracy")},
                    "model"
                )
        
        # بررسی بارگذاری نشدن مدل
        if not loaded:
            if self.last_status.get("model") != "not_loaded":
                self.last_status["model"] = "not_loaded"
                return self._create_alert(
                    "WARNING",
                    "⚠️ مدل بارگذاری نشده است (حالت DEMO)",
                    {},
                    "model"
                )
        
        # اگر همه چیز خوب بود، وضعیت رو ریست کن
        if self.last_status.get("model") in ["low_accuracy", "not_loaded"]:
            self.last_status["model"] = "ok"
        
        return None
    
    def _check_database(self, metrics: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """بررسی وضعیت دیتابیس"""
        databases: Dict[str, bool] = metrics.get("databases", {})
        disconnected: List[str] = [name for name, status in databases.items() if not status]
        
        if disconnected:
            if self.last_status.get("database") != str(disconnected):
                self.last_status["database"] = str(disconnected)
                return self._create_alert(
                    "CRITICAL",
                    f"🚨 دیتابیس‌های زیر قطع هستند: {', '.join(disconnected)}",
                    {"disconnected": disconnected},
                    "database"
                )
        else:
            if self.last_status.get("database") is not None:
                self.last_status["database"] = None
                # هشدار رفع شدن
                return self._create_alert(
                    "INFO",
                    f"✅ همه دیتابیس‌ها متصل هستند",
                    {},
                    "database"
                )
        return None
    
    # ---------- توابع کمکی ----------
    
    def _create_alert(self, level: str, message: str, data: Dict[str, Any], source: str) -> Dict[str, Any]:
        """ایجاد یک هشدار جدید"""
        return {
            "id": len(self.alerts) + 1,
            "level": level,
            "message": message,
            "source": source,
            "data": data,
            "timestamp": datetime.now().isoformat(),
            "resolved": False
        }
    
    def _send_alert(self, alert: Dict[str, Any]) -> None:
        """ارسال هشدار به مقصدهای مختلف"""
        # ۱. لاگ
        log_level: int = logging.WARNING if alert['level'] in ["WARNING", "CRITICAL"] else logging.INFO
        logger.log(log_level, f"[{alert['level']}] {alert['message']}")
        
        # ۲. کنسول (رنگی)
        if alert['level'] == "CRITICAL":
            print(f"\033[91m🚨 [{alert['level']}] {alert['message']}\033[0m")
        elif alert['level'] == "WARNING":
            print(f"\033[93m⚠️ [{alert['level']}] {alert['message']}\033[0m")
        else:
            print(f"✅ [{alert['level']}] {alert['message']}")
        
        # ============================================================
        # ⚠️ بخش تلگرام - کامنت شده
        # ============================================================
        # if self.telegram_enabled:
        #     self._send_telegram(alert)
    
    # ============================================================
    # ⚠️ متد _send_telegram - کامنت شده
    # ============================================================
    # def _send_telegram(self, alert: Dict[str, Any]) -> None:
    #     """ارسال هشدار به تلگرام"""
    #     try:
    #         emoji: str = "🚨" if alert['level'] == "CRITICAL" else "⚠️" if alert['level'] == "WARNING" else "ℹ️"
    #         message: str = f"""
    # {emoji} *هشدار سیستم تحلیلگر*
    # 
    # *سطح:* {alert['level']}
    # *منبع:* {alert['source']}
    # *پیام:* {alert['message']}
    # *زمان:* {alert['timestamp']}
    # 
    # #alert #{alert['source']}
    # """
    #         url: str = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
    #         payload: Dict[str, str] = {
    #             "chat_id": self.telegram_chat_id,
    #             "text": message,
    #             "parse_mode": "Markdown"
    #         }
    #         response: requests.Response = requests.post(url, json=payload, timeout=5)
    #         if response.status_code != 200:
    #             logger.error(f"❌ Telegram error: {response.text}")
    #     except Exception as e:
    #         logger.error(f"❌ Telegram error: {e}")
    
    def get_alerts(self, limit: int = 20, resolved: Optional[bool] = None) -> List[Dict[str, Any]]:
        """دریافت هشدارهای اخیر"""
        alerts: List[Dict[str, Any]] = self.alerts[-limit:] if self.alerts else []
        if resolved is not None:
            alerts = [a for a in alerts if a.get("resolved", False) == resolved]
        return alerts
    
    def resolve_alert(self, alert_id: int) -> bool:
        """علامت‌گذاری یک هشدار به عنوان رفع‌شده"""
        for alert in self.alerts:
            if alert.get("id") == alert_id:
                alert["resolved"] = True
                alert["resolved_at"] = datetime.now().isoformat()
                logger.info(f"✅ Alert {alert_id} resolved")
                return True
        return False


# نمونه Singleton
alerter: Alerter = Alerter()
