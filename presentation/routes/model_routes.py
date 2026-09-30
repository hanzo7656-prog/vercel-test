# presentation/routes/model_routes.py
# ============================================================
# Model Routes - نسخه ۱.۰
# RuleEngine + WeightCalibrator + Version Management
# ============================================================
# 
# شامل ۱۸ endpoint در ۶ گروه:
#   - Status & Info (4)
#   - Rules & Config (7)
#   - Calibration (4)
#   - Versions (4)
#   - Schedule (3)
#   - Export & History (2)
# ============================================================

import json
import logging
from datetime import datetime

from flask import (
    Blueprint,
    request,
    jsonify,
    current_app,
    send_file,
)
import io

from infrastructure.auth.auth_manager import require_auth
from infrastructure.database import get_primary

logger = logging.getLogger(__name__)

model_bp = Blueprint('model', __name__, url_prefix='/api/model')


# ============================================================
# Helpers
# ============================================================

def _get_model_manager():
    """دریافت ModelManager از Container"""
    container = current_app.container
    return container.get('model_manager')


def _get_trainer():
    """دریافت AutoTrainer (Calibrator) از Container"""
    container = current_app.container
    return container.get('trainer')


def _success(data=None, **extra):
    """پاسخ موفق استاندارد"""
    response = {'success': True}
    if data is not None:
        response['data'] = data
    response.update(extra)
    response['timestamp'] = datetime.now().isoformat()
    return jsonify(response)


def _error(message: str, status_code: int = 400, **extra):
    """پاسخ خطا استاندارد"""
    response = {
        'success': False,
        'error': message,
        'timestamp': datetime.now().isoformat(),
    }
    response.update(extra)
    return jsonify(response), status_code


# ============================================================
# گروه ۱: Status & Info
# ============================================================

@model_bp.route('', methods=['GET'])
@model_bp.route('/', methods=['GET'])
@require_auth()
def model_home():
    """
    صفحه اصلی Model API
    """
    return _success({
        'name': 'Model API',
        'version': '1.0.0',
        'engine': 'RuleEngine',
        'endpoints': {
            'status': {
                'status': '/api/model/status',
                'stats': '/api/model/stats',
                'trainer_stats': '/api/model/trainer-stats',
            },
            'rules_config': {
                'rules': '/api/model/rules',
                'rule_detail': '/api/model/rules/<name>',
                'config': '/api/model/config',
                'runtime_config': '/api/model/config/runtime',
                'validate_config': '/api/model/config/validate',
            },
            'calibration': {
                'profiles': '/api/model/calibrate/profiles',
                'calibrate': '/api/model/calibrate',
                'force': '/api/model/calibrate/force',
                'history': '/api/model/calibrate/history',
            },
            'versions': {
                'list': '/api/model/versions',
                'detail': '/api/model/versions/<version>',
                'activate': '/api/model/versions/<version>/activate',
                'export': '/api/model/export/<version>',
            },
            'schedule': {
                'status': '/api/model/schedule/status',
                'start': '/api/model/schedule/start',
                'stop': '/api/model/schedule/stop',
            },
        },
    })


@model_bp.route('/status', methods=['GET'])
@require_auth()
def model_status():
    """
    وضعیت کلی مدل
    
    خروجی:
        - loaded: آیا RuleEngine بارگذاری شده؟
        - version: نسخه فعال
        - rule_count: تعداد ruleها
        - aggregation: روش ترکیب امتیازها
        - min_pass_score: آستانه قبولی
        - runtime_config_active: آیا runtime config داریم؟
        - model_type: rule_config
    """
    try:
        mm = _get_model_manager()
        stats = mm.get_stats()
        engine_stats = stats.get('engine', {})
        
        return _success({
            'loaded': stats.get('loaded', False),
            'version': stats.get('version', 'default'),
            'model_type': 'rule_config',
            'mode': 'RULE_ENGINE',
            
            'rule_count': stats.get('rule_count', 0),
            'aggregation': engine_stats.get('aggregation', 'weighted_sum'),
            'min_pass_score': engine_stats.get('min_pass_score', 0.55),
            
            'runtime_config_active': stats.get('runtime_config_active', False),
            'runtime_keys': stats.get('runtime_keys', []),
            
            'db_connected': stats.get('db_connected', False),
            'cache_connected': stats.get('cache_connected', False),
        })
    
    except Exception as e:
        logger.error(f"Model status error: {e}", exc_info=True)
        return _error(str(e), 500)


