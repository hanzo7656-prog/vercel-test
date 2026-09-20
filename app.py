# app.py
# ============================================================
# ورودی اصلی سیستم - نسخه ۱۰.۰
# Bootstrap + Graceful Shutdown + Error Handling
# ============================================================

import os
import sys
import signal
import logging
import threading
from datetime import datetime
from flask import Flask, jsonify

from config.version import VERSION, APP_NAME
from container import container, start_services
from providers import init_container, shutdown_services
logger = logging.getLogger(__name__)


# ============================================================
# Signal Handler
# ============================================================

def signal_handler(sig, frame) -> None:
    """Graceful shutdown"""
    logger.info(f"🛑 Signal {sig} received, shutting down...")

    try:
        shutdown_services()
    except Exception as e:
        logger.error(f"❌ Shutdown services error: {e}")

    try:
        if container.has('metrics_scheduler'):
            metrics = container.get('metrics_scheduler')
            if metrics and hasattr(metrics, 'stop'):
                metrics.stop()
    except Exception as e:
        logger.error(f"❌ Metrics stop error: {e}")

    try:
        if container.has('threading_manager'):
            tm = container.get('threading_manager')
            if tm and hasattr(tm, 'stop_all'):
                tm.stop_all()
    except Exception as e:
        logger.error(f"❌ Threading stop error: {e}")

    try:
        from core.parallel_processor import parallel_processor
        parallel_processor.shutdown()
    except Exception as e:
        logger.error(f"❌ Parallel shutdown error: {e}")

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

# ✅ Force init database_factory FIRST — با thread جدا و timeout
#    دلیل: db_factory.__init__ به ۶ دیتابیس وصل می‌شود و ممکن است
#    در import time دقیقه‌ها طول بکشد → gunicorn port timeout می‌دهد.

def _init_db_factory() -> None:
    """Init db_factory در thread جدا"""
    import time as _time
    started = _time.time()
    try:
        logger.info("🔄 Initializing database_factory...")
        from infrastructure.database.database_factory import db_factory
        elapsed = _time.time() - started
        logger.info(f"✅ database_factory initialized in {elapsed:.2f}s")

        # چک سلامت همه دیتابیس‌ها
        try:
            from infrastructure.database import health_check
            health = health_check()
            for name, info in health.items():
                status = "✅" if info.get("connected") else "❌"
                logger.info(
                    f"  {status} {name}: "
                    f"type={info.get('type', 'unknown')} | "
                    f"connected={info.get('connected', False)}"
                )
        except Exception as e:
            logger.warning(f"⚠️ Health check after init failed: {e}")

    except Exception as e:
        elapsed = _time.time() - started
        logger.error(f"❌ database_factory init failed after {elapsed:.2f}s: {e}")
        import traceback
        logger.error(traceback.format_exc())


_init_thread = threading.Thread(
    target=_init_db_factory,
    name="DBFactoryInit",
    daemon=True,
)
_init_thread.start()
_init_thread.join(timeout=60)

if _init_thread.is_alive():
    logger.warning(
        "⚠️ database_factory init timed out after 60s, continuing anyway "
        "(gunicorn will bind port now)"
    )
else:
    logger.info("✅ database_factory init completed within 60s")


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
    """شروع سیستم Alert + Self-Healing"""
    try:
        from infrastructure.external.alerter import alerter

        metrics = container.get('metrics_scheduler')
        if not metrics:
            logger.warning("⚠️ Alert system disabled (no metrics)")
            return

        if getattr(metrics, 'healer', None) is None:
            try:
                healer = container.get('self_healer')
                metrics.healer = healer
                logger.info("✅ SelfHealer attached to metrics")
            except Exception as e:
                logger.warning(f"⚠️ SelfHealer not available: {e}")

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
            alert_thread = threading.Thread(target=alert_loop, daemon=False)
            alert_thread.start()
            logger.info("✅ Alert system started")

    except Exception as e:
        logger.error(f"❌ Alert system failed: {e}")
        import traceback
        logger.error(traceback.format_exc())


# ============================================================
# Start DB Health Check
# ============================================================

def start_db_health_check() -> None:
    """شروع DB Health Check با Self-Healing"""
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

# ============================================================
# Start All — فقط در Worker (اولین request)
# ============================================================

@app.before_request
def _lazy_start_services():
    """
    🆕 سرویس‌های پس‌زمینه را فقط در Worker شروع کن

    چرا: اگر در import time صدا زده شوند، در Master ساخته می‌شوند
    و بعد از fork، threadها در Worker نیستند.
    """
    if getattr(app, '_services_started', False):
        return
    app._services_started = True

    import os
    if os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        return
    if os.environ.get("SKIP_BACKGROUND", "").lower() == "true":
        return

    logger.info("🚀 [Worker] Starting background services...")

    # ۱. Container services (Binance WS, PriceManager, ...)
    try:
        from providers import start_services
        start_services()
        logger.info("✅ [Worker] Container services started")
    except Exception as e:
        logger.error(f"❌ [Worker] start_services failed: {e}")
        import traceback
        logger.error(traceback.format_exc())

    # ۲. Metrics Scheduler
    try:
        start_metrics_scheduler()
    except Exception as e:
        logger.error(f"❌ [Worker] metrics_scheduler failed: {e}")

    # ۳. Alert System
    try:
        start_alert_system()
    except Exception as e:
        logger.error(f"❌ [Worker] alert_system failed: {e}")

    # ۴. DB Health Check
    try:
        start_db_health_check()
    except Exception as e:
        logger.error(f"❌ [Worker] db_health_check failed: {e}")

    logger.info("✅ [Worker] All background services started")
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
# Main
# ============================================================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "False").lower() == "true"

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
