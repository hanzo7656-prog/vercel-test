# routes/metrics_routes.py
# ============================================================
# روت‌های متریک - با Scheduler جدید
# ============================================================

from flask import jsonify, request
from datetime import datetime
import logging

from core import metrics_scheduler

logger = logging.getLogger(__name__)


def register_metrics_routes(app):
    """ثبت روت‌های متریک در Flask app"""
    
    @app.route('/api/metrics', methods=['GET'])
    def get_metrics():
        """دریافت آخرین متریک‌ها از Scheduler جدید"""
        try:
            data = metrics_scheduler.get_metrics()
            return jsonify({
                "success": True,
                "data": data,
                "timestamp": datetime.now().isoformat()
            })
        except Exception as e:
            logger.error(f"Error in get_metrics: {e}")
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route('/api/metrics/history', methods=['GET'])
    def get_metrics_history():
        """دریافت تاریخچه متریک‌ها"""
        try:
            name = request.args.get('name')
            limit = request.args.get('limit', 100, type=int)
            history = metrics_scheduler.get_history(name, limit)
            return jsonify({
                "success": True,
                "data": history,
                "count": len(history),
                "timestamp": datetime.now().isoformat()
            })
        except Exception as e:
            logger.error(f"Error in get_metrics_history: {e}")
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route('/api/metrics/summary', methods=['GET'])
    def get_metrics_summary():
        """دریافت خلاصه وضعیت Scheduler"""
        try:
            summary = metrics_scheduler.get_summary()
            return jsonify({
                "success": True,
                "data": summary,
                "timestamp": datetime.now().isoformat()
            })
        except Exception as e:
            logger.error(f"Error in get_metrics_summary: {e}")
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route('/api/metrics/config', methods=['POST'])
    def update_metrics_config():
        """به‌روزرسانی تنظیمات متریک‌ها"""
        try:
            data = request.json
            metric = data.get('metric')
            interval = data.get('interval')
            enabled = data.get('enabled')
            
            if not metric:
                return jsonify({"success": False, "error": "metric name required"}), 400
            
            if interval is not None:
                metrics_scheduler.update_interval(metric, interval)
            if enabled is not None:
                metrics_scheduler.enable_metric(metric, enabled)
            
            return jsonify({
                "success": True,
                "message": f"✅ {metric} updated",
                "timestamp": datetime.now().isoformat()
            })
        except Exception as e:
            logger.error(f"Error in update_metrics_config: {e}")
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route('/api/dashboard/metrics', methods=['GET'])
    def dashboard_metrics():
        """داده‌های خلاصه برای داشبورد"""
        try:
            data = metrics_scheduler.get_dashboard_metrics()
            return jsonify({
                "success": True,
                "data": data,
                "timestamp": datetime.now().isoformat()
            })
        except Exception as e:
            logger.error(f"Error in dashboard_metrics: {e}")
            return jsonify({"success": False, "error": str(e)}), 500

    # روت‌های سلامت (با Scheduler جدید)
    @app.route('/health', methods=['GET'])
    def health():
        """بررسی کامل سلامت سیستم"""
        try:
            result = metrics_scheduler.get_health()
            http_status = 200 if result.get('status') in ['ok', 'degraded'] else 503
            return jsonify(result), http_status
        except Exception as e:
            logger.error(f"Error in health: {e}")
            return jsonify({
                "status": "error",
                "message": str(e),
                "timestamp": datetime.now().isoformat()
            }), 500

    @app.route('/health/simple', methods=['GET'])
    def health_simple():
        """بررسی ساده سلامت (برای Uptime Robot)"""
        try:
            cache = metrics_scheduler.metrics_cache
            api_status = cache.get("api_status", {}).get("value", "unknown")
            
            if api_status == "ok":
                return jsonify({
                    "status": "ok",
                    "timestamp": datetime.now().isoformat()
                }), 200
            else:
                return jsonify({
                    "status": "degraded",
                    "timestamp": datetime.now().isoformat()
                }), 503
        except Exception as e:
            return jsonify({
                "status": "error",
                "message": str(e),
                "timestamp": datetime.now().isoformat()
            }), 500

    @app.route('/health/cpu', methods=['GET'])
    def health_cpu():
        """دریافت مصرف CPU"""
        cache = metrics_scheduler.metrics_cache
        cpu = cache.get("cpu", {}).get("value", 0)
        
        status = "healthy"
        if cpu > 90:
            status = "danger"
        elif cpu > 70:
            status = "warning"
        
        return jsonify({
            "cpu_percent": round(cpu, 1),
            "status": status
        })

    @app.route('/stats', methods=['GET'])
    def stats():
        """دریافت آمار کامل سیستم"""
        try:
            from core import system
            summary = metrics_scheduler.get_summary()
            cache = metrics_scheduler.metrics_cache
            
            return jsonify({
                "api_stats": system.api.get_stats(),
                "model_loaded": cache.get("model_status", {}).get("value", {}).get("loaded", False),
                "uptime": cache.get("uptime", {}).get("value", "0s"),
                "scheduler": summary,
                "timestamp": datetime.now().isoformat()
            }), 200
        except Exception as e:
            logger.error(f"Error in stats: {e}")
            return jsonify({
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }), 500

    @app.route('/stats/memory', methods=['GET'])
    def stats_memory():
        """دریافت وضعیت حافظه"""
        try:
            cache = metrics_scheduler.metrics_cache
            ram = cache.get("ram", {}).get("value", 0)
            total_mb = 512
            used_mb = (ram / 100) * total_mb
            
            return jsonify({
                "success": True,
                "data": {
                    "used_mb": round(used_mb, 1),
                    "total_mb": round(total_mb, 1),
                    "percent": round(ram, 1),
                    "status": "healthy" if ram < 80 else "warning"
                },
                "timestamp": datetime.now().isoformat()
            }), 200
        except Exception as e:
            logger.error(f"Error in stats_memory: {e}")
            return jsonify({
                "success": False,
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }), 500

    @app.route('/stats/cache', methods=['GET'])
    def stats_cache():
        """دریافت وضعیت کش"""
        try:
            from core import system
            api_stats = system.api.get_stats()
            scheduler_summary = metrics_scheduler.get_summary()
            
            return jsonify({
                "success": True,
                "data": {
                    "cache_size": api_stats.get('cache_size', 0),
                    "cache_keys": api_stats.get('cache_keys', []),
                    "scheduler_history": scheduler_summary.get('history_size', 0)
                },
                "timestamp": datetime.now().isoformat()
            }), 200
        except Exception as e:
            logger.error(f"Error in stats_cache: {e}")
            return jsonify({
                "success": False,
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }), 500