@model_bp.route('/stats', methods=['GET'])
@require_auth()
def model_stats():
    """
    آمار کامل مدل
    
    خروجی:
        - model: آمار RuleEngine
        - repository: آمار Repository (نسخه‌ها، دقت‌ها)
        - quota: وضعیت فضا
        - runtime_stats: تعداد عملیات انجام‌شده
    """
    try:
        mm = _get_model_manager()
        stats = mm.get_stats()
        
        return _success(stats)
    
    except Exception as e:
        logger.error(f"Model stats error: {e}", exc_info=True)
        return _error(str(e), 500)


@model_bp.route('/trainer-stats', methods=['GET'])
@require_auth()
def model_trainer_stats():
    """
    آمار کامل AutoTrainer (WeightCalibrator)
    
    خروجی:
        - is_running: آیا کالیبراسیون خودکار فعاله؟
        - is_calibrating: آیا در حال کالیبراسیونه؟
        - stats: آمار تفصیلی
        - api_status: وضعیت API
        - quota: وضعیت فضا
        - recent_logs: آخرین لاگ‌ها
    """
    try:
        trainer = _get_trainer()
        
        if not hasattr(trainer, 'get_stats'):
            return _error('Trainer does not support get_stats', 503)
        
        stats = trainer.get_stats()
        return _success(stats)
    
    except Exception as e:
        logger.error(f"Trainer stats error: {e}", exc_info=True)
        return _error(str(e), 500)


# ============================================================
# گروه ۲: Rules & Config
# ============================================================

@model_bp.route('/rules', methods=['GET'])
@require_auth()
def model_rules():
    """
    لیست ruleهای فعال با وزن‌ها
    
    خروجی:
        [
            {
                "name": "rsi",
                "enabled": true,
                "weight": 0.30,
                "config": {...}
            },
            ...
        ]
    """
    try:
        mm = _get_model_manager()
        
        if mm.engine is None:
            return _error('RuleEngine not loaded', 400)
        
        rules = []
        for rule in mm.engine.rules:
            rules.append({
                'name': rule.name,
                'enabled': rule.enabled,
                'weight': rule.weight,
                'config': rule.config,
            })
        
        return _success(rules, count=len(rules))
    
    except Exception as e:
        logger.error(f"Model rules error: {e}", exc_info=True)
        return _error(str(e), 500)


@model_bp.route('/rules/<name>', methods=['GET'])
@require_auth()
def model_rule_detail(name):
    """
    جزئیات یک rule خاص
    """
    try:
        mm = _get_model_manager()
        
        if mm.engine is None:
            return _error('RuleEngine not loaded', 400)
        
        for rule in mm.engine.rules:
            if rule.name == name:
                return _success({
                    'name': rule.name,
                    'enabled': rule.enabled,
                    'weight': rule.weight,
                    'config': rule.config,
                    'class': type(rule).__name__,
                })
        
        return _error(f"Rule '{name}' not found", 404)
    
    except Exception as e:
        logger.error(f"Model rule detail error: {e}", exc_info=True)
        return _error(str(e), 500)


@model_bp.route('/config', methods=['GET'])
@require_auth()
def model_config():
    """
    دریافت config فعلی (default + override + runtime)
    """
    try:
        mm = _get_model_manager()
        config = mm.get_active_config()
        
        return _success(config)
    
    except Exception as e:
        logger.error(f"Model config error: {e}", exc_info=True)
        return _error(str(e), 500)


