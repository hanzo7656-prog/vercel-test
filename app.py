# app.py
# ============================================================
# ورودی اصلی - نسخه ۸.۰ نهایی 
# ============================================================

import os
import sys
import signal
import logging
from flask import Flask

from config.version import VERSION, APP_NAME
from core.threading_manager import threading_manager
from core.metrics import metrics_scheduler
from core.parallel_processor import parallel_processor
from services import prediction_service, training_service, batch_processor
from alerter import alerter
from self_healer import SelfHealer
from database.database_factory import ensure_databases_connected

# ============================================================
# تنظیمات لاگ
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================================
# Signal Handler برای Stop Graceful
# ============================================================

def signal_handler(sig, frame):
    logger.info(f"🛑 Received signal {sig}, shutting down gracefully...")
    
    # توقف همه Threadها
    threading_manager.stop_all()
    metrics_scheduler.stop()
    
    # خاموش کردن Poolها
    parallel_processor.shutdown()
    
    logger.info("✅ Graceful shutdown complete")
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# ============================================================
# ایجاد Flask App
# ============================================================

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
app.config['JSON_SORT_KEYS'] = False

# ============================================================
# ایمپورت Core
# ============================================================

from core.system import system

# ============================================================
# ایمپورت روت‌ها
# ============================================================

from routes import register_all_routes
register_all_routes(app, system)

# ============================================================
# راه‌اندازی Scheduler با ThreadingManager
# ============================================================

def metrics_thread_func():
    """تابع متریک برای اجرا در Thread"""
    metrics_scheduler.start()

threading_manager.register(
    name="metrics",
    target=metrics_thread_func,
    daemon=False,
    auto_restart=True,
    max_restarts=3,
    restart_delay=10
)

logger.info("✅ Metrics Scheduler started with ThreadingManager")

# ============================================================
# راه‌اندازی حلقه Alert و Self-Healing
# ============================================================

from self_healer import SelfHealer
self_healer = SelfHealer(system.model_manager, system.trainer)

def alert_loop():
    """حلقه بررسی هشدارها"""
    while True:
        try:
            from core.metrics import metrics_scheduler
            alert_metrics = metrics_scheduler.get_alert_metrics()
            alerts = alerter.check_and_alert(alert_metrics)
            if alerts:
                self_healer.check_and_heal(alert_metrics)
            import time
            time.sleep(30)
        except Exception as e:
            logger.error(f"❌ Alert loop error: {e}")
            import time
            time.sleep(30)

threading_manager.register(
    name="alert",
    target=alert_loop,
    daemon=False,
    auto_restart=True,
    max_restarts=5,
    restart_delay=15
)

logger.info("✅ Alert & Self-Healing loop started")

# ============================================================
# اطمینان از اتصال دیتابیس‌ها
# ============================================================

def check_databases():
    """بررسی دوره‌ای دیتابیس‌ها"""
    while True:
        try:
            ensure_databases_connected()
            import time
            time.sleep(60)  # هر ۱ دقیقه
        except Exception as e:
            logger.error(f"❌ Database health check error: {e}")
            import time
            time.sleep(120)

threading_manager.register(
    name="db_health",
    target=check_databases,
    daemon=True,
    auto_restart=True,
    max_restarts=10
)

logger.info("✅ Database health check started")

# ============================================================
# اجرای اصلی
# ============================================================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "False").lower() == "true"
    
    print("=" * 60)
    print(f"🚀 {APP_NAME} v{VERSION}")
    print(f"📡 Port: {port}")
    print(f"🐛 Debug: {debug}")
    print(f"🧠 Model: {'✅ Loaded' if system.model_manager.current_model else '❌ Not Loaded'}")
    print(f"🔧 Threads: {len(threading_manager._threads)} active")
    print(f"⚡ Parallel Processing: Enabled (Threads: 10, Processes: 4)")
    print("=" * 60)
    print("📌 New Features:")
    print("  🔄 Multi-coin parallel prediction")
    print("  📊 Batch processing for heavy tasks")
    print("  🚀 Async predictions (async/await)")
    print("  🐕 Advanced Watchdog with auto-restart")
    print("=" * 60)
    
    # شروع سرویس‌ها
    try:
        app.run(host="0.0.0.0", port=port, debug=debug)
    except KeyboardInterrupt:
        logger.info("🛑 Shutting down...")
        threading_manager.stop_all()
        parallel_processor.shutdown()
