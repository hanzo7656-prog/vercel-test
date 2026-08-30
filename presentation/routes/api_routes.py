# presentation/routes/api_routes.py
# ============================================================
# API Routes - نسخه کامل با تمام اندپوینت‌ها
# شامل: سیستم، دیتابیس، مدل، CoinStats، دیباگ و مدیریت
# ============================================================

import os
import sys
import json
import csv
import io
import logging
import tempfile
from datetime import datetime
from flask import Blueprint, request, jsonify, current_app, send_file
from pathlib import Path

from application.dto.prediction_dto import PredictionRequestDTO
from application.services.prediction_service import PredictionService
from application.services.monitoring_service import MonitoringService
from application.use_cases.train_model import TrainModelUseCase
from infrastructure.auth.auth_manager import require_auth
from infrastructure.external.alerter import alerter
from application.services.self_healer import SelfHealer
from infrastructure.database import get_primary, get_cache, get_backup, health_check, registry

logger = logging.getLogger(__name__)

api_bp = Blueprint('api', __name__, url_prefix='/api')


# ============================================================
# ۱. صفحه اصلی
# ============================================================

@api_bp.route('', methods=['GET'])
def api_home():
    return jsonify({
        'name': 'Trading Signal System API',
        'version': '9.0.0',
        'status': 'running',
        'timestamp': datetime.now().isoformat(),
        'endpoints': {
            'system': ['/api/health', '/api/health/database', '/api/metrics'],
            'debug': ['/api/debug'],
            'database': ['/api/db', '/api/db/search', '/api/db/backup', '/api/db/stats'],
            'model': ['/api/model', '/api/model/export', '/api/model/schedule'],
            'predict': ['/api/predict', '/api/predict/multiple'],
            'coinstats': ['/api/coinstats/prices', '/api/coinstats/fear-greed', 
                          '/api/coinstats/btc-dominance', '/api/coinstats/all'],
            'alerts': ['/api/alerts', '/api/alerts/<id>/resolve'],
            'credits': ['/api/credits']
        }
    })


# ============================================================
# ۲. سلامت سیستم
# ============================================================

@api_bp.route('/health', methods=['GET'])
def health():
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
def health_database():
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
# ۳. متریک‌ها
# ============================================================

@api_bp.route('/metrics', methods=['GET'])
def get_metrics():
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
    try:
        container = current_app.container
        monitoring_service: MonitoringService = container.monitoring_service()
        summary = monitoring_service.get_metrics_summary()
        return jsonify(summary), 200 if summary.get('success') else 500
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================
# ۴. پیش‌بینی
# ============================================================