@model_bp.route('/config', methods=['POST'])
@require_auth('admin')
def update_model_config():
    """
    آپدیت config (ذخیره در DB)
    
    Body (نمونه):
        {
            "rules": {
                "rsi": {"weight": 0.40, "min": 30, "max": 65},
                "volume": {"weight": 0.25, "multiplier": 1.5}
            },
            "scoring": {
                "min_pass_score": 0.60
            }
        }
    """
    try:
        data = request.json or {}
        
        if not data:
            return _error('Empty body', 400)
        
        mm = _get_model_manager()
        
        # کاربر
        updated_by = None
        try:
            if hasattr(request, 'user') and request.user:
                updated_by = request.user.get('username')
        except Exception:
            pass
        
        result = mm.update_active_config(
            updates=data,
            persist=True,
            updated_by=updated_by,
        )
        
        return _success(
            result.get('config'),
            applied_keys=result.get('applied_keys', []),
            persisted=True,
        ) if result.get('success') else _error(
            result.get('error', 'Config update failed'),
            400,
        )
    
    except Exception as e:
        logger.error(f"Update config error: {e}", exc_info=True)
        return _error(str(e), 500)


@model_bp.route('/config/runtime', methods=['PATCH'])
@require_auth('admin')
def update_runtime_config():
    """
    آپدیت موقت config (فقط در memory، تا restart بعدی)
    
    Body: مثل /config
    """
    try:
        data = request.json or {}
        
        if not data:
            return _error('Empty body', 400)
        
        mm = _get_model_manager()
        
        result = mm.update_active_config(
            updates=data,
            persist=False,
        )
        
        return _success(
            result.get('config'),
            applied_keys=result.get('applied_keys', []),
            persisted=False,
        ) if result.get('success') else _error(
            result.get('error', 'Config update failed'),
            400,
        )
    
    except Exception as e:
        logger.error(f"Update runtime config error: {e}", exc_info=True)
        return _error(str(e), 500)


@model_bp.route('/config/runtime', methods=['DELETE'])
@require_auth('admin')
def reset_runtime_config():
    """
    ریست runtime config (برگشت به config پایه)
    """
    try:
        mm = _get_model_manager()
        result = mm.reset_runtime_config()
        
        return _success(result.get('config')) if result.get('success') else _error(
            result.get('error', 'Reset failed'),
            400,
        )
    
    except Exception as e:
        logger.error(f"Reset runtime config error: {e}", exc_info=True)
        return _error(str(e), 500)


