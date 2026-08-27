# app.py
# ============================================================
# ورودی اصلی سیستم - نسخه ۷.۱ با واتچ‌داگ قوی برای Scheduler
# ============================================================

import os
import sys
import time
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
# ✅ واتچ‌داگ قوی برای نگه‌داشتن ترد Scheduler
# ============================================================

scheduler_watchdog_thread = None
scheduler_watchdog_running = False

def scheduler_watchdog():
    """هر ۱۰ ثانیه چک می‌کند اگر ترد Scheduler مرده بود دوباره روشنش کن."""
    global scheduler_watchdog_running
    scheduler_watchdog_running = True
    logger.info("🛡️ Scheduler Watchdog started (checking every 10 seconds)")
    
    while scheduler_watchdog_running:
        time.sleep(10)
        try:
            # 1. چک کن که آیا ترد واقعاً مرده؟
            thread_is_dead = not metrics_scheduler._running or not metrics_scheduler._is_thread_alive()
            
            if thread_is_dead:
                logger.warning("⚠️ Watchdog: Scheduler thread is dead! Restarting...")
                try:
                    # 2. کشتن کامل ترد قدیمی و ری‌استارت
                    metrics_scheduler.stop()
                    time.sleep(0.5)
                    metrics_scheduler._running = False
                    metrics_scheduler._thread = None
                    metrics_scheduler.start()
                    logger.info("✅ Watchdog: Scheduler successfully restarted.")
                except Exception as e:
                    logger.error(f"❌ Watchdog: Failed to restart scheduler: {e}")
            
            # 3. یک لاگ کوچک برای اینکه بفهمیم زنده است
            elif int(time.time()) % 60 == 0:
                logger.debug(f"🔹 Watchdog: Scheduler is alive. Collections: {metrics_scheduler.stats['collections']}")
                
        except Exception as e:
            logger.error(f"❌ Watchdog loop error: {e}")

# راه‌اندازی واتچ‌داگ
scheduler_watchdog_thread = threading.Thread(target=scheduler_watchdog, daemon=True)
scheduler_watchdog_thread.start()

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
            time.sleep(30)
        except Exception as e:
            logger.error(f"❌ Alert loop error: {e}")
            time.sleep(30)

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
    print("🚀 سیستم تشخیص الگوهای بازاری (نسخه ۷.۱ - با واتچ‌داگ)")
    print(f"📡 پورت: {port}")
    print(f"🐛 دیباگ: {debug}")
    print(f"🧠 مدل: {'✅ بارگذاری شده' if system.model_manager.current_model else '❌ بارگذاری نشده'}")
    print("=" * 60)
    print("📌 اندپوینت‌های اصلی:")
    print("  /api/metrics       - متریک‌های لحظه‌ای")
    print("  /health            - بررسی سلامت")
    print("  /predict           - پیش‌بینی")
    print("  /dashboard         - داشبورد")
    print("=" * 60)

    app.run(host="0.0.0.0", port=port, debug=debug)
