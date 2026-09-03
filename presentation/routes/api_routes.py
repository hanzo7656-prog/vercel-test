# presentation/routes/api_routes.py
# ============================================================
# API Routes - نسخه کامل نهایی (v10.0)
# ============================================================
# شامل: ۵۷+ اندپوینت تفکیک شده
# - سیستم (System): 7
# - آمار اپلیکیشن (App Stats): 1
# - دیتابیس PostgreSQL: 5
# - دیتابیس Redis: 4
# - دیتابیس SQLite: 4
# - دیتابیس عمومی: 4
# - مدل (Model): 8
# - زمان‌بندی (Schedule): 3
# - پیش‌بینی (Predictions): 3
# - کوین‌استتس (CoinStats): 6
# - هشدارها (Alerts): 3
# - کاربر (User): 2
# - دیباگ (Debug): 9
# - احراز هویت (Auth): 1
# ============================================================

import os
import sys
import json
import csv
import io
import logging
import tempfile
import time
import traceback
from datetime import datetime
from flask import Blueprint, request, jsonify, current_app, send_file, make_response
from pathlib import Path

from application.dto.prediction_dto import PredictionRequestDTO
from application.services.prediction_service import PredictionService
from application.services.monitoring_service import MonitoringService
from application.use_cases.train_model import TrainModelUseCase
from infrastructure.auth.auth_manager import require_auth
from infrastructure.external.alerter import alerter
from infrastructure.database import get_primary, get_cache, get_backup, health_check, registry

logger = logging.getLogger(__name__)

api_bp = Blueprint('api', __name__, url_prefix='/api')


# ============================================================
# ۱. صفحه اصلی (HOME)
# ============================================================

@api_bp.route('', methods=['GET'])
def api_home():
    """صفحه اصلی API - لیست همه اندپوینت‌ها"""
    return jsonify({
        'name': 'Trading Signal System API',
        'version': '10.0.0',
        'status': 'running',
        'timestamp': datetime.now().isoformat(),
        'endpoints': {
            'system': {
                'health': '/api/health',
                'health_simple': '/api/health/simple',
                'health_database': '/api/health/database',
                'stats': '/api/stats',
                'metrics': '/api/metrics',
                'metrics_summary': '/api/metrics/summary',
                'metrics_dashboard': '/api/metrics/dashboard'
            },
            'app_stats': {
                'stats': '/api/app/stats'
            },
            'database': {
                'postgresql_tables': '/api/db/postgresql/tables',
                'postgresql_table': '/api/db/postgresql/table/<name>',
                'postgresql_stats': '/api/db/postgresql/stats',
                'postgresql_export': '/api/db/postgresql/export/<name>',
                'postgresql_backup': '/api/db/postgresql/backup',
                'redis_keys': '/api/db/redis/keys',
                'redis_key': '/api/db/redis/key/<key>',
                'redis_stats': '/api/db/redis/stats',
                'redis_clear': '/api/db/redis/clear',
                'sqlite_tables': '/api/db/sqlite/tables',
                'sqlite_table': '/api/db/sqlite/table/<name>',
                'sqlite_stats': '/api/db/sqlite/stats',
                'sqlite_export': '/api/db/sqlite/export/<name>',
                'search': '/api/db/search',
                'health': '/api/db/health',
                'query': '/api/db/query',
                'tables': '/api/db/tables',
                'stats_general': '/api/db/stats'
            },
            'model': {
                'status': '/api/model/status',
                'history': '/api/model/history',
                'features': '/api/model/features',
                'data': '/api/model/data',
                'train': '/api/model/train',
                'export': '/api/model/export',
                'import': '/api/model/import',
                'activate': '/api/model/activate',
                'delete': '/api/model/delete'
            },
            'schedule': {
                'status': '/api/schedule/status',
                'start': '/api/schedule/start',
                'stop': '/api/schedule/stop'
            },
            'predict': {
                'single': '/api/predict/single',
                'multiple': '/api/predict/multiple',
                'explain': '/api/predict/explain'
            },
            'coinstats': {
                'price': '/api/coinstats/price/<coin>',
                'prices': '/api/coinstats/prices',
                'fear_greed': '/api/coinstats/fear-greed',
                'btc_dominance': '/api/coinstats/btc-dominance',
                'all': '/api/coinstats/all'
            },
            'alerts': {
                'list': '/api/alerts',
                'resolve': '/api/alerts/<id>/resolve',
                'resolve_all': '/api/alerts/resolve-all'
            },
            'user': {
                'info': '/api/user',
                'credits': '/api/credits'
            },
            'debug': {
                'status': '/api/debug/status',
                'logs': '/api/debug/logs',
                'logs_clear': '/api/debug/logs/clear',
                'system': '/api/debug/system',
                'processes': '/api/debug/processes',
                'exec': '/api/debug/exec',
                'cache': '/api/debug/cache',
                'cache_clear': '/api/debug/cache/clear',
                'loglevel': '/api/debug/loglevel'
            },
            'auth': {
                'login': '/api/login'
            }
        }
    })


# ============================================================
# ۲. سلامت سیستم (SYSTEM HEALTH)
# ============================================================

@api_bp.route('/health', methods=['GET'])
def health():
    """وضعیت کلی سیستم"""
    try:
        container = current_app.container
        monitoring_service: MonitoringService = container.monitoring_service()
        health_data = monitoring_service.get_health()
        return jsonify(health_data), 200 if health_data.get('status') == 'ok' else 503
    except Exception as e:
        logger.error(f"Health error: {e}", exc_info=True)
        return jsonify({'status': 'error', 'error': str(e)}), 500


@api_bp.route('/health/simple', methods=['GET'])
def health_simple():
    """وضعیت ساده سیستم (بدون جزئیات)"""
    try:
        container = current_app.container
        monitoring_service: MonitoringService = container.monitoring_service()
        health_data = monitoring_service.get_health()
        if health_data.get('status') == 'ok':
            return jsonify({'status': 'ok', 'timestamp': datetime.now().isoformat()}), 200
        return jsonify({'status': 'degraded'}), 503
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500


