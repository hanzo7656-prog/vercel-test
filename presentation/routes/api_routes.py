# presentation/routes/api_routes.py
# ============================================================
# API Routes - نسخه ۳.۰ (فقط JSON)
# ============================================================

import json
import logging
import os
import sys
from datetime import datetime
from flask import Blueprint, request, jsonify, current_app

from application.dto.prediction_dto import PredictionRequestDTO
from application.services.prediction_service import PredictionService
from application.services.monitoring_service import MonitoringService
from application.use_cases.train_model import TrainModelUseCase
from infrastructure.auth.auth_manager import require_auth
from infrastructure.external.alerter import alerter
from application.services.self_healer import SelfHealer

logger = logging.getLogger(__name__)

api_bp = Blueprint('api', __name__, url_prefix='/api')


# ============================================================
# ۱. پیش‌بینی
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


# ============================================================
# ۲. مدل
# ============================================================

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


@api_bp.route('/model/history', methods=['GET'])
@require_auth()
def model_history():
    try:
        container = current_app.container
        model_manager = container.model_manager()
        history = model_manager.get_version_history(limit=20)
        return jsonify({'success': True, 'data': history}), 200
    except Exception as e:
        logger.error(f"Error in model_history: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================
# ۳. سلامت
# ============================================================

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


@api_bp.route('/health/simple', methods=['GET'])
def health_simple():
    try:
        container = current_app.container
        monitoring_service: MonitoringService = container.monitoring_service()
        health_data = monitoring_service.get_health()
        if health_data.get('status') == 'ok':
            return jsonify({'status': 'ok', 'timestamp': datetime.now().isoformat()}), 200
        return jsonify({'status': 'degraded', 'timestamp': datetime.now().isoformat()}), 503
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500


# ============================================================
# ۴. هشدارها
# ============================================================

@api_bp.route('/alerts', methods=['GET'])
@require_auth()
def get_alerts():
    try:
        limit = request.args.get('limit', 20, type=int)
        resolved = request.args.get('resolved')
        if resolved is not None:
            resolved = resolved.lower() == 'true'
        alerts = alerter.get_alerts(limit=limit, resolved=resolved)
        return jsonify({'success': True, 'data': alerts, 'count': len(alerts)}), 200
    except Exception as e:
        logger.error(f"Error in get_alerts: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/alerts/<int:alert_id>/resolve', methods=['POST'])
@require_auth('admin')
def resolve_alert(alert_id):
    try:
        success = alerter.resolve_alert(alert_id)
        return jsonify({'success': success}), 200
    except Exception as e:
        logger.error(f"Error in resolve_alert: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================
# ۵. اعتبار API
# ============================================================

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


# ============================================================
# ۶. دیباگ (فقط ادمین)
# ============================================================

@api_bp.route('/debug/exec', methods=['POST'])
@require_auth('admin')
def debug_exec():
    try:
        data = request.json
        command = data.get('command', '').strip()
        if not command:
            return jsonify({'success': False, 'error': 'دستور وارد نشده'}), 400
        
        dangerous_keywords = ['import os; os.system', 'import subprocess', 'exec(', 'eval(', '__import__', 'open(', 'file(']
        for keyword in dangerous_keywords:
            if keyword in command:
                return jsonify({'success': False, 'error': 'دستور غیرمجاز'}), 403
        
        import io
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        sys.stdout = io.StringIO()
        sys.stderr = io.StringIO()
        
        try:
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
            output = "✅ Command executed successfully (no output)"
        
        return jsonify({'success': True, 'result': output})
    except Exception as e:
        logger.error(f"Error in debug_exec: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/debug/env', methods=['GET'])
@require_auth('admin')
def debug_env():
    try:
        env_vars = {}
        safe_keys = ['PORT', 'FLASK_DEBUG', 'FLASK_ENV', 'COINSTATS_API_KEY', 'PYTHONPATH']
        for key in safe_keys:
            value = os.getenv(key)
            if value:
                if 'KEY' in key or 'SECRET' in key:
                    value = value[:6] + '...' + value[-4:] if len(value) > 10 else '***'
                env_vars[key] = value
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
    try:
        data = request.json
        filename = data.get('filename', '').strip()
        if not filename:
            return jsonify({'success': False, 'error': 'نام فایل وارد نشده'}), 400
        
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
            return jsonify({'success': False, 'error': 'دسترسی به این فایل مجاز نیست'}), 403
        
        with open(filename, 'r', encoding='utf-8') as f:
            content = f.read()
        return jsonify({'success': True, 'content': content}), 200
    except FileNotFoundError:
        return jsonify({'success': False, 'error': 'فایل یافت نشد'}), 404
    except Exception as e:
        logger.error(f"Error in debug_file: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================
# ۷. CoinStats مستقیم
# ============================================================

@api_bp.route('/coinstats/prices', methods=['GET'])
@require_auth()
def coinstats_prices():
    try:
        container = current_app.container
        api_client = container.api_client()
        btc = api_client.get_coin("bitcoin")
        eth = api_client.get_coin("ethereum")
        return jsonify({
            'success': True,
            'data': {
                'btc': {'price': btc.get('price', 0), 'change_24h': btc.get('priceChange1d', 0)} if btc else {},
                'eth': {'price': eth.get('price', 0), 'change_24h': eth.get('priceChange1d', 0)} if eth else {}
            }
        }), 200
    except Exception as e:
        logger.error(f"Error in coinstats_prices: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/coinstats/fear-greed', methods=['GET'])
@require_auth()
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
        logger.error(f"Error in coinstats_fear_greed: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/coinstats/all', methods=['GET'])
@require_auth()
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
                'btc': {'price': btc.get('price', 0), 'change_24h': btc.get('priceChange1d', 0)} if btc else {},
                'eth': {'price': eth.get('price', 0), 'change_24h': eth.get('priceChange1d', 0)} if eth else {},
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
        logger.error(f"Error in coinstats_all: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500
