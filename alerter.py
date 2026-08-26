# alerter.py
# ============================================================
# سیستم هشدار و اعلان - نسخه ۱.۰
# ============================================================

import os
import json
import logging
import requests
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class Alerter:
    """
    مدیریت هشدارها و اعلان‌ها
    پشتیبانی از: کنسول، لاگ، تلگرام، ایمیل (قابل توسعه)
    """
    
    def __init__(self):
        self.alerts = []
        self.max_alerts = 100
        self.alert_rules = self._load_rules()
        self.telegram_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
        
        # آخرین وضعیت برای جلوگیری از هشدار تکراری
        self.last_status = {
            "cpu": None,
            "ram": None,
            "api": None,
            "model": None,
            "database": None
        }
        
        logger.info("✅ Alerter initialized")
    
    def _load_rules(self) -> Dict:
        """بارگذاری قوانین هشدار"""
        rules_path = Path("config/alert_rules.json")
        
        default_rules = {
            "cpu": {
                "warning": 70,
                "critical": 85,
                "cooldown": 60  # ثانیه
            },
            "ram": {
                "warning": 70,
                "critical": 85,
                "cooldown": 60
            },
            "api": {
                "error_threshold": 3,  # تعداد خطای متوالی
                "cooldown": 120
            },
            "model": {
                "min_accuracy": 0.50,
                "no_update_hours": 24,
                "cooldown": 300
            },
            "database": {
                "max_disconnect": 2,  # تعداد قطعی متوالی
                "cooldown": 60
            }
        }
        
        if rules_path.exists():
            try:
                with open(rules_path, 'r') as f:
                    rules = json.load(f)
                    logger.info("✅ Alert rules loaded from file")
                    return rules
            except Exception as e:
                logger.error(f"❌ Error loading rules: {e}")
        
        # ذخیره قوانین پیش‌فرض
        try:
            rules_path.parent.mkdir(parents=True, exist_ok=True)
            with open(rules_path, 'w') as f:
                json.dump(default_rules, f, indent=4)
            logger.info("✅ Default alert rules created")
        except:
            pass
        
        return default_rules
    
    def check_and_alert(self, metrics: Dict) -> List[Dict]:
        """
        بررسی متریک‌ها و صدور هشدار در صورت نیاز
        
        پارامترها:
            metrics: دیکشنری متریک‌ها (از MetricsCollector)
        
        خروجی:
            لیست هشدارهای صادر شده
        """
        new_alerts = []
        
        # ۱. بررسی CPU
        cpu_alert = self._check_cpu(metrics)
        if cpu_alert:
            new_alerts.append(cpu_alert)
        
        # ۲. بررسی RAM
        ram_alert = self._check_ram(metrics)
        if ram_alert:
            new_alerts.append(ram_alert)
        
        # ۳. بررسی API
        api_alert = self._check_api(metrics)
        if api_alert:
            new_alerts.append(api_alert)
        
        # ۴. بررسی مدل
        model_alert = self._check_model(metrics)
        if model_alert:
            new_alerts.append(model_alert)
        
        # ۵. بررسی دیتابیس
        db_alert = self._check_database(metrics)
        if db_alert:
            new_alerts.append(db_alert)
        
        # ذخیره هشدارها
        for alert in new_alerts:
            self.alerts.append(alert)
            if len(self.alerts) > self.max_alerts:
                self.alerts = self.alerts[-self.max_alerts:]
            
            # ارسال هشدار
            self._send_alert(alert)
        
        return new_alerts
    
    # ---------- بررسی‌های اختصاصی ----------
    
    def _check_cpu(self, metrics: Dict) -> Optional[Dict]:
        """بررسی مصرف CPU"""
        cpu = metrics.get("cpu", 0)
        rules = self.alert_rules.get("cpu", {})
        
        if cpu >= rules.get("critical", 85):
            return self._create_alert(
                "CRITICAL",
                f"🚨 مصرف CPU بسیار بالا: {cpu}%",
                {"cpu": cpu, "threshold": rules.get("critical")},
                "cpu"
            )
        elif cpu >= rules.get("warning", 70):
            return self._create_alert(
                "WARNING",
                f"⚠️ مصرف CPU بالا: {cpu}%",
                {"cpu": cpu, "threshold": rules.get("warning")},
                "cpu"
            )
        return None
    
    def _check_ram(self, metrics: Dict) -> Optional[Dict]:
        """بررسی مصرف RAM"""
        ram = metrics.get("ram", 0)
        rules = self.alert_rules.get("ram", {})
        
        if ram >= rules.get("critical", 85):
            return self._create_alert(
                "CRITICAL",
                f"🚨 مصرف RAM بسیار بالا: {ram}%",
                {"ram": ram, "threshold": rules.get("critical")},
                "ram"
            )
        elif ram >= rules.get("warning", 70):
            return self._create_alert(
                "WARNING",
                f"⚠️ مصرف RAM بالا: {ram}%",
                {"ram": ram, "threshold": rules.get("warning")},
                "ram"
            )
        return None
    
    def _check_api(self, metrics: Dict) -> Optional[Dict]:
        """بررسی وضعیت API"""
        api_status = metrics.get("api_status", "unknown")
        
        if api_status in ["error", "unhealthy"]:
            return self._create_alert(
                "CRITICAL",
                f"🚨 API در دسترس نیست! وضعیت: {api_status}",
                {"status": api_status},
                "api"
            )
        elif api_status == "degraded":
            return self._create_alert(
                "WARNING",
                f"⚠️ API با کیفیت پایین: {api_status}",
                {"status": api_status},
                "api"
            )
        return None
    
    def _check_model(self, metrics: Dict) -> Optional[Dict]:
        """بررسی وضعیت مدل"""
        accuracy = metrics.get("model_accuracy")
        
        if accuracy is not None and accuracy < self.alert_rules.get("model", {}).get("min_accuracy", 0.50):
            return self._create_alert(
                "CRITICAL",
                f"🚨 دقت مدل پایین است: {accuracy*100:.1f}%",
                {"accuracy": accuracy, "threshold": self.alert_rules["model"]["min_accuracy"]},
                "model"
            )
        
        # بررسی عدم بروزرسانی مدل
        if not metrics.get("model_loaded", False):
            return self._create_alert(
                "WARNING",
                "⚠️ مدل بارگذاری نشده است (حالت DEMO)",
                {},
                "model"
            )
        return None
    
    def _check_database(self, metrics: Dict) -> Optional[Dict]:
        """بررسی وضعیت دیتابیس‌ها"""
        databases = metrics.get("databases", {})
        disconnected = [name for name, status in databases.items() if not status]
        
        if disconnected:
            return self._create_alert(
                "CRITICAL",
                f"🚨 دیتابیس‌های زیر قطع هستند: {', '.join(disconnected)}",
                {"disconnected": disconnected},
                "database"
            )
        return None
    
    # ---------- توابع کمکی ----------
    
    def _create_alert(self, level: str, message: str, data: Dict, source: str) -> Dict:
        """ساخت یک هشدار"""
        return {
            "id": len(self.alerts) + 1,
            "level": level,
            "message": message,
            "source": source,
            "data": data,
            "timestamp": datetime.now().isoformat(),
            "resolved": False
        }
    
    def _send_alert(self, alert: Dict):
        """ارسال هشدار به مقصدهای مختلف"""
        # ۱. لاگ
        logger.warning(f"[{alert['level']}] {alert['message']}")
        
        # ۲. کنسول (رنگی)
        color = "\033[91m" if alert['level'] == "CRITICAL" else "\033[93m"
        print(f"{color}[{alert['level']}] {alert['message']}\033[0m")
        
        # ۳. تلگرام (اگر تنظیم شده باشد)
        if self.telegram_token and self.telegram_chat_id:
            self._send_telegram(alert)
    
    def _send_telegram(self, alert: Dict):
        """ارسال هشدار به تلگرام"""
        try:
            emoji = "🚨" if alert['level'] == "CRITICAL" else "⚠️"
            message = f"""
{emoji} *هشدار سیستم تحلیلگر*

*سطح:* {alert['level']}
*منبع:* {alert['source']}
*پیام:* {alert['message']}
*زمان:* {alert['timestamp']}

#alert #{alert['source']}
"""
            url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
            payload = {
                "chat_id": self.telegram_chat_id,
                "text": message,
                "parse_mode": "Markdown"
            }
            requests.post(url, json=payload, timeout=5)
        except Exception as e:
            logger.error(f"❌ Telegram error: {e}")
    
    def get_alerts(self, limit: int = 20, resolved: bool = None) -> List[Dict]:
        """دریافت هشدارهای اخیر"""
        alerts = self.alerts[-limit:]
        if resolved is not None:
            alerts = [a for a in alerts if a.get("resolved", False) == resolved]
        return alerts
    
    def resolve_alert(self, alert_id: int) -> bool:
        """علامت‌گذاری یک هشدار به عنوان رفع‌شده"""
        for alert in self.alerts:
            if alert.get("id") == alert_id:
                alert["resolved"] = True
                alert["resolved_at"] = datetime.now().isoformat()
                return True
        return False


# ایجاد نمونه
alerter = Alerter()
