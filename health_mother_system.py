# health_mother_system.py
# ============================================================
# سیستم مادر سلامت و اعتبارسنجی
# شامل: سلامت سیستم، اعتبار API، آمار درخواست‌ها، مصرف CPU
# ============================================================

import os
import time
import psutil
from flask import jsonify, request
from datetime import datetime
import logging
from app import app, system

logger = logging.getLogger(__name__)


# ============================================================
# توابع CPU
# ============================================================

def get_cpu_percent():
    """دریافت مصرف واقعی CPU با استفاده از psutil"""
    try:
        cpu_percent = psutil.cpu_percent(interval=0.5)
        
        # تعیین وضعیت بر اساس مصرف
        if cpu_percent < 70:
            status = "healthy"
        elif cpu_percent < 90:
            status = "warning"
        else:
            status = "danger"
        
        return {
            "cpu_percent": round(cpu_percent, 1),
            "status": status
        }
    except Exception as e:
        logger.error(f"Error getting CPU: {e}")
        return {"cpu_percent": 0, "status": "unknown"}


# ============================================================
# ۱. بررسی سلامت سیستم
# ============================================================

@app.route('/health', methods=['GET'])
def health():
    """
    بررسی کامل سلامت سیستم
    - اتصال به API
    - وضعیت مدل
    - اعتبار باقیمانده
    - وضعیت حافظه
    - آمار درخواست‌ها
    """
    try:
        result = system.health_check()
        http_status = 200 if result.get('status') in ['ok', 'degraded'] else 503
        return jsonify(result), http_status
    except Exception as e:
        logger.error(f"Error in health check: {e}")
        return jsonify({
            "status": "error",
            "message": str(e),
            "timestamp": datetime.now().isoformat()
        }), 500


@app.route('/health/simple', methods=['GET'])
def health_simple():
    """
    بررسی ساده سلامت (برای Uptime Robot و پینگ‌های سریع)
    """
    try:
        status = system.api.get_status()
        if status and status.get('status') == 'ok':
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


@app.route('/health/components', methods=['GET'])
def health_components():
    """
    دریافت وضعیت تک تک اجزای سیستم
    """
    try:
        result = system.health_check()
        return jsonify({
            "status": result.get('status'),
            "components": result.get('components', {}),
            "timestamp": result.get('timestamp')
        }), 200
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e),
            "timestamp": datetime.now().isoformat()
        }), 500


@app.route('/health/cpu', methods=['GET'])
def health_cpu():
    """دریافت مصرف CPU"""
    return jsonify(get_cpu_percent())


# ============================================================
# ۲. اعتبار API
# ============================================================

@app.route('/credits', methods=['GET'])
def get_credits():
    """
    دریافت اطلاعات اعتبار API
    - کل اعتبار
    - استفاده شده
    - باقیمانده
    - نوع پلن
    """
    try:
        data = system.api.get_credits()
        
        if data and "error" not in data:
            return jsonify({
                "success": True,
                "data": {
                    "total": data.get('totalCredits'),
                    "used": data.get('usedCredits'),
                    "remaining": data.get('remainingCredits'),
                    "subscription": data.get('subscription', 'free')
                },
                "timestamp": datetime.now().isoformat()
            }), 200
        else:
            return jsonify({
                "success": False,
                "error": data.get("message", "خطا در دریافت اعتبار") if data else "داده‌ای دریافت نشد",
                "timestamp": datetime.now().isoformat()
            }), 400
    except Exception as e:
        logger.error(f"Error in credits: {e}")
        return jsonify({
            "success": False,
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }), 500


