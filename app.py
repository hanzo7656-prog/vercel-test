# app.py
# ============================================================
# ورودی اصلی سیستم - نسخه ۱۰.۰
# Bootstrap + Graceful Shutdown + Error Handling
# ============================================================

import os
import sys
import signal
import logging
from datetime import datetime
from flask import Flask, jsonify

from config.version import VERSION, APP_NAME
from container import container
from providers import init_container, shutdown_services

# Flask app
logger = logging.getLogger(__name__)


# ============================================================
# Signal Handler
# ============================================================

def signal_handler(sig, frame) -> None:
    """Graceful shutdown"""
    logger.info(f"🛑 Signal {sig} received, shutting down...")
    
    # ۱. سرویس‌های پس‌زمینه
    try:
        shutdown_services()
    except Exception as e:
        logger.error(f"❌ Shutdown services error: {e}")
    
    # ۲. Metrics Scheduler
    try:
        if container.has('metrics_scheduler'):
            metrics = container.get('metrics_scheduler')
            if metrics and hasattr(metrics, 'stop'):
                metrics.stop()
    except Exception as e:
        logger.error(f"❌ Metrics stop error: {e}")
    
    # ۳. Threading
    try:
        if container.has('threading_manager'):
            tm = container.get('threading_manager')
            if tm and hasattr(tm, 'stop_all'):
                tm.stop_all()
    except Exception as e:
        logger.error(f"❌ Threading stop error: {e}")
    
    # ۴. Parallel Processor
    try:
        from core.parallel_processor import parallel_processor
        parallel_processor.shutdown()
    except Exception as e:
        logger.error(f"❌ Parallel shutdown error: {e}")
    
    # ۵. Database Factory 🆕
    try:
        if container.has('db_factory'):
            db_factory = container.get('db_factory')
            if hasattr(db_factory, 'shutdown'):
                db_factory.shutdown()
                logger.info("✅ Database factory shutdown")
    except Exception as e:
        logger.error(f"❌ DB factory shutdown error: {e}")
    
    logger.info("✅ Graceful shutdown complete")
    sys.exit(0)


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


# ============================================================
# Flask App
# ============================================================

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
app.config['JSON_SORT_KEYS'] = False
app.config['JSON_AS_ASCII'] = False


# ============================================================
# Container Init
# ============================================================

# ✅ Force init database_factory FIRST
try:
    from infrastructure.database.database_factory import db_factory
    logger.info(f"✅ database_factory initialized")
except Exception as e:
    logger.error(f"❌ database_factory init failed: {e}")
    import traceback
    logger.error(traceback.format_exc())

# راه‌اندازی Container
init_container(app)
logger.info("✅ Container initialized")


# ============================================================
# Register Blueprints
# ============================================================

from presentation.routes.api_routes import api_bp
from presentation.routes.metrics_routes import metrics_bp
from presentation.routes.web_routes import web_bp

app.register_blueprint(web_bp)
app.register_blueprint(api_bp)
app.register_blueprint(metrics_bp)

logger.info("✅ Blueprints registered")


# ============================================================
# Start Metrics Scheduler
# ============================================================

def start_metrics_scheduler() -> None:
    """شروع Metrics Scheduler"""
    try:
        metrics = container.get('metrics_scheduler')
        if not metrics:
            logger.warning("⚠️ Metrics scheduler not available")
            return
        
        # از threading_manager استفاده کن
        if container.has('threading_manager'):
            tm = container.get('threading_manager')
            tm.register(
                name="metrics_scheduler",
                target=metrics.start,
                daemon=False,
                auto_restart=True,
                max_restarts=3,
                restart_delay=10,
            )
            logger.info("✅ Metrics Scheduler via ThreadingManager")
        else:
            metrics.start()
            logger.info("✅ Metrics Scheduler started")
    
    except Exception as e:
        logger.error(f"❌ Metrics scheduler failed: {e}")


# ============================================================
# Start Alert System
# ============================================================

def start_alert_system() -> None:
    """
    شروع سیستم Alert + Self-Healing
    
    ⚠️ توجه: خودکار alert_loop رو اجرا می‌کنه
    """
    try:
        from infrastructure.external.alerter import alerter
        
        # Metrics Scheduler (اگه داره healer)
        metrics = container.get('metrics_scheduler')
        if not metrics:
            logger.warning("⚠️ Alert system disabled (no metrics)")
            return
        
        # اگه healer نداره، بساز
        if getattr(metrics, 'healer', None) is None:
            try:
                healer = container.get('self_healer')
                metrics.healer = healer
                logger.info("✅ SelfHealer attached to metrics")
            except Exception as e:
                logger.warning(f"⚠️ SelfHealer not available: {e}")
        
        # Alert loop
        def alert_loop() -> None:
            import time
            while True:
                try:
                    metrics_s = container.get('metrics_scheduler')
                    if metrics_s:
                        alert_metrics = metrics_s.get_alert_metrics()
                        alerter.check_and_alert(alert_metrics)
                        
                        if metrics_s.healer:
                            metrics_s.healer.check_and_heal(alert_metrics)
                    
                    time.sleep(30)
                except Exception as e:
                    logger.error(f"❌ Alert loop error: {e}")
                    time.sleep(30)
        
        # از threading_manager
        if container.has('threading_manager'):
            tm = container.get('threading_manager')
            tm.register(
                name="alert_system",
                target=alert_loop,
                daemon=False,
                auto_restart=True,
                max_restarts=5,
                restart_delay=15,
            )
            logger.info("✅ Alert system via ThreadingManager")
        else:
            import threading
            alert_thread = threading.Thread(target=alert_loop, daemon=False)
            alert_thread.start()
            logger.info("✅ Alert system started")
    
    except Exception as e:
        logger.error(f"❌ Alert system failed: {e}")
        import traceback
        logger.error(traceback.format_exc())


