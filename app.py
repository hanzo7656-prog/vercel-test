# app.py
# ============================================================
# ورودی اصلی سیستم - نسخه ۷.۰ (ماژولار)
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
# ============================================================

from core import system, metrics_scheduler

# ============================================================
# ایمپورت روت‌ها
# ============================================================

from routes import register_api_routes, register_web_routes, register_metrics_routes

# ثبت روت‌ها
register_api_routes(app, system)
register_web_routes(app)
register_metrics_routes(app)

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
            alert_metrics = metrics_scheduler.get_alert_metrics()
            alerts = alerter.check_and_alert(alert_metrics)
            if alerts:
                self_healer.check_and_heal(alert_metrics)
            threading.Event().wait(30)
        except Exception as e:
            logger.error(f"❌ Alert loop error: {e}")
            threading.Event().wait(30)

alert_thread = threading.Thread(target=alert_loop, daemon=True)
alert_thread.start()
logger.info("✅ Alert & Self-Healing loop started")

# ============================================================
# کش پیش‌بینی (برای استفاده در core.system)
# ============================================================

prediction_cache = {}
PREDICTION_CACHE_TTL = 300

# ============================================================
# اجرای اصلی
# ============================================================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "False").lower() == "true"

    print("=" * 60)
    print("🚀 سیستم تشخیص الگوهای بازاری (نسخه ۷.۰ - ماژولار)")
    print(f"📡 پورت: {port}")
    print(f"🐛 دیباگ: {debug}")
    print(f"🧠 مدل: {'✅ بارگذاری شده' if system.model_manager.current_model else '❌ بارگذاری نشده'}")
    print(f"📊 نسخه مدل: {system.model_manager.current_version or 'N/A'}")
    print("=" * 60)
    print("📌 ساختار ماژولار:")
    print("  /core/system.py    - هسته اصلی سیستم")
    print("  /core/metrics.py   - سیستم جمع‌آوری متریک")
    print("  /routes/           - روت‌های Flask")
    print("=" * 60)

    app.run(host="0.0.0.0", port=port, debug=debug)
