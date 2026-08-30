# app.py
# ============================================================
# فقط بخش Import - نسخه اصلاح شده
# ============================================================

import os
import sys
import signal
import logging
from datetime import datetime
from flask import Flask, jsonify

from config.version import VERSION, APP_NAME
from container import container
from providers import init_container

# ✅ Import‌های اصلاح شده
from infrastructure.external.alerter import alerter
from application.services.self_healer import SelfHealer

logger = logging.getLogger(__name__)



# ============================================================
# Signal Handler برای Stop Graceful
# ============================================================

def signal_handler(sig, frame) -> None:
    """مدیریت سیگنال‌های توقف"""
    logger.info(f"🛑 Received signal {sig}, shutting down gracefully...")
    
    try:
        metrics_scheduler = container.get('metrics_scheduler')
        if metrics_scheduler:
            metrics_scheduler.stop()
            logger.info("✅ Metrics Scheduler stopped")
    except Exception as e:
        logger.error(f"❌ Error stopping metrics scheduler: {e}")
    
    try:
        threading_manager = container.get('threading_manager')
        if threading_manager:
            threading_manager.stop_all()
            logger.info("✅ All threads stopped")
    except Exception as e:
        logger.error(f"❌ Error stopping threads: {e}")
    
    try:
        from core.parallel_processor import parallel_processor
        parallel_processor.shutdown()
        logger.info("✅ Parallel processor shutdown")
    except Exception as e:
        logger.error(f"❌ Error shutting down parallel processor: {e}")
    
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
app.config['JSON_AS_ASCII'] = False


# ============================================================
# راه‌اندازی Container
# ============================================================

init_container(app)
logger.info("✅ Container initialized")


# ============================================================
# ثبت Blueprintها
# ============================================================

from presentation.routes.api_routes import api_bp
from presentation.routes.web_routes import web_bp
from presentation.routes.metrics_routes import metrics_bp

app.register_blueprint(api_bp)
app.register_blueprint(web_bp)
app.register_blueprint(metrics_bp)

logger.info("✅ Blueprints registered")


# ============================================================
# راه‌اندازی Scheduler
# ============================================================

def start_metrics_scheduler() -> None:
    """راه‌اندازی Scheduler متریک"""
    try:
        metrics_scheduler = container.get('metrics_scheduler')
        if metrics_scheduler:
            threading_manager = container.get('threading_manager')
            if threading_manager:
                threading_manager.register(
                    name="metrics_scheduler",
                    target=metrics_scheduler.start,
                    daemon=False,
                    auto_restart=True,
                    max_restarts=3,
                    restart_delay=10
                )
                logger.info("✅ Metrics Scheduler started via ThreadingManager")
            else:
                metrics_scheduler.start()
                logger.info("✅ Metrics Scheduler started directly")
    except Exception as e:
        logger.error(f"❌ Failed to start metrics scheduler: {e}")


# ============================================================
# راه‌اندازی Alert و Self-Healing
# ============================================================

def start_alert_system() -> None:
    """راه‌اندازی سیستم هشدار و خودترمیمی"""
    try:
        from infrastructure.external.alerter import alerter
        from infrastructure.services.self_healer import SelfHealer
        
        model_manager = container.get('model_manager')
        trainer = container.get('trainer')
        self_healer = SelfHealer(model_manager, trainer)
        
        def alert_loop() -> None:
            import time
            while True:
                try:
                    metrics_scheduler = container.get('metrics_scheduler')
                    if metrics_scheduler:
                        alert_metrics = metrics_scheduler.get_alert_metrics()
                        alerts = alerter.check_and_alert(alert_metrics)
                        if alerts:
                            self_healer.check_and_heal(alert_metrics)
                    time.sleep(30)
                except Exception as e:
                    logger.error(f"❌ Alert loop error: {e}")
                    time.sleep(30)
        
        threading_manager = container.get('threading_manager')
        if threading_manager:
            threading_manager.register(
                name="alert_system",
                target=alert_loop,
                daemon=False,
                auto_restart=True,
                max_restarts=5,
                restart_delay=15
            )
            logger.info("✅ Alert system started via ThreadingManager")
        else:
            import threading
            alert_thread = threading.Thread(target=alert_loop, daemon=False)
            alert_thread.start()
            logger.info("✅ Alert system started directly")
            
    except Exception as e:
        logger.error(f"❌ Failed to start alert system: {e}")


# ============================================================
# راه‌اندازی Database Health Check
# ============================================================

