# presentation/routes/model_routes.py
# ============================================================
# Model Routes - نسخه ۱.۰
# RuleEngine + WeightCalibrator + Screener + State Machine
# ============================================================
# 
# شامل ۴۱ endpoint در ۷ گروه:
#   ۱. Status & Info        (4)
#   ۲. Rules & Config       (7)
#   ۳. Calibration          (4)
#   ۴. Versions             (5)
#   ۵. Schedule             (3)
#   ۶. Screener             (9)
#   ۷. State Machine        (9)
# ============================================================

import io
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

from infrastructure.auth.auth_manager import require_auth
from infrastructure.database import get_primary

logger = logging.getLogger(__name__)


# ============================================================
# Blueprint
# ============================================================

model_bp = Blueprint('model', __name__, url_prefix='/api/model')


# ============================================================
# Helpers
# ============================================================

def _get_model_manager():
    """ModelManager از Container"""
    return current_app.container.get('model_manager')


def _get_trainer():
    """AutoTrainer (WeightCalibrator) از Container"""
    return current_app.container.get('trainer')


def _get_scan_use_case():
    """ScanMarketUseCase از Container"""
    return current_app.container.get('scan_market_use_case')


def _get_state_machine():
    """StateMachine از ModelManager"""
    mm = _get_model_manager()
    return mm.state_machine if mm else None


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


def _normalize_symbol(symbol: str) -> str:
    """
    تبدیل BTCUSDT → BTC/USDT
    
    پشتیبانی از:
        - BTCUSDT   → BTC/USDT
        - BTC_USDT  → BTC/USDT
        - BTC/USDT  → BTC/USDT (بدون تغییر)
        - btcusdt   → BTC/USDT
    """
    if not symbol:
        return symbol
    
    symbol = symbol.strip().upper()
    
    # اگه از قبل / داره
    if '/' in symbol:
        return symbol
    
    # اگه _ داره
    if '_' in symbol:
        return symbol.replace('_', '/')
    
    # BTCUSDT → BTC/USDT
    if symbol.endswith('USDT'):
        base = symbol[:-4]
        if base:
            return f"{base}/USDT"
    
    if symbol.endswith('USDC'):
        base = symbol[:-4]
        if base:
            return f"{base}/USDC"
    
    if symbol.endswith('BUSD'):
        base = symbol[:-4]
        if base:
            return f"{base}/BUSD"
    
    # fallback: فرض کن USDT داره
    return f"{symbol}/USDT"


# ============================================================
# گروه ۱: Status & Info
# ============================================================

