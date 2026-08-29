# presentation/routes/api_routes.py
# ============================================================
# API Routes - نسخه ۳.۰ (با Use Cases جدید)
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
from container import Container

logger = logging.getLogger(__name__)

# ایجاد Blueprint
api_bp = Blueprint('api', __name__, url_prefix='/api')


# ============================================================
# ۱. روت‌های پیش‌بینی
# ============================================================

@api_bp.route('/predict', methods=['GET'])
@require_auth()
def predict():
    """
    پیش‌بینی تک‌ارز
    
    Query Parameters:
        coin: شناسه ارز (پیش‌فرض: bitcoin)
        period: بازه زمانی (پیش‌فرض: 24h)
    
    Response:
        {
            "success": true,
            "data": {...},
            "timestamp": "..."
        }
    """
    try:
        coin = request.args.get('coin', 'bitcoin')
        period = request.args.get('period', '24h')
        
        # دریافت سرویس از Container
        container = current_app.container
        prediction_service: PredictionService = container.prediction_service()
        
        # اجرای پیش‌بینی
        dto = prediction_service.predict_single(coin, period)
        
        return jsonify({
            'success': dto.success,
            'data': dto.data,
            'error': dto.error,
            'timestamp': datetime.now().isoformat()
        }), 200 if dto.success else 400
        
    except ValueError as e:
        logger.warning(f"Validation error in predict: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 400
    except Exception as e:
        logger.error(f"Error in predict: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': 'Internal server error',
            'timestamp': datetime.now().isoformat()
        }), 500


