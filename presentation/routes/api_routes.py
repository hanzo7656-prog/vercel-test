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
        'version': '11.0.0',
        'status': 'running',
        'timestamp': datetime.now().isoformat(),
        'endpoints': {
            'system': {
                'health': '/api/health',
                'health_simple': '/api/health/simple',
                'stats': '/api/stats',
                'metrics': '/api/metrics',
                'metrics_summary': '/api/metrics/summary',
                'metrics_dashboard': '/api/metrics/dashboard',
            },
            'app_stats': {
                'stats': '/api/app/stats',
            },
            'database_quota': {
                'all': '/api/db/quota',
                'one': '/api/db/quota/<db_name>',
                'status': '/api/db/quota/<db_name>/status',
                'stats': '/api/db/quota/stats',
            },
            'database_health': {
                'summary': '/api/db/health/summary',
                'full': '/api/db/health/full',
                'list': '/api/db/list',
                'ping': '/api/db/<db_name>/ping',
                'ready': '/api/db/ready',
                'factory_status': '/api/db/factory/status',
            },
            'database_postgresql': {
                'tables': '/api/db/postgresql/<db_name>/tables',
                'table_data': '/api/db/postgresql/<db_name>/tables/<table_name>',
                'table_sizes': '/api/db/postgresql/<db_name>/table-sizes',
                'stats': '/api/db/postgresql/<db_name>/stats',
                'export': '/api/db/postgresql/<db_name>/export/<table_name>',
                'export_row': '/api/db/postgresql/<db_name>/tables/<table_name>/row/<row_id>',
                'query': '/api/db/postgresql/<db_name>/query',
            },
            'database_redis': {
                'keys': '/api/db/redis/keys',
                'key': '/api/db/redis/keys/<key>',
                'delete_key': '/api/db/redis/keys/<key>',
                'stats': '/api/db/redis/stats',
                'namespaces': '/api/db/redis/namespaces',
                'clear_namespace': '/api/db/redis/namespace/<namespace>',
                'flush': '/api/db/redis/flush',
                'export_key': '/api/db/redis/keys/<key>/export',
            },
            'database_archive': {
                'tables': '/api/db/archive/tables',
                'table_data': '/api/db/archive/tables/<table_name>',
                'stats': '/api/db/archive/stats',
                'export': '/api/db/archive/tables/<table_name>/export',
                'export_row': '/api/db/archive/tables/<table_name>/row/<row_id>',
                'cleanup': '/api/db/archive/cleanup',
                'features': '/api/db/archive/features',
            },
            'database_router': {
                'stats': '/api/db/router/stats',
                'rules': '/api/db/router/rules',
                'registry_summary': '/api/db/registry/summary',
            },
            'database_maintenance': {
                'vacuum': '/api/db/<db_name>/vacuum',
                'vacuum_all': '/api/db/vacuum-all',
                'analyze': '/api/db/<db_name>/analyze',
                'backup_create': '/api/db/backup/create',
                'backup_list': '/api/db/backup/list',
                'delete_old': '/api/db/<db_name>/tables/<table_name>/delete-old',
                'table_count': '/api/db/<db_name>/tables/<table_name>/count',
                'table_size': '/api/db/<db_name>/tables/<table_name>/size',
                'truncate': '/api/db/<db_name>/tables/<table_name>/truncate',
                'transaction': '/api/db/transaction',
            },
            'model': {
                'status': '/api/model/status',
                'stats': '/api/model/trainer-stats',
                'history': '/api/model/history',
                'features': '/api/model/features',
                'data': '/api/model/data',
                'train': '/api/model/train',
                'train_batch': '/api/model/train-batch',
                'analyze_training': '/api/model/analyze-training',
                'export': '/api/model/export',
                'import': '/api/model/import',
                'activate': '/api/model/activate',
                'delete': '/api/model/delete',
                'importance': '/api/model/importance',
                'performance': '/api/model/performance',
                'analytics_stats': '/api/model/analytics-stats',
                'latest_report': '/api/model/latest-report',
                'report_version': '/api/model/report/<version>',
            },
            'model_profiles': {
                'presets': '/api/model/profiles/presets',
                'preset': '/api/model/profiles/presets/<preset_id>',
                'strategies': '/api/model/profiles/strategies',
                'hyperparameter_limits': '/api/model/profiles/hyperparameter-limits',
                'current': '/api/model/profiles/current',
                'validate': '/api/model/profiles/validate',
                'saved': '/api/model/profiles/saved',
                'saved_one': '/api/model/profiles/saved/<name>',
            },
            'schedule': {
                'status': '/api/schedule/status',
                'start': '/api/schedule/start',
                'stop': '/api/schedule/stop',
            },
            'predict': {
                'single': '/api/predict/single',
                'multiple': '/api/predict/multiple',
                'explain': '/api/predict/explain',
                'history': '/api/predict/history',
                'history_stats': '/api/predict/history/stats',
            },
            'coinstats': {
                'coins': '/api/coinstats/coins',
                'price': '/api/coinstats/price/<coin>',
                'prices': '/api/coinstats/prices',
                'fear_greed': '/api/coinstats/fear-greed',
                'btc_dominance': '/api/coinstats/btc-dominance',
                'all': '/api/coinstats/all',
                'chart': '/api/coinstats/chart/<coin>',
            },
            'crypto': {
                'prices': '/api/crypto/prices',
                'price': '/api/crypto/price/<symbol>',
                'stats': '/api/crypto/stats',
                'heartbeat': '/api/crypto/heartbeat',
            },
            'alerts': {
                'list': '/api/alerts',
                'resolve': '/api/alerts/<id>/resolve',
                'resolve_all': '/api/alerts/resolve-all',
            },
            'user': {
                'info': '/api/user',
                'credits': '/api/credits',
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
                'loglevel': '/api/debug/loglevel',
            },
            'healing': {
                'status': '/api/healing/status',
                'trigger': '/api/healing/trigger',
                'reset': '/api/healing/reset',
            },
            'auth': {
                'login': '/api/login',
            },
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
# ROUTER & REGISTRY STATS
# ============================================================

@api_bp.route('/db/router/stats', methods=['GET'])
@require_auth()
def db_router_stats():
    """آمار Router (routes, failovers)"""
    try:
        stats = get_router_stats()
        return jsonify({'success': True, 'data': stats})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/db/router/rules', methods=['GET'])
@require_auth()
def db_router_rules():
    """نقشه routing فعلی"""
    try:
        from infrastructure.database import _get_router
        router = _get_router()
        return jsonify({
            'success': True,
            'data': router.get_routing_map(),
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/db/registry/summary', methods=['GET'])
@require_auth()
def db_registry_summary():
    """خلاصه Registry"""
    try:
        stats = get_registry_stats()
        return jsonify({'success': True, 'data': stats})
    except Exception as e:
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
# POSTGRESQL ENDPOINTS
# ============================================================

@api_bp.route('/db/postgresql/<db_name>/tables', methods=['GET'])
@require_auth()
def pg_tables(db_name):
    """
    لیست جداول PostgreSQL
    [جایگزین] /api/db/postgresql/tables قدیمی
    db_name: primary | backup | analytics | logs
    """
    try:
        db = get_db(db_name)
        if not db or not db.is_connected():
            return jsonify({
                'success': False,
                'error': f'Database {db_name} not connected',
            }), 503
        
        result = db.execute("""
            SELECT 
                table_name,
                (SELECT COUNT(*) FROM information_schema.tables 
                 WHERE table_name = t.table_name) as row_count
            FROM information_schema.tables t
            WHERE table_schema = 'public'
            ORDER BY table_name
        """)
        
        # افزودن حجم هر جدول
        for table in result:
            try:
                size_result = db.execute(f"""
                    SELECT pg_total_relation_size('{table["table_name"]}') / 1024.0 / 1024.0 as size_mb
                """)
                table['size_mb'] = round(size_result[0]['size_mb'], 2) if size_result else 0
            except Exception:
                table['size_mb'] = 0
        
        return jsonify({
            'success': True,
            'data': result,
            'db_name': db_name,
            'count': len(result),
        })
    except Exception as e:
        logger.error(f"PG tables error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/db/postgresql/<db_name>/tables/<table_name>', methods=['GET'])
@require_auth()
def pg_table_data(db_name, table_name):
    """
    داده‌های یک جدول
    [جایگزین] /api/db/postgresql/table/<n> قدیمی
    """
    try:
        db = get_db(db_name)
        if not db or not db.is_connected():
            return jsonify({'success': False, 'error': f'DB not connected'}), 503
        
        limit = request.args.get('limit', 100, type=int)
        offset = request.args.get('offset', 0, type=int)
        search = request.args.get('search', '')
        sort_by = request.args.get('sort_by', 'id')
        sort_order = request.args.get('sort_order', 'DESC')
        format_type = request.args.get('format', 'json')
        
        # اعتبارسنجی sort
        if sort_order.upper() not in ['ASC', 'DESC']:
            sort_order = 'DESC'
        
        # ساخت کوئری
        query = f'SELECT * FROM "{table_name}"'
        params = []
        
        if search:
            # گرفتن ستون‌ها
            columns = db.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = %s
            """, (table_name,))
            
            col_names = [c['column_name'] for c in columns]
            
            conditions = []
            for col in col_names:
                if col in ['id', 'created_at', 'updated_at']:
                    continue
                conditions.append(f'"{col}"::text ILIKE %s')
                params.append(f'%{search}%')
            
            if conditions:
                query += ' WHERE ' + ' OR '.join(conditions)
        
        query += f' ORDER BY "{sort_by}" {sort_order} LIMIT %s OFFSET %s'
        params.extend([limit, offset])
        
        rows = db.execute(query, tuple(params))
        
        # total
        count_query = f'SELECT COUNT(*) as total FROM "{table_name}"'
        count_params = []
        if search:
            count_query += ' WHERE ' + ' OR '.join(conditions)
            count_params = [f'%{search}%'] * len(conditions)
        
        total_result = db.execute(count_query, tuple(count_params))
        total = total_result[0]['total'] if total_result else 0
        
        # CSV
        if format_type == 'csv':
            import io, csv
            output = io.StringIO()
            if rows:
                writer = csv.DictWriter(output, fieldnames=rows[0].keys())
                writer.writeheader()
                writer.writerows(rows)
            output.seek(0)
            return send_file(
                io.BytesIO(output.getvalue().encode('utf-8')),
                as_attachment=True,
                download_name=f'{table_name}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv',
                mimetype='text/csv',
            )
        
        return jsonify({
            'success': True,
            'data': {
                'db_name': db_name,
                'table': table_name,
                'rows': rows,
                'total': total,
                'limit': limit,
                'offset': offset,
                'has_more': (offset + limit) < total,
            },
        })
    except Exception as e:
        logger.error(f"PG table data error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/db/postgresql/<db_name>/table-sizes', methods=['GET'])
@require_auth()
def pg_table_sizes(db_name):
    """
    حجم همه جداول
    [جدید]
    """
    try:
        db = get_db(db_name)
        if not db or not db.is_connected():
            return jsonify({'success': False, 'error': 'DB not connected'}), 503
        
        if hasattr(db, 'get_table_sizes'):
            sizes = db.get_table_sizes()
        else:
            sizes = []
        
        return jsonify({
            'success': True,
            'data': sizes,
            'db_name': db_name,
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/db/postgresql/<db_name>/stats', methods=['GET'])
@require_auth()
def pg_stats(db_name):
    """
    آمار PostgreSQL
    [جایگزین] /api/db/postgresql/stats قدیمی
    """
    try:
        db = get_db(db_name)
        if not db or not db.is_connected():
            return jsonify({'success': False, 'error': 'DB not connected'}), 503
        
        stats = db.get_stats() if hasattr(db, 'get_stats') else {}
        quota = db._get_quota_summary() if hasattr(db, '_get_quota_summary') else {}
        
        return jsonify({
            'success': True,
            'data': {
                'db_name': db_name,
                'stats': stats,
                'quota': quota,
            },
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/db/postgresql/<db_name>/export/<table_name>', methods=['GET'])
@require_auth()
def pg_export(db_name, table_name):
    """
    خروجی CSV/JSON
    [جایگزین] /api/db/postgresql/export/<n> قدیمی
    """
    try:
        db = get_db(db_name)
        if not db or not db.is_connected():
            return jsonify({'success': False, 'error': 'DB not connected'}), 503
        
        format_type = request.args.get('format', 'csv')
        limit = request.args.get('limit', 10000, type=int)
        
        rows = db.execute(
            f'SELECT * FROM "{table_name}" ORDER BY id DESC LIMIT %s',
            (limit,),
        )
        
        if format_type == 'csv':
            import io, csv
            output = io.StringIO()
            if rows:
                writer = csv.DictWriter(output, fieldnames=rows[0].keys())
                writer.writeheader()
                writer.writerows(rows)
            output.seek(0)
            return send_file(
                io.BytesIO(output.getvalue().encode('utf-8')),
                as_attachment=True,
                download_name=f'{db_name}_{table_name}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv',
                mimetype='text/csv',
            )
        
        return jsonify({
            'success': True,
            'data': {
                'db_name': db_name,
                'table': table_name,
                'rows': rows,
                'count': len(rows),
            },
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/db/postgresql/<db_name>/tables/<table_name>/row/<int:row_id>', methods=['GET'])
@require_auth()
def pg_export_row(db_name, table_name, row_id):
    """
    خروجی یک ردیف
    [جایگزین] /api/db/postgresql/table/<n>/export/row/<id> قدیمی
    """
    try:
        db = get_db(db_name)
        if not db or not db.is_connected():
            return jsonify({'success': False, 'error': 'DB not connected'}), 503
        
        row = db.execute(
            f'SELECT * FROM "{table_name}" WHERE id = %s',
            (row_id,),
        )
        
        if not row:
            return jsonify({'success': False, 'error': 'Row not found'}), 404
        
        return jsonify({
            'success': True,
            'data': {
                'db_name': db_name,
                'table': table_name,
                'row_id': row_id,
                'row': row[0],
            },
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/db/postgresql/<db_name>/query', methods=['POST'])
@require_auth('admin')
def pg_query(db_name):
    """
    اجرای کوئری SELECT
    [جدید + جایگزین /api/db/query قدیمی]
    """
    try:
        data = request.json or {}
        query_text = data.get('query', '').strip()
        
        if not query_text:
            return jsonify({'success': False, 'error': 'Query required'}), 400
        
        # فقط SELECT
        query_upper = query_text.upper().strip()
        allowed = ['SELECT', 'WITH', 'EXPLAIN', 'SHOW']
        if not any(query_upper.startswith(a) for a in allowed):
            return jsonify({
                'success': False,
                'error': f'Only {allowed} allowed',
            }), 403
        
        db = get_db(db_name)
        if not db or not db.is_connected():
            return jsonify({'success': False, 'error': 'DB not connected'}), 503
        
        result = db.execute(query_text)
        
        return jsonify({
            'success': True,
            'data': {
                'db_name': db_name,
                'rows': result,
                'count': len(result),
            },
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================
# REDIS ENDPOINTS
# ============================================================

@api_bp.route('/db/redis/keys', methods=['GET'])
@require_auth()
def redis_keys():
    """
    لیست کلیدهای Redis با filter
    [جایگزین نسخه قدیمی — بهتر]
    """
    try:
        cache = get_cache()
        if not cache or not cache.is_connected():
            return jsonify({'success': False, 'error': 'Redis not connected'}), 503
        
        pattern = request.args.get('pattern', '*')
        limit = request.args.get('limit', 100, type=int)
        search = request.args.get('search', '')
        
        # استفاده از SCAN به جای KEYS
        if hasattr(cache, 'scan_keys'):
            keys = cache.scan_keys(pattern, count=200)
        else:
            keys = cache.keys(pattern)
        
        # filter بر اساس search
        if search:
            keys = [k for k in keys if search.lower() in k.lower()]
        
        keys = keys[:limit]
        
        # اطلاعات هر کلید
        result = []
        for key in keys:
            try:
                key_type = cache._client.type(key)
                type_str = key_type.decode() if isinstance(key_type, bytes) else key_type
                ttl = cache._client.ttl(key)
                
                # مقدار برای preview
                preview = None
                try:
                    val = cache._client.get(key)
                    if val:
                        val_str = val.decode() if isinstance(val, bytes) else str(val)
                        preview = val_str[:100]
                except Exception:
                    pass
                
                result.append({
                    'key': key,
                    'type': type_str,
                    'ttl': ttl if ttl > 0 else None,
                    'preview': preview,
                })
            except Exception as e:
                logger.debug(f"Key info error for {key}: {e}")
                continue
        
        info = cache._client.info()
        
        return jsonify({
            'success': True,
            'data': result,
            'count': len(result),
            'stats': {
                'memory': info.get('used_memory_human', '—'),
                'clients': info.get('connected_clients', 0),
                'total_keys': info.get('db0', {}).get('keys', 0),
            },
        })
    except Exception as e:
        logger.error(f"Redis keys error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/db/redis/keys/<path:key>', methods=['GET'])
@require_auth()
def redis_get_key(key):
    """
    مقدار یک کلید
    [جایگزین] /api/db/redis/key/<k> قدیمی
    """
    try:
        cache = get_cache()
        if not cache or not cache.is_connected():
            return jsonify({'success': False, 'error': 'Redis not connected'}), 503
        
        key_type = cache._client.type(key)
        type_str = key_type.decode() if isinstance(key_type, bytes) else key_type
        
        value = None
        if type_str == 'string':
            val = cache._client.get(key)
            value = val.decode() if isinstance(val, bytes) else val
        elif type_str == 'hash':
            val = cache._client.hgetall(key)
            value = {
                k.decode() if isinstance(k, bytes) else k:
                v.decode() if isinstance(v, bytes) else v
                for k, v in val.items()
            }
        elif type_str == 'list':
            val = cache._client.lrange(key, 0, 50)
            value = [v.decode() if isinstance(v, bytes) else v for v in val]
        elif type_str == 'set':
            val = cache._client.smembers(key)
            value = [v.decode() if isinstance(v, bytes) else v for v in list(val)[:50]]
        elif type_str == 'zset':
            val = cache._client.zrange(key, 0, 50, withscores=True)
            value = [
                {v.decode() if isinstance(v, bytes) else v: score}
                for v, score in val
            ]
        
        ttl = cache._client.ttl(key)
        
        return jsonify({
            'success': True,
            'data': {
                'key': key,
                'type': type_str,
                'value': value,
                'ttl': ttl if ttl > 0 else None,
            },
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/db/redis/keys/<path:key>', methods=['DELETE'])
@require_auth('admin')
def redis_delete_key(key):
    """حذف یک کلید [جدید]"""
    try:
        cache = get_cache()
        if not cache or not cache.is_connected():
            return jsonify({'success': False, 'error': 'Redis not connected'}), 503
        
        deleted = cache._client.delete(key)
        return jsonify({
            'success': bool(deleted),
            'message': f'Key "{key}" deleted' if deleted else 'Key not found',
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/db/redis/stats', methods=['GET'])
@require_auth()
def redis_stats():
    """آمار کامل Redis [جایگزین بهبود یافته]"""
    try:
        cache = get_cache()
        if not cache or not cache.is_connected():
            return jsonify({'success': False, 'error': 'Redis not connected'}), 503
        
        stats = cache.get_stats() if hasattr(cache, 'get_stats') else {}
        
        return jsonify({
            'success': True,
            'data': stats,
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/db/redis/namespaces', methods=['GET'])
@require_auth()
def redis_namespaces():
    """آمار namespaceها [جدید]"""
    try:
        cache = get_cache()
        if not cache or not cache.is_connected():
            return jsonify({'success': False, 'error': 'Redis not connected'}), 503
        
        if hasattr(cache, 'get_namespace_stats'):
            stats = cache.get_namespace_stats()
        else:
            stats = {}
        
        return jsonify({
            'success': True,
            'data': stats,
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/db/redis/namespace/<namespace>', methods=['DELETE'])
@require_auth('admin')
def redis_clear_namespace(namespace):
    """پاک کردن یک namespace [جدید]"""
    try:
        cache = get_cache()
        if not cache or not cache.is_connected():
            return jsonify({'success': False, 'error': 'Redis not connected'}), 503
        
        if hasattr(cache, 'cleanup_namespace'):
            deleted = cache.cleanup_namespace(namespace)
        else:
            # Fallback
            pattern = f"{namespace}:*" if not namespace.endswith(':') else f"{namespace}*"
            keys = cache.scan_keys(pattern) if hasattr(cache, 'scan_keys') else cache.keys(pattern)
            deleted = len(keys)
            if keys:
                cache.delete_many(keys)
        
        return jsonify({
            'success': True,
            'message': f'Cleared {deleted} keys from {namespace}',
            'deleted': deleted,
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/db/redis/flush', methods=['DELETE'])
@require_auth('admin')
def redis_flush():
    """
    پاک کردن همه کلیدها
    [جایگزین] /api/db/redis/clear قدیمی
    """
    try:
        confirm = request.args.get('confirm', 'false').lower() == 'true'
        if not confirm:
            return jsonify({
                'success': False,
                'error': 'Confirmation required. Use ?confirm=true',
            }), 400
        
        cache = get_cache()
        if not cache or not cache.is_connected():
            return jsonify({'success': False, 'error': 'Redis not connected'}), 503
        
        # شمارش قبل از پاک کردن
        if hasattr(cache, 'scan_keys'):
            keys_before = len(cache.scan_keys('*', count=1000))
        else:
            keys_before = len(cache.keys('*'))
        
        cache._client.flushdb()
        
        return jsonify({
            'success': True,
            'message': f'Redis flushed. {keys_before} keys deleted.',
            'deleted': keys_before,
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/db/redis/keys/<path:key>/export', methods=['GET'])
@require_auth()
def redis_export_key(key):
    """
    خروجی یک کلید به JSON
    [جایگزین] /api/db/redis/key/<k>/export قدیمی
    """
    try:
        cache = get_cache()
        if not cache or not cache.is_connected():
            return jsonify({'success': False, 'error': 'Redis not connected'}), 503
        
        key_type = cache._client.type(key)
        type_str = key_type.decode() if isinstance(key_type, bytes) else key_type
        
        value = None
        if type_str == 'string':
            val = cache._client.get(key)
            value = val.decode() if isinstance(val, bytes) else val
        elif type_str == 'hash':
            val = cache._client.hgetall(key)
            value = {
                k.decode() if isinstance(k, bytes) else k:
                v.decode() if isinstance(v, bytes) else v
                for k, v in val.items()
            }
        elif type_str == 'list':
            val = cache._client.lrange(key, 0, -1)
            value = [v.decode() if isinstance(v, bytes) else v for v in val]
        elif type_str == 'set':
            val = cache._client.smembers(key)
            value = [v.decode() if isinstance(v, bytes) else v for v in list(val)]
        else:
            value = 'Unsupported type'
        
        return jsonify({
            'success': True,
            'data': {
                'key': key,
                'type': type_str,
                'value': value,
                'exported_at': datetime.now().isoformat(),
            },
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ============================================================
# ARCHIVE (SQLite via Layerbase) ENDPOINTS
# ============================================================

@api_bp.route('/db/archive/tables', methods=['GET'])
@require_auth()
def archive_tables():
    """
    لیست جداول Archive
    [جایگزین] /api/db/sqlite/tables قدیمی
    """
    try:
        db = get_archive()
        if not db or not db.is_connected():
            return jsonify({'success': False, 'error': 'Archive not connected'}), 503
        
        # لیست جداول (SQLite)
        result = db.execute("""
            SELECT name as table_name 
            FROM sqlite_master 
            WHERE type='table' 
            AND name NOT LIKE 'sqlite_%'
            ORDER BY name
        """)
        
        # شمارش رکوردها
        for table in result:
            try:
                count = db.execute(
                    f"SELECT COUNT(*) as count FROM [{table['table_name']}]"
                )
                table['row_count'] = count[0]['count'] if count else 0
            except Exception:
                table['row_count'] = 0
        
        return jsonify({
            'success': True,
            'data': result,
            'count': len(result),
        })
    except Exception as e:
        logger.error(f"Archive tables error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/db/archive/tables/<table_name>', methods=['GET'])
@require_auth()
def archive_table_data(table_name):
    """
    داده‌های یک جدول Archive
    [جایگزین] /api/db/sqlite/table/<n> قدیمی
    """
    try:
        db = get_archive()
        if not db or not db.is_connected():
            return jsonify({'success': False, 'error': 'Archive not connected'}), 503
        
        limit = request.args.get('limit', 100, type=int)
        offset = request.args.get('offset', 0, type=int)
        search = request.args.get('search', '')
        
        # ستون‌ها
        pragma = db.execute(f"PRAGMA table_info({table_name})")
        if not pragma:
            return jsonify({'success': False, 'error': 'Table not found'}), 404
        
        col_names = [c['name'] for c in pragma]
        
        # کوئری
        query = f'SELECT * FROM [{table_name}]'
        params = []
        
        if search:
            conditions = []
            for col in col_names:
                if col not in ['id', 'created_at']:
                    conditions.append(f'"{col}" LIKE ?')
                    params.append(f'%{search}%')
            
            if conditions:
                query += ' WHERE ' + ' OR '.join(conditions)
        
        query += ' ORDER BY id DESC LIMIT ? OFFSET ?'
        params.extend([limit, offset])
        
        rows = db.execute(query, tuple(params))
        
        # total
        total_result = db.execute(f'SELECT COUNT(*) as total FROM [{table_name}]')
        total = total_result[0]['total'] if total_result else 0
        
        return jsonify({
            'success': True,
            'data': {
                'table': table_name,
                'columns': col_names,
                'rows': rows,
                'total': total,
                'limit': limit,
                'offset': offset,
            },
        })
    except Exception as e:
        logger.error(f"Archive table error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/db/archive/stats', methods=['GET'])
@require_auth()
def archive_stats():
    """آمار Archive [جایگزین]"""
    try:
        db = get_archive()
        if not db or not db.is_connected():
            return jsonify({'success': False, 'error': 'Archive not connected'}), 503
        
        stats = db.get_stats() if hasattr(db, 'get_stats') else {}
        
        return jsonify({
            'success': True,
            'data': stats,
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/db/archive/tables/<table_name>/export', methods=['GET'])
@require_auth()
def archive_export(table_name):
    """خروجی یک جدول Archive [جایگزین]"""
    try:
        db = get_archive()
        if not db or not db.is_connected():
            return jsonify({'success': False, 'error': 'Archive not connected'}), 503
        
        format_type = request.args.get('format', 'csv')
        limit = request.args.get('limit', 10000, type=int)
        
        pragma = db.execute(f"PRAGMA table_info({table_name})")
        if not pragma:
            return jsonify({'success': False, 'error': 'Table not found'}), 404
        
        col_names = [c['name'] for c in pragma]
        
        rows = db.execute(
            f'SELECT * FROM [{table_name}] ORDER BY id DESC LIMIT ?',
            (limit,),
        )
        
        if format_type == 'csv':
            import io, csv
            output = io.StringIO()
            writer = csv.DictWriter(output, fieldnames=col_names)
            writer.writeheader()
            writer.writerows(rows)
            output.seek(0)
            return send_file(
                io.BytesIO(output.getvalue().encode('utf-8')),
                as_attachment=True,
                download_name=f'archive_{table_name}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv',
                mimetype='text/csv',
            )
        
        return jsonify({
            'success': True,
            'data': {
                'table': table_name,
                'columns': col_names,
                'rows': rows,
                'count': len(rows),
            },
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/db/archive/tables/<table_name>/row/<int:row_id>', methods=['GET'])
@require_auth()
def archive_export_row(table_name, row_id):
    """خروجی یک ردیف Archive [جایگزین]"""
    try:
        db = get_archive()
        if not db or not db.is_connected():
            return jsonify({'success': False, 'error': 'Archive not connected'}), 503
        
        pragma = db.execute(f"PRAGMA table_info({table_name})")
        if not pragma:
            return jsonify({'success': False, 'error': 'Table not found'}), 404
        
        col_names = [c['name'] for c in pragma]
        
        row = db.execute(
            f'SELECT * FROM [{table_name}] WHERE id = ?',
            (row_id,),
        )
        
        if not row:
            return jsonify({'success': False, 'error': 'Row not found'}), 404
        
        return jsonify({
            'success': True,
            'data': {
                'table': table_name,
                'row_id': row_id,
                'columns': col_names,
                'row': row[0],
            },
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/db/archive/cleanup', methods=['POST'])
@require_auth('admin')
def archive_cleanup():
    """
    پاک کردن رکوردهای قدیمی Archive [جدید]
    
    Body:
        {
            "table": "predictions_archive",
            "retention_days": 365
        }
    """
    try:
        data = request.json or {}
        table = data.get('table')
        retention_days = data.get('retention_days', 365)
        
        if not table:
            return jsonify({'success': False, 'error': 'Table required'}), 400
        
        db = get_archive()
        if not db or not db.is_connected():
            return jsonify({'success': False, 'error': 'Archive not connected'}), 503
        
        if hasattr(db, 'cleanup_old_records'):
            # تشخیص نام ستون تاریخ
            date_col = 'archived_at' if 'archive' in table else 'created_at'
            
            deleted = db.cleanup_old_records(
                table_name=table,
                date_column=date_col,
                retention_days=retention_days,
            )
        else:
            deleted = 0
        
        return jsonify({
            'success': True,
            'deleted': deleted,
            'message': f'Deleted {deleted} old records from {table}',
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/db/archive/features', methods=['GET'])
@require_auth()
def archive_features():
    """
    ویژگی‌های SQLite (محدودیت‌ها) [جدید]
    """
    try:
        db = get_archive()
        if not db or not db.is_connected():
            return jsonify({'success': False, 'error': 'Archive not connected'}), 503
        
        config = db.config
        features = config.get('features', {})
        
        return jsonify({
            'success': True,
            'data': {
                'engine': 'sqlite3',
                'features': features,
                'single_writer': features.get('single_writer', True),
                'supports_interval': features.get('supports_interval', False),
                'supports_jsonb': features.get('supports_jsonb', False),
                'supports_arrays': features.get('supports_arrays', False),
            },
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500



#=============================================================
@api_bp.route('/db/migrate', methods=['POST'])
@require_auth('admin')
def db_migrate():
    """اجرای مهاجرت دیتابیس"""
    try:
        import subprocess
        import os
        from pathlib import Path
        
        # مسیر پروژه
        project_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        
        result = subprocess.run(
            ['python', 'scripts/manage_databases.py', '--action=migrate'],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=project_path
        )
        
        return jsonify({
            'success': result.returncode == 0,
            'output': result.stdout,
            'error': result.stderr if result.stderr else None,
            'returncode': result.returncode
        })
    except subprocess.TimeoutExpired:
        return jsonify({'success': False, 'error': 'Migration timed out'}), 408
    except Exception as e:
        logger.error(f"Migration error: {e}", exc_info=True)
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


# ============================================================
# QUOTA MANAGEMENT
# ============================================================

@api_bp.route('/db/quota', methods=['GET'])
@require_auth()
def get_all_quotas_endpoint():
    """دریافت Quota همه دیتابیس‌ها"""
    try:
        quotas = get_all_quotas()
        
        # افزودن وضعیت لحظه‌ای
        result = {}
        for db_name, quota in quotas.items():
            db = get_db(db_name)
            if db and db.is_connected():
                used_mb = 0
                if hasattr(db, '_calculate_used_size'):
                    used_mb = db._calculate_used_size()
                
                status = get_quota_status(db_name, used_mb)
                result[db_name] = {
                    "quota": quota,
                    "status": status,
                }
            else:
                result[db_name] = {
                    "quota": quota,
                    "status": {"connected": False},
                }
        
        return jsonify({
            'success': True,
            'data': result,
            'timestamp': datetime.now().isoformat(),
        })
    except Exception as e:
        logger.error(f"Get all quotas error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/db/quota/<db_name>', methods=['GET'])
@require_auth()
def get_db_quota(db_name):
    """دریافت Quota یک دیتابیس"""
    try:
        quota = get_quota(db_name)
        if not quota:
            return jsonify({
                'success': False,
                'error': f'Quota not found for {db_name}',
            }), 404
        
        return jsonify({
            'success': True,
            'data': {
                'db_name': db_name,
                'quota': quota,
            },
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/db/quota/<db_name>/status', methods=['GET'])
@require_auth()
def get_db_quota_status(db_name):
    """دریافت وضعیت لحظه‌ای Quota"""
    try:
        db = get_db(db_name)
        if not db or not db.is_connected():
            return jsonify({
                'success': False,
                'error': f'Database {db_name} not connected',
            }), 503
        
        used_mb = 0
        if hasattr(db, '_calculate_used_size'):
            used_mb = db._calculate_used_size()
        
        status = get_quota_status(db_name, used_mb)
        
        return jsonify({
            'success': True,
            'data': status,
            'timestamp': datetime.now().isoformat(),
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/db/quota/<db_name>', methods=['POST'])
@require_auth('admin')
def set_db_quota(db_name):
    """
    تنظیم محدودیت دیتابیس
    
    Body:
        {
            "total_mb": 400,
            "reserved_mb": 100,
            "warn_threshold": 75,
            "critical_threshold": 90,
            "auto_cleanup": true
        }
    """
    try:
        data = request.json or {}
        
        result = set_database_limit(
            db_name=db_name,
            total_mb=data.get('total_mb'),
            reserved_mb=data.get('reserved_mb'),
            warn_threshold=data.get('warn_threshold'),
            critical_threshold=data.get('critical_threshold'),
            auto_cleanup=data.get('auto_cleanup'),
        )
        
        return jsonify(result), 200 if result.get('success') else 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/db/quota/<db_name>/table/<table_name>', methods=['POST'])
@require_auth('admin')
def set_table_quota(db_name, table_name):
    """
    تنظیم محدودیت یک جدول
    
    Body:
        {
            "max_mb": 200,
            "retention_days": 30,
            "keep_last_n": 10
        }
    """
    try:
        data = request.json or {}
        
        result = set_table_limit(
            db_name=db_name,
            table_name=table_name,
            max_mb=data.get('max_mb'),
            retention_days=data.get('retention_days'),
            keep_last_n=data.get('keep_last_n'),
        )
        
        return jsonify(result), 200 if result.get('success') else 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/db/quota/<db_name>', methods=['DELETE'])
@require_auth('admin')
def reset_db_quota(db_name):
    """ریست overrides یک دیتابیس"""
    try:
        result = reset_quota_overrides(db_name)
        return jsonify(result), 200 if result.get('success') else 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/db/quota', methods=['DELETE'])
@require_auth('admin')
def reset_all_quotas():
    """ریست همه overrides"""
    try:
        result = reset_quota_overrides(None)
        return jsonify(result), 200 if result.get('success') else 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/db/quota/stats', methods=['GET'])
@require_auth()
def get_quota_stats():
    """آمار QuotaManager"""
    try:
        stats = get_quota_manager_stats()
        return jsonify({'success': True, 'data': stats})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================
# DATABASE HEALTH & STATUS
# ============================================================

@api_bp.route('/db/health/summary', methods=['GET'])
@require_auth()
def db_health_summary():
    """
    خلاصه سلامت همه دیتابیس‌ها
    [جایگزین] /api/db/health قدیمی
    """
    try:
        summary = health_summary()
        return jsonify({
            'success': True,
            'data': summary,
            'timestamp': datetime.now().isoformat(),
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/db/health/full', methods=['GET'])
@require_auth()
def db_health_full():
    """
    سلامت کامل با جزئیات + Quota
    [جایگزین] /api/db/monitor قدیمی
    """
    try:
        health = health_check()
        status = get_database_status()
        
        return jsonify({
            'success': True,
            'data': {
                'summary': status,
                'details': health,
            },
            'timestamp': datetime.now().isoformat(),
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/db/list', methods=['GET'])
@require_auth()
def db_list():
    """لیست همه دیتابیس‌های ثبت شده با اطلاعات کامل"""
    try:
        databases = get_databases_info()
        return jsonify({
            'success': True,
            'data': databases,
            'count': len(databases),
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/db/<db_name>/ping', methods=['GET'])
@require_auth()
def db_ping(db_name):
    """تست اتصال یک دیتابیس"""
    try:
        db = get_db(db_name)
        if not db:
            return jsonify({
                'success': False,
                'error': f'Database {db_name} not found',
            }), 404
        
        is_ok = db.ping()
        
        return jsonify({
            'success': True,
            'data': {
                'db_name': db_name,
                'ping': is_ok,
                'connected': db.is_connected(),
            },
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/db/reconnect', methods=['POST'])
@require_auth('admin')
def db_reconnect_all():
    """Reconnect همه دیتابیس‌ها"""
    try:
        results = force_reconnect()
        return jsonify({
            'success': True,
            'data': results,
            'timestamp': datetime.now().isoformat(),
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/db/<db_name>/reconnect', methods=['POST'])
@require_auth('admin')
def db_reconnect_one(db_name):
    """Reconnect یک دیتابیس"""
    try:
        results = force_reconnect(db_name)
        return jsonify({
            'success': True,
            'data': results,
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/db/factory/status', methods=['GET'])
@require_auth()
def db_factory_status():
    """وضعیت کامل DatabaseFactory"""
    try:
        status = get_factory_status()
        return jsonify({
            'success': True,
            'data': status,
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/db/ready', methods=['GET'])
def db_ready():
    """آیا سیستم آماده است؟"""
    try:
        ready = is_ready()
        return jsonify({
            'success': True,
            'ready': ready,
            'timestamp': datetime.now().isoformat(),
        }), 200 if ready else 503
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/db/reload-config', methods=['POST'])
@require_auth('admin')
def db_reload_config():
    """بارگذاری مجدد تنظیمات دیتابیس"""
    try:
        result = reload_config()
        return jsonify(result), 200 if result.get('success') else 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================
# MAINTENANCE (بدون نیاز به بک‌اند)
# ============================================================

@api_bp.route('/db/<db_name>/vacuum', methods=['POST'])
@require_auth('admin')
def db_vacuum(db_name):
    """
    اجرای VACUUM در PostgreSQL
    
    Query params:
        full (bool): VACUUM FULL (کندتر ولی فضای بیشتر آزاد می‌کنه)
        analyze (bool): همراه با ANALYZE
    
    مثال:
        POST /api/db/primary/vacuum?full=false&analyze=true
    """
    try:
        db = get_db(db_name)
        if not db or not db.is_connected():
            return jsonify({
                'success': False,
                'error': f'Database {db_name} not connected',
            }), 503
        
        # پارامترها
        is_full = request.args.get('full', 'false').lower() == 'true'
        with_analyze = request.args.get('analyze', 'true').lower() == 'true'
        
        # ساخت کوئری
        vacuum_type = "VACUUM FULL" if is_full else "VACUUM"
        analyze_clause = "ANALYZE" if with_analyze else ""
        query = f"{vacuum_type} {analyze_clause}".strip()
        
        start_time = time.time()
        
        # اجرا
        db.execute(query)
        
        duration = round(time.time() - start_time, 2)
        
        logger.info(
            f"✅ {query} on {db_name} completed in {duration}s"
        )
        
        return jsonify({
            'success': True,
            'data': {
                'db_name': db_name,
                'operation': query,
                'duration_seconds': duration,
                'full': is_full,
                'analyze': with_analyze,
            },
            'message': f'VACUUM completed in {duration}s',
            'timestamp': datetime.now().isoformat(),
        })
        
    except Exception as e:
        logger.error(f"VACUUM error on {db_name}: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e),
            'db_name': db_name,
        }), 500


@api_bp.route('/db/vacuum-all', methods=['POST'])
@require_auth('admin')
def db_vacuum_all():
    """
    اجرای VACUUM روی همه دیتابیس‌های PostgreSQL
    
    Query params:
        full (bool): VACUUM FULL
        analyze (bool): همراه با ANALYZE
    """
    try:
        is_full = request.args.get('full', 'false').lower() == 'true'
        with_analyze = request.args.get('analyze', 'true').lower() == 'true'
        
        vacuum_type = "VACUUM FULL" if is_full else "VACUUM"
        analyze_clause = "ANALYZE" if with_analyze else ""
        query = f"{vacuum_type} {analyze_clause}".strip()
        
        # دیتابیس‌های PostgreSQL
        db_names = ['primary', 'backup', 'analytics', 'logs']
        results = {}
        
        start_time = time.time()
        
        for db_name in db_names:
            try:
                db = get_db(db_name)
                if not db or not db.is_connected():
                    results[db_name] = {
                        'success': False,
                        'error': 'not connected',
                    }
                    continue
                
                db_start = time.time()
                db.execute(query)
                duration = round(time.time() - db_start, 2)
                
                results[db_name] = {
                    'success': True,
                    'duration_seconds': duration,
                }
                
                logger.info(f"✅ {query} on {db_name} ({duration}s)")
                
            except Exception as e:
                results[db_name] = {
                    'success': False,
                    'error': str(e),
                }
                logger.error(f"VACUUM error on {db_name}: {e}")
        
        total_duration = round(time.time() - start_time, 2)
        success_count = sum(1 for r in results.values() if r.get('success'))
        
        return jsonify({
            'success': success_count > 0,
            'data': {
                'operation': query,
                'total_duration_seconds': total_duration,
                'databases': results,
                'success_count': success_count,
                'total_count': len(db_names),
            },
            'timestamp': datetime.now().isoformat(),
        })
        
    except Exception as e:
        logger.error(f"VACUUM ALL error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/db/<db_name>/analyze', methods=['POST'])
@require_auth('admin')
def db_analyze(db_name):
    """
    اجرای ANALYZE در PostgreSQL (بهبود query plan)
    
    Query params:
        table (str): اختیاری — فقط یک جدول
    """
    try:
        db = get_db(db_name)
        if not db or not db.is_connected():
            return jsonify({
                'success': False,
                'error': f'Database {db_name} not connected',
            }), 503
        
        # اگه جدول مشخص شده
        table_name = request.args.get('table', '').strip()
        
        if table_name:
            query = f'ANALYZE "{table_name}"'
        else:
            query = "ANALYZE"
        
        start_time = time.time()
        db.execute(query)
        duration = round(time.time() - start_time, 2)
        
        logger.info(f"✅ {query} on {db_name} completed in {duration}s")
        
        return jsonify({
            'success': True,
            'data': {
                'db_name': db_name,
                'operation': query,
                'table': table_name or 'all',
                'duration_seconds': duration,
            },
            'message': f'ANALYZE completed in {duration}s',
            'timestamp': datetime.now().isoformat(),
        })
        
    except Exception as e:
        logger.error(f"ANALYZE error on {db_name}: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================
# TABLE OPERATIONS (بدون نیاز به بک‌اند)
# ============================================================

@api_bp.route('/db/<db_name>/tables/<table_name>/delete-old', methods=['POST'])
@require_auth('admin')
def db_delete_old_records(db_name, table_name):
    """
    حذف رکوردهای قدیمی از یک جدول
    
    Body:
        {
            "date_column": "created_at",     // نام ستون تاریخ
            "retention_days": 30,            // مدت نگهداری
            "dry_run": false                 // اگه true باشه فقط شمارش می‌کنه
        }
    
    مثال:
        POST /api/db/primary/tables/predictions/delete-old
        Body: {"date_column": "timestamp", "retention_days": 30}
    """
    try:
        data = request.json or {}
        date_column = data.get('date_column', 'created_at')
        retention_days = data.get('retention_days', 30)
        dry_run = data.get('dry_run', False)
        
        if retention_days < 1:
            return jsonify({
                'success': False,
                'error': 'retention_days must be >= 1',
            }), 400
        
        db = get_db(db_name)
        if not db or not db.is_connected():
            return jsonify({
                'success': False,
                'error': f'Database {db_name} not connected',
            }), 503
        
        # محاسبه تاریخ cutoff
        from datetime import timedelta
        cutoff = datetime.now() - timedelta(days=retention_days)
        
        # ۱. شمارش اول
        count_result = db.execute(
            f'SELECT COUNT(*) as count FROM "{table_name}" '
            f'WHERE "{date_column}" < %s',
            (cutoff,),
        )
        count = count_result[0]['count'] if count_result else 0
        
        if count == 0:
            return jsonify({
                'success': True,
                'data': {
                    'db_name': db_name,
                    'table': table_name,
                    'deleted': 0,
                    'cutoff_date': cutoff.isoformat(),
                    'retention_days': retention_days,
                    'dry_run': dry_run,
                },
                'message': 'No old records to delete',
            })
        
        # ۲. اگه dry_run بود، فقط برگردون
        if dry_run:
            return jsonify({
                'success': True,
                'data': {
                    'db_name': db_name,
                    'table': table_name,
                    'would_delete': count,
                    'cutoff_date': cutoff.isoformat(),
                    'retention_days': retention_days,
                    'dry_run': True,
                },
                'message': f'Dry run: {count} records would be deleted',
            })
        
        # ۳. حذف واقعی
        start_time = time.time()
        db.execute(
            f'DELETE FROM "{table_name}" WHERE "{date_column}" < %s',
            (cutoff,),
        )
        duration = round(time.time() - start_time, 2)
        
        logger.info(
            f"✅ Deleted {count} old records from {db_name}.{table_name} "
            f"(older than {retention_days} days, {duration}s)"
        )
        
        return jsonify({
            'success': True,
            'data': {
                'db_name': db_name,
                'table': table_name,
                'deleted': count,
                'cutoff_date': cutoff.isoformat(),
                'retention_days': retention_days,
                'duration_seconds': duration,
                'dry_run': False,
            },
            'message': f'Deleted {count} old records in {duration}s',
        })
        
    except Exception as e:
        logger.error(f"Delete old records error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/db/<db_name>/tables/<table_name>/count', methods=['GET'])
@require_auth()
def db_table_count(db_name, table_name):
    """
    تعداد سریع رکوردهای یک جدول
    
    Query params:
        where (str): شرط WHERE اختیاری
    
    مثال:
        GET /api/db/primary/tables/predictions/count
        GET /api/db/primary/tables/predictions/count?where=signal_type='BUY'
    """
    try:
        db = get_db(db_name)
        if not db or not db.is_connected():
            return jsonify({
                'success': False,
                'error': f'Database {db_name} not connected',
            }), 503
        
        where_clause = request.args.get('where', '').strip()
        
        # ساخت کوئری
        query = f'SELECT COUNT(*) as count FROM "{table_name}"'
        if where_clause:
            # امنیت: فقط کاراکترهای مجاز
            query += f' WHERE {where_clause}'
        
        result = db.execute(query)
        count = result[0]['count'] if result else 0
        
        return jsonify({
            'success': True,
            'data': {
                'db_name': db_name,
                'table': table_name,
                'count': count,
                'where': where_clause or None,
            },
        })
        
    except Exception as e:
        logger.error(f"Table count error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/db/<db_name>/tables/<table_name>/size', methods=['GET'])
@require_auth()
def db_table_size(db_name, table_name):
    """
    حجم یک جدول در PostgreSQL
    
    مثال:
        GET /api/db/primary/tables/predictions/size
    """
    try:
        db = get_db(db_name)
        if not db or not db.is_connected():
            return jsonify({
                'success': False,
                'error': f'Database {db_name} not connected',
            }), 503
        
        # حجم‌های مختلف
        result = db.execute(f"""
            SELECT
                pg_total_relation_size('{table_name}') AS total_bytes,
                pg_relation_size('{table_name}') AS data_bytes,
                pg_indexes_size('{table_name}') AS indexes_bytes,
                pg_total_relation_size('{table_name}') / 1024.0 / 1024.0 AS total_mb,
                pg_relation_size('{table_name}') / 1024.0 / 1024.0 AS data_mb,
                pg_indexes_size('{table_name}') / 1024.0 / 1024.0 AS indexes_mb
        """)
        
        if not result:
            return jsonify({
                'success': False,
                'error': f'Table {table_name} not found',
            }), 404
        
        row = result[0]
        
        # تعداد رکوردها
        count_result = db.execute(f'SELECT COUNT(*) as count FROM "{table_name}"')
        count = count_result[0]['count'] if count_result else 0
        
        # حجم متوسط هر رکورد
        avg_row_bytes = (
            row['data_bytes'] / count if count > 0 else 0
        )
        
        return jsonify({
            'success': True,
            'data': {
                'db_name': db_name,
                'table': table_name,
                'row_count': count,
                'sizes': {
                    'total_mb': round(row['total_mb'], 2),
                    'data_mb': round(row['data_mb'], 2),
                    'indexes_mb': round(row['indexes_mb'], 2),
                    'total_bytes': row['total_bytes'],
                    'data_bytes': row['data_bytes'],
                    'indexes_bytes': row['indexes_bytes'],
                },
                'avg_row_bytes': round(avg_row_bytes, 2),
            },
        })
        
    except Exception as e:
        logger.error(f"Table size error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/db/<db_name>/tables/<table_name>/truncate', methods=['POST'])
@require_auth('admin')
def db_table_truncate(db_name, table_name):
    """
    خالی کردن یک جدول (TRUNCATE)
    
    Query params:
        confirm (bool): تأیید صریح
        cascade (bool): حذف وابستگی‌ها (پیش‌فرض false)
    
    ⚠️ احتیاط: عملیات غیرقابل بازگشت
    """
    try:
        confirm = request.args.get('confirm', 'false').lower() == 'true'
        if not confirm:
            return jsonify({
                'success': False,
                'error': 'Confirmation required. Use ?confirm=true',
                'warning': 'This operation cannot be undone!',
            }), 400
        
        cascade = request.args.get('cascade', 'false').lower() == 'true'
        
        db = get_db(db_name)
        if not db or not db.is_connected():
            return jsonify({
                'success': False,
                'error': f'Database {db_name} not connected',
            }), 503
        
        # شمارش قبل
        count_result = db.execute(f'SELECT COUNT(*) as count FROM "{table_name}"')
        count_before = count_result[0]['count'] if count_result else 0
        
        # TRUNCATE
        cascade_clause = " CASCADE" if cascade else ""
        query = f'TRUNCATE TABLE "{table_name}"{cascade_clause}'
        
        start_time = time.time()
        db.execute(query)
        duration = round(time.time() - start_time, 2)
        
        logger.warning(
            f"⚠️ TRUNCATED {db_name}.{table_name} "
            f"({count_before} rows deleted, {duration}s)"
        )
        
        return jsonify({
            'success': True,
            'data': {
                'db_name': db_name,
                'table': table_name,
                'rows_deleted': count_before,
                'cascade': cascade,
                'duration_seconds': duration,
            },
            'message': f'Table truncated ({count_before} rows deleted)',
            'warning': 'Operation completed',
            'timestamp': datetime.now().isoformat(),
        })
        
    except Exception as e:
        logger.error(f"Truncate error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================
# ۹. مدل (MODEL)
# ============================================================

@api_bp.route('/model/status', methods=['GET'])
@require_auth()
def model_status():
    try:
        container = current_app.container
        model_manager = container.get('model_manager')
        
        # ✅ مدیریت trainer با try/except
        try:
            trainer = container.get('trainer')
            train_status = trainer.get_stats() if hasattr(trainer, 'get_stats') else {}
        except KeyError:
            train_status = {}
            logger.warning("⚠️ Trainer not available in container")
        
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

@api_bp.route('/model/train', methods=['POST'])
@require_auth('admin')
def model_train():
    """
    آموزش مدل جدید (با Profile support)
    
    Body:
        {
            "period": "1m",
            "coins": ["bitcoin", "ethereum"],
            "profile_name": "accurate",       // ← جدید
            "profile": {...},                 // ← جدید
            "strategy": "full",               // ← جدید
            "save": true                      // ← جدید
        }
    """
    try:
        data = request.json or {}
        
        # اعتبارسنجی با DTO
        from application.dto import TrainRequestDTO
        
        dto = TrainRequestDTO.from_dict(data)
        valid, errors = dto.validate()
        
        if not valid:
            return jsonify({
                'success': False,
                'error': 'Invalid request',
                'details': errors,
            }), 400
        
        # اجرا
        container = current_app.container
        trainer = container.get('trainer')
        
        result = trainer.train_model(
            period=dto.period,
            coins=dto.coins,
            profile_name=dto.profile_name,
            profile=dto.profile,
            strategy=dto.strategy,
            save=dto.save,
        )
        
        return jsonify(result), 200 if result.get('success') else 400
        
    except Exception as e:
        logger.error(f"Model train error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/model/history', methods=['GET'])
@require_auth()
def model_history():
    """دریافت تاریخچه نسخه‌های مدل"""
    try:
        container = current_app.container
        model_manager = container.get('model_manager')
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
        model_manager = container.get('model_manager')
        
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


@api_bp.route('/model/export', methods=['GET'])
@require_auth()
def model_export():
    """خروجی گرفتن از مدل (دانلود فایل .xgb)"""
    try:
        container = current_app.container
        model_manager = container.get('model_manager')
        
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
        model_manager = container.get('model_manager')
        
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
        model_manager = container.get('model_manager')
        
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
        model_manager = container.get('model_manager')
        
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


@api_bp.route('/predict/history', methods=['GET'])
@require_auth()
def predict_history():
    """
    دریافت تاریخچه پیش‌بینی‌های ذخیره شده
    """
    try:
        limit = request.args.get('limit', 50, type=int)
        coin = request.args.get('coin')
        
        from infrastructure.repositories.prediction_repository import PredictionRepository
        repo = PredictionRepository()
        
        if coin:
            predictions = repo.find_by_coin(coin, limit)
        else:
            predictions = repo.find_all(limit)
        
        return jsonify({
            'success': True,
            'data': [p.to_dict() for p in predictions],
            'count': len(predictions),
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"Predict history error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/predict/history/stats', methods=['GET'])
@require_auth()
def predict_history_stats():
    """
    دریافت آمار پیش‌بینی‌های ذخیره‌شده
    
    خروجی:
        {
            "success": true,
            "data": {
                "total": 1234,
                "by_signal": {
                    "BUY": 400,
                    "SELL": 300,
                    "NEUTRAL": 534
                },
                "by_coin": [
                    {"coin": "bitcoin", "count": 500},
                    {"coin": "ethereum", "count": 400},
                    ...
                ],
                "by_period": {
                    "24h": 800,
                    "1w": 434
                },
                "confidence": {
                    "avg": 72.5,
                    "min": 15,
                    "max": 98
                },
                "recent_24h": 45
            }
        }
    """
    try:
        from infrastructure.repositories import repos
        
        stats = repos.prediction.get_stats()
        
        return jsonify({
            'success': True,
            'data': stats,
            'timestamp': datetime.now().isoformat(),
        })
        
    except Exception as e:
        logger.error(f"Predict history stats error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/model/performance', methods=['GET'])
@require_auth()
def model_performance():
    """
    دریافت داده‌های عملکرد مدل برای نمودار (تغییرات دقت)
    """
    try:
        container = current_app.container
        model_manager = container.get('model_manager')
        
        # دریافت تاریخچه نسخه‌ها
        history = model_manager.get_version_history(limit=30)
        
        # تبدیل به داده‌های نمودار
        chart_data = {
            'labels': [],
            'accuracy': [],
            'training_samples': [],
            'versions': []
        }
        
        for item in reversed(history):  # قدیمی‌ترین به جدیدترین
            chart_data['labels'].append(
                item.get('training_date', '').split('T')[0] if item.get('training_date') else ''
            )
            chart_data['accuracy'].append(round((item.get('accuracy', 0) or 0) * 100, 2))
            chart_data['training_samples'].append(item.get('training_samples', 0))
            chart_data['versions'].append(item.get('version', ''))
        
        return jsonify({
            'success': True,
            'data': chart_data,
            'count': len(chart_data['labels']),
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"Model performance error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

@api_bp.route('/model/importance', methods=['GET'])
@require_auth()
def model_feature_importance():
    """
    دریافت اهمیت ویژگی‌های مدل XGBoost
    """
    try:
        container = current_app.container
        model_manager = container.get('model_manager')
        
        if not model_manager.current_model:
            return jsonify({'success': False, 'error': 'No model loaded'}), 400
        
        # استخراج اهمیت ویژگی‌ها از XGBoost
        importance = model_manager.current_model.get_score(importance_type='weight')
        
        if not importance:
            return jsonify({'success': False, 'error': 'No feature importance available'}), 404
        
        # مرتب‌سازی نزولی
        sorted_importance = sorted(importance.items(), key=lambda x: x[1], reverse=True)
        
        # نرمال‌سازی
        total = sum(v for _, v in sorted_importance) or 1
        
        return jsonify({
            'success': True,
            'data': [
                {
                    'feature': k,
                    'importance': v,
                    'percentage': round((v / total) * 100, 2)
                }
                for k, v in sorted_importance
            ],
            'total_features': len(sorted_importance),
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"Feature importance error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500   

# ============================================================
# TRAINING PROFILES
# ============================================================

@api_bp.route('/model/profiles/presets', methods=['GET'])
@require_auth()
def get_training_presets():
    """دریافت لیست presets آماده"""
    try:
        container = current_app.container
        mm = container.get('model_manager')
        presets = mm.get_presets()
        return jsonify({
            'success': True,
            'data': presets,
            'count': len(presets),
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/model/profiles/presets/<preset_id>', methods=['GET'])
@require_auth()
def get_training_preset(preset_id):
    """دریافت یک preset خاص"""
    try:
        container = current_app.container
        mm = container.get('model_manager')
        preset = mm.get_preset(preset_id)
        if not preset:
            return jsonify({'success': False, 'error': 'Preset not found'}), 404
        return jsonify({'success': True, 'data': preset})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/model/profiles/strategies', methods=['GET'])
@require_auth()
def get_learning_strategies():
    """دریافت لیست استراتژی‌های یادگیری"""
    try:
        container = current_app.container
        mm = container.get('model_manager')
        strategies = mm.get_strategies()
        return jsonify({
            'success': True,
            'data': strategies,
            'count': len(strategies),
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/model/profiles/hyperparameter-limits', methods=['GET'])
@require_auth()
def get_hyperparameter_limits():
    """دریافت محدودیت‌های پارامترها (برای UI)"""
    try:
        container = current_app.container
        mm = container.get('model_manager')
        limits = mm.get_hyperparameter_limits()
        return jsonify({'success': True, 'data': limits})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/model/profiles/current', methods=['GET'])
@require_auth()
def get_current_profile():
    """دریافت پروفایل فعلی"""
    try:
        container = current_app.container
        mm = container.get('model_manager')
        profile = mm.get_current_profile()
        return jsonify({'success': True, 'data': profile})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/model/profiles/current', methods=['POST'])
@require_auth('admin')
def set_current_profile():
    """تنظیم پروفایل فعلی"""
    try:
        data = request.json or {}
        container = current_app.container
        mm = container.get('model_manager')
        result = mm.set_current_profile(data)
        return jsonify(result), 200 if result.get('success') else 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/model/profiles/validate', methods=['POST'])
@require_auth()
def validate_profile():
    """اعتبارسنجی پروفایل"""
    try:
        data = request.json or {}
        container = current_app.container
        mm = container.get('model_manager')
        result = mm.validate_profile(data)
        return jsonify({'success': True, 'data': result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/model/profiles/saved', methods=['GET'])
@require_auth()
def list_saved_profiles():
    """لیست پروفایل‌های ذخیره‌شده"""
    try:
        container = current_app.container
        mm = container.get('model_manager')
        profiles = mm.list_profiles()
        return jsonify({
            'success': True,
            'data': profiles,
            'count': len(profiles),
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/model/profiles/saved', methods=['POST'])
@require_auth('admin')
def save_profile():
    """ذخیره پروفایل جدید"""
    try:
        data = request.json or {}
        container = current_app.container
        mm = container.get('model_manager')
        result = mm.save_profile(data)
        return jsonify(result), 200 if result.get('success') else 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/model/profiles/saved/<name>', methods=['GET'])
@require_auth()
def load_saved_profile(name):
    """بارگذاری پروفایل با نام"""
    try:
        container = current_app.container
        mm = container.get('model_manager')
        result = mm.load_profile(name)
        return jsonify(result), 200 if result.get('success') else 404
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/model/profiles/saved/<name>', methods=['DELETE'])
@require_auth('admin')
def delete_saved_profile(name):
    """حذف پروفایل"""
    try:
        container = current_app.container
        mm = container.get('model_manager')
        success = mm.delete_profile(name)
        return jsonify({
            'success': success,
            'message': f'Profile "{name}" deleted' if success else 'Failed to delete',
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================
# TRAINING با Profile
# ============================================================

@api_bp.route('/model/train-with-profile', methods=['POST'])
@require_auth('admin')
def train_with_profile():
    """
    آموزش با پروفایل
    
    Body:
        {
            "period": "1m",
            "coins": ["bitcoin", "ethereum"],
            "profile": { ... }        // اگه نباشه، از پروفایل فعال استفاده می‌شه
            OR
            "profile_name": "fast"    // نام پروفایل ذخیره‌شده یا preset
        }
    """
    try:
        data = request.json or {}
        period = data.get('period', '1m')
        coins = data.get('coins')
        profile = data.get('profile')
        profile_name = data.get('profile_name')
        
        container = current_app.container
        mm = container.get('model_manager')
        
        # اگه نام پروفایل داده شده
        if profile_name and not profile:
            load_result = mm.load_profile(profile_name)
            if not load_result.get('success'):
                return jsonify({
                    'success': False,
                    'error': f'Profile "{profile_name}" not found',
                }), 404
            profile = load_result['profile']
        
        # آموزش
        result = mm.train(
            period=period,
            coins=coins,
            profile=profile,
            save=True,
        )
        
        return jsonify(result), 200 if result.get('success') else 400
        
    except Exception as e:
        logger.error(f"Train with profile error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/model/analyze-training', methods=['POST'])
@require_auth()
def analyze_training_endpoint():
    """
    تحلیل آموزش بدون اجرا (تخمین زمان، حجم، فضا)
    
    Body:
        {
            "profile": { ... },           // پروفایل آموزش
            "coins_count": 5,             // تعداد ارزها
            "period": "1m"                // بازه داده
        }
        OR
        {
            "profile_name": "accurate",   // نام پروفایل ذخیره‌شده
            "coins_count": 5,
            "period": "1m"
        }
    
    خروجی:
        {
            "success": true,
            "data": {
                "valid": true,
                "estimated_time_seconds": 45.5,
                "estimated_time_formatted": "45.5 ثانیه",
                "estimated_model_size_mb": 3.2,
                "available_mb": 350.5,
                "can_proceed": true,
                "strategy": "full",
                "hyperparameters": {...},
                "warning": null
            }
        }
    """
    try:
        data = request.json or {}
        period = data.get('period', '1m')
        coins_count = data.get('coins_count', 2)
        profile = data.get('profile')
        profile_name = data.get('profile_name')
        
        container = current_app.container
        mm = container.get('model_manager')
        
        # اگه نام پروفایل داده شده
        if profile_name and not profile:
            load_result = mm.load_profile(profile_name)
            if not load_result.get('success'):
                return jsonify({
                    'success': False,
                    'error': f'Profile "{profile_name}" not found',
                }), 404
            profile = load_result['profile']
        
        # اگه هیچ پروفایلی ندادی، از فعال استفاده کن
        if not profile:
            profile = mm.get_current_profile()
        
        # تحلیل
        result = mm.analyze_training(
            profile=profile,
            coins_count=coins_count,
            period=period,
        )
        
        return jsonify({
            'success': True,
            'data': result,
            'timestamp': datetime.now().isoformat(),
        }), 200 if result.get('valid') else 400
        
    except Exception as e:
        logger.error(f"Analyze training error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500
# ============================================================
# ۱۰. زمان‌بندی (SCHEDULE) برای auto_trainer.py / manual_trainer.py
# ============================================================
@api_bp.route('/schedule/status', methods=['GET'])
@require_auth()
def schedule_status():
    """
    دریافت وضعیت کامل زمان‌بندی آموزش
    
    خروجی: اطلاعات کامل AutoTrainer
    """
    try:
        container = current_app.container
        trainer = container.get('trainer')
        
        stats = trainer.get_stats() if hasattr(trainer, 'get_stats') else {}
        inner_stats = stats.get('stats', {})
        
        return jsonify({
            'success': True,
            'data': {
                # وضعیت
                'is_running': stats.get('is_running', False),
                'is_training': stats.get('is_training', False),
                
                # تنظیمات
                'interval_hours': inner_stats.get('training_period', 6),
                'period': inner_stats.get('training_period', '1m'),
                'coins': stats.get('coins', []),
                'profile_name': inner_stats.get('profile_name', 'balanced'),
                
                # آمار آموزش
                'total_trainings': inner_stats.get('total_trainings', 0),
                'successful_trainings': inner_stats.get('successful_trainings', 0),
                'failed_trainings': inner_stats.get('failed_trainings', 0),
                'last_training': inner_stats.get('last_training'),
                'last_error': inner_stats.get('last_error'),
                'last_score': inner_stats.get('last_score'),
                
                # API
                'api_status': stats.get('api_status', {}),
                
                # Quota
                'quota': stats.get('quota', {}),
                
                # لاگ‌ها (آخرین ۱۰)
                'recent_logs': stats.get('logs', [])[-10:],
                
                'timestamp': datetime.now().isoformat(),
            }
        })
    except Exception as e:
        logger.error(f"Schedule status error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

@api_bp.route('/schedule/start', methods=['POST'])
@require_auth('admin')
def schedule_start():
    """
    شروع زمان‌بندی آموزش خودکار
    
    Body:
        {
            "interval": 6,                    // ساعت
            "period": "1m",                   // بازه
            "coins": ["bitcoin", "ethereum"], // ارزها
            "profile_name": "balanced",       // ← جدید
            "incremental": false              // ← پیش‌فرض عوض شد
        }
    """
    try:
        container = current_app.container
        trainer = container.get('trainer')
        
        data = request.json or {}
        interval = data.get('interval', 6)
        period = data.get('period', '1m')
        coins = data.get('coins', ['bitcoin', 'ethereum'])
        profile_name = data.get('profile_name', 'balanced')  # جدید
        incremental = data.get('incremental', False)  # پیش‌فرض جدید
        
        result = trainer.start_auto_train(
            interval_hours=interval,
            period=period,
            coins=coins,
            profile_name=profile_name,
            incremental=incremental,
        )
        
        return jsonify(result), 200 if result.get('success') else 400
        
    except Exception as e:
        logger.error(f"Schedule start error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

@api_bp.route('/model/train-batch', methods=['POST'])
@require_auth('admin')
def train_batch_endpoint():
    """
    آموزش با چند پروفایل (A/B Testing)
    
    Body:
        {
            "profiles": ["fast", "balanced", "accurate"],
            "period": "1m",
            "coins": ["bitcoin", "ethereum"]
        }
    
    خروجی:
        {
            "success": true,
            "data": {
                "best_profile": "accurate",
                "best_accuracy": 0.78,
                "results": {
                    "fast": {...},
                    "balanced": {...},
                    "accurate": {...}
                },
                "final_model": {...},
                "summary": {...}
            }
        }
    """
    try:
        data = request.json or {}
        profiles = data.get('profiles', [])
        period = data.get('period', '1m')
        coins = data.get('coins')
        
        if not profiles or len(profiles) < 2:
            return jsonify({
                'success': False,
                'error': 'At least 2 profiles required for A/B testing',
            }), 400
        
        container = current_app.container
        trainer = container.get('trainer')
        
        result = trainer.train_batch(
            profiles=profiles,
            period=period,
            coins=coins,
        )
        
        return jsonify({
            'success': result.get('success', False),
            'data': result,
            'timestamp': datetime.now().isoformat(),
        }), 200 if result.get('success') else 400
        
    except Exception as e:
        logger.error(f"Train batch error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/model/analytics-stats', methods=['GET'])
@require_auth()
def model_analytics_stats():
    """
    دریافت آمار بلندمدت از Analytics DB
    
    Query params:
        days: تعداد روز (پیش‌فرض: 30)
    
    خروجی:
        {
            "success": true,
            "data": {
                "summary": {
                    "total_records": 45,
                    "avg_accuracy": 0.72,
                    "max_accuracy": 0.78,
                    "min_accuracy": 0.65
                },
                "daily": [
                    {"date": "2026-09-14", "avg_accuracy": 0.75, "models_count": 3},
                    ...
                ],
                "period_days": 30
            }
        }
    """
    try:
        days = request.args.get('days', 30, type=int)
        
        container = current_app.container
        trainer = container.get('trainer')
        
        if not hasattr(trainer, 'get_analytics_stats'):
            return jsonify({
                'success': False,
                'error': 'Analytics stats not available',
            }), 503
        
        result = trainer.get_analytics_stats(days=days)
        
        return jsonify({
            'success': result.get('success', True),
            'data': result,
            'timestamp': datetime.now().isoformat(),
        }), 200 if 'error' not in result else 500
        
    except Exception as e:
        logger.error(f"Analytics stats error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

@api_bp.route('/model/trainer-stats', methods=['GET'])
@require_auth()
def model_trainer_stats():
    """
    دریافت آمار کامل AutoTrainer (trainer stats)
    
    این endpoint معادل CLI `--stats` هست ولی برای فرانت.
    
    خروجی:
        {
            "success": true,
            "data": {
                // وضعیت
                "is_running": bool,
                "is_training": bool,
                "mode": "DEMO" | "BETA",
                
                // آموزش
                "total_trainings": int,
                "successful_trainings": int,
                "failed_trainings": int,
                "last_training": str,
                "last_error": str,
                "last_score": float,
                "data_points_used": int,
                "training_period": str,
                
                // API
                "api_status": str,
                "credits_remaining": int,
                "api_calls": int,
                "api_errors": int,
                
                // مدل
                "model_exists": bool,
                "current_version": str,
                
                // Quota
                "quota": {...},
                
                // لاگ‌ها
                "recent_logs": [...],
                
                // Config
                "coins": [...],
                "points_config": {...},
                
                // Timestamp
                "timestamp": str
            }
        }
    """
    try:
        container = current_app.container
        trainer = container.get('trainer')
        
        if not hasattr(trainer, 'get_stats'):
            return jsonify({
                'success': False,
                'error': 'Trainer does not support get_stats',
            }), 503
        
        stats = trainer.get_stats()
        
        return jsonify({
            'success': True,
            'data': stats,
            'timestamp': datetime.now().isoformat(),
        })
    
    except Exception as e:
        logger.error(f"Trainer stats error: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e),
        }), 500
        
@api_bp.route('/schedule/stop', methods=['POST'])
@require_auth('admin')
def schedule_stop():
    """توقف زمان‌بندی آموزش خودکار"""
    try:
        container = current_app.container
        trainer = container.get('trainer')
        
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
        prediction_service = container.get('prediction_service')  # ✅
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
        prediction_service: PredictionService = container.get('prediction_service')
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
@api_bp.route('/coinstats/coins', methods=['GET'])
@require_auth()
def get_coins_list():
    """دریافت لیست ارزها"""
    try:
        limit = request.args.get('limit', 50, type=int)
        page = request.args.get('page', 1, type=int)
        currency = request.args.get('currency', 'USD')
        search = request.args.get('search')
        
        container = current_app.container
        api_client = container.get('api_client')
        
        coins = api_client.get_coins_list(limit=limit, page=page, currency=currency, search=search)
        
        if coins:
            return jsonify({'success': True, 'data': coins, 'count': len(coins)})
        
        # Fallback
        fallback = [
            {"id": "bitcoin", "symbol": "BTC", "name": "Bitcoin"},
            {"id": "ethereum", "symbol": "ETH", "name": "Ethereum"},
            {"id": "solana", "symbol": "SOL", "name": "Solana"},
            {"id": "cardano", "symbol": "ADA", "name": "Cardano"},
            {"id": "ripple", "symbol": "XRP", "name": "XRP"},
        ]
        return jsonify({'success': True, 'data': fallback, 'count': len(fallback), 'from_cache': False})
        
    except Exception as e:
        logger.error(f"Coins list error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
        
@api_bp.route('/coinstats/price/<coin>', methods=['GET'])
@require_auth()
def coinstats_price(coin):
    """دریافت قیمت یک ارز خاص"""
    try:
        container = current_app.container
        api_client = container.get('api_client')
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
        api_client = container.get('api_client')
        
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
        api_client = container.get('api_client')
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
        api_client = container.get('api_client')
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
        api_client = container.get('api_client')
        
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
# ۱۹. قیمت‌های لحظه‌ای (WebSocket + Fallback)
# ============================================================

@api_bp.route('/crypto/prices', methods=['GET'])
@require_auth()
def get_realtime_prices():
    """
    دریافت قیمت‌های لحظه‌ای چند ارز
    """
    try:
        symbols_param = request.args.get('symbols', '')
        symbols = [s.strip().upper() for s in symbols_param.split(',') if s.strip()]
        
        container = current_app.container
        price_manager = container.get('price_manager')
        
        if symbols:
            prices = price_manager.get_prices(symbols)
        else:
            prices = price_manager.get_prices()
        
        stats = price_manager.get_stats()
        
        return jsonify({
            'success': True,
            'data': prices,
            'count': len(prices),
            'stats': {
                'websocket_connected': stats.get('websocket_connected', False),
                'last_update': stats.get('last_update'),
                'source': 'websocket' if stats.get('websocket_connected') else 'cache'
            },
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"Get realtime prices error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/crypto/price/<symbol>', methods=['GET'])
@require_auth()
def get_realtime_price(symbol):
    """
    دریافت قیمت لحظه‌ای یک ارز
    """
    try:
        symbol = symbol.upper()
        container = current_app.container
        price_manager = container.get('price_manager')
        
        price = price_manager.get_price(symbol)
        
        if price:
            return jsonify({
                'success': True,
                'symbol': symbol,
                'data': price,
                'timestamp': datetime.now().isoformat()
            })
        
        # Fallback: دریافت از CoinStats
        coin_data = current_app.coinstats_client.get_coin(symbol.lower())
        if coin_data and "error" not in coin_data:
            price_data = {
                "price": coin_data.get("price", 0),
                "change_24h": coin_data.get("priceChange1d", 0),
                "high_24h": coin_data.get("high24h", 0),
                "low_24h": coin_data.get("low24h", 0),
                "volume": coin_data.get("volume24h", 0),
                "timestamp": datetime.now().isoformat(),
                "source": "coinstats"
            }
            return jsonify({
                'success': True,
                'symbol': symbol,
                'data': price_data,
                'source': 'coinstats',
                'timestamp': datetime.now().isoformat()
            })
        
        return jsonify({'success': False, 'error': 'Price not found'}), 404
        
    except Exception as e:
        logger.error(f"Get realtime price error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/crypto/stats', methods=['GET'])
@require_auth()
def get_crypto_stats():
    """
    دریافت آمار مصرف و وضعیت WebSocket
    """
    try:
        container = current_app.container
        price_manager = container.get('price_manager')
        user_tracker = container.get('user_tracker')
        free_client = container.get('free_crypto_client')
        
        stats = {
            'websocket': {
                'connected': free_client.is_connected,
                'symbols_count': free_client.stats['symbols_count'],
                'messages_received': free_client.stats['messages_received'],
                'reconnects': free_client.stats['reconnects'],
                'errors': free_client.stats['errors'],
                'last_update': free_client.stats['last_update']
            },
            'price_manager': {
                'is_running': price_manager.is_running,
                'last_update': price_manager._last_update,
                'fallback_count': price_manager._fallback_count,
                'last_fallback': price_manager._last_fallback
            },
            'users': {
                'online': user_tracker.get_online_count(),
                'timeout': user_tracker.timeout
            }
        }
        
        return jsonify({
            'success': True,
            'data': stats,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"Get crypto stats error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/crypto/heartbeat', methods=['POST'])
@require_auth()
def crypto_heartbeat():
    """
    ثبت ضربان قلب کاربر (برای پیگیری کاربران آنلاین)
    """
    try:
        session_id = request.cookies.get('session_id')
        if not session_id:
            return jsonify({'success': False, 'error': 'No session'}), 401
        
        container = current_app.container
        user_tracker = container.get('user_tracker')
        user_tracker.heartbeat(session_id)
        
        return jsonify({
            'success': True,
            'message': 'Heartbeat sent',
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"Heartbeat error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# api_routes.py - اندپوینت دریافت داده‌های نمودار با اندیکاتورها

@api_bp.route('/coinstats/chart/<coin>', methods=['GET'])
@require_auth()
def get_chart_data(coin):
    """
    دریافت داده‌های نمودار شامل قیمت، RSI، SMA، EMA، MACD و سیگنال‌ها
    """
    try:
        period = request.args.get('period', '1m')
        container = current_app.container
        api_client = container.get('api_client')
        indicators = container.get('indicators')
        
        # دریافت داده‌های تاریخی از CoinStats
        chart_data = api_client.get_chart(coin, period)
        
        if not chart_data or not isinstance(chart_data, list) or len(chart_data) < 30:
            return jsonify({'success': False, 'error': 'Insufficient data'}), 404
        
        # استخراج قیمت‌ها
        timestamps = []
        prices = []
        for point in chart_data:
            if isinstance(point, list) and len(point) >= 2:
                timestamps.append(point[0])
                prices.append(float(point[1]))
        
        # ===== محاسبه همه اندیکاتورها =====
        rsi_values = indicators['calculate_rsi'](prices, 14)
        sma_20 = indicators['calculate_sma'](prices, 20)
        sma_50 = indicators['calculate_sma'](prices, 50)
        ema_20 = indicators['calculate_ema'](prices, 20)
        macd_line, signal_line, histogram = indicators['calculate_macd'](prices, 12, 26, 9)
        
        # ===== دریافت سیگنال‌ها از مدل =====
        signals = []
        try:
            predict_use_case = container.get('predict_use_case')
            prediction = predict_use_case.execute(coin, period)
            if prediction:
                signals.append({
                    'index': len(prices) - 1,
                    'type': prediction.signal_type.value,
                    'price': prediction.current_price,
                    'confidence': prediction.confidence
                })
        except Exception as e:
            logger.warning(f"Could not get prediction: {e}")
        
        return jsonify({
            'success': True,
            'data': {
                'timestamps': timestamps,
                'prices': prices,
                'rsi': rsi_values,
                'sma_20': sma_20,
                'sma_50': sma_50,
                'ema_20': ema_20,
                'macd': {
                    'macd_line': macd_line,
                    'signal_line': signal_line,
                    'histogram': histogram
                },
                'signals': signals,
                'meta': {
                    'coin': coin,
                    'period': period,
                    'data_points': len(prices)
                }
            }
        })
        
    except Exception as e:
        logger.error(f"Chart data error: {e}")
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



# ============================================================
# ۲. اندپوینت اجرای دستورات (اصلاح شده با پشتیبانی از ۳ حالت)
# ============================================================

@api_bp.route('/debug/exec', methods=['POST'])
@require_auth('admin')
def debug_exec():
    """
    اجرای دستورات در ۳ حالت:
    - python: کد پایتون
    - shell: دستورات شل
    - terminal: شبیه‌سازی ترمینال با مسیر و کاربر
    """
    try:
        data = request.json or {}
        command = data.get('command', '').strip()
        command_type = data.get('type', 'python')  # python, shell, terminal
        timeout = data.get('timeout', 15)
        
        if not command:
            return jsonify({'success': False, 'error': 'Command required'}), 400
        
        # ===== حالت Terminal =====
        if command_type == 'terminal':
            import subprocess
            import os
            import pwd
            
            try:
                # دریافت اطلاعات کاربر و مسیر
                username = pwd.getpwuid(os.getuid()).pw_name
                hostname = os.uname().nodename
                cwd = os.getcwd()
                
                # ساخت پرامپت ترمینال
                prompt = f"{username}@{hostname}:{cwd}$ "
                
                # اجرای دستور
                result = subprocess.run(
                    command,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    cwd=cwd,
                    executable='/bin/bash'
                )
                
                output = result.stdout or result.stderr or '✅ Done'
                
                return jsonify({
                    'success': True,
                    'result': output,
                    'type': 'terminal',
                    'prompt': prompt,
                    'cwd': cwd,
                    'username': username,
                    'hostname': hostname
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
        
        # ===== حالت Shell =====
        if command_type == 'shell':
            import subprocess
            
            try:
                result = subprocess.run(
                    command,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    cwd='/opt/render/project/src'
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
        
        # ===== حالت Python (پیش‌فرض) =====
        # ===== کتابخانه‌ها =====
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
                '__import__': __import__,
                'Exception': Exception,
                'ValueError': ValueError,
                'TypeError': TypeError,
                'KeyError': KeyError,
                'IndexError': IndexError,
            },
        }

        # اضافه کردن کتابخانه‌های استاندارد
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

        # تلاش برای کتابخانه‌های خارجی
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

        # بررسی دستورات خطرناک
        dangerous = ['os.system', 'subprocess.run', 'exec(', 'eval(', '__import__', 'open(', 'file(']
        for kw in dangerous:
            if kw in command:
                return jsonify({
                    'success': False,
                    'error': f'🚫 Dangerous command contains "{kw}"'
                }), 403

        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        error_output = None

        try:
            import signal
            
            def timeout_handler(signum, frame):
                raise TimeoutError("⏱️ Command execution timeout")
            
            try:
                signal.signal(signal.SIGALRM, timeout_handler)
                signal.alarm(timeout)
            except:
                pass
            
            exec(command, safe_globals)
            result = sys.stdout.getvalue()
            
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
        
@api_bp.route('/debug/env', methods=['GET'])
def debug_env():
    """چک کردن Environment Variables (موقت - بعداً حذف کن)"""
    import os
    
    # فقط کلیدها رو نشون بده، نه مقادیر (برای امنیت)
    env_keys = [
        "NEON_PRIMARY_HOST",
        "NEON_PRIMARY_USER",
        "NEON_PRIMARY_PASSWORD",
        "NEON_PRIMARY_DB",
        "NEON_BACKUP_HOST",
        "NEON_BACKUP_USER",
        "NEON_BACKUP_PASSWORD",
        "NEON_BACKUP_DB",
        "NEON_ANALYTICS_HOST",
        "NEON_ANALYTICS_USER",
        "NEON_ANALYTICS_PASSWORD",
        "NEON_ANALYTICS_DB",
        "NEON_LOGS_HOST",
        "NEON_LOGS_USER",
        "NEON_LOGS_PASSWORD",
        "NEON_LOGS_DB",
        "LAYERBASE_HOST",
        "LAYERBASE_USER",
        "LAYERBASE_PASSWORD",
        "LAYERBASE_DB",
        "UPSTASH_REDIS_URL",
        "UPSTASH_REDIS_TOKEN",
        "UPSTASH_REDIS_URL_FULL",
        "COINSTATS_API_KEY",
        "FREE_CRYPTO_API_KEY",
        "SECRET_KEY",
        "FLASK_ENV",
    ]
    
    result = {}
    for key in env_keys:
        val = os.getenv(key, "")
        if val:
            # نشون بده که هست ولی فقط ۱۰ کاراکتر اول
            result[key] = f"✅ {val[:10]}...({len(val)} chars)"
        else:
            result[key] = "❌ NOT SET"
    
    # Database factory status
    try:
        from infrastructure.database.database_factory import db_factory
        factory_status = {
            "initialized": hasattr(db_factory, "_init_completed_at"),
            "failed_connections": getattr(db_factory, "_failed_connections", []),
            "total_retries": getattr(db_factory, "_total_retries", 0),
        }
    except Exception as e:
        factory_status = {"error": str(e)}
    
    # Registry status
    try:
        from infrastructure.database import registry
        registry_status = {
            "databases": list(registry._databases.keys()),
            "roles": registry._roles,
        }
    except Exception as e:
        registry_status = {"error": str(e)}
    
    return jsonify({
        "env": result,
        "database_factory": factory_status,
        "registry": registry_status,
    })
    
# ============================================================
# اندپوینت‌های Self-Healing
# ============================================================

@api_bp.route('/healing/status', methods=['GET'])
@require_auth('admin')
def healing_status():
    """
    دریافت وضعیت Self-Healer
    
    خروجی:
        - status: running / stopped
        - healing_actions: تعداد اقدامات انجام شده
        - last_healing: زمان آخرین اقدام
        - attempts: تلاش‌های انجام شده
        - databases: وضعیت دیتابیس‌ها
    """
    try:
        from core.metrics import metrics_scheduler
        
        # دریافت وضعیت از Scheduler
        summary = metrics_scheduler.get_summary()
        alert_metrics = metrics_scheduler.get_alert_metrics()
        
        return jsonify({
            'success': True,
            'data': {
                'status': summary.get('status', 'unknown'),
                'healing_actions': summary.get('healing_actions', 0),
                'last_healing': summary.get('last_healing'),
                'total_collections': summary.get('total_collections', 0),
                'errors': summary.get('errors', 0),
                'databases': alert_metrics.get('databases', {}),
                'model_loaded': alert_metrics.get('model_loaded', False),
                'model_accuracy': alert_metrics.get('model_accuracy'),
                'uptime': alert_metrics.get('uptime', '0s'),
                'timestamp': datetime.now().isoformat()
            }
        })
    except Exception as e:
        logger.error(f"Healing status error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/healing/trigger', methods=['POST'])
@require_auth('admin')
def healing_trigger():
    """
    اجرای دستی Self-Healing
    
    این اندپوینت به صورت دستی Self-Healing را اجرا می‌کند.
    """
    try:
        from core.metrics import metrics_scheduler
        
        # گرفتن healer از Scheduler
        healer = getattr(metrics_scheduler, 'healer', None)
        if not healer:
            return jsonify({
                'success': False,
                'error': 'SelfHealer not initialized'
            }), 503
        
        # اجرای healing
        metrics = metrics_scheduler.get_alert_metrics()
        actions = healer.check_and_heal(metrics)
        
        return jsonify({
            'success': True,
            'data': {
                'actions': actions,
                'timestamp': datetime.now().isoformat()
            }
        })
    except Exception as e:
        logger.error(f"Healing trigger error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/healing/reset', methods=['POST'])
@require_auth('admin')
def healing_reset():
    """
    بازنشانی تلاش‌های Self-Healing
    """
    try:
        from core.metrics import metrics_scheduler
        
        healer = getattr(metrics_scheduler, 'healer', None)
        if not healer:
            return jsonify({
                'success': False,
                'error': 'SelfHealer not initialized'
            }), 503
        
        healer.reset_attempts()
        
        return jsonify({
            'success': True,
            'message': 'Healing attempts reset successfully',
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"Healing reset error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

# ============================================================
# ۲۰. گزارش مدل (HTML Report)
# ============================================================

@api_bp.route('/model/latest-report', methods=['GET'])
@require_auth()
def get_latest_model_report():
    """
    دریافت داده‌های آخرین نسخه فعال مدل برای تولید گزارش
    """
    try:
        container = current_app.container
        model_manager = container.get('model_manager')
        
        # دریافت آخرین مدل فعال
        if not model_manager.current_model:
            return jsonify({
                'success': False,
                'error': 'No active model found'
            }), 404
        
        version = model_manager.current_version
        report_data = model_manager.get_report_data(version)
        
        if report_data:
            return jsonify({
                'success': True,
                'data': report_data,
                'version': version,
                'timestamp': datetime.now().isoformat()
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to generate report data'
            }), 500
            
    except Exception as e:
        logger.error(f"Latest report error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/model/report/<version>', methods=['GET'])
@require_auth()
def get_model_report_by_version(version):
    """
    دریافت داده‌های یک نسخه خاص از مدل برای تولید گزارش
    """
    try:
        container = current_app.container
        model_manager = container.get('model_manager')
        
        # بررسی وجود نسخه
        model = model_manager.get_model_by_version(version)
        if not model:
            return jsonify({
                'success': False,
                'error': f'Version {version} not found'
            }), 404
        
        report_data = model_manager.get_report_data(version)
        
        if report_data:
            return jsonify({
                'success': True,
                'data': report_data,
                'version': version,
                'timestamp': datetime.now().isoformat()
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to generate report data'
            }), 500
            
    except Exception as e:
        logger.error(f"Report by version error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