@api_bp.route('/health/database', methods=['GET'])
@require_auth()
def health_database():
    """وضعیت سلامت دیتابیس‌ها"""
    try:
        health = health_check()
        return jsonify({
            'success': True,
            'data': health,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"Database health error: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500


# ============================================================
# ۳. متریک‌ها و آمار (METRICS & STATS)
# ============================================================

@api_bp.route('/metrics', methods=['GET'])
def get_metrics():
    """دریافت متریک‌های لحظه‌ای"""
    try:
        container = current_app.container
        monitoring_service: MonitoringService = container.monitoring_service()
        metrics = monitoring_service.get_metrics()
        return jsonify(metrics), 200 if metrics.get('success') else 500
    except Exception as e:
        logger.error(f"Metrics error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/metrics/summary', methods=['GET'])
def get_metrics_summary():
    """دریافت خلاصه متریک‌ها"""
    try:
        container = current_app.container
        monitoring_service: MonitoringService = container.monitoring_service()
        summary = monitoring_service.get_metrics_summary()
        return jsonify(summary), 200 if summary.get('success') else 500
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/metrics/dashboard', methods=['GET'])
def get_dashboard_metrics():
    """دریافت متریک‌های مخصوص داشبورد (همه داده‌ها در یک جا)"""
    try:
        container = current_app.container
        monitoring_service: MonitoringService = container.monitoring_service()
        metrics = monitoring_service.get_dashboard_metrics()
        return jsonify(metrics), 200 if metrics.get('success') else 500
    except Exception as e:
        logger.error(f"Dashboard metrics error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/stats', methods=['GET'])
@require_auth()
def get_stats():
    """دریافت آمار خلاصه سیستم (uptime, collections, predictions)"""
    try:
        container = current_app.container
        monitoring_service: MonitoringService = container.monitoring_service()
        metrics = monitoring_service.get_metrics()
        
        uptime = metrics.get('data', {}).get('metrics', {}).get('uptime', {}).get('value', '0s')
        collections = metrics.get('data', {}).get('stats', {}).get('collections', 0)
        predictions = metrics.get('data', {}).get('stats', {}).get('predictions', 0)
        
        return jsonify({
            'success': True,
            'data': {
                'uptime': uptime,
                'collections': collections,
                'predictions': predictions,
                'timestamp': datetime.now().isoformat()
            }
        })
    except Exception as e:
        logger.error(f"Stats error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================
# ۴. آمار واقعی اپلیکیشن (APP STATS) - جدید
# ============================================================

@api_bp.route('/app/stats', methods=['GET'])
@require_auth()
def app_stats():
    """دریافت آمار واقعی اپلیکیشن (RAM، CPU، Uptime) - لحظه‌ای"""
    try:
        import psutil
        import os
        import time
        
        pid = os.getpid()
        process = psutil.Process(pid)
        mem_info = process.memory_info()
        
        # ===== RAM واقعی اپلیکیشن =====
        rss_mb = mem_info.rss / (1024 * 1024)
        
        # محدودیت کانتینر (اگر وجود داشته باشد)
        try:
            with open('/sys/fs/cgroup/memory/memory.limit_in_bytes', 'r') as f:
                container_limit = int(f.read().strip())
                container_limit_mb = container_limit / (1024 * 1024)
        except:
            container_limit_mb = psutil.virtual_memory().total / (1024 * 1024)
        
        # ===== CPU واقعی اپلیکیشن =====
        cpu_percent = process.cpu_percent(interval=0.3)
        
        # ===== uptime اپلیکیشن (از زمان شروع فرآیند) =====
        create_time = process.create_time()
        app_uptime = time.time() - create_time
        
        # ===== uptime سیستم =====
        system_uptime = time.time() - psutil.boot_time()
        
        return jsonify({
            'success': True,
            'data': {
                'ram': {
                    'used_mb': round(rss_mb, 1),
                    'limit_mb': round(container_limit_mb, 1),
                    'percent': round((rss_mb / container_limit_mb) * 100, 1) if container_limit_mb > 0 else 0,
                    'free_mb': round(container_limit_mb - rss_mb, 1)
                },
                'cpu': {
                    'percent': round(cpu_percent, 1),
                    'threads': process.num_threads(),
                    'system_percent': round(psutil.cpu_percent(interval=0.3), 1)
                },
                'uptime': {
                    'app_seconds': int(app_uptime),
                    'app_formatted': format_uptime(app_uptime),
                    'system_seconds': int(system_uptime),
                    'system_formatted': format_uptime(system_uptime)
                },
                'process': {
                    'pid': pid,
                    'status': process.status(),
                    'memory_percent': round(process.memory_percent(), 2)
                }
            }
        })
    except Exception as e:
        logger.error(f"App stats error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


def format_uptime(seconds):
    """تبدیل ثانیه به فرمت خوانا"""
    days = int(seconds // 86400)
    hours = int((seconds % 86400) // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    
    parts = []
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    parts.append(f"{secs}s")
    
    return " ".join(parts)


# ============================================================
# ۵. دیتابیس - PostgreSQL
# ============================================================

@api_bp.route('/db/postgresql/tables', methods=['GET'])
@require_auth()
def postgresql_tables():
    """دریافت لیست جدول‌های PostgreSQL با جزئیات کامل"""
    try:
        db = get_primary()
        if not db or not db.is_connected():
            return jsonify({'success': False, 'error': 'PostgreSQL not connected'}), 503
        
        result = db.execute("""
            SELECT 
                table_name,
                (SELECT COUNT(*) FROM information_schema.tables WHERE table_name = t.table_name) as row_count
            FROM information_schema.tables t
            WHERE table_schema = 'public'
            ORDER BY table_name
        """)
        
        for table in result:
            # حجم جدول
            size_result = db.execute(f"""
                SELECT pg_total_relation_size('{table['table_name']}') / 1024 / 1024 as size_mb
            """)
            table['size_mb'] = size_result[0]['size_mb'] if size_result else 0
            
            # آخرین بروزرسانی
            try:
                update_result = db.execute(f"""
                    SELECT MAX(updated_at) as last_update FROM "{table['table_name']}"
                """)
                table['last_update'] = update_result[0]['last_update'] if update_result else None
            except:
                table['last_update'] = None
        
        return jsonify({
            'success': True,
            'data': result,
            'count': len(result)
        })
    except Exception as e:
        logger.error(f"PostgreSQL tables error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/db/postgresql/table/<table_name>', methods=['GET'])
@require_auth()
def postgresql_table_data(table_name):
    """دریافت داده‌های یک جدول خاص PostgreSQL با قابلیت صفحه‌بندی و جستجو"""
    try:
        db = get_primary()
        if not db or not db.is_connected():
            return jsonify({'success': False, 'error': 'PostgreSQL not connected'}), 503
        
        limit = request.args.get('limit', 100, type=int)
        offset = request.args.get('offset', 0, type=int)
        search = request.args.get('search', '')
        sort_by = request.args.get('sort_by', 'id')
        sort_order = request.args.get('sort_order', 'DESC')
        format_type = request.args.get('format', 'json')
        
        # بررسی وجود جدول
        columns = db.execute("""
            SELECT column_name, data_type
            FROM information_schema.columns 
            WHERE table_name = %s
            ORDER BY ordinal_position
        """, (table_name,))
        
        if not columns:
            return jsonify({'success': False, 'error': 'Table not found'}), 404
        
        col_names = [c['column_name'] for c in columns]
        
        # ساخت کوئری با جستجو
        query = f'SELECT * FROM "{table_name}"'
        params = []
        
        if search:
            search_conditions = []
            for col in col_names:
                if col in ['id', 'created_at', 'updated_at']:
                    continue
                search_conditions.append(f'"{col}"::text ILIKE %s')
                params.append(f'%{search}%')
            
            if search_conditions:
                query += ' WHERE ' + ' OR '.join(search_conditions)
        
        # مرتب‌سازی
        if sort_by in col_names:
            query += f' ORDER BY "{sort_by}" {sort_order}'
        else:
            query += ' ORDER BY id DESC'
        
        # صفحه‌بندی
        query += ' LIMIT %s OFFSET %s'
        params.extend([limit, offset])
        
        rows = db.execute(query, tuple(params))
        
        # دریافت تعداد کل
        count_query = f'SELECT COUNT(*) as total FROM "{table_name}"'
        count_params = []
        
        if search:
            count_query += ' WHERE ' + ' OR '.join(search_conditions)
            count_params = [f'%{search}%'] * len(search_conditions) if search_conditions else []
        
        total_result = db.execute(count_query, tuple(count_params))
        total = total_result[0]['total'] if total_result else 0
        
        # خروجی CSV
        if format_type == 'csv':
            output = io.StringIO()
            writer = csv.DictWriter(output, fieldnames=col_names)
            writer.writeheader()
            writer.writerows(rows)
            output.seek(0)
            return send_file(
                io.BytesIO(output.getvalue().encode('utf-8')),
                as_attachment=True,
                download_name=f'{table_name}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv',
                mimetype='text/csv'
            )
        
        return jsonify({
            'success': True,
            'data': {
                'table': table_name,
                'columns': col_names,
                'rows': rows,
                'total': total,
                'limit': limit,
                'offset': offset,
                'has_more': (offset + limit) < total
            }
        })
    except Exception as e:
        logger.error(f"PostgreSQL table data error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/db/postgresql/stats', methods=['GET'])
@require_auth()
def postgresql_stats():
    """دریافت آمار کامل PostgreSQL"""
    try:
        db = get_primary()
        if not db or not db.is_connected():
            return jsonify({'success': False, 'error': 'PostgreSQL not connected'}), 503
        
        # حجم کل دیتابیس
        size = db.execute("""
            SELECT 
                pg_database_size(current_database()) / 1024 / 1024 as total_size_mb,
                pg_database_size(current_database()) as total_size_bytes
        """)
        
        # تعداد جدول‌ها
        tables = db.execute("""
            SELECT COUNT(*) as table_count 
            FROM information_schema.tables 
            WHERE table_schema = 'public'
        """)
        
        # تعداد کل رکوردها (تقریبی)
        total_rows = 0
        table_list = db.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public'
        """)
        for t in table_list:
            try:
                count = db.execute(f'SELECT COUNT(*) as count FROM "{t["table_name"]}"')
                total_rows += count[0]['count'] if count else 0
            except:
                pass
        
        # اتصالات فعال
        connections = db.execute("""
            SELECT COUNT(*) as active_connections 
            FROM pg_stat_activity 
            WHERE state = 'active'
        """)
        
        return jsonify({
            'success': True,
            'data': {
                'total_size_mb': size[0]['total_size_mb'] if size else 0,
                'total_size_bytes': size[0]['total_size_bytes'] if size else 0,
                'table_count': tables[0]['table_count'] if tables else 0,
                'total_rows': total_rows,
                'active_connections': connections[0]['active_connections'] if connections else 0,
                'connected': True,
                'timestamp': datetime.now().isoformat()
            }
        })
    except Exception as e:
        logger.error(f"PostgreSQL stats error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/db/postgresql/export/<table_name>', methods=['GET'])
@require_auth()
def postgresql_export(table_name):
    """خروجی کامل یک جدول PostgreSQL (CSV/JSON)"""
    try:
        format_type = request.args.get('format', 'csv')
        limit = request.args.get('limit', 10000, type=int)
        
        db = get_primary()
        if not db or not db.is_connected():
            return jsonify({'success': False, 'error': 'PostgreSQL not connected'}), 503
        
        # بررسی وجود جدول
        columns = db.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = %s
            ORDER BY ordinal_position
        """, (table_name,))
        
        if not columns:
            return jsonify({'success': False, 'error': 'Table not found'}), 404
        
        col_names = [c['column_name'] for c in columns]
        
        # دریافت داده‌ها
        rows = db.execute(f'SELECT * FROM "{table_name}" ORDER BY id DESC LIMIT %s', (limit,))
        
        if format_type == 'csv':
            output = io.StringIO()
            writer = csv.DictWriter(output, fieldnames=col_names)
            writer.writeheader()
            writer.writerows(rows)
            output.seek(0)
            return send_file(
                io.BytesIO(output.getvalue().encode('utf-8')),
                as_attachment=True,
                download_name=f'{table_name}_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv',
                mimetype='text/csv'
            )
        
        # JSON
        return jsonify({
            'success': True,
            'data': {
                'table': table_name,
                'columns': col_names,
                'rows': rows,
                'count': len(rows),
                'exported_at': datetime.now().isoformat()
            }
        })
    except Exception as e:
        logger.error(f"PostgreSQL export error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/db/postgresql/backup', methods=['GET'])
@require_auth('admin')
def postgresql_backup():
    """بک‌آپ کامل PostgreSQL (دانلود فایل SQL)"""
    try:
        import subprocess
        import tempfile
        
        # دریافت تنظیمات دیتابیس از محیط
        db_name = os.getenv('POSTGRES_DB', 'trading')
        db_user = os.getenv('POSTGRES_USER', 'postgres')
        db_host = os.getenv('POSTGRES_HOST', 'localhost')
        db_port = os.getenv('POSTGRES_PORT', '5432')
        
        # ایجاد فایل موقت
        with tempfile.NamedTemporaryFile(delete=False, suffix='.sql') as tmp:
            tmp_path = tmp.name
        
        # اجرای pg_dump
        cmd = f'pg_dump -h {db_host} -p {db_port} -U {db_user} -d {db_name} -f {tmp_path}'
        try:
            subprocess.run(cmd, shell=True, check=True, capture_output=True)
        except subprocess.CalledProcessError as e:
            logger.error(f"pg_dump failed: {e.stderr}")
            return jsonify({'success': False, 'error': 'Backup failed'}), 500
        
        return send_file(
            tmp_path,
            as_attachment=True,
            download_name=f'postgresql_backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.sql',
            mimetype='application/sql'
        )
    except Exception as e:
        logger.error(f"PostgreSQL backup error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================
# ۶. دیتابیس - Redis
# ============================================================

@api_bp.route('/db/redis/keys', methods=['GET'])
@require_auth()
def redis_keys():
    """دریافت کلیدهای Redis با جزئیات کامل و قابلیت جستجو"""
    try:
        cache = get_cache()
        if not cache or not cache.is_connected():
            return jsonify({'success': False, 'error': 'Redis not connected'}), 503
        
        pattern = request.args.get('pattern', '*')
        limit = request.args.get('limit', 100, type=int)
        search = request.args.get('search', '')
        
        # دریافت کلیدها
        keys = cache._client.keys(pattern)
        
        # فیلتر بر اساس جستجو
        if search:
            keys = [k for k in keys if search.lower() in (k.decode('utf-8') if isinstance(k, bytes) else k).lower()]
        
        keys = keys[:limit]
        
        result = []
        for key in keys:
            key_str = key.decode('utf-8') if isinstance(key, bytes) else key
            key_type = cache._client.type(key)
            type_str = key_type.decode('utf-8') if isinstance(key_type, bytes) else key_type
            ttl = cache._client.ttl(key)
            
            # دریافت مقدار (برای نمایش)
            value = None
            try:
                if type_str == 'string':
                    val = cache._client.get(key)
                    value = val.decode('utf-8') if isinstance(val, bytes) else val
                elif type_str == 'hash':
                    val = cache._client.hgetall(key)
                    value = {k.decode('utf-8') if isinstance(k, bytes) else k: 
                            v.decode('utf-8') if isinstance(v, bytes) else v 
                            for k, v in val.items()}
                elif type_str == 'list':
                    val = cache._client.lrange(key, 0, 10)
                    value = [v.decode('utf-8') if isinstance(v, bytes) else v for v in val]
                elif type_str == 'set':
                    val = cache._client.smembers(key)
                    value = [v.decode('utf-8') if isinstance(v, bytes) else v for v in list(val)[:10]]
                elif type_str == 'zset':
                    val = cache._client.zrange(key, 0, 10, withscores=True)
                    value = [{v.decode('utf-8') if isinstance(v, bytes) else v: score} for v, score in val]
            except:
                value = '—'
            
            result.append({
                'key': key_str,
                'type': type_str,
                'ttl': f'{ttl}s' if ttl > 0 else '∞' if ttl == -1 else 'expired',
                'value': value,
                'size': len(key_str) + (len(str(value)) if value else 0)
            })
        
        info = cache._client.info()
        
        return jsonify({
            'success': True,
            'data': result,
            'count': len(result),
            'stats': {
                'memory': info.get('used_memory_human', '—'),
                'clients': info.get('connected_clients', '—'),
                'total_keys': info.get('db0', {}).get('keys', 0),
                'uptime': info.get('uptime_in_seconds', 0),
                'hit_rate': info.get('keyspace_hits', 0) / (info.get('keyspace_hits', 0) + info.get('keyspace_misses', 1)) * 100
            }
        })
    except Exception as e:
        logger.error(f"Redis keys error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/db/redis/key/<path:key>', methods=['GET'])
@require_auth()
def redis_get_key(key):
    """دریافت مقدار یک کلید خاص Redis"""
    try:
        cache = get_cache()
        if not cache or not cache.is_connected():
            return jsonify({'success': False, 'error': 'Redis not connected'}), 503
        
        # دریافت نوع کلید
        key_type = cache._client.type(key)
        type_str = key_type.decode('utf-8') if isinstance(key_type, bytes) else key_type
        
        # دریافت مقدار بر اساس نوع
        value = None
        if type_str == 'string':
            val = cache._client.get(key)
            value = val.decode('utf-8') if isinstance(val, bytes) else val
        elif type_str == 'hash':
            val = cache._client.hgetall(key)
            value = {k.decode('utf-8') if isinstance(k, bytes) else k: 
                    v.decode('utf-8') if isinstance(v, bytes) else v 
                    for k, v in val.items()}
        elif type_str == 'list':
            val = cache._client.lrange(key, 0, 50)
            value = [v.decode('utf-8') if isinstance(v, bytes) else v for v in val]
        elif type_str == 'set':
            val = cache._client.smembers(key)
            value = [v.decode('utf-8') if isinstance(v, bytes) else v for v in list(val)[:50]]
        elif type_str == 'zset':
            val = cache._client.zrange(key, 0, 50, withscores=True)
            value = [{v.decode('utf-8') if isinstance(v, bytes) else v: score} for v, score in val]
        else:
            value = 'Unsupported type'
        
        # دریافت TTL
        ttl = cache._client.ttl(key)
        
        return jsonify({
            'success': True,
            'data': {
                'key': key,
                'type': type_str,
                'value': value,
                'ttl': ttl if ttl > 0 else None
            }
        })
    except Exception as e:
        logger.error(f"Redis get key error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/db/redis/stats', methods=['GET'])
@require_auth()
def redis_stats():
    """دریافت آمار کامل Redis"""
    try:
        cache = get_cache()
        if not cache or not cache.is_connected():
            return jsonify({'success': False, 'error': 'Redis not connected'}), 503
        
        info = cache._client.info()
        
        return jsonify({
            'success': True,
            'data': {
                'memory': {
                    'used': info.get('used_memory_human', '—'),
                    'peak': info.get('used_memory_peak_human', '—'),
                    'rss': info.get('used_memory_rss_human', '—'),
                    'max': info.get('maxmemory_human', '—')
                },
                'clients': {
                    'connected': info.get('connected_clients', 0),
                    'blocked': info.get('blocked_clients', 0),
                    'max': info.get('maxclients', 10000)
                },
                'keys': {
                    'total': info.get('db0', {}).get('keys', 0),
                    'expires': info.get('db0', {}).get('expires', 0),
                    'avg_ttl': info.get('db0', {}).get('avg_ttl', 0)
                },
                'performance': {
                    'hit_rate': info.get('keyspace_hits', 0) / (info.get('keyspace_hits', 0) + info.get('keyspace_misses', 1)) * 100,
                    'commands_processed': info.get('total_commands_processed', 0),
                    'connections_received': info.get('total_connections_received', 0)
                },
                'uptime': info.get('uptime_in_seconds', 0),
                'connected': True,
                'timestamp': datetime.now().isoformat()
            }
        })
    except Exception as e:
        logger.error(f"Redis stats error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/db/redis/clear', methods=['DELETE'])
@require_auth('admin')
def redis_clear():
    """پاک کردن همه کلیدهای Redis (با تأیید)"""
    try:
        confirm = request.args.get('confirm', 'false').lower() == 'true'
        if not confirm:
            return jsonify({
                'success': False, 
                'error': 'Confirmation required. Use ?confirm=true'
            }), 400
        
        cache = get_cache()
        if not cache or not cache.is_connected():
            return jsonify({'success': False, 'error': 'Redis not connected'}), 503
        
        key_count = len(cache._client.keys('*'))
        cache._client.flushdb()
        
        return jsonify({
            'success': True, 
            'message': f'Redis cache cleared. {key_count} keys deleted.'
        })
    except Exception as e:
        logger.error(f"Redis clear error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================
# ۷. دیتابیس - SQLite
# ============================================================

@api_bp.route('/db/sqlite/tables', methods=['GET'])
@require_auth()
def sqlite_tables():
    """دریافت جدول‌های SQLite با تعداد رکوردها و آخرین بروزرسانی"""
    try:
        sqlite = get_backup()
        if not sqlite or not sqlite.is_connected():
            return jsonify({'success': False, 'error': 'SQLite not connected'}), 503
        
        tables = sqlite.execute("""
            SELECT name as table_name 
            FROM sqlite_master 
            WHERE type='table' 
            AND name NOT LIKE 'sqlite_%'
            ORDER BY name
        """)
        
        for table in tables:
            try:
                count = sqlite.execute(
                    f"SELECT COUNT(*) as count FROM [{table['table_name']}]"
                )
                table['row_count'] = count[0]['count'] if count else 0
            except:
                table['row_count'] = 0
            
            # آخرین بروزرسانی (اگر ستون created_at یا updated_at وجود داشته باشد)
            try:
                update = sqlite.execute(
                    f"SELECT MAX(created_at) as last_update FROM [{table['table_name']}]"
                )
                table['last_update'] = update[0]['last_update'] if update else None
            except:
                table['last_update'] = None
        
        return jsonify({
            'success': True,
            'data': tables,
            'count': len(tables)
        })
    except Exception as e:
        logger.error(f"SQLite tables error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/db/sqlite/table/<table_name>', methods=['GET'])
@require_auth()
def sqlite_table_data(table_name):
    """دریافت داده‌های یک جدول خاص SQLite"""
    try:
        sqlite = get_backup()
        if not sqlite or not sqlite.is_connected():
            return jsonify({'success': False, 'error': 'SQLite not connected'}), 503
        
        limit = request.args.get('limit', 100, type=int)
        offset = request.args.get('offset', 0, type=int)
        search = request.args.get('search', '')
        format_type = request.args.get('format', 'json')
        
        # دریافت اطلاعات ستون‌ها
        pragma = sqlite.execute(f"PRAGMA table_info({table_name})")
        if not pragma:
            return jsonify({'success': False, 'error': 'Table not found'}), 404
        
        col_names = [c['name'] for c in pragma]
        
        # ساخت کوئری
        query = f'SELECT * FROM [{table_name}]'
        params = []
        
        if search:
            search_conditions = []
            for col in col_names:
                if col not in ['id', 'created_at', 'updated_at']:
                    search_conditions.append(f'"{col}" LIKE ?')
                    params.append(f'%{search}%')
            
            if search_conditions:
                query += ' WHERE ' + ' OR '.join(search_conditions)
        
        query += ' ORDER BY id DESC LIMIT ? OFFSET ?'
        params.extend([limit, offset])
        
        rows = sqlite.execute(query, tuple(params))
        
        # تعداد کل
        count_query = f'SELECT COUNT(*) as total FROM [{table_name}]'
        count_params = []
        if search:
            count_query += ' WHERE ' + ' OR '.join(search_conditions)
            count_params = [f'%{search}%'] * len(search_conditions) if search_conditions else []
        
        total_result = sqlite.execute(count_query, tuple(count_params))
        total = total_result[0]['total'] if total_result else 0
        
        if format_type == 'csv':
            output = io.StringIO()
            writer = csv.DictWriter(output, fieldnames=col_names)
            writer.writeheader()
            writer.writerows(rows)
            output.seek(0)
            return send_file(
                io.BytesIO(output.getvalue().encode('utf-8')),
                as_attachment=True,
                download_name=f'{table_name}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv',
                mimetype='text/csv'
            )
        
        return jsonify({
            'success': True,
            'data': {
                'table': table_name,
                'columns': col_names,
                'rows': rows,
                'total': total,
                'limit': limit,
                'offset': offset,
                'has_more': (offset + limit) < total
            }
        })
    except Exception as e:
        logger.error(f"SQLite table data error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/db/sqlite/stats', methods=['GET'])
@require_auth()
def sqlite_stats():
    """دریافت آمار SQLite"""
    try:
        sqlite = get_backup()
        if not sqlite or not sqlite.is_connected():
            return jsonify({'success': False, 'error': 'SQLite not connected'}), 503
        
        # تعداد جدول‌ها
        tables = sqlite.execute("""
            SELECT COUNT(*) as count 
            FROM sqlite_master 
            WHERE type='table' AND name NOT LIKE 'sqlite_%'
        """)
        
        # حجم فایل
        import os
        db_path = os.path.join(os.path.dirname(__file__), '../../data/trading.db')
        size_bytes = os.path.getsize(db_path) if os.path.exists(db_path) else 0
        
        # تعداد کل رکوردها
        total_rows = 0
        table_list = sqlite.execute("""
            SELECT name as table_name 
            FROM sqlite_master 
            WHERE type='table' AND name NOT LIKE 'sqlite_%'
        """)
        for t in table_list:
            try:
                count = sqlite.execute(f'SELECT COUNT(*) as count FROM [{t["table_name"]}]')
                total_rows += count[0]['count'] if count else 0
            except:
                pass
        
        return jsonify({
            'success': True,
            'data': {
                'table_count': tables[0]['count'] if tables else 0,
                'total_rows': total_rows,
                'size_bytes': size_bytes,
                'size_mb': round(size_bytes / 1024 / 1024, 2),
                'connected': True,
                'timestamp': datetime.now().isoformat()
            }
        })
    except Exception as e:
        logger.error(f"SQLite stats error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/db/sqlite/export/<table_name>', methods=['GET'])
@require_auth()
def sqlite_export(table_name):
    """خروجی کامل یک جدول SQLite (CSV/JSON)"""
    try:
        format_type = request.args.get('format', 'csv')
        limit = request.args.get('limit', 10000, type=int)
        
        sqlite = get_backup()
        if not sqlite or not sqlite.is_connected():
            return jsonify({'success': False, 'error': 'SQLite not connected'}), 503
        
        # دریافت ستون‌ها
        pragma = sqlite.execute(f"PRAGMA table_info({table_name})")
        if not pragma:
            return jsonify({'success': False, 'error': 'Table not found'}), 404
        
        col_names = [c['name'] for c in pragma]
        
        rows = sqlite.execute(f'SELECT * FROM [{table_name}] ORDER BY id DESC LIMIT ?', (limit,))
        
        if format_type == 'csv':
            output = io.StringIO()
            writer = csv.DictWriter(output, fieldnames=col_names)
            writer.writeheader()
            writer.writerows(rows)
            output.seek(0)
            return send_file(
                io.BytesIO(output.getvalue().encode('utf-8')),
                as_attachment=True,
                download_name=f'{table_name}_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv',
                mimetype='text/csv'
            )
        
        return jsonify({
            'success': True,
            'data': {
                'table': table_name,
                'columns': col_names,
                'rows': rows,
                'count': len(rows),
                'exported_at': datetime.now().isoformat()
            }
        })
    except Exception as e:
        logger.error(f"SQLite export error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

@api_bp.route('/db/monitor', methods=['GET'])
@require_auth()
def db_monitor():
    """دریافت داده‌های مانیتورینگ دیتابیس‌ها با Health Score"""
    try:
        import time
        import psutil
        
        result = {}
        
        # ===== PostgreSQL =====
        try:
            pg = get_primary()
            if pg and pg.is_connected():
                # تست زمان پاسخ‌دهی
                start = time.time()
                pg.execute("SELECT 1")
                ping_ms = round((time.time() - start) * 1000, 1)
                
                # دریافت آمار
                tables = pg.execute("""
                    SELECT COUNT(*) as count 
                    FROM information_schema.tables 
                    WHERE table_schema = 'public'
                """)
                table_count = tables[0]['count'] if tables else 0
                
                size = pg.execute("""
                    SELECT pg_database_size(current_database()) / 1024 / 1024 as size_mb
                """)
                size_mb = size[0]['size_mb'] if size else 0
                
                rows = 0
                if table_count > 0:
                    table_list = pg.execute("""
                        SELECT table_name 
                        FROM information_schema.tables 
                        WHERE table_schema = 'public'
                    """)
                    for t in table_list:
                        try:
                            count = pg.execute(f'SELECT COUNT(*) as count FROM "{t["table_name"]}"')
                            rows += count[0]['count'] if count else 0
                        except:
                            pass
                
                # Health Score
                health_score = 0
                if ping_ms < 10:
                    health_score += 40
                elif ping_ms < 50:
                    health_score += 30
                elif ping_ms < 100:
                    health_score += 20
                else:
                    health_score += 10
                
                if table_count > 10:
                    health_score += 30
                elif table_count > 5:
                    health_score += 20
                elif table_count > 0:
                    health_score += 10
                
                if size_mb < 100:
                    health_score += 30
                elif size_mb < 500:
                    health_score += 20
                elif size_mb < 1000:
                    health_score += 10
                
                result['postgresql'] = {
                    'status': 'connected',
                    'ping_ms': ping_ms,
                    'tables': table_count,
                    'size_mb': round(size_mb, 2),
                    'rows': rows,
                    'health_score': min(health_score, 100),
                    'version': pg._connection.info.server_version if hasattr(pg._connection, 'info') else 'unknown'
                }
            else:
                result['postgresql'] = {
                    'status': 'disconnected',
                    'ping_ms': None,
                    'tables': 0,
                    'size_mb': 0,
                    'rows': 0,
                    'health_score': 0,
                    'version': 'unknown'
                }
        except Exception as e:
            logger.error(f"PostgreSQL monitor error: {e}")
            result['postgresql'] = {
                'status': 'error',
                'ping_ms': None,
                'tables': 0,
                'size_mb': 0,
                'rows': 0,
                'health_score': 0,
                'version': 'unknown',
                'error': str(e)
            }
        
        # ===== Redis =====
        try:
            redis = get_cache()
            if redis and redis.is_connected():
                start = time.time()
                redis._client.ping()
                ping_ms = round((time.time() - start) * 1000, 1)
                
                info = redis._client.info()
                keys = info.get('db0', {}).get('keys', 0)
                memory = info.get('used_memory_human', '0B')
                memory_bytes = info.get('used_memory', 0)
                clients = info.get('connected_clients', 0)
                
                # Health Score
                health_score = 0
                if ping_ms < 5:
                    health_score += 40
                elif ping_ms < 20:
                    health_score += 30
                elif ping_ms < 50:
                    health_score += 20
                else:
                    health_score += 10
                
                if keys > 100:
                    health_score += 30
                elif keys > 50:
                    health_score += 20
                elif keys > 0:
                    health_score += 10
                
                if clients < 10:
                    health_score += 30
                elif clients < 50:
                    health_score += 20
                else:
                    health_score += 10
                
                result['redis'] = {
                    'status': 'connected',
                    'ping_ms': ping_ms,
                    'keys': keys,
                    'memory_mb': round(memory_bytes / (1024 * 1024), 2),
                    'memory_human': memory,
                    'clients': clients,
                    'health_score': min(health_score, 100),
                    'version': info.get('redis_version', 'unknown')
                }
            else:
                result['redis'] = {
                    'status': 'disconnected',
                    'ping_ms': None,
                    'keys': 0,
                    'memory_mb': 0,
                    'memory_human': '0B',
                    'clients': 0,
                    'health_score': 0,
                    'version': 'unknown'
                }
        except Exception as e:
            logger.error(f"Redis monitor error: {e}")
            result['redis'] = {
                'status': 'error',
                'ping_ms': None,
                'keys': 0,
                'memory_mb': 0,
                'memory_human': '0B',
                'clients': 0,
                'health_score': 0,
                'version': 'unknown',
                'error': str(e)
            }
        
        # ===== SQLite =====
        try:
            sqlite = get_backup()
            if sqlite and sqlite.is_connected():
                start = time.time()
                sqlite.execute("SELECT 1")
                ping_ms = round((time.time() - start) * 1000, 1)
                
                tables = sqlite.execute("""
                    SELECT name as table_name 
                    FROM sqlite_master 
                    WHERE type='table' AND name NOT LIKE 'sqlite_%'
                """)
                table_count = len(tables)
                
                rows = 0
                for t in tables:
                    try:
                        count = sqlite.execute(f'SELECT COUNT(*) as count FROM [{t["table_name"]}]')
                        rows += count[0]['count'] if count else 0
                    except:
                        pass
                
                import os
                db_path = os.path.join(os.path.dirname(__file__), '../../data/trading.db')
                size_bytes = os.path.getsize(db_path) if os.path.exists(db_path) else 0
                size_mb = round(size_bytes / (1024 * 1024), 2)
                
                # Health Score
                health_score = 0
                if ping_ms < 10:
                    health_score += 40
                elif ping_ms < 50:
                    health_score += 30
                elif ping_ms < 100:
                    health_score += 20
                else:
                    health_score += 10
                
                if table_count > 5:
                    health_score += 30
                elif table_count > 0:
                    health_score += 20
                
                if size_mb < 10:
                    health_score += 30
                elif size_mb < 50:
                    health_score += 20
                elif size_mb < 100:
                    health_score += 10
                
                result['sqlite'] = {
                    'status': 'connected',
                    'ping_ms': ping_ms,
                    'tables': table_count,
                    'size_mb': size_mb,
                    'rows': rows,
                    'health_score': min(health_score, 100),
                    'version': 'SQLite 3'
                }
            else:
                result['sqlite'] = {
                    'status': 'disconnected',
                    'ping_ms': None,
                    'tables': 0,
                    'size_mb': 0,
                    'rows': 0,
                    'health_score': 0,
                    'version': 'unknown'
                }
        except Exception as e:
            logger.error(f"SQLite monitor error: {e}")
            result['sqlite'] = {
                'status': 'error',
                'ping_ms': None,
                'tables': 0,
                'size_mb': 0,
                'rows': 0,
                'health_score': 0,
                'version': 'unknown',
                'error': str(e)
            }
        
        # ===== آمار کلی =====
        total_health = 0
        connected_count = 0
        for db in result.values():
            if db.get('status') == 'connected':
                connected_count += 1
                total_health += db.get('health_score', 0)
        
        avg_health = round(total_health / connected_count, 1) if connected_count > 0 else 0
        
        return jsonify({
            'success': True,
            'data': {
                'databases': result,
                'summary': {
                    'total': len(result),
                    'connected': connected_count,
                    'disconnected': len(result) - connected_count,
                    'avg_health_score': avg_health,
                    'timestamp': datetime.now().isoformat()
                }
            }
        })
    except Exception as e:
        logger.error(f"DB monitor error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500
        
# ============================================================
# ۸. دیتابیس - عمومی
# ============================================================

@api_bp.route('/db/search', methods=['GET'])
@require_auth()
def database_search():
    """جستجوی یکپارچه در همه جدول‌ها با نمایش کامل نتایج"""
    try:
        query = request.args.get('q', '').strip()
        if not query or len(query) < 2:
            return jsonify({'success': False, 'error': 'Search term too short (min 2 chars)'}), 400
        
        db = get_primary()
        if not db or not db.is_connected():
            return jsonify({'success': False, 'error': 'Database not connected'}), 503
        
        # دریافت لیست جدول‌ها
        tables_result = db.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public'
            ORDER BY table_name
        """)
        tables = [r['table_name'] for r in tables_result]
        
        results = []
        for table in tables:
            try:
                # دریافت ستون‌های متنی
                columns = db.execute("""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name = %s 
                    AND data_type IN ('text', 'varchar', 'char', 'character varying', 'json', 'jsonb')
                """, (table,))
                
                if not columns:
                    continue
                
                col_names = [c['column_name'] for c in columns]
                
                # ساخت شرط LIKE برای همه ستون‌ها
                like_conditions = ' OR '.join([f'"{c}"::text ILIKE %s' for c in col_names])
                search_query = f'SELECT * FROM "{table}" WHERE {like_conditions} LIMIT 20'
                params = [f'%{query}%'] * len(col_names)
                
                rows = db.execute(search_query, tuple(params))
                
                if rows:
                    # اضافه کردن نام ستون‌ها به نتیجه
                    results.append({
                        'table': table,
                        'columns': col_names,
                        'rows': rows,
                        'count': len(rows)
                    })
            except Exception as e:
                logger.warning(f"Search error in table {table}: {e}")
                continue
        
        return jsonify({
            'success': True,
            'data': results,
            'total': sum(r['count'] for r in results),
            'query': query
        })
    except Exception as e:
        logger.error(f"Database search error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/db/health', methods=['GET'])
@require_auth()
def database_health():
    """دریافت وضعیت سلامت همه دیتابیس‌ها"""
    try:
        health = health_check()
        return jsonify({
            'success': True,
            'data': health,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"Database health error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/db/query', methods=['POST'])
@require_auth()
def database_query():
    """اجرای کوئری SELECT روی دیتابیس (فقط SELECT و CREATE TABLE)"""
    try:
        data = request.json
        query_text = data.get('query', '').strip()
        
        if not query_text:
            return jsonify({'success': False, 'error': 'Query is required'}), 400
        
        query_upper = query_text.upper().strip()
        allowed = ['SELECT', 'CREATE TABLE', 'PRAGMA', 'EXPLAIN']
        if not any(query_upper.startswith(a) for a in allowed):
            return jsonify({
                'success': False,
                'error': f'Only {", ".join(allowed)} queries are allowed'
            }), 403
        
        db = get_primary()
        if not db or not db.is_connected():
            return jsonify({'success': False, 'error': 'Database not available'}), 503
        
        result = db.execute(query_text)
        
        return jsonify({
            'success': True,
            'data': {
                'rows': result,
                'count': len(result) if result else 0,
                'query': query_text
            }
        })
    except Exception as e:
        logger.error(f"Database query error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/db/tables', methods=['GET'])
@require_auth()
def db_tables():
    """دریافت لیست همه جدول‌ها با اطلاعات کامل"""
    try:
        db = get_primary()
        if not db or not db.is_connected():
            return jsonify({'success': False, 'error': 'Database not connected'}), 503
        
        result = db.execute("""
            SELECT 
                table_name,
                (SELECT COUNT(*) FROM information_schema.tables WHERE table_name = t.table_name) as row_count
            FROM information_schema.tables t
            WHERE table_schema = 'public'
            ORDER BY table_name
        """)
        
        for table in result:
            size_result = db.execute(f"""
                SELECT pg_total_relation_size('{table['table_name']}') / 1024 / 1024 as size_mb
            """)
            table['size_mb'] = size_result[0]['size_mb'] if size_result else 0
        
        return jsonify({
            'success': True,
            'data': result
        })
    except Exception as e:
        logger.error(f"DB tables error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/db/stats', methods=['GET'])
@require_auth()
def db_stats():
    """دریافت آمار کلی دیتابیس"""
    try:
        db = get_primary()
        if not db or not db.is_connected():
            return jsonify({'success': False, 'error': 'Database not connected'}), 503
        
        # تعداد جدول‌ها
        tables = db.execute("""
            SELECT COUNT(*) as table_count 
            FROM information_schema.tables 
            WHERE table_schema = 'public'
        """)
        
        # حجم کل دیتابیس
        size = db.execute("""
            SELECT 
                pg_database_size(current_database()) / 1024 / 1024 as total_size_mb,
                pg_database_size(current_database()) as total_size_bytes
        """)
        
        return jsonify({
            'success': True,
            'data': {
                'table_count': tables[0]['table_count'] if tables else 0,
                'total_size_mb': size[0]['total_size_mb'] if size else 0,
                'total_size_bytes': size[0]['total_size_bytes'] if size else 0
            }
        })
    except Exception as e:
        logger.error(f"DB stats error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

# ============================================================
# اضافه کردن به api_routes.py - بخش دیتابیس
# ============================================================

@api_bp.route('/db/postgresql/table/<table_name>/export/row/<int:row_id>', methods=['GET'])
@require_auth()
def export_postgresql_row(table_name, row_id):
    """خروجی یک رکورد خاص از جدول PostgreSQL (JSON/CSV)"""
    try:
        db = get_primary()
        if not db or not db.is_connected():
            return jsonify({'success': False, 'error': 'PostgreSQL not connected'}), 503
        
        format_type = request.args.get('format', 'json')
        
        # دریافت ستون‌ها
        columns = db.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = %s
            ORDER BY ordinal_position
        """, (table_name,))
        
        if not columns:
            return jsonify({'success': False, 'error': 'Table not found'}), 404
        
        col_names = [c['column_name'] for c in columns]
        
        # دریافت رکورد
        row = db.execute(f'SELECT * FROM "{table_name}" WHERE id = %s', (row_id,))
        if not row:
            return jsonify({'success': False, 'error': 'Row not found'}), 404
        
        if format_type == 'csv':
            output = io.StringIO()
            writer = csv.DictWriter(output, fieldnames=col_names)
            writer.writeheader()
            writer.writerow(row[0])
            output.seek(0)
            return send_file(
                io.BytesIO(output.getvalue().encode('utf-8')),
                as_attachment=True,
                download_name=f'{table_name}_row_{row_id}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv',
                mimetype='text/csv'
            )
        
        return jsonify({
            'success': True,
            'data': {
                'table': table_name,
                'row_id': row_id,
                'columns': col_names,
                'row': row[0]
            }
        })
    except Exception as e:
        logger.error(f"Export PostgreSQL row error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/db/sqlite/table/<table_name>/export/row/<int:row_id>', methods=['GET'])
@require_auth()
def export_sqlite_row(table_name, row_id):
    """خروجی یک رکورد خاص از جدول SQLite (JSON/CSV)"""
    try:
        sqlite = get_backup()
        if not sqlite or not sqlite.is_connected():
            return jsonify({'success': False, 'error': 'SQLite not connected'}), 503
        
        format_type = request.args.get('format', 'json')
        
        # دریافت ستون‌ها
        pragma = sqlite.execute(f"PRAGMA table_info({table_name})")
        if not pragma:
            return jsonify({'success': False, 'error': 'Table not found'}), 404
        
        col_names = [c['name'] for c in pragma]
        
        # دریافت رکورد
        row = sqlite.execute(f'SELECT * FROM [{table_name}] WHERE id = %s', (row_id,))
        if not row:
            return jsonify({'success': False, 'error': 'Row not found'}), 404
        
        if format_type == 'csv':
            output = io.StringIO()
            writer = csv.DictWriter(output, fieldnames=col_names)
            writer.writeheader()
            writer.writerow(row[0])
            output.seek(0)
            return send_file(
                io.BytesIO(output.getvalue().encode('utf-8')),
                as_attachment=True,
                download_name=f'{table_name}_row_{row_id}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv',
                mimetype='text/csv'
            )
        
        return jsonify({
            'success': True,
            'data': {
                'table': table_name,
                'row_id': row_id,
                'columns': col_names,
                'row': row[0]
            }
        })
    except Exception as e:
        logger.error(f"Export SQLite row error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/db/redis/key/<path:key>/export', methods=['GET'])
@require_auth()
def export_redis_key(key):
    """خروجی یک کلید Redis به صورت JSON"""
    try:
        cache = get_cache()
        if not cache or not cache.is_connected():
            return jsonify({'success': False, 'error': 'Redis not connected'}), 503
        
        key_type = cache._client.type(key)
        type_str = key_type.decode('utf-8') if isinstance(key_type, bytes) else key_type
        
        value = None
        if type_str == 'string':
            val = cache._client.get(key)
            value = val.decode('utf-8') if isinstance(val, bytes) else val
        elif type_str == 'hash':
            val = cache._client.hgetall(key)
            value = {k.decode('utf-8') if isinstance(k, bytes) else k: 
                    v.decode('utf-8') if isinstance(v, bytes) else v 
                    for k, v in val.items()}
        elif type_str == 'list':
            val = cache._client.lrange(key, 0, -1)
            value = [v.decode('utf-8') if isinstance(v, bytes) else v for v in val]
        elif type_str == 'set':
            val = cache._client.smembers(key)
            value = [v.decode('utf-8') if isinstance(v, bytes) else v for v in list(val)]
        else:
            value = 'Unsupported type'
        
        return jsonify({
            'success': True,
            'data': {
                'key': key,
                'type': type_str,
                'value': value,
                'exported_at': datetime.now().isoformat()
            }
        })
    except Exception as e:
        logger.error(f"Export Redis key error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500
        
# ============================================================
# ۹. مدل (MODEL)
# ============================================================

@api_bp.route('/model/status', methods=['GET'])
@require_auth()
def model_status():
    """دریافت وضعیت مدل فعلی"""
    try:
        container = current_app.container
        model_manager = container.model_manager()
        trainer = container.trainer()
        
        train_status = trainer.get_stats() if hasattr(trainer, 'get_stats') else {}
        
        return jsonify({
            'success': True,
            'data': {
                'loaded': model_manager.current_model is not None,
                'version': model_manager.current_version,
                'is_training': train_status.get('is_training', False),
                'total_trainings': train_status.get('stats', {}).get('total_trainings', 0),
                'last_score': train_status.get('stats', {}).get('last_score'),
                'mode': 'PRODUCTION' if model_manager.current_model else 'DEMO',
                'timestamp': datetime.now().isoformat()
            }
        })
    except Exception as e:
        logger.error(f"Model status error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/model/history', methods=['GET'])
@require_auth()
def model_history():
    """دریافت تاریخچه نسخه‌های مدل"""
    try:
        container = current_app.container
        model_manager = container.model_manager()
        limit = request.args.get('limit', 20, type=int)
        
        history = model_manager.get_version_history(limit=limit)
        return jsonify({'success': True, 'data': history})
    except Exception as e:
        logger.error(f"Model history error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/model/features', methods=['GET'])
@require_auth()
def model_features():
    """دریافت ویژگی‌های مدل"""
    try:
        container = current_app.container
        model_manager = container.model_manager()
        
        if model_manager.current_model:
            features = model_manager.config.get('features', [])
            # اضافه کردن اهمیت ویژگی‌ها (اگر موجود باشد)
            importance = model_manager.config.get('feature_importance', {})
            feature_list = []
            for f in features:
                feature_list.append({
                    'name': f,
                    'importance': importance.get(f, 0)
                })
            return jsonify({'success': True, 'data': feature_list})
        return jsonify({'success': False, 'error': 'No model loaded'}), 400
    except Exception as e:
        logger.error(f"Model features error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/model/data', methods=['GET'])
@require_auth()
def model_data():
    """دریافت داده‌های آموزشی مدل"""
    try:
        db = get_primary()
        if not db or not db.is_connected():
            return jsonify({'success': False, 'error': 'Database not connected'}), 503
        
        result = db.execute(
            "SELECT * FROM model_training_history ORDER BY created_at DESC LIMIT 50"
        )
        return jsonify({'success': True, 'data': result})
    except Exception as e:
        logger.error(f"Model data error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/model/train', methods=['POST'])
@require_auth('admin')
def model_train():
    """آموزش مدل جدید"""
    try:
        container = current_app.container
        trainer = container.trainer()
        
        data = request.json or {}
        period = data.get('period', '1m')
        coins = data.get('coins', ['bitcoin', 'ethereum'])
        incremental = data.get('incremental', False)
        
        result = trainer.train_model(period=period) if not incremental else trainer.incremental_train(period=period)
        return jsonify(result), 200 if result.get('success') else 400
    except Exception as e:
        logger.error(f"Model train error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/model/export', methods=['GET'])
@require_auth()
def model_export():
    """خروجی گرفتن از مدل (دانلود فایل .xgb)"""
    try:
        container = current_app.container
        model_manager = container.model_manager()
        
        version = request.args.get('version')
        
        if version:
            model = model_manager.get_model_by_version(version)
            if not model:
                return jsonify({'success': False, 'error': 'Model not found'}), 404
        else:
            if not model_manager.current_model:
                return jsonify({'success': False, 'error': 'No model loaded'}), 404
            model = model_manager.current_model
            version = model_manager.current_version or 'current'
        
        with tempfile.NamedTemporaryFile(delete=False, suffix='.xgb') as tmp:
            model.save_model(tmp.name)
            tmp_path = tmp.name
        
        return send_file(
            tmp_path,
            as_attachment=True,
            download_name=f'model_{version}.xgb',
            mimetype='application/octet-stream'
        )
    except Exception as e:
        logger.error(f"Model export error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/model/import', methods=['POST'])
@require_auth('admin')
def model_import():
    """واردات مدل از فایل .xgb"""
    try:
        container = current_app.container
        model_manager = container.model_manager()
        
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'No file uploaded'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'success': False, 'error': 'Empty filename'}), 400
        
        if not file.filename.endswith('.xgb'):
            return jsonify({'success': False, 'error': 'Invalid file format. Use .xgb'}), 400
        
        import xgboost as xgb
        
        with tempfile.NamedTemporaryFile(delete=False, suffix='.xgb') as tmp:
            file.save(tmp.name)
            tmp_path = tmp.name
        
        model = xgb.Booster()
        model.load_model(tmp_path)
        os.unlink(tmp_path)
        
        accuracy = request.form.get('accuracy', 0.5, type=float)
        period = request.form.get('period', '1m')
        
        result = model_manager.save_model(model, accuracy, period)
        
        if result.get('success'):
            return jsonify({
                'success': True,
                'message': 'Model imported successfully',
                'version': result.get('version')
            })
        return jsonify({'success': False, 'error': result.get('error')}), 400
    except Exception as e:
        logger.error(f"Model import error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/model/activate', methods=['POST'])
@require_auth('admin')
def model_activate():
    """فعال‌سازی یک نسخه خاص از مدل"""
    try:
        container = current_app.container
        model_manager = container.model_manager()
        
        data = request.json or {}
        version = data.get('version')
        
        if not version:
            return jsonify({'success': False, 'error': 'Version required'}), 400
        
        model = model_manager.get_model_by_version(version)
        if model:
            model_manager.current_model = model
            model_manager.current_version = version
            return jsonify({'success': True, 'message': f'Model {version} activated'})
        return jsonify({'success': False, 'error': 'Version not found'}), 404
    except Exception as e:
        logger.error(f"Model activate error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/model/delete', methods=['DELETE'])
@require_auth('admin')
def model_delete():
    """حذف یک نسخه از مدل"""
    try:
        container = current_app.container
        model_manager = container.model_manager()
        
        data = request.json or {}
        version = data.get('version')
        
        if not version:
            return jsonify({'success': False, 'error': 'Version required'}), 400
        
        if model_manager.current_version == version:
            return jsonify({'success': False, 'error': 'Cannot delete active model'}), 400
        
        db = get_primary()
        if db and db.is_connected():
            db.execute("DELETE FROM models WHERE version = %s", (version,))
            return jsonify({'success': True, 'message': f'Model {version} deleted'})
        return jsonify({'success': False, 'error': 'Database not connected'}), 503
    except Exception as e:
        logger.error(f"Model delete error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================
# ۱۰. زمان‌بندی (SCHEDULE)
# ============================================================

@api_bp.route('/schedule/status', methods=['GET'])
@require_auth()
def schedule_status():
    """دریافت وضعیت زمان‌بندی آموزش"""
    try:
        container = current_app.container
        trainer = container.trainer()
        
        stats = trainer.get_stats() if hasattr(trainer, 'get_stats') else {}
        return jsonify({
            'success': True,
            'data': {
                'is_running': stats.get('is_running', False),
                'interval_hours': stats.get('stats', {}).get('training_period', 6),
                'coins': stats.get('coins', []),
                'last_training': stats.get('stats', {}).get('last_training'),
                'period': stats.get('period', '1m'),
                'next_training': stats.get('stats', {}).get('next_training')
            }
        })
    except Exception as e:
        logger.error(f"Schedule status error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/schedule/start', methods=['POST'])
@require_auth('admin')
def schedule_start():
    """شروع زمان‌بندی آموزش خودکار"""
    try:
        container = current_app.container
        trainer = container.trainer()
        
        data = request.json or {}
        interval = data.get('interval', 6)
        period = data.get('period', '1m')
        coins = data.get('coins', ['bitcoin', 'ethereum'])
        incremental = data.get('incremental', True)
        
        result = trainer.start_auto_train(
            interval_hours=interval,
            period=period,
            incremental=incremental
        )
        return jsonify(result), 200 if result.get('success') else 400
    except Exception as e:
        logger.error(f"Schedule start error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/schedule/stop', methods=['POST'])
@require_auth('admin')
def schedule_stop():
    """توقف زمان‌بندی آموزش خودکار"""
    try:
        container = current_app.container
        trainer = container.trainer()
        
        result = trainer.stop_auto_train()
        return jsonify(result), 200 if result.get('success') else 400
    except Exception as e:
        logger.error(f"Schedule stop error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================
# ۱۱. پیش‌بینی (PREDICTIONS)
# ============================================================

@api_bp.route('/predict/single', methods=['GET'])
def predict_single():
    """پیش‌بینی برای یک ارز"""
    try:
        coin = request.args.get('coin', 'bitcoin')
        period = request.args.get('period', '24h')
        
        container = current_app.container
        prediction_service: PredictionService = container.prediction_service()
        dto = prediction_service.predict_single(coin, period)
        
        return jsonify({
            'success': dto.success,
            'data': dto.data,
            'error': dto.error,
            'timestamp': datetime.now().isoformat()
        }), 200 if dto.success else 400
    except Exception as e:
        logger.error(f"Predict single error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/predict/multiple', methods=['POST'])
def predict_multiple():
    """پیش‌بینی برای چند ارز"""
    try:
        data = request.json
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400
        
        coins = data.get('coins', [])
        period = data.get('period', '24h')
        
        if not coins:
            return jsonify({'success': False, 'error': 'No coins provided'}), 400
        
        container = current_app.container
        prediction_service: PredictionService = container.prediction_service()
        dto = prediction_service.predict_multiple(coins, period)
        
        return jsonify({
            'success': dto.success,
            'data': dto.data,
            'count': dto.count,
            'error': dto.error,
            'timestamp': datetime.now().isoformat()
        }), 200 if dto.success else 400
    except Exception as e:
        logger.error(f"Predict multiple error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/predict/explain', methods=['GET'])
@require_auth()
def predict_explain():
    """توضیح پیش‌بینی (Feature Importance)"""
    try:
        coin = request.args.get('coin', 'bitcoin')
        
        return jsonify({
            'success': True,
            'data': {
                'coin': coin,
                'message': 'Feature importance explanation',
                'features': [
                    {'name': 'price_change_24h', 'importance': 0.25},
                    {'name': 'volume_24h', 'importance': 0.20},
                    {'name': 'fear_greed_index', 'importance': 0.15},
                    {'name': 'btc_dominance', 'importance': 0.12},
                    {'name': 'rsi_14', 'importance': 0.10},
                    {'name': 'moving_average_50', 'importance': 0.08},
                    {'name': 'volatility', 'importance': 0.06},
                    {'name': 'social_volume', 'importance': 0.04},
                ]
            }
        })
    except Exception as e:
        logger.error(f"Predict explain error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================
# ۱۲. کوین‌استتس (COINSTATS)
# ============================================================

@api_bp.route('/coinstats/price/<coin>', methods=['GET'])
@require_auth()
def coinstats_price(coin):
    """دریافت قیمت یک ارز خاص"""
    try:
        container = current_app.container
        api_client = container.api_client()
        data = api_client.get_coin(coin)
        
        if data:
            return jsonify({
                'success': True,
                'data': {
                    'coin': coin,
                    'price': data.get('price', 0),
                    'change_24h': data.get('priceChange1d', 0),
                    'market_cap': data.get('marketCap', 0),
                    'volume_24h': data.get('volume24h', 0),
                    'high_24h': data.get('high24h', 0),
                    'low_24h': data.get('low24h', 0),
                    'timestamp': datetime.now().isoformat()
                }
            })
        return jsonify({'success': False, 'error': 'Coin not found'}), 404
    except Exception as e:
        logger.error(f"CoinStats price error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/coinstats/prices', methods=['GET'])
@require_auth()
def coinstats_prices():
    """دریافت قیمت‌های اصلی (BTC, ETH)"""
    try:
        container = current_app.container
        api_client = container.api_client()
        
        btc = api_client.get_coin("bitcoin")
        eth = api_client.get_coin("ethereum")
        
        return jsonify({
            'success': True,
            'data': {
                'btc': {
                    'price': btc.get('price', 0) if btc else 0,
                    'change_24h': btc.get('priceChange1d', 0) if btc else 0,
                    'market_cap': btc.get('marketCap', 0) if btc else 0
                } if btc else {},
                'eth': {
                    'price': eth.get('price', 0) if eth else 0,
                    'change_24h': eth.get('priceChange1d', 0) if eth else 0,
                    'market_cap': eth.get('marketCap', 0) if eth else 0
                } if eth else {},
                'timestamp': datetime.now().isoformat()
            }
        })
    except Exception as e:
        logger.error(f"CoinStats prices error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/coinstats/fear-greed', methods=['GET'])
@require_auth()
def coinstats_fear_greed():
    """دریافت شاخص ترس و طمع"""
    try:
        container = current_app.container
        api_client = container.api_client()
        fg = api_client.get_fear_greed(use_cache=True)
        
        now = fg.get('now', {})
        history = fg.get('history', [])[:10]
        
        return jsonify({
            'success': True,
            'data': {
                'value': now.get('value', 50),
                'classification': now.get('value_classification', 'Neutral'),
                'timestamp': now.get('timestamp', datetime.now().isoformat()),
                'history': history
            }
        })
    except Exception as e:
        logger.error(f"Fear-greed error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/coinstats/btc-dominance', methods=['GET'])
@require_auth()
def coinstats_btc_dominance():
    """دریافت سلطه بیت‌کوین"""
    try:
        container = current_app.container
        api_client = container.api_client()
        dominance = api_client.get_btc_dominance(use_cache=True)
        
        return jsonify({
            'success': True,
            'data': {
                'value': dominance.get('dominance', 50) if dominance else 50,
                'timestamp': datetime.now().isoformat()
            }
        })
    except Exception as e:
        logger.error(f"BTC dominance error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/coinstats/all', methods=['GET'])
@require_auth()
def coinstats_all():
    """دریافت همه داده‌های بازار در یک جا"""
    try:
        container = current_app.container
        api_client = container.api_client()
        
        btc = api_client.get_coin("bitcoin")
        eth = api_client.get_coin("ethereum")
        fg = api_client.get_fear_greed(use_cache=True)
        dominance = api_client.get_btc_dominance(use_cache=True)
        credits = api_client.get_credits()
        status = api_client.get_status()
        
        return jsonify({
            'success': True,
            'data': {
                'btc': {
                    'price': btc.get('price', 0) if btc else 0,
                    'change_24h': btc.get('priceChange1d', 0) if btc else 0
                } if btc else {},
                'eth': {
                    'price': eth.get('price', 0) if eth else 0,
                    'change_24h': eth.get('priceChange1d', 0) if eth else 0
                } if eth else {},
                'fear_greed': {
                    'value': fg.get('now', {}).get('value', 50) if fg else 50,
                    'classification': fg.get('now', {}).get('value_classification', 'Neutral') if fg else 'Neutral'
                },
                'btc_dominance': dominance.get('dominance', 50) if dominance else 50,
                'credits': credits.get('remainingCredits', 0) if credits else 0,
                'api_status': status.get('status', 'unknown') if status else 'unknown',
                'timestamp': datetime.now().isoformat()
            }
        })
    except Exception as e:
        logger.error(f"CoinStats all error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================
# ۱۳. هشدارها (ALERTS)
# ============================================================

@api_bp.route('/alerts', methods=['GET'])
@require_auth()
def get_alerts():
    """دریافت لیست هشدارها با قابلیت فیلتر"""
    try:
        limit = request.args.get('limit', 20, type=int)
        resolved = request.args.get('resolved')
        level = request.args.get('level')
        source = request.args.get('source')
        
        if resolved is not None:
            resolved = resolved.lower() == 'true'
        
        alerts = alerter.get_alerts(limit=limit, resolved=resolved)
        
        # فیلتر بر اساس سطح
        if level:
            alerts = [a for a in alerts if a.get('level', '').lower() == level.lower()]
        
        # فیلتر بر اساس منبع
        if source:
            alerts = [a for a in alerts if source.lower() in a.get('source', '').lower()]
        
        return jsonify({
            'success': True, 
            'data': alerts, 
            'count': len(alerts),
            'filters': {
                'resolved': resolved,
                'level': level,
                'source': source
            }
        })
    except Exception as e:
        logger.error(f"Alerts error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/alerts/<int:alert_id>/resolve', methods=['POST'])
@require_auth()
def resolve_alert(alert_id):
    """حل کردن یک هشدار"""
    try:
        success = alerter.resolve_alert(alert_id)
        return jsonify({'success': success})
    except Exception as e:
        logger.error(f"Resolve alert error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/alerts/resolve-all', methods=['POST'])
@require_auth('admin')
def resolve_all_alerts():
    """حل کردن همه هشدارها"""
    try:
        level = request.args.get('level')
        count = alerter.resolve_all(level=level)
        return jsonify({
            'success': True,
            'message': f'{count} alerts resolved',
            'count': count
        })
    except Exception as e:
        logger.error(f"Resolve all alerts error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================
# ۱۴. کاربر (USER)
# ============================================================

@api_bp.route('/user', methods=['GET'])
@require_auth()
def get_user_info():
    """دریافت اطلاعات کاربر فعلی"""
    try:
        from infrastructure.auth.auth_manager import get_auth
        auth = get_auth()
        
        session_id = request.cookies.get('session_id')
        if not session_id:
            return jsonify({'success': False, 'error': 'No session found'}), 401
        
        user_data = auth.get_session(session_id)
        if not user_data:
            return jsonify({'success': False, 'error': 'Invalid session'}), 401
        
        return jsonify({
            'success': True,
            'data': {
                'username': user_data.get('username', 'guest'),
                'role': user_data.get('role', 'guest'),
                'session_id': session_id,
                'login_time': user_data.get('login_time')
            }
        })
    except Exception as e:
        logger.error(f"User info error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================
# ۱۵. اعتبار (CREDITS)
# ============================================================

@api_bp.route('/credits', methods=['GET'])
@require_auth()
def credits():
    """دریافت اعتبار باقی‌مانده API"""
    try:
        container = current_app.container
        api_client = container.api_client()
        credits_data = api_client.get_credits()
        return jsonify({
            'success': True, 
            'data': credits_data,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"Credits error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================
# ۱۶. ورود (LOGIN)
# ============================================================

@api_bp.route('/login', methods=['POST'])
def api_login():
    """ورود به سیستم"""
    try:
        data = request.json
        username = data.get('username')
        password = data.get('password')
        
        if not username or not password:
            return jsonify({'success': False, 'error': 'Username and password required'}), 400
        
        from infrastructure.auth.auth_manager import get_auth
        auth = get_auth()
        result = auth.login(username, password)
        
        if result.get('success'):
            response = jsonify({
                'success': True,
                'session_id': result.get('session_id'),
                'username': result.get('username'),
                'role': result.get('role', 'guest')
            })
            # تنظیم کوکی
            response.set_cookie(
                'session_id',
                result.get('session_id'),
                max_age=86400,
                httponly=True,
                secure=True,
                samesite='Lax',
                path='/'
            )
            return response
        
        return jsonify({'success': False, 'error': 'Invalid credentials'}), 401
    except Exception as e:
        logger.error(f"Login error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================
# ۱۷. دیباگ (DEBUG)
# ============================================================

@api_bp.route('/debug/status', methods=['GET'])
@require_auth('admin')
def debug_status():
    """دریافت وضعیت سیستم (CPU, RAM, Disk, Network)"""
    try:
        import psutil
        
        return jsonify({
            'success': True,
            'data': {
                'cpu': {
                    'percent': psutil.cpu_percent(interval=0.5),
                    'cores': psutil.cpu_count(),
                    'frequency': psutil.cpu_freq().current if psutil.cpu_freq() else None,
                    'per_core': psutil.cpu_percent(interval=0.5, percpu=True)
                },
                'memory': {
                    'total': psutil.virtual_memory().total,
                    'available': psutil.virtual_memory().available,
                    'percent': psutil.virtual_memory().percent,
                    'used': psutil.virtual_memory().used,
                    'free': psutil.virtual_memory().free,
                    'swap': {
                        'total': psutil.swap_memory().total,
                        'used': psutil.swap_memory().used,
                        'percent': psutil.swap_memory().percent
                    }
                },
                'disk': {
                    'total': psutil.disk_usage('/').total,
                    'used': psutil.disk_usage('/').used,
                    'free': psutil.disk_usage('/').free,
                    'percent': psutil.disk_usage('/').percent,
                    'partitions': [
                        {'device': p.device, 'mountpoint': p.mountpoint, 'fstype': p.fstype}
                        for p in psutil.disk_partitions()
                    ]
                },
                'network': {
                    'connections': len(psutil.net_connections()),
                    'interfaces': list(psutil.net_if_addrs().keys()),
                    'io': {
                        'bytes_sent': psutil.net_io_counters().bytes_sent,
                        'bytes_recv': psutil.net_io_counters().bytes_recv,
                        'packets_sent': psutil.net_io_counters().packets_sent,
                        'packets_recv': psutil.net_io_counters().packets_recv
                    }
                },
                'timestamp': datetime.now().isoformat()
            }
        })
    except Exception as e:
        logger.error(f"Debug status error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/debug/logs', methods=['GET'])
@require_auth('admin')
def debug_logs():
    """دریافت لاگ‌های سیستم با قابلیت فیلتر"""
    try:
        limit = request.args.get('limit', 50, type=int)
        level = request.args.get('level', 'ALL')
        since = request.args.get('since')
        
        log_file = Path('logs/system.log')
        if not log_file.exists():
            return jsonify({'success': True, 'data': [], 'count': 0})
        
        with open(log_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        # فیلتر بر اساس سطح
        if level != 'ALL':
            lines = [l for l in lines if f'[{level}]' in l or f' {level} ' in l]
        
        # فیلتر بر اساس زمان
        if since:
            try:
                since_dt = datetime.fromisoformat(since)
                filtered = []
                for line in lines:
                    try:
                        time_str = line.split('[')[1].split(']')[0]
                        log_dt = datetime.fromisoformat(time_str)
                        if log_dt >= since_dt:
                            filtered.append(line)
                    except:
                        filtered.append(line)
                lines = filtered
            except:
                pass
        
        lines = lines[-limit:]
        
        return jsonify({
            'success': True,
            'data': lines,
            'count': len(lines),
            'limit': limit,
            'level': level
        })
    except Exception as e:
        logger.error(f"Debug logs error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/debug/logs/clear', methods=['DELETE'])
@require_auth('admin')
def debug_logs_clear():
    """پاک کردن لاگ‌ها"""
    try:
        confirm = request.args.get('confirm', 'false').lower() == 'true'
        if not confirm:
            return jsonify({
                'success': False,
                'error': 'Confirmation required. Use ?confirm=true'
            }), 400
        
        log_file = Path('logs/system.log')
        if log_file.exists():
            with open(log_file, 'w') as f:
                f.write('')
        
        error_file = Path('logs/errors.log')
        if error_file.exists():
            with open(error_file, 'w') as f:
                f.write('')
        
        return jsonify({'success': True, 'message': 'Logs and errors cleared'})
    except Exception as e:
        logger.error(f"Debug logs clear error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/debug/system', methods=['GET'])
@require_auth('admin')
def debug_system():
    """دریافت اطلاعات کامل سیستم"""
    try:
        import platform
        
        return jsonify({
            'success': True,
            'data': {
                'python': sys.version,
                'platform': sys.platform,
                'machine': platform.machine(),
                'processor': platform.processor(),
                'cwd': os.getcwd(),
                'environment': os.getenv('FLASK_ENV', 'development'),
                'timezone': os.getenv('TZ', 'UTC'),
                'hostname': platform.node(),
                'system': platform.system(),
                'release': platform.release(),
                'version': platform.version()
            }
        })
    except Exception as e:
        logger.error(f"Debug system error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/debug/processes', methods=['GET'])
@require_auth('admin')
def debug_processes():
    """دریافت لیست پردازش‌ها با جستجو و مرتب‌سازی"""
    try:
        import psutil
        search = request.args.get('search', '')
        sort_by = request.args.get('sort_by', 'cpu_percent')
        sort_order = request.args.get('sort_order', 'desc')
        
        processes = []
        for proc in psutil.process_iter(['pid', 'name', 'status', 'memory_percent', 'cpu_percent', 'create_time', 'username']):
            try:
                info = proc.info
                if search and search.lower() not in info.get('name', '').lower():
                    continue
                processes.append(info)
            except:
                pass
        
        # مرتب‌سازی
        reverse = sort_order == 'desc'
        if sort_by in ['pid', 'cpu_percent', 'memory_percent']:
            processes.sort(key=lambda x: x.get(sort_by, 0) or 0, reverse=reverse)
        elif sort_by == 'name':
            processes.sort(key=lambda x: x.get('name', ''), reverse=reverse)
        elif sort_by == 'status':
            processes.sort(key=lambda x: x.get('status', ''), reverse=reverse)
        
        # محدودیت
        limit = request.args.get('limit', 50, type=int)
        processes = processes[:limit]
        
        return jsonify({
            'success': True,
            'data': processes,
            'count': len(processes),
            'total': len(processes) if not search else None
        })
    except Exception as e:
        logger.error(f"Debug processes error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/debug/exec', methods=['POST'])
@require_auth('admin')
def debug_exec():
    """اجرای دستور پایتون با کتابخانه‌های بیشتر و مدیریت خطا"""
    try:
        data = request.json or {}
        command = data.get('command', '').strip()
        command_type = data.get('type', 'python')  # python یا shell
        timeout = data.get('timeout', 10)
        
        if not command:
            return jsonify({'success': False, 'error': 'Command required'}), 400
        
        # ===== اجرای دستورات Shell =====
        if command_type == 'shell':
            import subprocess
            try:
                result = subprocess.run(
                    command,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=timeout
                )
                output = result.stdout or result.stderr or '✅ Done'
                return jsonify({
                    'success': True,
                    'result': output,
                    'type': 'shell'
                })
            except subprocess.TimeoutExpired:
                return jsonify({
                    'success': False,
                    'error': f'⏱️ Command timeout after {timeout}s'
                }), 408
            except Exception as e:
                return jsonify({
                    'success': False,
                    'error': str(e)
                }), 500
        
        # ===== اجرای دستورات Python =====
        # ===== کتابخانه‌هایی که کاربر بهشون نیاز داره =====
        safe_globals = {
            '__builtins__': {
                'print': print,
                'len': len,
                'range': range,
                'list': list,
                'dict': dict,
                'str': str,
                'int': int,
                'float': float,
                'bool': bool,
                'sum': sum,
                'min': min,
                'max': max,
                'sorted': sorted,
                'enumerate': enumerate,
                'zip': zip,
                'map': map,
                'filter': filter,
                'any': any,
                'all': all,
                'isinstance': isinstance,
                'type': type,
                'hasattr': hasattr,
                'getattr': getattr,
                'setattr': setattr,
                'dir': dir,
                'help': help,
                'open': open,
                'Exception': Exception,
                'ValueError': ValueError,
                'TypeError': TypeError,
                'KeyError': KeyError,
                'IndexError': IndexError,
                '__import__': __import__,  # ← برای import
            },
        }

        # ===== اضافه کردن کتابخانه‌های استاندارد =====
        import os, sys, time, datetime, json, re, math, random
        import collections, itertools, functools, hashlib, base64
        import pprint, inspect, traceback, logging, subprocess

        safe_globals.update({
            'os': os,
            'sys': sys,
            'time': time,
            'datetime': datetime,
            'json': json,
            're': re,
            'math': math,
            'random': random,
            'collections': collections,
            'itertools': itertools,
            'functools': functools,
            'hashlib': hashlib,
            'base64': base64,
            'pprint': pprint,
            'inspect': inspect,
            'traceback': traceback,
            'logging': logging,
            'subprocess': subprocess,
        })

        # ===== تلاش برای اضافه کردن کتابخانه‌های خارجی =====
        try:
            import psutil
            safe_globals['psutil'] = psutil
        except ImportError:
            pass

        try:
            import requests
            safe_globals['requests'] = requests
        except ImportError:
            pass

        # ===== بررسی دستورات خطرناک =====
        dangerous = ['os.system', 'subprocess.run', 'exec(', 'eval(', '__import__', 'open(', 'file(']
        for kw in dangerous:
            if kw in command:
                return jsonify({
                    'success': False,
                    'error': f'🚫 Dangerous command contains "{kw}"'
                }), 403

        # ===== ذخیره خروجی =====
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        error_output = None

        try:
            # ===== اجرا با محدودیت زمان =====
            import signal
            
            def timeout_handler(signum, frame):
                raise TimeoutError("⏱️ Command execution timeout")
            
            # تنظیم timeout (فقط در سیستم‌های Unix)
            try:
                signal.signal(signal.SIGALRM, timeout_handler)
                signal.alarm(timeout)
            except:
                pass  # در سیستم‌هایی که SIGALRM ندارند (ویندوز)
            
            # اجرای دستور
            exec(command, safe_globals)
            result = sys.stdout.getvalue()
            
            # خاموش کردن alarm
            try:
                signal.alarm(0)
            except:
                pass
                
        except TimeoutError as e:
            result = f"⏱️ Timeout after {timeout}s"
        except Exception as e:
            result = f"❌ Error: {str(e)}\n{traceback.format_exc()}"
        finally:
            sys.stdout = old_stdout

        # ===== اگر نتیجه خالی بود، پیام موفقیت =====
        if not result or result.strip() == '':
            result = '✅ Done'

        return jsonify({
            'success': True,
            'result': result,
            'command': command,
            'type': 'python'
        })

    except Exception as e:
        logger.error(f"Debug exec error: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@api_bp.route('/debug/cache', methods=['GET'])
@require_auth('admin')
def debug_cache():
    """دریافت وضعیت کش (Redis)"""
    try:
        cache = get_cache()
        if not cache or not cache.is_connected():
            return jsonify({'success': False, 'error': 'Cache not available'}), 503
        
        pattern = request.args.get('pattern', '*')
        limit = request.args.get('limit', 20, type=int)
        
        keys = cache._client.keys(pattern)
        key_list = []
        for k in keys[:limit]:
            key_str = k.decode('utf-8') if isinstance(k, bytes) else k
            key_type = cache._client.type(k)
            type_str = key_type.decode('utf-8') if isinstance(key_type, bytes) else key_type
            ttl = cache._client.ttl(k)
            key_list.append({
                'key': key_str,
                'type': type_str,
                'ttl': ttl if ttl > 0 else None
            })
        
        info = cache._client.info()
        
        return jsonify({
            'success': True,
            'data': {
                'keys': key_list,
                'total_keys': len(keys),
                'connected': True,
                'memory': info.get('used_memory_human', '—'),
                'uptime': info.get('uptime_in_seconds', 0),
                'clients': info.get('connected_clients', 0)
            }
        })
    except Exception as e:
        logger.error(f"Debug cache error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/debug/cache/clear', methods=['DELETE'])
@require_auth('admin')
def debug_cache_clear():
    """پاک کردن کش (Redis)"""
    try:
        confirm = request.args.get('confirm', 'false').lower() == 'true'
        if not confirm:
            return jsonify({
                'success': False,
                'error': 'Confirmation required. Use ?confirm=true'
            }), 400
        
        cache = get_cache()
        if not cache or not cache.is_connected():
            return jsonify({'success': False, 'error': 'Cache not available'}), 503
        
        key_count = len(cache._client.keys('*'))
        cache._client.flushdb()
        
        return jsonify({
            'success': True,
            'message': f'Cache cleared. {key_count} keys deleted.'
        })
    except Exception as e:
        logger.error(f"Debug cache clear error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/debug/loglevel', methods=['POST'])
@require_auth('admin')
def debug_loglevel():
    """تغییر سطح لاگ"""
    try:
        data = request.json or {}
        level = data.get('level', 'INFO')
        
        valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if level not in valid_levels:
            return jsonify({
                'success': False,
                'error': f'Invalid log level. Valid: {", ".join(valid_levels)}'
            }), 400
        
        logging.getLogger().setLevel(getattr(logging, level))
        
        return jsonify({
            'success': True,
            'message': f'Log level set to {level}',
            'level': level
        })
    except Exception as e:
        logger.error(f"Debug loglevel error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/debug/processes/<int:pid>/kill', methods=['POST'])
@require_auth('admin')
def kill_process(pid):
    """خاتمه دادن به یک پردازش با PID"""
    try:
        import psutil
        process = psutil.Process(pid)
        process.terminate()
        return jsonify({
            'success': True,
            'message': f'Process {pid} terminated successfully'
        })
    except psutil.NoSuchProcess:
        return jsonify({'success': False, 'error': f'Process {pid} not found'}), 404
    except psutil.AccessDenied:
        return jsonify({'success': False, 'error': 'Access denied'}), 403
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/debug/processes/<int:pid>/details', methods=['GET'])
@require_auth('admin')
def process_details(pid):
    """دریافت جزئیات کامل یک پردازش"""
    try:
        import psutil
        process = psutil.Process(pid)
        
        return jsonify({
            'success': True,
            'data': {
                'pid': pid,
                'name': process.name(),
                'status': process.status(),
                'cpu_percent': process.cpu_percent(interval=0.3),
                'memory_percent': process.memory_percent(),
                'memory_rss': process.memory_info().rss,
                'memory_vms': process.memory_info().vms,
                'create_time': process.create_time(),
                'create_time_formatted': datetime.fromtimestamp(process.create_time()).isoformat(),
                'cmdline': process.cmdline(),
                'cwd': process.cwd(),
                'username': process.username(),
                'num_threads': process.num_threads(),
                'ppid': process.ppid(),
                'connections': len(process.connections()),
                'open_files': len(process.open_files()) if hasattr(process, 'open_files') else 0,
                'nice': process.nice() if hasattr(process, 'nice') else None,
                'ionice': process.ionice() if hasattr(process, 'ionice') else None,
            }
        })
    except psutil.NoSuchProcess:
        return jsonify({'success': False, 'error': f'Process {pid} not found'}), 404
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/debug/cache/search', methods=['GET'])
@require_auth('admin')
def cache_search():
    """جستجوی کلیدها در Redis با الگو"""
    try:
        cache = get_cache()
        if not cache or not cache.is_connected():
            return jsonify({'success': False, 'error': 'Cache not available'}), 503
        
        pattern = request.args.get('pattern', '*')
        limit = request.args.get('limit', 50, type=int)
        
        keys = cache._client.keys(pattern)
        keys = keys[:limit]
        
        result = []
        for k in keys:
            key_str = k.decode('utf-8') if isinstance(k, bytes) else k
            key_type = cache._client.type(k)
            type_str = key_type.decode('utf-8') if isinstance(key_type, bytes) else key_type
            ttl = cache._client.ttl(k)
            result.append({
                'key': key_str,
                'type': type_str,
                'ttl': ttl if ttl > 0 else None
            })
        
        return jsonify({
            'success': True,
            'data': result,
            'count': len(result),
            'total_matched': len(keys)
        })
    except Exception as e:
        logger.error(f"Cache search error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/debug/cache/key', methods=['DELETE'])
@require_auth('admin')
def cache_delete_key():
    """حذف یک کلید خاص از Redis"""
    try:
        cache = get_cache()
        if not cache or not cache.is_connected():
            return jsonify({'success': False, 'error': 'Cache not available'}), 503
        
        key = request.args.get('key')
        if not key:
            return jsonify({'success': False, 'error': 'Key is required'}), 400
        
        deleted = cache._client.delete(key)
        if deleted:
            return jsonify({'success': True, 'message': f'Key "{key}" deleted'})
        return jsonify({'success': False, 'error': f'Key "{key}" not found'}), 404
    except Exception as e:
        logger.error(f"Cache delete key error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/debug/cache/purge', methods=['POST'])
@require_auth('admin')
def cache_purge():
    """پاک کردن کامل حافظه Redis (MEMORY PURGE)"""
    try:
        cache = get_cache()
        if not cache or not cache.is_connected():
            return jsonify({'success': False, 'error': 'Cache not available'}), 503
        
        # اجرای FLUSHDB و MEMORY PURGE
        cache._client.flushdb()
        try:
            cache._client.execute_command('MEMORY', 'PURGE')
        except:
            pass  # بعضی نسخه‌های Redis این دستور رو ندارن
        
        return jsonify({
            'success': True, 
            'message': 'Cache cleared and memory purged'
        })
    except Exception as e:
        logger.error(f"Cache purge error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500
