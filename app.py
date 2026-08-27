# app.py
# ============================================================
# ورودی اصلی سیستم - نسخه ۷.۰ (ماژولار، بدون وابستگی دایره‌ای)
# ============================================================

import os
import sys
import threading
import logging
from datetime import datetime
from flask import Flask

# ============================================================
# تنظیمات لاگ
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================================
# ایجاد Flask App
# ============================================================

app = Flask(__name__)

# ============================================================
# ایمپورت Core (سیستم اصلی + متریک)
# ✅ دیگر از app.py در core/system.py استفاده نمی‌شود
# ============================================================

from core.system import system
from core.metrics import metrics_scheduler

# ============================================================
# ایمپورت روت‌ها
# ============================================================

from routes import register_all_routes

# ثبت همه روت‌ها
register_all_routes(app, system)

# ============================================================
# راه‌اندازی Scheduler جدید
# ============================================================

metrics_scheduler.start()
logger.info("✅ Metrics Scheduler started")

# ============================================================
# راه‌اندازی حلقه Alert
# ============================================================

from alerter import alerter
from self_healer import SelfHealer

self_healer = SelfHealer(system.model_manager, system.trainer)

def alert_loop():
    """حلقه بررسی هشدارها با Scheduler جدید"""
    while True:
        try:
            # ✅ دریافت متریک‌ها از Scheduler
            alert_metrics = metrics_scheduler.get_alert_metrics()
            
            # بررسی هشدارها
            alerts = alerter.check_and_alert(alert_metrics)
            
            # خودترمیمی (فقط اگر هشدار وجود داشت)
            if alerts:
                self_healer.check_and_heal(alert_metrics)
            
            # هر ۳۰ ثانیه یکبار
            threading.Event().wait(30)
            
        except Exception as e:
            logger.error(f"❌ Alert loop error: {e}")
            threading.Event().wait(30)

alert_thread = threading.Thread(target=alert_loop, daemon=True)
alert_thread.start()
logger.info("✅ Alert & Self-Healing loop started")

# ============================================================
# اجرای اصلی
# ============================================================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "False").lower() == "true"

    print("=" * 60)
    print("🚀 سیستم تشخیص الگوهای بازاری (نسخه ۷.۰ - بدون وابستگی دایره‌ای)")
    print(f"📡 پورت: {port}")
    print(f"🐛 دیباگ: {debug}")
    print(f"🧠 مدل: {'✅ بارگذاری شده' if system.model_manager.current_model else '❌ بارگذاری نشده'}")
    print(f"📊 نسخه مدل: {system.model_manager.current_version or 'N/A'}")
    print("=" * 60)
    print("📌 ساختار ماژولار:")
    print("  /core/system.py    - هسته اصلی سیستم (با کش داخلی)")
    print("  /core/metrics.py   - سیستم جمع‌آوری متریک")
    print("  /routes/           - روت‌های Flask")
    print("  /models/           - مدیریت و آموزش مدل")
    print("=" * 60)
    print("📌 اندپوینت‌های اصلی:")
    print("  /api/metrics       - متریک‌های لحظه‌ای")
    print("  /health            - بررسی سلامت")
    print("  /predict           - پیش‌بینی")
    print("  /dashboard         - داشبورد")
    print("=" * 60)

    app.run(host="0.0.0.0", port=port, debug=debug)
