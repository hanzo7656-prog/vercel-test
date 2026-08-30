# presentation/routes/api_routes.py
# ============================================================
# API Routes - نسخه کامل (همه اندپوینت‌ها)
# ============================================================

import os
import sys
import logging
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
# ۱. صفحه اصلی (سلامت ساده)
# ============================================================

@api_bp.route('', methods=['GET'])
def api_home():
    return jsonify({
        'name': 'Trading Signal System API',
        'version': '9.0.0',
        'status': 'running',
        'timestamp': datetime.now().isoformat(),
        'endpoints': [
            '/api/health',
            '/api/metrics',
            '/api/predict',
            '/api/model/status',
            '/api/model/train',
            '/api/alerts',
            '/api/credits',
            '/api/coinstats/prices',
            '/api/coinstats/fear-greed',
            '/api/coinstats/all'
        ]
    })


# ============================================================
# ۲. سلامت
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



# ============================================================
# ۳. دیتابیس
# ============================================================

@api_bp.route('/health/database', methods=['GET'])
def health_database():
    """بررسی سلامت همه دیتابیس‌ها"""
    try:
        from infrastructure.database import health_check
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
# ۵. مدل
# ============================================================

@api_bp.route('/model/status', methods=['GET'])
def model_status():
    try:
        container = current_app.container
        train_use_case: TrainModelUseCase = container.train_use_case()
        status = train_use_case.get_status()
        return jsonify({'success': True, 'data': status}), 200
    except Exception as e:
        logger.error(f"Model status error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/model/train', methods=['POST'])
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
        logger.error(f"Train model error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/model/clear-logs', methods=['POST'])
def clear_logs():
    try:
        container = current_app.container
        trainer = container.trainer()
        if hasattr(trainer, 'clear_logs'):
            trainer.clear_logs()
            return jsonify({'success': True, 'message': 'Logs cleared'}), 200
        return jsonify({'success': False, 'error': 'Method not available'}), 400
    except Exception as e:
        logger.error(f"Clear logs error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/model/history', methods=['GET'])
def model_history():
    try:
        container = current_app.container
        model_manager = container.model_manager()
        history = model_manager.get_version_history(limit=20)
        return jsonify({'success': True, 'data': history}), 200
    except Exception as e:
        logger.error(f"Model history error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================
# ۶. CoinStats (داده‌های مستقیم)
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
# ۷. هشدارها
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
# ۸. اعتبار
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


# ============================================================
# ۹. دیباگ
# ============================================================

@api_bp.route('/debug/exec', methods=['POST'])
def debug_exec():
    try:
        data = request.json
        command = data.get('command', '').strip()
        if not command:
            return jsonify({'success': False, 'error': 'Command required'}), 400
        
        dangerous = ['os.system', 'subprocess', 'exec(', 'eval(', '__import__']
        for kw in dangerous:
            if kw in command:
                return jsonify({'success': False, 'error': 'Dangerous command'}), 403
        
        import io
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
    except Exception as e:
        logger.error(f"Debug exec error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/debug/env', methods=['GET'])
def debug_env():
    try:
        env = {
            'PORT': os.getenv('PORT'),
            'FLASK_DEBUG': os.getenv('FLASK_DEBUG'),
            'FLASK_ENV': os.getenv('FLASK_ENV'),
            'COINSTATS_API_KEY': '***' if os.getenv('COINSTATS_API_KEY') else None,
        }
        return jsonify({'success': True, 'data': env}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