@model_bp.route('/config/validate', methods=['POST'])
@require_auth()
def validate_config():
    """
    اعتبارسنجی config قبل از اعمال
    
    Body: config پیشنهادی
    
    خروجی:
        {
            "valid": true/false,
            "errors": [],
            "warnings": [],
            "normalized_config": {...}
        }
    """
    try:
        data = request.json or {}
        
        if not data:
            return _error('Empty body', 400)
        
        # اعتبارسنجی ساده
        errors = []
        warnings = []
        normalized = {}
        
        # چک rules
        if 'rules' in data:
            rules = data['rules']
            if not isinstance(rules, dict):
                errors.append("rules must be a dict")
            else:
                normalized['rules'] = {}
                for rule_name, rule_config in rules.items():
                    if not isinstance(rule_config, dict):
                        errors.append(f"rules.{rule_name} must be a dict")
                        continue
                    
                    # weight
                    if 'weight' in rule_config:
                        try:
                            w = float(rule_config['weight'])
                            if not (0 <= w <= 1):
                                errors.append(
                                    f"rules.{rule_name}.weight must be 0-1"
                                )
                            else:
                                normalized['rules'][rule_name] = {'weight': w}
                        except (ValueError, TypeError):
                            errors.append(
                                f"rules.{rule_name}.weight must be numeric"
                            )
                    
                    # rule-specific validation
                    if rule_name == 'rsi':
                        if 'min' in rule_config:
                            try:
                                v = float(rule_config['min'])
                                if not (0 <= v <= 100):
                                    errors.append("rsi.min must be 0-100")
                                else:
                                    normalized['rules'].setdefault(rule_name, {})['min'] = v
                            except (ValueError, TypeError):
                                errors.append("rsi.min must be numeric")
                        
                        if 'max' in rule_config:
                            try:
                                v = float(rule_config['max'])
                                if not (0 <= v <= 100):
                                    errors.append("rsi.max must be 0-100")
                                else:
                                    normalized['rules'].setdefault(rule_name, {})['max'] = v
                            except (ValueError, TypeError):
                                errors.append("rsi.max must be numeric")
                    
                    elif rule_name == 'volume':
                        if 'multiplier' in rule_config:
                            try:
                                v = float(rule_config['multiplier'])
                                if v <= 0:
                                    errors.append("volume.multiplier must be > 0")
                                else:
                                    normalized['rules'].setdefault(rule_name, {})['multiplier'] = v
                            except (ValueError, TypeError):
                                errors.append("volume.multiplier must be numeric")
        
        # چک scoring
        if 'scoring' in data:
            scoring = data['scoring']
            if not isinstance(scoring, dict):
                errors.append("scoring must be a dict")
            else:
                normalized['scoring'] = {}
                
                if 'min_pass_score' in scoring:
                    try:
                        v = float(scoring['min_pass_score'])
                        if not (0 <= v <= 1):
                            errors.append("scoring.min_pass_score must be 0-1")
                        else:
                            normalized['scoring']['min_pass_score'] = v
                    except (ValueError, TypeError):
                        errors.append("scoring.min_pass_score must be numeric")
                
                if 'aggregation' in scoring:
                    valid_agg = ['weighted_sum', 'max', 'voting']
                    if scoring['aggregation'] not in valid_agg:
                        errors.append(
                            f"scoring.aggregation must be one of {valid_agg}"
                        )
                    else:
                        normalized['scoring']['aggregation'] = scoring['aggregation']
        
        return _success({
            'valid': len(errors) == 0,
            'errors': errors,
            'warnings': warnings,
            'normalized_config': normalized,
        })
    
    except Exception as e:
        logger.error(f"Validate config error: {e}", exc_info=True)
        return _error(str(e), 500)


# ============================================================
# گروه ۳: Calibration
# ============================================================

@model_bp.route('/calibrate/profiles', methods=['GET'])
@require_auth()
def calibration_profiles():
    """
    لیست profileهای کالیبراسیون
    
    خروجی:
        [
            {
                "id": "fast",
                "name": "سریع",
                "description": "...",
                "strategy": "grid",
                "estimated_time_seconds": 30
            },
            ...
        ]
    """
    try:
        trainer = _get_trainer()
        
        if hasattr(trainer, 'get_presets'):
            presets = trainer.get_presets()
        else:
            # fallback
            from models.trainer.auto_trainer import CALIBRATION_PROFILES
            presets = [
                {'id': k, **v}
                for k, v in CALIBRATION_PROFILES.items()
            ]
        
        return _success(presets, count=len(presets))
    
    except Exception as e:
        logger.error(f"Calibration profiles error: {e}", exc_info=True)
        return _error(str(e), 500)


@model_bp.route('/calibrate', methods=['POST'])
@require_auth('admin')
def calibrate_model():
    """
    اجرای کالیبراسیون وزن‌ها
    
    Body:
        {
            "period": "1m",
            "profile_name": "balanced",
            "strategy": "grid",           // اختیاری (override)
            "coins": ["bitcoin", "ethereum"],  // اختیاری
            "save": true
        }
    """
    try:
        data = request.json or {}
        
        period = data.get('period', '1m')
        profile_name = data.get('profile_name', 'balanced')
        strategy = data.get('strategy')
        coins = data.get('coins')
        save = data.get('save', True)
        
        trainer = _get_trainer()
        
        result = trainer.calibrate(
            period=period,
            coins=coins,
            profile_name=profile_name,
            strategy=strategy,
            save=save,
        )
        
        return _success(result) if result.get('success') else _error(
            result.get('error', 'Calibration failed'),
            400,
            details=result,
        )
    
    except Exception as e:
        logger.error(f"Calibrate error: {e}", exc_info=True)
        return _error(str(e), 500)


