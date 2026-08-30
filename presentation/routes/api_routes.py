# presentation/routes/api_routes.py
# ============================================================
# API Routes - نسخه ۳.۰ (با روت دیباگ)
# ============================================================

import json
import logging
from datetime import datetime
from flask import Blueprint, request, jsonify, current_app

from application.dto.prediction_dto import PredictionRequestDTO
from application.services.prediction_service import PredictionService
from application.services.monitoring_service import MonitoringService
from application.use_cases.train_model import TrainModelUseCase
from infrastructure.auth.auth_manager import require_auth, get_current_user_from_request
from infrastructure.external.alerter import alerter
from application.services.self_healer import SelfHealer

logger = logging.getLogger(__name__)

api_bp = Blueprint('api', __name__, url_prefix='/api')


# ============================================================
# ۱. روت‌های پیش‌بینی
# ============================================================

@api_bp.route('/predict', methods=['GET'])
@require_auth()
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
        logger.error(f"Error in predict: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/predict/multiple', methods=['POST'])
@require_auth()
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
        logger.error(f"Error in predict_multiple: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/model/status', methods=['GET'])
@require_auth()
def model_status():
    try:
        container = current_app.container
        train_use_case: TrainModelUseCase = container.train_use_case()
        status = train_use_case.get_status()
        return jsonify({'success': True, 'data': status}), 200
    except Exception as e:
        logger.error(f"Error in model_status: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/model/train', methods=['POST'])
@require_auth('admin')
def train_model():
    try:
        data = request.json or {}
        period = data.get('period', '1m')
        coins = data.get('coins', ['bitcoin', 'ethereum'])
        incremental = data.get('incremental', False)
        container = current_app.container
        train_use_case: TrainModelUseCase = container.train_use_case()
        result = train_use_case.execute(period, coins, incremental)
        return jsonify(result), 200 if result.get('success') else 400
    except Exception as e:
        logger.error(f"Error in train_model: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/model/clear-logs', methods=['POST'])
@require_auth('admin')
def clear_logs():
    try:
        container = current_app.container
        trainer = container.trainer()
        if hasattr(trainer, 'clear_logs'):
            trainer.clear_logs()
            return jsonify({'success': True, 'message': 'Logs cleared'}), 200
        return jsonify({'success': False, 'error': 'Method not available'}), 400
    except Exception as e:
        logger.error(f"Error in clear_logs: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/health', methods=['GET'])
def health():
    try:
        container = current_app.container
        monitoring_service: MonitoringService = container.monitoring_service()
        health_data = monitoring_service.get_health()
        status_code = 200 if health_data.get('status') == 'ok' else 503
        return jsonify(health_data), status_code
    except Exception as e:
        logger.error(f"Error in health: {e}", exc_info=True)
        return jsonify({'status': 'error', 'error': str(e)}), 500


@api_bp.route('/credits', methods=['GET'])
@require_auth()
def credits():
    try:
        container = current_app.container
        api_client = container.api_client()
        credits_data = api_client.get_credits()
        return jsonify({'success': True, 'data': credits_data}), 200
    except Exception as e:
        logger.error(f"Error in credits: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/api/alerts', methods=['GET'])
@require_auth()
def get_alerts():
    try:
        limit = request.args.get('limit', 20, type=int)
        alerts = alerter.get_alerts(limit=limit)
        return jsonify({'success': True, 'data': alerts}), 200
    except Exception as e:
        logger.error(f"Error in get_alerts: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/api/alerts/<int:alert_id>/resolve', methods=['POST'])
@require_auth('admin')
def resolve_alert(alert_id):
    try:
        success = alerter.resolve_alert(alert_id)
        return jsonify({'success': success}), 200
    except Exception as e:
        logger.error(f"Error in resolve_alert: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================
# 🆕 روت دیباگ - اجرای دستورات پایتون (فقط ادمین)
# ============================================================

@api_bp.route('/debug/exec', methods=['POST'])
@require_auth('admin')
def debug_exec():
    """
    اجرای دستور پایتون (فقط برای توسعه و دیباگ)
    
    Body:
        {
            "command": "print('Hello')"
        }
    """
    try:
        data = request.json
        command = data.get('command', '').strip()
        
        if not command:
            return jsonify({'success': False, 'error': 'دستور وارد نشده'}), 400
        
        # ایمنی: جلوگیری از دستورات خطرناک
        dangerous_keywords = ['import os; os.system', 'import subprocess', 'exec(', 'eval(', '__import__', 'open(', 'file(']
        for keyword in dangerous_keywords:
            if keyword in command:
                return jsonify({
                    'success': False,
                    'error': 'دستور غیرمجاز: حاوی کد خطرناک است'
                }), 403
        
        # اجرای دستور
        import io
        import sys
        
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        sys.stdout = io.StringIO()
        sys.stderr = io.StringIO()
        
        try:
            # ایجاد namespace برای اجرا
            namespace = {
                '__builtins__': __builtins__,
                'os': __import__('os'),
                'sys': __import__('sys'),
                'json': __import__('json'),
                'datetime': __import__('datetime'),
                'time': __import__('time'),
                'Path': __import__('pathlib').Path,
            }
            
            exec(command, namespace)
            result = sys.stdout.getvalue()
            error = sys.stderr.getvalue()
            
        except Exception as e:
            result = sys.stdout.getvalue()
            error = str(e)
        
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr
        
        output = result
        if error:
            output += f"\n❌ Error: {error}"
        
        if not output.strip():
            output = "✅ دستور با موفقیت اجرا شد (بدون خروجی)"
        
        return jsonify({
            'success': True,
            'result': output
        })
        
    except Exception as e:
        logger.error(f"Error in debug_exec: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@api_bp.route('/debug/env', methods=['GET'])
@require_auth('admin')
def debug_env():
    """دریافت متغیرهای محیطی (فقط ادمین)"""
    try:
        env_vars = {}
        safe_keys = ['PORT', 'FLASK_DEBUG', 'FLASK_ENV', 'COINSTATS_API_KEY', 'PYTHONPATH']
        
        for key in safe_keys:
            value = os.getenv(key)
            if value:
                # مخفی کردن کلیدهای API
                if 'KEY' in key or 'SECRET' in key:
                    value = value[:6] + '...' + value[-4:] if len(value) > 10 else '***'
                env_vars[key] = value
        
        # اضافه کردن متغیرهای SYSTEM
        env_vars['SYSTEM'] = {
            'cwd': os.getcwd(),
            'python_version': sys.version,
            'platform': sys.platform,
        }
        
        return jsonify({'success': True, 'data': env_vars}), 200
    except Exception as e:
        logger.error(f"Error in debug_env: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/debug/file', methods=['POST'])
@require_auth('admin')
def debug_file():
    """خواندن محتوای فایل (فقط ادمین)"""
    try:
        data = request.json
        filename = data.get('filename', '').strip()
        
        if not filename:
            return jsonify({'success': False, 'error': 'نام فایل وارد نشده'}), 400
        
        # لیست فایل‌های مجاز
        allowed_files = [
            'config/settings.json',
            'config/databases.json',
            'config/users.json',
            'config/alert_rules.json',
            'app.py',
            'container.py',
            'requirements.txt'
        ]
        
        if filename not in allowed_files:
            return jsonify({
                'success': False,
                'error': 'دسترسی به این فایل مجاز نیست'
            }), 403
        
        with open(filename, 'r', encoding='utf-8') as f:
            content = f.read()
        
        return jsonify({
            'success': True,
            'content': content
        }), 200
        
    except FileNotFoundError:
        return jsonify({'success': False, 'error': 'فایل یافت نشد'}), 404
    except Exception as e:
        logger.error(f"Error in debug_file: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500