@app.route('/credits/usage', methods=['GET'])
def get_credit_usage():
    """
    دریافت آمار مصرف اعتبار به صورت روزانه/ماهانه
    """
    try:
        data = system.api.get_credits()
        
        if data and "error" not in data:
            total = data.get('totalCredits', 0)
            used = data.get('usedCredits', 0)
            remaining = data.get('remainingCredits', 0)
            
            usage_percent = round((used / total) * 100, 1) if total > 0 else 0
            
            if usage_percent > 80:
                status = "critical"
            elif usage_percent > 60:
                status = "warning"
            else:
                status = "healthy"
            
            return jsonify({
                "success": True,
                "data": {
                    "total": total,
                    "used": used,
                    "remaining": remaining,
                    "usage_percent": usage_percent,
                    "status": status,
                    "subscription": data.get('subscription', 'free')
                },
                "timestamp": datetime.now().isoformat()
            }), 200
        else:
            return jsonify({
                "success": False,
                "error": data.get("message", "خطا در دریافت اعتبار") if data else "داده‌ای دریافت نشد"
            }), 400
    except Exception as e:
        logger.error(f"Error in credit usage: {e}")
        return jsonify({
            "success": False,
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }), 500


# ============================================================
# ۳. آمار و اطلاعات سیستم
# ============================================================

@app.route('/stats', methods=['GET'])
def stats():
    """
    دریافت آمار کامل سیستم
    - آمار درخواست‌های API
    - وضعیت مدل
    - آپتایم
    - تعداد تسک‌های پس‌زمینه
    """
    try:
        return jsonify({
            "api_stats": system.api.get_stats(),
            "model_loaded": system.model_loaded,
            "uptime": str(datetime.now() - system.start_time).split('.')[0],
            "timestamp": datetime.now().isoformat()
        }), 200
    except Exception as e:
        logger.error(f"Error in stats: {e}")
        return jsonify({
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }), 500


@app.route('/stats/requests', methods=['GET'])
def stats_requests():
    """
    دریافت آمار درخواست‌های API
    """
    try:
        stats = system.api.get_stats()
        return jsonify({
            "success": True,
            "data": stats,
            "timestamp": datetime.now().isoformat()
        }), 200
    except Exception as e:
        logger.error(f"Error in request stats: {e}")
        return jsonify({
            "success": False,
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }), 500


@app.route('/stats/cache', methods=['GET'])
def stats_cache():
    """
    دریافت وضعیت کش
    """
    try:
        stats = system.api.get_stats()
        return jsonify({
            "success": True,
            "data": {
                "cache_size": stats.get('cache_size', 0),
                "cache_keys": stats.get('cache_keys', [])
            },
            "timestamp": datetime.now().isoformat()
        }), 200
    except Exception as e:
        logger.error(f"Error in cache stats: {e}")
        return jsonify({
            "success": False,
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }), 500


@app.route('/stats/memory', methods=['GET'])
def stats_memory():
    """
    دریافت وضعیت حافظه
    """
    try:
        used_mb, total_mb = system._get_memory_usage()
        if total_mb == 0 or total_mb > 10000:
            total_mb = 512
        memory_percent = (used_mb / total_mb) * 100 if total_mb > 0 else 0
        
        return jsonify({
            "success": True,
            "data": {
                "used_mb": round(used_mb, 1),
                "total_mb": round(total_mb, 1),
                "percent": round(memory_percent, 1),
                "status": "healthy" if memory_percent < 80 else "warning"
            },
            "timestamp": datetime.now().isoformat()
        }), 200
    except Exception as e:
        logger.error(f"Error in memory stats: {e}")
        return jsonify({
            "success": False,
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }), 500


# ============================================================
# ۴. وضعیت کلی سیستم (ساده)
# ============================================================

@app.route('/status', methods=['GET'])
def system_status():
    """
    وضعیت کلی سیستم (ساده)
    """
    try:
        health = system.health_check()
        return jsonify({
            "status": health.get('status', 'unknown'),
            "model": "loaded" if system.model_loaded else "demo",
            "timestamp": datetime.now().isoformat()
        }), 200
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e),
            "timestamp": datetime.now().isoformat()
        }), 500


# ============================================================
# ۵. ریست/پاک کردن کش (برای مدیریت)
# ============================================================

@app.route('/admin/cache/clear', methods=['POST'])
def clear_cache():
    """
    پاک کردن کش (فقط برای مدیریت)
    """
    try:
        system.api._clear_cache()
        return jsonify({
            "success": True,
            "message": "کش با موفقیت پاک شد",
            "timestamp": datetime.now().isoformat()
        }), 200
    except Exception as e:
        logger.error(f"Error clearing cache: {e}")
        return jsonify({
            "success": False,
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }), 500