@model_bp.route('/calibrate/force', methods=['POST'])
@require_auth('admin')
def force_calibrate():
    """
    کالیبراسیون اجباری (از SelfHealer)
    
    Body:
        {
            "profile_name": "fast",
            "period": "1m"
        }
    """
    try:
        data = request.json or {}
        profile_name = data.get('profile_name', 'fast')
        period = data.get('period', '1m')
        
        container = current_app.container
        healer = container.get('self_healer')
        
        if healer is None:
            return _error('SelfHealer not available', 503)
        
        result = healer.force_recalibrate(
            profile_name=profile_name,
            period=period,
        )
        
        return _success(result) if result.get('success') else _error(
            result.get('error', 'Force calibration failed'),
            400,
            details=result,
        )
    
    except Exception as e:
        logger.error(f"Force calibrate error: {e}", exc_info=True)
        return _error(str(e), 500)


@model_bp.route('/calibrate/history', methods=['GET'])
@require_auth()
def calibration_history():
    """
    تاریخچه کالیبراسیون‌ها
    
    Query params:
        limit: حداکثر تعداد (پیش‌فرض: 20)
        period: فیلتر بازه (اختیاری)
    """
    try:
        limit = request.args.get('limit', 20, type=int)
        period = request.args.get('period')
        
        trainer = _get_trainer()
        
        history = trainer.get_training_history(
            period=period,
            limit=limit,
        )
        
        return _success(history, count=len(history))
    
    except Exception as e:
        logger.error(f"Calibration history error: {e}", exc_info=True)
        return _error(str(e), 500)


# ============================================================
# گروه ۴: Versions
# ============================================================

@model_bp.route('/versions', methods=['GET'])
@require_auth()
def list_versions():
    """
    لیست نسخه‌ها
    
    Query params:
        limit: حداکثر تعداد (پیش‌فرض: 50)
        model_type: فیلتر نوع (rule_config / xgboost)
    """
    try:
        limit = request.args.get('limit', 50, type=int)
        model_type = request.args.get('model_type', 'rule_config')
        
        mm = _get_model_manager()
        versions = mm.get_version_history(
            limit=limit,
            model_type=model_type,
        )
        
        return _success(versions, count=len(versions))
    
    except Exception as e:
        logger.error(f"List versions error: {e}", exc_info=True)
        return _error(str(e), 500)


@model_bp.route('/versions/<version>', methods=['GET'])
@require_auth()
def version_detail(version):
    """
    جزئیات یک نسخه
    """
    try:
        mm = _get_model_manager()
        
        # از Repository
        info = mm.repository.find_by_version(version)
        if not info:
            return _error(f"Version '{version}' not found", 404)
        
        # config کامل
        config = mm.repository.load_rule_config(version)
        
        return _success({
            'info': info,
            'config': config,
        })
    
    except Exception as e:
        logger.error(f"Version detail error: {e}", exc_info=True)
        return _error(str(e), 500)


@model_bp.route('/versions/<version>/activate', methods=['POST'])
@require_auth('admin')
def activate_version(version):
    """
    فعال‌سازی یک نسخه
    """
    try:
        mm = _get_model_manager()
        
        success = mm.set_active(version)
        
        if success:
            return _success({
                'activated': version,
                'current_version': mm.current_version,
            })
        
        return _error(f"Failed to activate '{version}'", 400)
    
    except Exception as e:
        logger.error(f"Activate version error: {e}", exc_info=True)
        return _error(str(e), 500)


@model_bp.route('/versions/<version>', methods=['DELETE'])
@require_auth('admin')
def delete_version(version):
    """
    حذف یک نسخه
    
    نکته: نسخه فعال حذف نمی‌شه.
    """
    try:
        mm = _get_model_manager()
        
        # چک نبودن نسخه فعال
        if mm.current_version == version:
            return _error('Cannot delete active version', 400)
        
        success = mm.delete_version(version)
        
        if success:
            return _success({'deleted': version})
        
        return _error(f"Failed to delete '{version}'", 400)
    
    except Exception as e:
        logger.error(f"Delete version error: {e}", exc_info=True)
        return _error(str(e), 500)


