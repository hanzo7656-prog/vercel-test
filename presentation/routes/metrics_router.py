# presentation/routes/metrics_routes.py
# ============================================================
# Metrics Routes - روت‌های متریک
# ============================================================

import logging
from datetime import datetime
from flask import Blueprint, jsonify, request, current_app

from application.services.monitoring_service import MonitoringService

logger = logging.getLogger(__name__)

metrics_bp = Blueprint('metrics', __name__, url_prefix='/api/metrics')


@metrics_bp.route('', methods=['GET'])
def get_metrics():
    """دریافت متریک‌های لحظه‌ای"""
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


@metrics_bp.route('/summary', methods=['GET'])
def get_metrics_summary():
    """دریافت خلاصه متریک‌ها"""
    try:
        container = current_app.container
        monitoring_service: MonitoringService = container.monitoring_service()
        
        summary = monitoring_service.get_metrics_summary()
        
        return jsonify(summary), 200 if summary.get('success') else 500
        
    except Exception as e:
        logger.error(f"Error in get_metrics_summary: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500


@metrics_bp.route('/dashboard', methods=['GET'])
def get_dashboard_metrics():
    """دریافت متریک‌های داشبورد"""
    try:
        container = current_app.container
        monitoring_service: MonitoringService = container.monitoring_service()
        
        metrics = monitoring_service.get_dashboard_metrics()
        
        return jsonify(metrics), 200 if metrics.get('success') else 500
        
    except Exception as e:
        logger.error(f"Error in get_dashboard_metrics: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500


@metrics_bp.route('/threads', methods=['GET'])
def get_thread_metrics():
    """دریافت وضعیت Threadها"""
    try:
        container = current_app.container
        monitoring_service: MonitoringService = container.monitoring_service()
        
        status = monitoring_service.get_thread_status()
        
        return jsonify(status), 200 if status.get('success') else 500
        
    except Exception as e:
        logger.error(f"Error in get_thread_metrics: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500


@metrics_bp.route('/api', methods=['GET'])
def get_api_metrics():
    """دریافت آمار API"""
    try:
        container = current_app.container
        monitoring_service: MonitoringService = container.monitoring_service()
        api_client = container.api_client()
        
        stats = monitoring_service.get_api_stats(api_client)
        
        return jsonify(stats), 200 if stats.get('success') else 500
        
    except Exception as e:
        logger.error(f"Error in get_api_metrics: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500