def start_db_health_check() -> None:
    """راه‌اندازی بررسی دوره‌ای دیتابیس"""
    try:
        from infrastructure.database.database_factory import ensure_databases_connected
        
        def db_health_loop() -> None:
            import time
            while True:
                try:
                    ensure_databases_connected()
                    time.sleep(60)
                except Exception as e:
                    logger.error(f"❌ DB health check error: {e}")
                    time.sleep(120)
        
        threading_manager = container.get('threading_manager')
        if threading_manager:
            threading_manager.register(
                name="db_health_check",
                target=db_health_loop,
                daemon=True,
                auto_restart=True,
                max_restarts=10
            )
            logger.info("✅ Database health check started")
            
    except Exception as e:
        logger.error(f"❌ Failed to start DB health check: {e}")


# ============================================================
# اجرای راه‌اندازی‌ها
# ============================================================

start_metrics_scheduler()
start_alert_system()
start_db_health_check()


# ============================================================
# Error Handlers
# ============================================================

@app.errorhandler(404)
def not_found(error):
    """مدیریت خطای 404"""
    return jsonify({
        'success': False,
        'error': 'NotFound',
        'message': 'Endpoint not found',
        'timestamp': datetime.now().isoformat()
    }), 404


@app.errorhandler(405)
def method_not_allowed(error):
    """مدیریت خطای 405"""
    return jsonify({
        'success': False,
        'error': 'MethodNotAllowed',
        'message': 'Method not allowed',
        'timestamp': datetime.now().isoformat()
    }), 405


@app.errorhandler(500)
def internal_error(error):
    """مدیریت خطای 500"""
    logger.error(f"Internal server error: {error}")
    return jsonify({
        'success': False,
        'error': 'InternalServerError',
        'message': 'An internal error occurred',
        'timestamp': datetime.now().isoformat()
    }), 500


# ============================================================
# قبل از هر درخواست
# ============================================================

@app.before_request
def before_request():
    """قبل از هر درخواست - تنظیمات اولیه"""
    import time
    import flask
    flask.g.start_time = time.time()


# ============================================================
# بعد از هر درخواست
# ============================================================

@app.after_request
def after_request(response):
    """بعد از هر درخواست - آمار و لاگ"""
    try:
        import time
        import flask
        elapsed = time.time() - flask.g.start_time
        logger.debug(f"Response time: {elapsed*1000:.2f}ms")
    except Exception:
        pass
    return response


# ============================================================
# راه‌اندازی Watchdog
# ============================================================

try:
    threading_manager = container.get('threading_manager')
    if threading_manager:
        threading_manager.start_watchdog(check_interval=10)
        logger.info("✅ Watchdog started")
except Exception as e:
    logger.error(f"❌ Failed to start watchdog: {e}")


# ============================================================
# اجرای اصلی
# ============================================================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "False").lower() == "true"
    
    container_status = container.get_status()
    
    print("=" * 70)
    print(f"🚀 {APP_NAME} v{VERSION}")
    print(f"📡 Port: {port}")
    print(f"🐛 Debug: {debug}")
    print("=" * 70)
    print("📊 Architecture Status:")
    print(f"   ✅ Domain Layer: Entities + Value Objects")
    print(f"   ✅ Application Layer: Use Cases + Services")
    print(f"   ✅ Infrastructure Layer: API + Database + Repositories")
    print(f"   ✅ Presentation Layer: Routes + Middlewares")
    print(f"   ✅ DI Container: {container_status['total']} services")
    print("=" * 70)
    
    # دریافت وضعیت مدل با Lazy Loading
    try:
        model_manager = container.get('model_manager')
        if model_manager and model_manager.current_model:
            print(f"🧠 Model: ✅ Loaded (v{model_manager.current_version})")
        else:
            print(f"🧠 Model: ❌ Not Loaded (DEMO mode)")
    except Exception:
        print(f"🧠 Model: ❌ Not Available")
    
    # دریافت وضعیت Threadها
    try:
        threading_manager = container.get('threading_manager')
        if threading_manager:
            thread_status = threading_manager.get_summary()
            print(f"🔧 Threads: {thread_status.get('total_threads', 0)} active")
    except Exception:
        pass
    
    print("=" * 70)
    print("📌 Available Endpoints:")
    print("  GET  /api/predict           - Predict single coin")
    print("  POST /api/predict/multiple  - Predict multiple coins")
    print("  POST /api/model/train       - Train model")
    print("  GET  /api/health            - Health check")
    print("  GET  /api/metrics           - System metrics")
    print("  GET  /dashboard             - Web dashboard")
    print("=" * 70)
    print("🔧 Use CTRL+C to stop gracefully")
    print("=" * 70)
    
    try:
        app.run(host="0.0.0.0", port=port, debug=debug, threaded=True)
    except KeyboardInterrupt:
        logger.info("🛑 Shutting down...")
        signal_handler(signal.SIGINT, None)