# ============================================================
# گروه ۵: Schedule (کالیبراسیون خودکار)
# ============================================================

@model_bp.route('/schedule/status', methods=['GET'])
@require_auth()
def schedule_status():
    """
    وضعیت کالیبراسیون خودکار
    """
    try:
        trainer = _get_trainer()
        stats = trainer.get_stats() if hasattr(trainer, 'get_stats') else {}
        inner = stats.get('stats', {})
        
        return _success({
            'is_running': stats.get('is_running', False),
            'is_calibrating': stats.get('is_calibrating', False),
            
            'interval_hours': inner.get('interval_hours', 6),
            'period': inner.get('training_period', '1m'),
            'coins': stats.get('coins', []),
            'profile_name': inner.get('profile_name', 'balanced'),
            
            'total_calibrations': inner.get('total_calibrations', 0),
            'successful_calibrations': inner.get('successful_calibrations', 0),
            'failed_calibrations': inner.get('failed_calibrations', 0),
            'last_calibration': inner.get('last_calibration'),
            'last_error': inner.get('last_error'),
            'last_score': inner.get('last_score'),
            'last_improvement': inner.get('last_improvement'),
            
            'recent_logs': stats.get('logs', [])[-10:],
        })
    
    except Exception as e:
        logger.error(f"Schedule status error: {e}", exc_info=True)
        return _error(str(e), 500)


@model_bp.route('/schedule/start', methods=['POST'])
@require_auth('admin')
def schedule_start():
    """
    شروع کالیبراسیون خودکار
    
    Body:
        {
            "interval_hours": 6,
            "period": "1m",
            "profile_name": "balanced",
            "coins": ["bitcoin", "ethereum"]
        }
    """
    try:
        data = request.json or {}
        
        interval_hours = data.get('interval_hours', 6)
        period = data.get('period', '1m')
        profile_name = data.get('profile_name', 'balanced')
        coins = data.get('coins')
        
        trainer = _get_trainer()
        
        result = trainer.start_auto_train(
            interval_hours=interval_hours,
            period=period,
            profile_name=profile_name,
            coins=coins,
        )
        
        return _success(result) if result.get('success') else _error(
            result.get('message', 'Start failed'),
            400,
        )
    
    except Exception as e:
        logger.error(f"Schedule start error: {e}", exc_info=True)
        return _error(str(e), 500)


@model_bp.route('/schedule/stop', methods=['POST'])
@require_auth('admin')
def schedule_stop():
    """
    توقف کالیبراسیون خودکار
    """
    try:
        trainer = _get_trainer()
        result = trainer.stop_auto_train()
        
        return _success(result) if result.get('success') else _error(
            result.get('message', 'Stop failed'),
            400,
        )
    
    except Exception as e:
        logger.error(f"Schedule stop error: {e}", exc_info=True)
        return _error(str(e), 500)


# ============================================================
# گروه ۶: Export
# ============================================================

@model_bp.route('/export/<version>', methods=['GET'])
@require_auth()
def export_version(version):
    """
    خروجی JSON config یک نسخه
    
    Query params:
        download: اگه true، فایل دانلود می‌شه (پیش‌فرض: false)
    """
    try:
        mm = _get_model_manager()
        
        # config
        config = mm.repository.load_rule_config(version)
        if config is None:
            return _error(f"Version '{version}' not found", 404)
        
        download = request.args.get('download', 'false').lower() == 'true'
        
        if download:
            # به‌عنوان فایل
            json_bytes = json.dumps(
                config,
                ensure_ascii=False,
                indent=2,
            ).encode('utf-8')
            
            return send_file(
                io.BytesIO(json_bytes),
                as_attachment=True,
                download_name=f'rule_config_{version}.json',
                mimetype='application/json',
            )
        
        # به‌عنوان JSON
        return _success({
            'version': version,
            'config': config,
        })
    
    except Exception as e:
        logger.error(f"Export version error: {e}", exc_info=True)
        return _error(str(e), 500)