@api_bp.route('/predict/multiple', methods=['POST'])
@require_auth()
def predict_multiple():
    """
    پیش‌بینی چندارز (موازی)
    
    Body:
        {
            "coins": ["bitcoin", "ethereum", "solana"],
            "period": "24h"
        }
    
    Response:
        {
            "success": true,
            "data": {"results": [...]},
            "count": 3,
            "timestamp": "..."
        }
    """
    try:
        data = request.json
        if not data:
            return jsonify({
                'success': False,
                'error': 'No data provided',
                'timestamp': datetime.now().isoformat()
            }), 400
        
        coins = data.get('coins', [])
        period = data.get('period', '24h')
        
        if not coins:
            return jsonify({
                'success': False,
                'error': 'No coins provided',
                'timestamp': datetime.now().isoformat()
            }), 400
        
        # دریافت سرویس از Container
        container = current_app.container
        prediction_service: PredictionService = container.prediction_service()
        
        # ایجاد DTO درخواست
        request_dto = PredictionRequestDTO(coins=coins, period=period)
        
        # اجرای پیش‌بینی
        dto = prediction_service.predict_from_request(request_dto)
        
        return jsonify({
            'success': dto.success,
            'data': dto.data,
            'count': dto.count,
            'error': dto.error,
            'timestamp': datetime.now().isoformat()
        }), 200 if dto.success else 400
        
    except Exception as e:
        logger.error(f"Error in predict_multiple: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500


@api_bp.route('/predict/batch', methods=['POST'])
@require_auth()
def predict_batch():
    """
    پیش‌بینی دسته‌ای
    
    Body:
        {
            "coins": ["bitcoin", "ethereum", "solana", "cardano"],
            "period": "24h",
            "batch_size": 2
        }
    """
    try:
        data = request.json
        if not data:
            return jsonify({
                'success': False,
                'error': 'No data provided',
                'timestamp': datetime.now().isoformat()
            }), 400
        
        coins = data.get('coins', [])
        period = data.get('period', '24h')
        
        if not coins:
            return jsonify({
                'success': False,
                'error': 'No coins provided',
                'timestamp': datetime.now().isoformat()
            }), 400
        
        # دریافت سرویس از Container
        container = current_app.container
        prediction_service: PredictionService = container.prediction_service()
        
        # اجرای پیش‌بینی
        dto = prediction_service.predict_multiple(coins, period)
        
        return jsonify({
            'success': dto.success,
            'data': dto.data,
            'count': dto.count,
            'error': dto.error,
            'timestamp': datetime.now().isoformat()
        }), 200 if dto.success else 400
        
    except Exception as e:
        logger.error(f"Error in predict_batch: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500


# ============================================================
# ۲. روت‌های آموزش مدل
# ============================================================

@api_bp.route('/model/train', methods=['POST'])
@require_auth('admin')
def train_model():
    """
    آموزش مدل
    
    Body:
        {
            "period": "1m",
            "coins": ["bitcoin", "ethereum"],
            "incremental": false
        }
    """
    try:
        data = request.json or {}
        period = data.get('period', '1m')
        coins = data.get('coins', ['bitcoin', 'ethereum'])
        incremental = data.get('incremental', False)
        
        container = current_app.container
        train_use_case: TrainModelUseCase = container.train_use_case()
        
        result = train_use_case.execute(period, coins, incremental)
        
        return jsonify({
            'success': result.get('success', False),
            'data': result,
            'timestamp': datetime.now().isoformat()
        }), 200 if result.get('success') else 400
        
    except Exception as e:
        logger.error(f"Error in train_model: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500


@api_bp.route('/model/train/start', methods=['POST'])
@require_auth('admin')
def start_auto_train():
    """شروع آموزش خودکار"""
    try:
        data = request.json or {}
        interval = data.get('interval', 6)
        period = data.get('period', '1m')
        
        container = current_app.container
        train_use_case: TrainModelUseCase = container.train_use_case()
        
        result = train_use_case.execute_auto(interval, period)
        
        return jsonify({
            'success': result.get('success', False),
            'data': result,
            'timestamp': datetime.now().isoformat()
        }), 200 if result.get('success') else 400
        
    except Exception as e:
        logger.error(f"Error in start_auto_train: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500


@api_bp.route('/model/train/stop', methods=['POST'])
@require_auth('admin')
def stop_auto_train():
    """متوقف کردن آموزش خودکار"""
    try:
        container = current_app.container
        train_use_case: TrainModelUseCase = container.train_use_case()
        
        result = train_use_case.stop_auto()
        
        return jsonify({
            'success': result.get('success', False),
            'data': result,
            'timestamp': datetime.now().isoformat()
        }), 200 if result.get('success') else 400
        
    except Exception as e:
        logger.error(f"Error in stop_auto_train: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500


@api_bp.route('/model/status', methods=['GET'])
@require_auth()
def model_status():
    """دریافت وضعیت مدل"""
    try:
        container = current_app.container
        train_use_case: TrainModelUseCase = container.train_use_case()
        
        status = train_use_case.get_status()
        
        return jsonify({
            'success': True,
            'data': status,
            'timestamp': datetime.now().isoformat()
        }), 200
        
    except Exception as e:
        logger.error(f"Error in model_status: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500


# ============================================================
# ۳. روت‌های مانیتورینگ
# ============================================================

@api_bp.route('/health', methods=['GET'])
def health():
    """بررسی سلامت سیستم"""
    try:
        container = current_app.container
        monitoring_service: MonitoringService = container.monitoring_service()
        
        health_data = monitoring_service.get_health()
        
        status_code = 200 if health_data.get('status') == 'ok' else 503
        
        return jsonify(health_data), status_code
        
    except Exception as e:
        logger.error(f"Error in health: {e}", exc_info=True)
        return jsonify({
            'status': 'error',
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500


@api_bp.route('/health/simple', methods=['GET'])
def health_simple():
    """بررسی ساده سلامت (برای Uptime Robot)"""
    try:
        container = current_app.container
        monitoring_service: MonitoringService = container.monitoring_service()
        
        health_data = monitoring_service.get_health()
        
        if health_data.get('status') == 'ok':
            return jsonify({
                'status': 'ok',
                'timestamp': datetime.now().isoformat()
            }), 200
        else:
            return jsonify({
                'status': 'degraded',
                'timestamp': datetime.now().isoformat()
            }), 503
            
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500


@api_bp.route('/metrics', methods=['GET'])
@require_auth()
def get_metrics():
    """دریافت متریک‌های سیستم"""
    try:
        container = current_app.container
        monitoring_service: MonitoringService = container.monitoring_service()
        
        metrics = monitoring_service.get_metrics()
        
        return jsonify(metrics), 200 if metrics.get('success') else 500
        
    except Exception as e:
        logger.error(f"Error in get_metrics: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500


@api_bp.route('/metrics/dashboard', methods=['GET'])
@require_auth()
def dashboard_metrics():
    """دریافت متریک‌های داشبورد"""
    try:
        container = current_app.container
        monitoring_service: MonitoringService = container.monitoring_service()
        
        metrics = monitoring_service.get_dashboard_metrics()
        
        return jsonify(metrics), 200 if metrics.get('success') else 500
        
    except Exception as e:
        logger.error(f"Error in dashboard_metrics: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500


@api_bp.route('/threads', methods=['GET'])
@require_auth('admin')
def get_threads():
    """دریافت وضعیت Threadها"""
    try:
        container = current_app.container
        monitoring_service: MonitoringService = container.monitoring_service()
        
        status = monitoring_service.get_thread_status()
        
        return jsonify(status), 200 if status.get('success') else 500
        
    except Exception as e:
        logger.error(f"Error in get_threads: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500


# ============================================================
# ۴. روت‌های تست و دیباگ
# ============================================================

@api_bp.route('/test/api', methods=['GET'])
@require_auth()
def test_api():
    """تست ارتباط با API"""
    try:
        container = current_app.container
        api_client = container.api_client()
        
        status = api_client.get_status()
        credits = api_client.get_credits()
        
        return jsonify({
            'success': True,
            'data': {
                'api_status': status,
                'credits': credits,
                'timestamp': datetime.now().isoformat()
            }
        }), 200
        
    except Exception as e:
        logger.error(f"Error in test_api: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500


@api_bp.route('/cache/clear', methods=['POST'])
@require_auth('admin')
def clear_cache():
    """پاک کردن کش"""
    try:
        container = current_app.container
        cache_manager = container.cache_manager()
        
        success = cache_manager.clear()
        
        return jsonify({
            'success': success,
            'message': 'Cache cleared' if success else 'Failed to clear cache',
            'timestamp': datetime.now().isoformat()
        }), 200 if success else 500
        
    except Exception as e:
        logger.error(f"Error in clear_cache: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500