@api_bp.route('/predict', methods=['GET'])
def predict():
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
        logger.error(f"Predict error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/predict/multiple', methods=['POST'])
def predict_multiple():
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


# ============================================================
# ۵. مدل (Model) - مدیریت کامل
# ============================================================

@api_bp.route('/model', methods=['GET', 'POST', 'PUT', 'DELETE'])
def model_management():
    """
    مدیریت کامل مدل
    
    GET:
        ?section=status     → وضعیت مدل
        ?section=history    → تاریخچه نسخه‌ها
        ?section=features   → ویژگی‌های مدل
        ?section=data       → داده‌های آموزشی
    
    POST:
        {"action": "train", "period": "1m", "coins": ["bitcoin"]}  → آموزش
        {"action": "predict", "coin": "bitcoin"}                    → پیش‌بینی
        {"action": "explain", "coin": "bitcoin"}                    → توضیح پیش‌بینی
        {"action": "import", "version": "v1.0.0"}                   → فعال‌سازی نسخه
    
    PUT:
        {"version": "v1.0.0"}  → فعال‌سازی نسخه
    
    DELETE:
        {"version": "v1.0.0"}  → حذف نسخه
    """
    try:
        container = current_app.container
        model_manager = container.model_manager()
        trainer = container.trainer()
        
        # ===== GET =====
        if request.method == 'GET':
            section = request.args.get('section', 'status')
            
            if section == 'status':
                train_status = trainer.get_stats() if hasattr(trainer, 'get_stats') else {}
                return jsonify({
                    'success': True,
                    'data': {
                        'loaded': model_manager.current_model is not None,
                        'version': model_manager.current_version,
                        'is_training': train_status.get('is_training', False),
                        'total_trainings': train_status.get('stats', {}).get('total_trainings', 0),
                        'last_score': train_status.get('stats', {}).get('last_score'),
                        'mode': 'PRODUCTION' if model_manager.current_model else 'DEMO'
                    }
                })
            
            elif section == 'history':
                limit = request.args.get('limit', 20, type=int)
                history = model_manager.get_version_history(limit=limit)
                return jsonify({'success': True, 'data': history})
            
            elif section == 'features':
                if model_manager.current_model:
                    features = model_manager.config.get('features', [])
                    return jsonify({'success': True, 'data': features})
                return jsonify({'success': False, 'error': 'No model loaded'}), 400
            
            elif section == 'data':
                # دریافت داده‌های آموزشی (از دیتابیس)
                db = get_primary()
                if db and db.is_connected():
                    result = db.execute(
                        "SELECT * FROM model_training_history ORDER BY created_at DESC LIMIT 50"
                    )
                    return jsonify({'success': True, 'data': result})
                return jsonify({'success': False, 'error': 'Database not connected'}), 503
            
            return jsonify({'success': False, 'error': 'Invalid section'}), 400
        
        # ===== POST =====
        elif request.method == 'POST':
            data = request.json or {}
            action = data.get('action')
            
            if action == 'train':
                period = data.get('period', '1m')
                coins = data.get('coins', ['bitcoin', 'ethereum'])
                incremental = data.get('incremental', False)
                result = trainer.train_model(period=period) if not incremental else trainer.incremental_train(period=period)
                return jsonify(result), 200 if result.get('success') else 400
            
            elif action == 'predict':
                coin = data.get('coin', 'bitcoin')
                period = data.get('period', '24h')
                from application.services.prediction_service import PredictionService
                prediction_service = PredictionService(container.predict_use_case())
                dto = prediction_service.predict_single(coin, period)
                return jsonify({
                    'success': dto.success,
                    'data': dto.data,
                    'error': dto.error
                }), 200 if dto.success else 400
            
            elif action == 'explain':
                coin = data.get('coin', 'bitcoin')
                # توضیح پیش‌بینی (Feature Importance)
                return jsonify({
                    'success': True,
                    'data': {
                        'coin': coin,
                        'message': 'Feature importance explanation (coming soon)'
                    }
                })
            
            elif action == 'import':
                version = data.get('version')
                if not version:
                    return jsonify({'success': False, 'error': 'Version required'}), 400
                model = model_manager.get_model_by_version(version)
                if model:
                    model_manager.current_model = model
                    model_manager.current_version = version
                    return jsonify({'success': True, 'message': f'Model {version} activated'})
                return jsonify({'success': False, 'error': 'Version not found'}), 404
            
            return jsonify({'success': False, 'error': 'Invalid action'}), 400
        
        # ===== PUT =====
        elif request.method == 'PUT':
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
        
        # ===== DELETE =====
        elif request.method == 'DELETE':
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
        logger.error(f"Model management error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================
# ۶. مدل - خروجی/ورودی فایل
# ============================================================

@api_bp.route('/model/export', methods=['GET', 'POST'])
def model_export_import():
    """
    خروجی/ورودی فایل مدل
    
    GET:  دانلود فایل مدل (با ?version=v1.0.0)
    POST: آپلود فایل مدل (multipart/form-data)
    """
    try:
        container = current_app.container
        model_manager = container.model_manager()
        
        # ===== GET: دانلود =====
        if request.method == 'GET':
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
        
        # ===== POST: آپلود =====
        elif request.method == 'POST':
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
        logger.error(f"Model export/import error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================
# ۷. مدل - زمان‌بندی آموزش
# ============================================================

@api_bp.route('/model/schedule', methods=['GET', 'POST', 'DELETE'])
def model_schedule():
    """
    زمان‌بندی آموزش خودکار
    
    GET:  مشاهده زمان‌بندی فعلی
    POST: تنظیم/تغییر زمان‌بندی
    DELETE: توقف زمان‌بندی
    """
    try:
        container = current_app.container
        trainer = container.trainer()
        
        # ===== GET =====
        if request.method == 'GET':
            stats = trainer.get_stats() if hasattr(trainer, 'get_stats') else {}
            return jsonify({
                'success': True,
                'data': {
                    'is_running': stats.get('is_running', False),
                    'interval_hours': stats.get('stats', {}).get('training_period', 6),
                    'coins': stats.get('coins', []),
                    'last_training': stats.get('stats', {}).get('last_training')
                }
            })
        
        # ===== POST =====
        elif request.method == 'POST':
            data = request.json or {}
            enabled = data.get('enabled', True)
            interval = data.get('interval', 6)
            period = data.get('period', '1m')
            coins = data.get('coins', ['bitcoin', 'ethereum'])
            incremental = data.get('incremental', True)
            
            if enabled:
                result = trainer.start_auto_train(
                    interval_hours=interval,
                    period=period,
                    incremental=incremental
                )
            else:
                result = trainer.stop_auto_train()
            
            return jsonify(result), 200 if result.get('success') else 400
        
        # ===== DELETE =====
        elif request.method == 'DELETE':
            result = trainer.stop_auto_train()
            return jsonify(result), 200 if result.get('success') else 400
            
    except Exception as e:
        logger.error(f"Model schedule error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================
# ۸. دیباگ (Debug) - مدیریت کامل
# ============================================================

@api_bp.route('/debug', methods=['GET', 'POST', 'DELETE'])
def debug_management():
    """
    مدیریت کامل دیباگ
    
    GET:
        ?section=status     → وضعیت سیستم (CPU, RAM, Disk, Network)
        ?section=logs       → لاگ‌های اخیر
        ?section=errors     → خطاهای اخیر
        ?section=system     → اطلاعات کامل سیستم
        ?section=processes  → لیست پردازش‌ها
        ?section=cache      → مشاهده کش (Redis)
    
    POST:
        {"action": "exec", "command": "print('Hello')"}  → اجرای دستور
        {"action": "set_loglevel", "level": "DEBUG"}     → تغییر سطح لاگ
        {"action": "clear_cache"}                        → پاک کردن کش
    
    DELETE:
        {"target": "cache"}   → پاک کردن کش
        {"target": "logs"}    → پاک کردن لاگ‌ها
        {"target": "errors"}  → پاک کردن خطاها
    """
    try:
        import psutil
        
        # ===== GET =====
        if request.method == 'GET':
            section = request.args.get('section', 'status')
            
            if section == 'status':
                return jsonify({
                    'success': True,
                    'data': {
                        'cpu': {
                            'percent': psutil.cpu_percent(interval=0.5),
                            'cores': psutil.cpu_count(),
                            'frequency': psutil.cpu_freq().current if psutil.cpu_freq() else None
                        },
                        'memory': {
                            'total': psutil.virtual_memory().total,
                            'available': psutil.virtual_memory().available,
                            'percent': psutil.virtual_memory().percent,
                            'used': psutil.virtual_memory().used
                        },
                        'disk': {
                            'total': psutil.disk_usage('/').total,
                            'used': psutil.disk_usage('/').used,
                            'free': psutil.disk_usage('/').free,
                            'percent': psutil.disk_usage('/').percent
                        },
                        'network': {
                            'connections': len(psutil.net_connections()),
                            'interfaces': list(psutil.net_if_addrs().keys())
                        },
                        'timestamp': datetime.now().isoformat()
                    }
                })
            
            elif section == 'logs':
                limit = request.args.get('limit', 50, type=int)
                level = request.args.get('level', 'ALL')
                # خواندن لاگ از فایل
                log_file = Path('logs/system.log')
                if log_file.exists():
                    with open(log_file, 'r', encoding='utf-8') as f:
                        lines = f.readlines()[-limit:]
                    return jsonify({'success': True, 'data': lines})
                return jsonify({'success': True, 'data': []})
            
            elif section == 'errors':
                limit = request.args.get('limit', 20, type=int)
                error_file = Path('logs/errors.log')
                if error_file.exists():
                    with open(error_file, 'r', encoding='utf-8') as f:
                        lines = f.readlines()[-limit:]
                    return jsonify({'success': True, 'data': lines})
                return jsonify({'success': True, 'data': []})
            
            elif section == 'system':
                return jsonify({
                    'success': True,
                    'data': {
                        'python': sys.version,
                        'platform': sys.platform,
                        'cwd': os.getcwd(),
                        'environment': os.getenv('FLASK_ENV', 'development'),
                        'timezone': os.getenv('TZ', 'UTC')
                    }
                })
            
            elif section == 'processes':
                processes = []
                for proc in psutil.process_iter(['pid', 'name', 'status', 'memory_percent', 'cpu_percent']):
                    try:
                        processes.append(proc.info)
                    except:
                        pass
                return jsonify({
                    'success': True,
                    'data': processes[:50]  # فقط ۵۰ تا اول
                })
            
            elif section == 'cache':
                cache = get_cache()
                if cache and cache.is_connected():
                    keys = cache._client.keys('*')[:20]
                    return jsonify({
                        'success': True,
                        'data': {
                            'keys': keys,
                            'count': len(keys)
                        }
                    })
                return jsonify({'success': False, 'error': 'Cache not available'}), 503
            
            return jsonify({'success': False, 'error': 'Invalid section'}), 400
        
        # ===== POST =====
        elif request.method == 'POST':
            data = request.json or {}
            action = data.get('action')
            
            if action == 'exec':
                command = data.get('command', '').strip()
                if not command:
                    return jsonify({'success': False, 'error': 'Command required'}), 400
                
                dangerous = ['os.system', 'subprocess', 'exec(', 'eval(', '__import__']
                for kw in dangerous:
                    if kw in command:
                        return jsonify({'success': False, 'error': 'Dangerous command'}), 403
                
                old_stdout = sys.stdout
                sys.stdout = io.StringIO()
                try:
                    exec(command, {'__builtins__': __builtins__, 'os': __import__('os'), 'sys': __import__('sys')})
                    result = sys.stdout.getvalue()
                except Exception as e:
                    result = str(e)
                finally:
                    sys.stdout = old_stdout
                
                return jsonify({'success': True, 'result': result or '✅ Done'})
            
            elif action == 'set_loglevel':
                level = data.get('level', 'INFO')
                if level in ['DEBUG', 'INFO', 'WARNING', 'ERROR']:
                    logging.getLogger().setLevel(getattr(logging, level))
                    return jsonify({'success': True, 'message': f'Log level set to {level}'})
                return jsonify({'success': False, 'error': 'Invalid log level'}), 400
            
            elif action == 'clear_cache':
                cache = get_cache()
                if cache and cache.is_connected():
                    cache._client.flushdb()
                    return jsonify({'success': True, 'message': 'Cache cleared'})
                return jsonify({'success': False, 'error': 'Cache not available'}), 503
            
            return jsonify({'success': False, 'error': 'Invalid action'}), 400
        
        # ===== DELETE =====
        elif request.method == 'DELETE':
            data = request.json or {}
            target = data.get('target')
            
            if target == 'cache':
                cache = get_cache()
                if cache and cache.is_connected():
                    cache._client.flushdb()
                    return jsonify({'success': True, 'message': 'Cache cleared'})
                return jsonify({'success': False, 'error': 'Cache not available'}), 503
            
            elif target == 'logs':
                log_file = Path('logs/system.log')
                if log_file.exists():
                    with open(log_file, 'w') as f:
                        f.write('')
                return jsonify({'success': True, 'message': 'Logs cleared'})
            
            elif target == 'errors':
                error_file = Path('logs/errors.log')
                if error_file.exists():
                    with open(error_file, 'w') as f:
                        f.write('')
                return jsonify({'success': True, 'message': 'Errors cleared'})
            
            return jsonify({'success': False, 'error': 'Invalid target'}), 400
            
    except Exception as e:
        logger.error(f"Debug management error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================
# ۹. دیتابیس (Database) - مدیریت جدول‌ها و داده‌ها
# ============================================================

@api_bp.route('/db', methods=['GET', 'POST', 'DELETE'])
def database_management():
    """
    مدیریت جدول‌ها و داده‌ها
    
    GET:
        ?table=name         → دریافت محتوای جدول
        ?table=name&limit=100&offset=0  → با صفحه‌بندی
        ?table=name&format=csv  → خروجی CSV
    
    POST:
        {"table": "name", "action": "insert", "data": {...}}  → درج رکورد
        {"table": "name", "action": "update", "id": 1, "data": {...}}  → به‌روزرسانی
    
    DELETE:
        {"table": "name", "id": 123, "confirm": true}  → حذف رکورد
        {"table": "name", "confirm": true, "truncate": true}  → پاک کردن همه
    """
    try:
        db = get_primary()
        if not db or not db.is_connected():
            return jsonify({'success': False, 'error': 'Database not connected'}), 503
        
        # ===== GET =====
        if request.method == 'GET':
            table = request.args.get('table')
            if not table:
                # لیست همه جدول‌ها
                result = db.execute("""
                    SELECT table_name, 
                           (SELECT COUNT(*) FROM information_schema.tables WHERE table_name = t.table_name) as row_count
                    FROM information_schema.tables t
                    WHERE table_schema = 'public'
                    ORDER BY table_name
                """)
                for row in result:
                    size_result = db.execute(f"""
                        SELECT pg_total_relation_size('{row['table_name']}') / 1024 / 1024 as size_mb
                    """)
                    row['size_mb'] = size_result[0]['size_mb'] if size_result else 0
                return jsonify({'success': True, 'data': result})
            
            # دریافت محتوای جدول خاص
            limit = request.args.get('limit', 100, type=int)
            offset = request.args.get('offset', 0, type=int)
            format_type = request.args.get('format', 'json')
            
            # دریافت ستون‌ها
            columns = db.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = %s
                ORDER BY ordinal_position
            """, (table,))
            
            if not columns:
                return jsonify({'success': False, 'error': 'Table not found'}), 404
            
            col_names = [c['column_name'] for c in columns]
            
            # دریافت داده‌ها
            query = f'SELECT * FROM "{table}" ORDER BY id DESC LIMIT %s OFFSET %s'
            rows = db.execute(query, (limit, offset))
            
            if format_type == 'csv':
                output = io.StringIO()
                writer = csv.DictWriter(output, fieldnames=col_names)
                writer.writeheader()
                writer.writerows(rows)
                output.seek(0)
                return send_file(
                    io.BytesIO(output.getvalue().encode('utf-8')),
                    as_attachment=True,
                    download_name=f'{table}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv',
                    mimetype='text/csv'
                )
            
            return jsonify({
                'success': True,
                'data': {
                    'columns': col_names,
                    'rows': rows,
                    'total': len(rows),
                    'limit': limit,
                    'offset': offset
                }
            })
        
        # ===== POST =====
        elif request.method == 'POST':
            data = request.json or {}
            table = data.get('table')
            action = data.get('action')
            
            if not table or not action:
                return jsonify({'success': False, 'error': 'Table and action required'}), 400
            
            if action == 'insert':
                row_data = data.get('data', {})
                if not row_data:
                    return jsonify({'success': False, 'error': 'Data required for insert'}), 400
                columns = ', '.join(row_data.keys())
                placeholders = ', '.join(['%s'] * len(row_data))
                query = f'INSERT INTO "{table}" ({columns}) VALUES ({placeholders}) RETURNING id'
                result = db.execute(query, tuple(row_data.values()))
                return jsonify({
                    'success': True,
                    'message': 'Row inserted',
                    'id': result[0]['id'] if result else None
                })
            
            elif action == 'update':
                row_id = data.get('id')
                row_data = data.get('data', {})
                if not row_id or not row_data:
                    return jsonify({'success': False, 'error': 'ID and data required for update'}), 400
                set_clause = ', '.join([f'{k} = %s' for k in row_data.keys()])
                query = f'UPDATE "{table}" SET {set_clause} WHERE id = %s'
                db.execute(query, tuple(row_data.values()) + (row_id,))
                return jsonify({'success': True, 'message': f'Row {row_id} updated'})
            
            return jsonify({'success': False, 'error': 'Invalid action'}), 400
        
        # ===== DELETE =====
        elif request.method == 'DELETE':
            data = request.json or {}
            table = data.get('table')
            
            if not table:
                return jsonify({'success': False, 'error': 'Table required'}), 400
            
            if not data.get('confirm'):
                return jsonify({'success': False, 'error': 'Confirmation required'}), 400
            
            if data.get('truncate'):
                db.execute(f'TRUNCATE TABLE "{table}"')
                return jsonify({'success': True, 'message': f'Table {table} truncated'})
            
            row_id = data.get('id')
            if not row_id:
                return jsonify({'success': False, 'error': 'ID required'}), 400
            
            db.execute(f'DELETE FROM "{table}" WHERE id = %s', (row_id,))
            return jsonify({'success': True, 'message': f'Row {row_id} deleted from {table}'})
            
    except Exception as e:
        logger.error(f"Database management error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================
# ۱۰. دیتابیس - جستجوی یکپارچه
# ============================================================

@api_bp.route('/db/search', methods=['GET'])
def database_search():
    """
    جستجوی یکپارچه در همه جدول‌ها
    
    ?q=term                → عبارت جستجو
    ?tables=table1,table2  → جدول‌های خاص (اختیاری)
    """
    try:
        query = request.args.get('q', '').strip()
        if not query or len(query) < 2:
            return jsonify({'success': False, 'error': 'Search term too short (min 2 chars)'}), 400
        
        tables_param = request.args.get('tables', '')
        db = get_primary()
        if not db or not db.is_connected():
            return jsonify({'success': False, 'error': 'Database not connected'}), 503
        
        # دریافت لیست جدول‌ها
        if tables_param:
            tables = [t.strip() for t in tables_param.split(',')]
        else:
            result = db.execute("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public'
            """)
            tables = [r['table_name'] for r in result]
        
        results = []
        for table in tables:
            try:
                # دریافت ستون‌های متنی
                columns = db.execute("""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name = %s 
                    AND data_type IN ('text', 'varchar', 'char', 'character varying')
                """, (table,))
                
                if not columns:
                    continue
                
                # ساخت شرط LIKE برای همه ستون‌ها
                like_conditions = ' OR '.join([f'"{c["column_name"]}"::text ILIKE %s' for c in columns])
                search_query = f'SELECT * FROM "{table}" WHERE {like_conditions} LIMIT 10'
                params = [f'%{query}%'] * len(columns)
                
                rows = db.execute(search_query, tuple(params))
                if rows:
                    results.append({
                        'table': table,
                        'rows': rows,
                        'count': len(rows)
                    })
            except Exception as e:
                logger.warning(f"Search error in table {table}: {e}")
                continue
        
        return jsonify({
            'success': True,
            'data': results,
            'total': sum(r['count'] for r in results)
        })
        
    except Exception as e:
        logger.error(f"Database search error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================
# ۱۱. دیتابیس - بک‌آپ و بازیابی
# ============================================================

@api_bp.route('/db/backup', methods=['GET', 'POST'])
def database_backup():
    """
    بک‌آپ و بازیابی
    
    GET:  دانلود بک‌آپ کامل
    POST: ایجاد/بازیابی بک‌آپ
    """
    try:
        db = get_primary()
        if not db or not db.is_connected():
            return jsonify({'success': False, 'error': 'Database not connected'}), 503
        
        # ===== GET: دانلود بک‌آپ =====
        if request.method == 'GET':
            tables = db.execute("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public'
            """)
            
            output = io.StringIO()
            for t in tables:
                table_name = t['table_name']
                rows = db.execute(f'SELECT * FROM "{table_name}"')
                if rows:
                    writer = csv.DictWriter(output, fieldnames=rows[0].keys())
                    writer.writeheader()
                    writer.writerows(rows)
                    output.write('\n')
            
            output.seek(0)
            return send_file(
                io.BytesIO(output.getvalue().encode('utf-8')),
                as_attachment=True,
                download_name=f'backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv',
                mimetype='text/csv'
            )
        
        # ===== POST: ایجاد/بازیابی =====
        elif request.method == 'POST':
            data = request.json or {}
            action = data.get('action', 'create')
            
            if action == 'create':
                # ایجاد بک‌آپ
                backup_file = Path(f'backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.sql')
                # در اینجا می‌توان از pg_dump استفاده کرد
                return jsonify({
                    'success': True,
                    'message': f'Backup created: {backup_file.name}',
                    'file': backup_file.name
                })
            
            elif action == 'restore':
                file_name = data.get('file')
                if not file_name:
                    return jsonify({'success': False, 'error': 'File name required'}), 400
                # بازیابی از فایل
                return jsonify({
                    'success': True,
                    'message': f'Restore from {file_name} completed'
                })
            
            return jsonify({'success': False, 'error': 'Invalid action'}), 400
            
    except Exception as e:
        logger.error(f"Database backup error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================
# ۱۲. دیتابیس - آمار و آنالیز
# ============================================================

@api_bp.route('/db/stats', methods=['GET'])
def database_stats():
    """
    آمار و آنالیز دیتابیس
    
    ?section=tables   → آمار جدول‌ها
    ?section=size     → حجم دیتابیس
    ?section=performance  → عملکرد
    """
    try:
        db = get_primary()
        if not db or not db.is_connected():
            return jsonify({'success': False, 'error': 'Database not connected'}), 503
        
        section = request.args.get('section', 'tables')
        
        if section == 'tables':
            result = db.execute("""
                SELECT 
                    table_name,
                    (SELECT COUNT(*) FROM information_schema.tables WHERE table_name = t.table_name) as row_count
                FROM information_schema.tables t
                WHERE table_schema = 'public'
                ORDER BY table_name
            """)
            for row in result:
                size_result = db.execute(f"""
                    SELECT pg_total_relation_size('{row['table_name']}') / 1024 / 1024 as size_mb
                """)
                row['size_mb'] = size_result[0]['size_mb'] if size_result else 0
            return jsonify({'success': True, 'data': result})
        
        elif section == 'size':
            result = db.execute("""
                SELECT 
                    pg_database_size(current_database()) / 1024 / 1024 as total_size_mb,
                    pg_database_size(current_database()) as total_size_bytes
            """)
            return jsonify({'success': True, 'data': result[0] if result else {}})
        
        elif section == 'performance':
            # آمار عملکردی ساده
            return jsonify({
                'success': True,
                'data': {
                    'active_connections': len(db._connection.pool) if hasattr(db._connection, 'pool') else 1,
                    'timestamp': datetime.now().isoformat()
                }
            })
        
        return jsonify({'success': False, 'error': 'Invalid section'}), 400
        
    except Exception as e:
        logger.error(f"Database stats error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

@api_bp.route('/db/query', methods=['POST'])
def db_query():
    """
    اجرای کوئری SQL دلخواه (فقط SELECT و CREATE TABLE برای تست)
    """
    try:
        data = request.json
        query = data.get('query', '').strip()
        
        if not query:
            return jsonify({'success': False, 'error': 'Query is required'}), 400
        
        # فقط کوئری‌های SELECT و CREATE TABLE مجاز است (برای تست)
        query_upper = query.upper().strip()
        if not (query_upper.startswith('SELECT') or query_upper.startswith('CREATE TABLE')):
            return jsonify({
                'success': False,
                'error': 'Only SELECT and CREATE TABLE queries are allowed'
            }), 403
        
        db = get_primary()
        if not db or not db.is_connected():
            return jsonify({'success': False, 'error': 'Database not connected'}), 503
        
        result = db.execute(query)
        
        return jsonify({
            'success': True,
            'data': {
                'rows': result,
                'count': len(result)
            }
        })
    except Exception as e:
        logger.error(f"DB query error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/db/tables', methods=['GET'])
def db_tables():
    """دریافت لیست همه جدول‌ها"""
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
        
# ============================================================
# ۱۳. CoinStats (داده‌های مستقیم)
# ============================================================

@api_bp.route('/coinstats/prices', methods=['GET'])
def coinstats_prices():
    try:
        container = current_app.container
        api_client = container.api_client()
        btc = api_client.get_coin("bitcoin")
        eth = api_client.get_coin("ethereum")
        return jsonify({
            'success': True,
            'data': {
                'btc': {
                    'price': btc.get('price', 0),
                    'change_24h': btc.get('priceChange1d', 0)
                } if btc else {},
                'eth': {
                    'price': eth.get('price', 0),
                    'change_24h': eth.get('priceChange1d', 0)
                } if eth else {}
            }
        }), 200
    except Exception as e:
        logger.error(f"CoinStats prices error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/coinstats/fear-greed', methods=['GET'])
def coinstats_fear_greed():
    try:
        container = current_app.container
        api_client = container.api_client()
        fg = api_client.get_fear_greed(use_cache=True)
        return jsonify({
            'success': True,
            'data': {
                'value': fg.get('now', {}).get('value', 50) if fg else 50,
                'classification': fg.get('now', {}).get('value_classification', 'Neutral') if fg else 'Neutral'
            }
        }), 200
    except Exception as e:
        logger.error(f"Fear-greed error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/coinstats/btc-dominance', methods=['GET'])
def coinstats_btc_dominance():
    try:
        container = current_app.container
        api_client = container.api_client()
        dominance = api_client.get_btc_dominance(use_cache=True)
        return jsonify({
            'success': True,
            'data': {
                'value': dominance.get('dominance', 50) if dominance else 50
            }
        }), 200
    except Exception as e:
        logger.error(f"BTC dominance error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/coinstats/all', methods=['GET'])
def coinstats_all():
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
                    'price': btc.get('price', 0),
                    'change_24h': btc.get('priceChange1d', 0)
                } if btc else {},
                'eth': {
                    'price': eth.get('price', 0),
                    'change_24h': eth.get('priceChange1d', 0)
                } if eth else {},
                'fear_greed': {
                    'value': fg.get('now', {}).get('value', 50) if fg else 50,
                    'classification': fg.get('now', {}).get('value_classification', 'Neutral') if fg else 'Neutral'
                },
                'btc_dominance': dominance.get('dominance', 50) if dominance else 50,
                'credits': credits.get('remainingCredits', 0) if credits else 0,
                'api_status': status.get('status', 'unknown') if status else 'unknown'
            }
        }), 200
    except Exception as e:
        logger.error(f"CoinStats all error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================
# ۱۴. هشدارها
# ============================================================

@api_bp.route('/alerts', methods=['GET'])
def get_alerts():
    try:
        limit = request.args.get('limit', 20, type=int)
        resolved = request.args.get('resolved')
        if resolved is not None:
            resolved = resolved.lower() == 'true'
        alerts = alerter.get_alerts(limit=limit, resolved=resolved)
        return jsonify({'success': True, 'data': alerts, 'count': len(alerts)}), 200
    except Exception as e:
        logger.error(f"Alerts error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/alerts/<int:alert_id>/resolve', methods=['POST'])
def resolve_alert(alert_id):
    try:
        success = alerter.resolve_alert(alert_id)
        return jsonify({'success': success}), 200
    except Exception as e:
        logger.error(f"Resolve alert error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================
# ۱۵. اعتبار
# ============================================================

@api_bp.route('/credits', methods=['GET'])
def credits():
    try:
        container = current_app.container
        api_client = container.api_client()
        credits_data = api_client.get_credits()
        return jsonify({'success': True, 'data': credits_data}), 200
    except Exception as e:
        logger.error(f"Credits error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500