# ============================================================
# Start DB Health Check (🆕)
# ============================================================

def start_db_health_check() -> None:
    """
    شروع DB Health Check با Self-Healing
    
    ارتقا: الان از db_factory استفاده می‌کنه
    """
    try:
        if not container.has('db_factory'):
            logger.warning("⚠️ DB factory not available")
            return
        
        def db_health_loop() -> None:
            import time
            while True:
                try:
                    from infrastructure.database import health_check
                    health = health_check()
                    
                    # بررسی سلامت
                    disconnected = [
                        name for name, info in health.items()
                        if not info.get('connected', False)
                    ]
                    
                    if disconnected:
                        logger.warning(f"⚠️ DBs disconnected: {disconnected}")
                    
                    time.sleep(60)
                except Exception as e:
                    logger.error(f"❌ DB health error: {e}")
                    time.sleep(120)
        
        if container.has('threading_manager'):
            tm = container.get('threading_manager')
            tm.register(
                name="db_health_check",
                target=db_health_loop,
                daemon=True,
                auto_restart=True,
                max_restarts=10,
            )
            logger.info("✅ DB health check started")
    
    except Exception as e:
        logger.error(f"❌ DB health check failed: {e}")


# ============================================================
# Start All
# ============================================================

def _should_start_background() -> bool:
    """
    فقط در پروسه‌ی اصلی (نه reloader، نه worker اضافه) سرویس‌ها را استارت بزن
    """
    # اگه با Flask reloader اجرا می‌شه، فقط در پروسه‌ی اصلی
    if os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        return False
    # اگه صریحاً گفته شده skip کن
    if os.environ.get("SKIP_BACKGROUND", "").lower() == "true":
        return False
    return True


if _should_start_background():
    start_metrics_scheduler()
    start_alert_system()
    start_db_health_check()
else:
    logger.info("⏭️ Background services skipped (worker/reloader)")


# ============================================================
# Error Handlers
# ============================================================

@app.errorhandler(404)
def not_found(error):
    return jsonify({
        'success': False,
        'error': 'NotFound',
        'message': 'Endpoint not found',
        'timestamp': datetime.now().isoformat(),
    }), 404


@app.errorhandler(405)
def method_not_allowed(error):
    return jsonify({
        'success': False,
        'error': 'MethodNotAllowed',
        'message': 'Method not allowed',
        'timestamp': datetime.now().isoformat(),
    }), 405


@app.errorhandler(500)
def internal_error(error):
    logger.error(f"Internal server error: {error}")
    return jsonify({
        'success': False,
        'error': 'InternalServerError',
        'message': 'An internal error occurred',
        'timestamp': datetime.now().isoformat(),
    }), 500


# ============================================================
# Root Endpoint
# ============================================================

@app.route('/')
def home():
    """روت ساده"""
    try:
        container_status = container.get_status()
        ws_connected = False
        try:
            if container.has('free_crypto_client'):
                fc = container.get('free_crypto_client')
                ws_connected = fc.is_connected if fc else False
        except Exception:
            pass
        
        return jsonify({
            'name': APP_NAME,
            'version': VERSION,
            'status': 'running',
            'container': {
                'services_count': container_status.get('total', 0),
            },
            'websocket': {'connected': ws_connected},
            'timestamp': datetime.now().isoformat(),
            'endpoints': [
                '/api/health',
                '/api/metrics',
                '/api/model/status',
                '/api/model/profiles/presets',
                '/api/predict/single',
                '/api/crypto/prices',
            ],
        })
    except Exception as e:
        logger.error(f"Root endpoint error: {e}")
        return jsonify({
            'name': APP_NAME,
            'version': VERSION,
            'status': 'running',
        })


# ============================================================
# Watchdog
# ============================================================

try:
    if container.has('threading_manager'):
        tm = container.get('threading_manager')
        tm.start_watchdog(check_interval=10)
        logger.info("✅ Watchdog started")
except Exception as e:
    logger.error(f"❌ Watchdog failed: {e}")


# ============================================================
# Main
# ============================================================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "False").lower() == "true"
    
    # Status
    try:
        status = container.get_status()
        services_count = status.get('total', 0)
    except Exception:
        services_count = 0
    
    print("=" * 70)
    print(f"🚀 {APP_NAME} v{VERSION}")
    print(f"📡 Port: {port}")
    print(f"🐛 Debug: {debug}")
    print(f"📦 Services: {services_count}")
    print("=" * 70)
    
    try:
        app.run(
            host="0.0.0.0",
            port=port,
            debug=debug,
            threaded=True,
        )
    except KeyboardInterrupt:
        logger.info("🛑 Shutting down...")
        signal_handler(signal.SIGINT, None)