@model_bp.route('', methods=['GET'])
@model_bp.route('/', methods=['GET'])
@require_auth()
def model_home():
    """
    صفحه اصلی Model API — لیست همه endpoint‌ها
    """
    return _success({
        'name': 'Model API',
        'version': '1.0.0',
        'engine': 'RuleEngine',
        'endpoints': {
            'status': {
                'home': '/api/model/',
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
            'screener': {
                'scan': '/api/model/screener/scan',
                'latest': '/api/model/screener/scan/latest',
                'result': '/api/model/screener/scan/<scan_id>',
                'single': '/api/model/screener/scan/single',
                'history': '/api/model/screener/history',
                'history_stats': '/api/model/screener/history/stats',
                'config': '/api/model/screener/config',
                'validate_config': '/api/model/screener/config/validate',
            },
            'state': {
                'home': '/api/model/state/',
                'summary': '/api/model/state/summary',
                'transitions': '/api/model/state/transitions',
                'snapshots': '/api/model/state/snapshots',
                'symbol': '/api/model/state/<symbol>',
                'symbol_transitions': '/api/model/state/<symbol>/transitions',
                'symbol_reset': '/api/model/state/<symbol>/reset',
                'symbol_activate': '/api/model/state/<symbol>/activate',
                'symbol_cooling': '/api/model/state/<symbol>/cooling',
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
        - aggregation: روش ترکیب
        - min_pass_score: آستانه
        - runtime_config_active: آیا runtime config فعاله؟
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
    
    Body نمونه:
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
        
        # کاربر (اختیاری)
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
        
        if result.get('success'):
            return _success(
                result.get('config'),
                applied_keys=result.get('applied_keys', []),
                persisted=True,
            )
        
        return _error(
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
    آپدیت موقت config (فقط در memory)
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
        
        if result.get('success'):
            return _success(
                result.get('config'),
                applied_keys=result.get('applied_keys', []),
                persisted=False,
            )
        
        return _error(
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
        
        if result.get('success'):
            return _success(result.get('config'))
        
        return _error(result.get('error', 'Reset failed'), 400)
    
    except Exception as e:
        logger.error(f"Reset runtime config error: {e}", exc_info=True)
        return _error(str(e), 500)


@model_bp.route('/config/validate', methods=['POST'])
@require_auth()
def validate_config():
    """
    اعتبارسنجی config قبل از اعمال
    """
    try:
        data = request.json or {}
        
        if not data:
            return _error('Empty body', 400)
        
        errors = []
        warnings = []
        normalized = {}
        
        # ============================================================
        # چک rules
        # ============================================================
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
                    
                    normalized['rules'][rule_name] = {}
                    
                    # weight
                    if 'weight' in rule_config:
                        try:
                            w = float(rule_config['weight'])
                            if not (0 <= w <= 1):
                                errors.append(
                                    f"rules.{rule_name}.weight must be 0-1"
                                )
                            else:
                                normalized['rules'][rule_name]['weight'] = w
                        except (ValueError, TypeError):
                            errors.append(
                                f"rules.{rule_name}.weight must be numeric"
                            )
                    
                    # enabled
                    if 'enabled' in rule_config:
                        if isinstance(rule_config['enabled'], bool):
                            normalized['rules'][rule_name]['enabled'] = rule_config['enabled']
                        else:
                            errors.append(
                                f"rules.{rule_name}.enabled must be boolean"
                            )
                    
                    # rule-specific
                    if rule_name == 'rsi':
                        if 'min' in rule_config:
                            try:
                                v = float(rule_config['min'])
                                if not (0 <= v <= 100):
                                    errors.append("rsi.min must be 0-100")
                                else:
                                    normalized['rules'][rule_name]['min'] = v
                            except (ValueError, TypeError):
                                errors.append("rsi.min must be numeric")
                        
                        if 'max' in rule_config:
                            try:
                                v = float(rule_config['max'])
                                if not (0 <= v <= 100):
                                    errors.append("rsi.max must be 0-100")
                                else:
                                    normalized['rules'][rule_name]['max'] = v
                            except (ValueError, TypeError):
                                errors.append("rsi.max must be numeric")
                    
                    elif rule_name == 'volume':
                        if 'multiplier' in rule_config:
                            try:
                                v = float(rule_config['multiplier'])
                                if v <= 0:
                                    errors.append("volume.multiplier must be > 0")
                                else:
                                    normalized['rules'][rule_name]['multiplier'] = v
                            except (ValueError, TypeError):
                                errors.append("volume.multiplier must be numeric")
                    
                    elif rule_name == 'trend':
                        if 'vs_ma' in rule_config:
                            valid = ['above', 'below', 'any']
                            if rule_config['vs_ma'] not in valid:
                                errors.append(
                                    f"trend.vs_ma must be one of {valid}"
                                )
                            else:
                                normalized['rules'][rule_name]['vs_ma'] = rule_config['vs_ma']
        
        # ============================================================
        # چک scoring
        # ============================================================
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
    """
    try:
        trainer = _get_trainer()
        
        if hasattr(trainer, 'get_presets'):
            presets = trainer.get_presets()
        else:
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
            "strategy": "grid",         // اختیاری
            "coins": ["bitcoin"],        // اختیاری
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
        
        if result.get('success'):
            return _success(result)
        
        return _error(
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
    """
    try:
        data = request.json or {}
        profile_name = data.get('profile_name', 'fast')
        period = data.get('period', '1m')
        
        healer = current_app.container.get('self_healer')
        
        if healer is None:
            return _error('SelfHealer not available', 503)
        
        result = healer.force_recalibrate(
            profile_name=profile_name,
            period=period,
        )
        
        if result.get('success'):
            return _success(result)
        
        return _error(
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
        
        info = mm.repository.find_by_version(version)
        if not info:
            return _error(f"Version '{version}' not found", 404)
        
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
    حذف یک نسخه (نسخه فعال حذف نمی‌شه)
    """
    try:
        mm = _get_model_manager()
        
        if mm.current_version == version:
            return _error('Cannot delete active version', 400)
        
        success = mm.delete_version(version)
        
        if success:
            return _success({'deleted': version})
        
        return _error(f"Failed to delete '{version}'", 400)
    
    except Exception as e:
        logger.error(f"Delete version error: {e}", exc_info=True)
        return _error(str(e), 500)


@model_bp.route('/export/<version>', methods=['GET'])
@require_auth()
def export_version(version):
    """
    خروجی JSON config یک نسخه
    
    Query params:
        download: اگه true، فایل دانلود می‌شه
    """
    try:
        mm = _get_model_manager()
        
        config = mm.repository.load_rule_config(version)
        if config is None:
            return _error(f"Version '{version}' not found", 404)
        
        download = request.args.get('download', 'false').lower() == 'true'
        
        if download:
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
        
        return _success({
            'version': version,
            'config': config,
        })
    
    except Exception as e:
        logger.error(f"Export version error: {e}", exc_info=True)
        return _error(str(e), 500)


# ============================================================
# گروه ۵: Schedule
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
        
        if result.get('success'):
            return _success(result)
        
        return _error(result.get('message', 'Start failed'), 400)
    
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
        
        if result.get('success'):
            return _success(result)
        
        return _error(result.get('message', 'Stop failed'), 400)
    
    except Exception as e:
        logger.error(f"Schedule stop error: {e}", exc_info=True)
        return _error(str(e), 500)


# ============================================================
# گروه ۶: Screener 
# ============================================================

@model_bp.route('/screener/scan', methods=['POST'])
@require_auth('admin')
def screener_scan():
    """
    اجرای اسکن کامل بازار
    
    Body (همه اختیاری):
        {
            "symbols": ["BTC/USDT", "ETH/USDT"],  // اگه None، از config می‌گیره
            "top_n": 30,
            "timeframe": "4h",
            "max_results": 10,
            "update_state": true,
            "use_cache": true
        }
    
    خروجی:
        {
            "scan_id": "scan-20250930-1430-abc123",
            "total_scanned": 187,
            "passed_count": 8,
            "results": [...],
            "duration_seconds": 12.5,
            "config_used": {...}
        }
    """
    try:
        data = request.json or {}
        
        symbols = data.get('symbols')
        top_n = data.get('top_n', 30)
        timeframe = data.get('timeframe')
        max_results = data.get('max_results', 10)
        update_state = data.get('update_state', True)
        use_cache = data.get('use_cache', True)
        
        use_case = _get_scan_use_case()
        
        result = use_case.execute(
            symbols=symbols,
            top_n=top_n,
            timeframe=timeframe,
            max_results=max_results,
            update_state=update_state,
            use_cache=use_cache,
        )
        
        return _success(result.to_dict())
    
    except Exception as e:
        logger.error(f"Screener scan error: {e}", exc_info=True)
        return _error(str(e), 500)


@model_bp.route('/screener/scan/latest', methods=['GET'])
@require_auth()
def screener_latest():
    """
    آخرین اسکن انجام‌شده
    """
    try:
        use_case = _get_scan_use_case()
        cached = use_case.get_cached_scan("latest")
        
        if not cached:
            return _error('No recent scan found', 404)
        
        return _success(cached)
    
    except Exception as e:
        logger.error(f"Screener latest error: {e}", exc_info=True)
        return _error(str(e), 500)


@model_bp.route('/screener/scan/<scan_id>', methods=['GET'])
@require_auth()
def screener_result(scan_id):
    """
    بازیابی نتیجه یک اسکن با ID
    
    مثال:
        GET /api/model/screener/scan/scan-20250930-1430-abc123
    """
    try:
        use_case = _get_scan_use_case()
        cached = use_case.get_cached_scan(scan_id)
        
        if not cached:
            return _error(f"Scan '{scan_id}' not found", 404)
        
        return _success(cached)
    
    except Exception as e:
        logger.error(f"Screener result error: {e}", exc_info=True)
        return _error(str(e), 500)


@model_bp.route('/screener/scan/single', methods=['POST'])
@require_auth()
def screener_scan_single():
    """
    اسکن یک symbol خاص
    
    Body:
        {
            "coin_id": "bitcoin",
            "period": "24h"
        }
    
    خروجی:
        {
            "symbol": "BTC/USDT",
            "score": 0.72,
            "state": "SETUP",
            "reasons": [...],
            "rule_results": [...]
        }
    """
    try:
        data = request.json or {}
        
        coin_id = data.get('coin_id')
        period = data.get('period', '24h')
        
        if not coin_id:
            return _error('coin_id is required', 400)
        
        use_case = _get_scan_use_case()
        result = use_case.execute_single(
            coin_id=coin_id,
            period=period,
        )
        
        if result is None:
            return _error(f"Could not scan '{coin_id}'", 400)
        
        return _success(result)
    
    except Exception as e:
        logger.error(f"Screener scan single error: {e}", exc_info=True)
        return _error(str(e), 500)


@model_bp.route('/screener/history', methods=['GET'])
@require_auth()
def screener_history():
    """
    تاریخچه اسکن‌ها
    
    Query params:
        limit: حداکثر تعداد (پیش‌فرض: 20)
    """
    try:
        limit = request.args.get('limit', 20, type=int)
        
        use_case = _get_scan_use_case()
        history = use_case.get_scan_history(limit=limit)
        
        return _success(history, count=len(history))
    
    except Exception as e:
        logger.error(f"Screener history error: {e}", exc_info=True)
        return _error(str(e), 500)


@model_bp.route('/screener/history/stats', methods=['GET'])
@require_auth()
def screener_history_stats():
    """
    آمار اسکن‌ها
    
    خروجی:
        {
            "total_scans": 45,
            "avg_passed": 8.5,
            "avg_duration": 12.3,
            "last_scan": "2025-09-30T14:30:00",
            "recent_24h": 5
        }
    """
    try:
        db = get_primary()
        if not db or not db.is_connected():
            return _error('Database not connected', 503)
        
        # چک وجود جدول
        try:
            result = db.execute("""
                SELECT
                    COUNT(*) as total_scans,
                    AVG(passed_count) as avg_passed,
                    AVG(duration_seconds) as avg_duration,
                    MAX(created_at) as last_scan,
                    SUM(CASE WHEN created_at >= NOW() - INTERVAL '24 hours'
                             THEN 1 ELSE 0 END) as recent_24h
                FROM scan_history
            """)
            
            if result:
                row = result[0]
                return _success({
                    'total_scans': row.get('total_scans', 0),
                    'avg_passed': round(row.get('avg_passed', 0) or 0, 2),
                    'avg_duration': round(row.get('avg_duration', 0) or 0, 2),
                    'last_scan': (
                        row['last_scan'].isoformat()
                        if row.get('last_scan') else None
                    ),
                    'recent_24h': row.get('recent_24h', 0),
                })
        except Exception as e:
            logger.debug(f"scan_history table not found: {e}")
        
        return _success({
            'total_scans': 0,
            'avg_passed': 0,
            'avg_duration': 0,
            'last_scan': None,
            'recent_24h': 0,
        })
    
    except Exception as e:
        logger.error(f"Screener history stats error: {e}", exc_info=True)
        return _error(str(e), 500)


@model_bp.route('/screener/config', methods=['GET'])
@require_auth()
def screener_config():
    """
    دریافت config اسکن فعلی
    
    خروجی:
        {
            "batch": {
                "batch_size": 30,
                "max_concurrent_fetches": 10,
                "max_workers": 4,
                "timeframe": "4h",
                "candle_limit": 100
            },
            "symbols": {
                "mode": "top_volume",
                "count": 30,
                "exclude_stablecoins": true,
                "min_volatility_24h": 0.015
            },
            "scoring": {
                "min_pass_score": 0.55,
                "aggregation": "weighted_sum"
            }
        }
    """
    try:
        mm = _get_model_manager()
        config = mm.get_active_config()
        
        # فقط بخش‌های مربوط به screener
        return _success({
            'batch': config.get('batch', {}),
            'symbols': config.get('symbols', {}),
            'scoring': config.get('scoring', {}),
            'indicators': config.get('indicators', {}),
        })
    
    except Exception as e:
        logger.error(f"Screener config error: {e}", exc_info=True)
        return _error(str(e), 500)


@model_bp.route('/screener/config', methods=['PATCH'])
@require_auth('admin')
def update_screener_config():
    """
    آپدیت بخشی از config اسکن (runtime)
    
    Body نمونه:
        {
            "batch": {
                "batch_size": 45,
                "timeframe": "1h"
            },
            "symbols": {
                "count": 50
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
        
        # اعتبارسنجی سریع
        errors = []
        
        if 'batch' in data:
            batch = data['batch']
            if not isinstance(batch, dict):
                errors.append("batch must be a dict")
            else:
                if 'batch_size' in batch:
                    try:
                        bs = int(batch['batch_size'])
                        if not (1 <= bs <= 200):
                            errors.append("batch.batch_size must be 1-200")
                    except (ValueError, TypeError):
                        errors.append("batch.batch_size must be int")
                
                if 'timeframe' in batch:
                    valid_tf = ['1m', '5m', '15m', '1h', '4h', '1d']
                    if batch['timeframe'] not in valid_tf:
                        errors.append(
                            f"batch.timeframe must be one of {valid_tf}"
                        )
        
        if 'symbols' in data:
            symbols = data['symbols']
            if not isinstance(symbols, dict):
                errors.append("symbols must be a dict")
            else:
                if 'count' in symbols:
                    try:
                        c = int(symbols['count'])
                        if not (1 <= c <= 500):
                            errors.append("symbols.count must be 1-500")
                    except (ValueError, TypeError):
                        errors.append("symbols.count must be int")
        
        if 'scoring' in data:
            scoring = data['scoring']
            if not isinstance(scoring, dict):
                errors.append("scoring must be a dict")
            else:
                if 'min_pass_score' in scoring:
                    try:
                        v = float(scoring['min_pass_score'])
                        if not (0 <= v <= 1):
                            errors.append("scoring.min_pass_score must be 0-1")
                    except (ValueError, TypeError):
                        errors.append("scoring.min_pass_score must be numeric")
        
        if errors:
            return _error('Validation failed', 400, details=errors)
        
        # اعمال
        mm = _get_model_manager()
        result = mm.update_active_config(
            updates=data,
            persist=False,  # اسکن config فقط runtime
        )
        
        if result.get('success'):
            config = result.get('config', {})
            return _success({
                'batch': config.get('batch', {}),
                'symbols': config.get('symbols', {}),
                'scoring': config.get('scoring', {}),
            }, applied_keys=result.get('applied_keys', []))
        
        return _error(result.get('error', 'Update failed'), 400)
    
    except Exception as e:
        logger.error(f"Update screener config error: {e}", exc_info=True)
        return _error(str(e), 500)


@model_bp.route('/screener/config/validate', methods=['POST'])
@require_auth()
def validate_screener_config():
    """
    اعتبارسنجی config اسکن قبل از اعمال
    
    Body: مثل PATCH /screener/config
    """
    try:
        data = request.json or {}
        
        if not data:
            return _error('Empty body', 400)
        
        errors = []
        warnings = []
        normalized = {}
        
        # ============================================================
        # batch
        # ============================================================
        if 'batch' in data:
            batch = data['batch']
            if not isinstance(batch, dict):
                errors.append("batch must be a dict")
            else:
                normalized['batch'] = {}
                
                if 'batch_size' in batch:
                    try:
                        v = int(batch['batch_size'])
                        if not (1 <= v <= 200):
                            errors.append("batch.batch_size must be 1-200")
                        else:
                            normalized['batch']['batch_size'] = v
                    except (ValueError, TypeError):
                        errors.append("batch.batch_size must be int")
                
                if 'max_concurrent_fetches' in batch:
                    try:
                        v = int(batch['max_concurrent_fetches'])
                        if not (1 <= v <= 50):
                            errors.append("batch.max_concurrent_fetches must be 1-50")
                        else:
                            normalized['batch']['max_concurrent_fetches'] = v
                    except (ValueError, TypeError):
                        errors.append("batch.max_concurrent_fetches must be int")
                
                if 'max_workers' in batch:
                    try:
                        v = int(batch['max_workers'])
                        if not (1 <= v <= 20):
                            errors.append("batch.max_workers must be 1-20")
                        else:
                            normalized['batch']['max_workers'] = v
                    except (ValueError, TypeError):
                        errors.append("batch.max_workers must be int")
                
                if 'timeframe' in batch:
                    valid_tf = ['1m', '5m', '15m', '1h', '4h', '1d']
                    if batch['timeframe'] not in valid_tf:
                        errors.append(
                            f"batch.timeframe must be one of {valid_tf}"
                        )
                    else:
                        normalized['batch']['timeframe'] = batch['timeframe']
                
                if 'candle_limit' in batch:
                    try:
                        v = int(batch['candle_limit'])
                        if not (20 <= v <= 1000):
                            errors.append("batch.candle_limit must be 20-1000")
                        else:
                            normalized['batch']['candle_limit'] = v
                    except (ValueError, TypeError):
                        errors.append("batch.candle_limit must be int")
        
        # ============================================================
        # symbols
        # ============================================================
        if 'symbols' in data:
            symbols = data['symbols']
            if not isinstance(symbols, dict):
                errors.append("symbols must be a dict")
            else:
                normalized['symbols'] = {}
                
                if 'count' in symbols:
                    try:
                        v = int(symbols['count'])
                        if not (1 <= v <= 500):
                            errors.append("symbols.count must be 1-500")
                        else:
                            normalized['symbols']['count'] = v
                    except (ValueError, TypeError):
                        errors.append("symbols.count must be int")
                
                if 'exclude_stablecoins' in symbols:
                    if isinstance(symbols['exclude_stablecoins'], bool):
                        normalized['symbols']['exclude_stablecoins'] = symbols['exclude_stablecoins']
                    else:
                        errors.append("symbols.exclude_stablecoins must be boolean")
                
                if 'min_volatility_24h' in symbols:
                    try:
                        v = float(symbols['min_volatility_24h'])
                        if not (0 <= v <= 1):
                            errors.append("symbols.min_volatility_24h must be 0-1")
                        else:
                            normalized['symbols']['min_volatility_24h'] = v
                    except (ValueError, TypeError):
                        errors.append("symbols.min_volatility_24h must be numeric")
        
        # ============================================================
        # scoring
        # ============================================================
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
        
        return _success({
            'valid': len(errors) == 0,
            'errors': errors,
            'warnings': warnings,
            'normalized_config': normalized,
        })
    
    except Exception as e:
        logger.error(f"Validate screener config error: {e}", exc_info=True)
        return _error(str(e), 500)
        

# ============================================================
# گروه ۷: State Machine
# ============================================================


@model_bp.route('/state', methods=['GET'])
@model_bp.route('/state/', methods=['GET'])
@require_auth()
def state_home():
    """
    صفحه اصلی State API — لیست endpoint‌ها
    """
    return _success({
        'name': 'State Machine API',
        'version': '1.0.0',
        'states': ['IDLE', 'WATCHING', 'SETUP', 'ACTIVE', 'COOLING'],
        'endpoints': {
            'summary': '/api/model/state/summary',
            'transitions': '/api/model/state/transitions',
            'snapshots': '/api/model/state/snapshots',
            'symbol': '/api/model/state/<symbol>',
            'symbol_transitions': '/api/model/state/<symbol>/transitions',
            'symbol_reset': '/api/model/state/<symbol>/reset',
            'symbol_activate': '/api/model/state/<symbol>/activate',
            'symbol_cooling': '/api/model/state/<symbol>/cooling',
        },
    })


@model_bp.route('/state/summary', methods=['GET'])
@require_auth()
def state_summary():
    """
    خلاصه stateها
    
    Query params:
        symbols: لیست symbolها (جدا با کاما) — اختیاری
                 اگه ندیم، همه stateهای موجود در cache بررسی می‌شن
    
    خروجی:
        {
            "counts": {
                "IDLE": 15,
                "WATCHING": 8,
                "SETUP": 3,
                "ACTIVE": 2,
                "COOLING": 4
            },
            "total": 32,
            "by_state": {
                "IDLE": ["BTC/USDT", ...],
                "WATCHING": [...],
                ...
            }
        }
    """
    try:
        sm = _get_state_machine()
        if sm is None:
            return _error('StateMachine not available', 503)
        
        # از query params
        symbols_param = request.args.get('symbols', '')
        
        if symbols_param:
            symbols = [
                _normalize_symbol(s.strip())
                for s in symbols_param.split(',')
                if s.strip()
            ]
        else:
            # تلاش برای خواندن همه snapshotها از cache
            symbols = _get_all_cached_symbols(sm)
        
        # ساخت summary
        counts = {
            'IDLE': 0,
            'WATCHING': 0,
            'SETUP': 0,
            'ACTIVE': 0,
            'COOLING': 0,
        }
        by_state = {
            'IDLE': [],
            'WATCHING': [],
            'SETUP': [],
            'ACTIVE': [],
            'COOLING': [],
        }
        
        for symbol in symbols:
            try:
                snapshot = sm.get_state(symbol)
                state_name = snapshot.state.value
                
                if state_name in counts:
                    counts[state_name] += 1
                    by_state[state_name].append(symbol)
            except Exception as e:
                logger.debug(f"State read failed for {symbol}: {e}")
                continue
        
        return _success({
            'counts': counts,
            'total': sum(counts.values()),
            'by_state': by_state,
        })
    
    except Exception as e:
        logger.error(f"State summary error: {e}", exc_info=True)
        return _error(str(e), 500)


def _get_all_cached_symbols(sm) -> list:
    """
    خواندن همه symbolهای موجود در cache
    
    اگه cache در دسترس نباشه، لیست خالی برمی‌گردونه
    """
    try:
        if not sm.cache or not sm.cache.is_connected():
            return []
        
        keys = sm.cache.scan_keys('state:market:*', count=1000)
        
        symbols = []
        for key in keys:
            # state:market:BTC/USDT → BTC/USDT
            if key.startswith('state:market:'):
                symbols.append(key[len('state:market:'):])
        
        return symbols
    except Exception as e:
        logger.debug(f"Get cached symbols failed: {e}")
        return []


@model_bp.route('/state/transitions', methods=['GET'])
@require_auth()
def state_transitions():
    """
    تاریخچه کل transitionها
    
    Query params:
        limit: حداکثر تعداد (پیش‌فرض: 50)
        from_state: فیلتر state مبدأ
        to_state: فیلتر state مقصد
    """
    try:
        sm = _get_state_machine()
        if sm is None:
            return _error('StateMachine not available', 503)
        
        limit = request.args.get('limit', 50, type=int)
        from_state = request.args.get('from_state')
        to_state = request.args.get('to_state')
        
        # دریافت از DB
        transitions = sm.get_transitions(limit=limit * 2)  # بیشتر برای فیلتر
        
        # فیلتر
        if from_state:
            transitions = [
                t for t in transitions
                if str(t.get('from_state', '')).upper() == from_state.upper()
            ]
        
        if to_state:
            transitions = [
                t for t in transitions
                if str(t.get('to_state', '')).upper() == to_state.upper()
            ]
        
        transitions = transitions[:limit]
        
        return _success(transitions, count=len(transitions))
    
    except Exception as e:
        logger.error(f"State transitions error: {e}", exc_info=True)
        return _error(str(e), 500)


@model_bp.route('/state/snapshots', methods=['GET'])
@require_auth()
def state_snapshots():
    """
    لیست snapshotهای موجود در cache
    
    Query params:
        limit: حداکثر تعداد (پیش‌فرض: 100)
    
    خروجی:
        [
            {
                "symbol": "BTC/USDT",
                "state": "SETUP",
                "entered_at": "...",
                "signal_count": 3
            },
            ...
        ]
    """
    try:
        sm = _get_state_machine()
        if sm is None:
            return _error('StateMachine not available', 503)
        
        limit = request.args.get('limit', 100, type=int)
        
        symbols = _get_all_cached_symbols(sm)
        symbols = symbols[:limit]
        
        snapshots = []
        for symbol in symbols:
            try:
                snapshot = sm.get_state(symbol)
                snapshots.append(snapshot.to_dict())
            except Exception as e:
                logger.debug(f"Snapshot read failed for {symbol}: {e}")
                continue
        
        return _success(snapshots, count=len(snapshots))
    
    except Exception as e:
        logger.error(f"State snapshots error: {e}", exc_info=True)
        return _error(str(e), 500)


@model_bp.route('/state/<path:symbol>', methods=['GET'])
@require_auth()
def state_symbol(symbol):
    """
    وضعیت state یک symbol
    
    مثال:
        GET /api/model/state/BTCUSDT
        GET /api/model/state/BTC/USDT
        GET /api/model/state/btcusdt
    
    خروجی:
        {
            "symbol": "BTC/USDT",
            "state": "SETUP",
            "entered_at": "...",
            "last_change_at": "...",
            "signal_count": 5,
            "context": {...}
        }
    """
    try:
        normalized = _normalize_symbol(symbol)
        
        sm = _get_state_machine()
        if sm is None:
            return _error('StateMachine not available', 503)
        
        snapshot = sm.get_state(normalized)
        
        return _success(snapshot.to_dict())
    
    except Exception as e:
        logger.error(f"State symbol error: {e}", exc_info=True)
        return _error(str(e), 500)


@model_bp.route('/state/<path:symbol>/transitions', methods=['GET'])
@require_auth()
def state_symbol_transitions(symbol):
    """
    تاریخچه transitionهای یک symbol
    
    Query params:
        limit: حداکثر تعداد (پیش‌فرض: 50)
    """
    try:
        normalized = _normalize_symbol(symbol)
        limit = request.args.get('limit', 50, type=int)
        
        sm = _get_state_machine()
        if sm is None:
            return _error('StateMachine not available', 503)
        
        transitions = sm.get_transitions(
            symbol=normalized,
            limit=limit,
        )
        
        return _success(transitions, count=len(transitions))
    
    except Exception as e:
        logger.error(f"State symbol transitions error: {e}", exc_info=True)
        return _error(str(e), 500)


@model_bp.route('/state/<path:symbol>/reset', methods=['POST'])
@require_auth('admin')
def state_symbol_reset(symbol):
    """
    ریست state یک symbol به IDLE
    """
    try:
        normalized = _normalize_symbol(symbol)
        
        sm = _get_state_machine()
        if sm is None:
            return _error('StateMachine not available', 503)
        
        snapshot = sm.reset(normalized)
        
        return _success(snapshot.to_dict(), message=f"State reset for {normalized}")
    
    except Exception as e:
        logger.error(f"State symbol reset error: {e}", exc_info=True)
        return _error(str(e), 500)


@model_bp.route('/state/<path:symbol>/activate', methods=['POST'])
@require_auth('admin')
def state_symbol_activate(symbol):
    """
    علامت‌گذاری symbol به‌عنوان ACTIVE
    
    استفاده: از پورتفولیو وقتی پوزیشن باز می‌شه
    
    Body:
        {
            "entry_price": 80245.50,
            "side": "long",
            "size": 0.1,
            "leverage": 10
        }
    """
    try:
        normalized = _normalize_symbol(symbol)
        data = request.json or {}
        
        # ساخت context
        context = {
            'entry_price': data.get('entry_price'),
            'side': data.get('side', 'long'),
            'size': data.get('size', 0),
            'leverage': data.get('leverage', 1),
            'activated_at': datetime.now().isoformat(),
            'source': 'portfolio',
        }
        
        sm = _get_state_machine()
        if sm is None:
            return _error('StateMachine not available', 503)
        
        snapshot = sm.set_active(normalized, context=context)
        
        return _success(
            snapshot.to_dict(),
            message=f"State set to ACTIVE for {normalized}",
        )
    
    except Exception as e:
        logger.error(f"State symbol activate error: {e}", exc_info=True)
        return _error(str(e), 500)


@model_bp.route('/state/<path:symbol>/cooling', methods=['POST'])
@require_auth('admin')
def state_symbol_cooling(symbol):
    """
    علامت‌گذاری symbol به‌عنوان COOLING
    
    استفاده: بعد از exit از پورتفولیو
    
    Body:
        {
            "exit_price": 82000.0,
            "pnl": 175.5,
            "reason": "Take Profit"
        }
    """
    try:
        normalized = _normalize_symbol(symbol)
        data = request.json or {}
        
        context = {
            'exit_price': data.get('exit_price'),
            'pnl': data.get('pnl', 0),
            'reason': data.get('reason', 'Manual'),
            'cooling_started_at': datetime.now().isoformat(),
            'source': 'portfolio',
        }
        
        sm = _get_state_machine()
        if sm is None:
            return _error('StateMachine not available', 503)
        
        snapshot = sm.set_cooling(normalized, context=context)
        
        return _success(
            snapshot.to_dict(),
            message=f"State set to COOLING for {normalized}",
        )
    
    except Exception as e:
        logger.error(f"State symbol cooling error: {e}", exc_info=True)
        return _error(str(e), 500)
