# models/trainer/auto_trainer.py
# ============================================================
# AutoTrainer → WeightCalibrator - نسخه ۶.۰
# OHLCV واقعی + لاگ کامل + خطایابی دقیق
# ============================================================

import itertools
import logging
import random
import threading
import time
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from infrastructure.database import (
    get_primary,
    get_analytics,
    get_cache,
)
from infrastructure.repositories import repos
from config import get_historical_points, get_auto_trainer_config
from core.rule_engine import (
    RuleEngine,
    StateMachine,
    create_engine_from_config,
    load_default_config,
)

logger = logging.getLogger(__name__)


# ============================================================
# Constants
# ============================================================

# period → interval (برای OHLCV)
PERIOD_TO_INTERVAL: Dict[str, str] = {
    "24h": "1h",
    "1w":  "4h",
    "1m":  "4h",
    "3m":  "1d",
    "6m":  "1d",
}

# profile → range (بازه داده تاریخی برای کالیبراسیون)
PROFILE_TO_RANGE: Dict[str, str] = {
    "fast":     "3mo",
    "balanced": "6mo",
    "accurate": "1y",
    "hill_climb": "6mo",
    "random":   "6mo",
}

# حداقل کندل لازم
MIN_CANDLES = 100

# حداکثر coin برای کالیبراسیون
MAX_CALIBRATION_COINS = 5


# ============================================================
# Calibration Profiles
# ============================================================

CALIBRATION_PROFILES: Dict[str, Dict[str, Any]] = {
    "fast": {
        "name": "سریع",
        "description": "Grid Search کوچک",
        "icon": "🚀",
        "color": "#f59e0b",
        "strategy": "grid",
        "max_iterations": 20,
        "weight_step": 0.10,
        "estimated_time_seconds": 30,
        "range": "3mo",
    },
    "balanced": {
        "name": "متعادل",
        "description": "Grid Search متوسط (پیش‌فرض)",
        "icon": "⚖️",
        "color": "#10b981",
        "strategy": "grid",
        "max_iterations": 100,
        "weight_step": 0.05,
        "estimated_time_seconds": 120,
        "range": "6mo",
    },
    "accurate": {
        "name": "دقیق",
        "description": "Grid Search دقیق",
        "icon": "🎯",
        "color": "#8b5cf6",
        "strategy": "grid",
        "max_iterations": 500,
        "weight_step": 0.025,
        "estimated_time_seconds": 600,
        "range": "1y",
    },
    "hill_climb": {
        "name": "تپه‌نوردی",
        "description": "بهینه‌سازی تکاملی",
        "icon": "🏔️",
        "color": "#22d3ee",
        "strategy": "hill_climb",
        "max_iterations": 80,
        "weight_step": 0.05,
        "estimated_time_seconds": 240,
        "range": "6mo",
    },
    "random": {
        "name": "تصادفی",
        "description": "جستجوی تصادفی",
        "icon": "🎲",
        "color": "#ec4899",
        "strategy": "random",
        "max_iterations": 150,
        "weight_step": 0.05,
        "estimated_time_seconds": 300,
        "range": "6mo",
    },
}


# ============================================================
# AutoTrainer
# ============================================================

class AutoTrainer:
    """
    AutoTrainer → WeightCalibrator
    
    کالیبراسیون وزن‌های RuleEngine از طریق Backtest OHLCV واقعی
    """
    
    def __init__(self, api: Any, model_manager: Any) -> None:
        self.api: Any = api
        self.model_manager: Any = model_manager
        self.db: Any = get_primary()
        self.analytics_db: Any = get_analytics()
        self.cache: Any = get_cache()
        self.config_repo = repos.rule_config
        
        # تنظیمات
        self.auto_trainer_config: Dict[str, Any] = get_auto_trainer_config()
        self.historical_points_config: Dict[str, int] = {
            "fear_greed": get_historical_points("fear_greed"),
            "btc_dominance": get_historical_points("btc_dominance"),
            "global_market": get_historical_points("global_market"),
            "chart": get_historical_points("chart"),
        }
        
        # State
        self.is_running: bool = False
        self.is_training: bool = False
        self.is_calibrating: bool = False
        self.stop_event: threading.Event = threading.Event()
        self.thread: Optional[threading.Thread] = None
        self._lock: threading.Lock = threading.Lock()
        
        # لاگ‌ها
        self.logs: List[str] = []
        
        # ارزها
        self.coins: List[str] = self.auto_trainer_config.get(
            "coins", ["bitcoin", "ethereum", "solana"]
        )[:MAX_CALIBRATION_COINS]
        
        # آمار
        self.stats: Dict[str, Any] = {
            "is_running": False,
            "is_training": False,
            "is_calibrating": False,
            "total_trainings": 0,
            "successful_trainings": 0,
            "failed_trainings": 0,
            "total_calibrations": 0,
            "successful_calibrations": 0,
            "failed_calibrations": 0,
            "last_training": None,
            "last_calibration": None,
            "last_error": None,
            "last_score": None,
            "last_improvement": None,
            "data_points_used": 0,
            "training_period": self.auto_trainer_config.get("period", "1m"),
            "api_status": "unknown",
            "credits_remaining": 0,
            "api_calls": 0,
            "api_errors": 0,
            "mode": "RULE_ENGINE",
            "coins_used": [],
            "total_candles_fetched": 0,
        }
        
        self._register_with_scheduler()
        
        # ============================================================
        # لاگ راه‌اندازی
        # ============================================================
        
        self._add_log("=" * 60)
        self._add_log("🚀 AutoTrainer v6.0 (WeightCalibrator) راه‌اندازی شد")
        self._add_log(f"🪙 ارزهای فعال: {self.coins}")
        self._add_log(f"📅 بازه پیش‌فرض: {self.stats['training_period']}")
        
        if model_manager and model_manager.engine is not None:
            rule_count = len(model_manager.engine.rules) if model_manager.engine else 0
            self._add_log(
                f"✅ RuleEngine موجود "
                f"(نسخه: {model_manager.current_version or 'default'}, "
                f"{rule_count} rule)"
            )
        else:
            self._add_log("⚠️ RuleEngine بارگذاری نشده")
        
        self._add_log("=" * 60)
        
        logger.info(
            f"✅ AutoTrainer v6.0 initialized "
            f"(coins={self.coins})"
        )
    
    # ============================================================
    # Scheduler Registration
    # ============================================================
    
    def _register_with_scheduler(self) -> None:
        try:
            from core.metrics import metrics_scheduler
            logger.debug("AutoTrainer registered with Metrics Scheduler")
        except ImportError:
            pass
        except Exception as e:
            logger.debug(f"Could not register with scheduler: {e}")
    
    # ============================================================
    # Log Management
    # ============================================================
    
    def _add_log(self, message: str) -> None:
        """افزودن به لاگ‌ها"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] {message}"
        self.logs.append(log_entry)
        
        if len(self.logs) > 300:
            self.logs = self.logs[-300:]
        
        # لاگ به logging هم بره
        if "❌" in message or "ERROR" in message.upper():
            logger.error(message)
        elif "⚠️" in message:
            logger.warning(message)
        else:
            logger.info(message)
    
    def clear_logs(self) -> None:
        self.logs = []
        self._add_log("🗑️ لاگ‌ها پاک شدند")
    
    def get_logs(self) -> List[str]:
        return self.logs
    
    # ============================================================
    # API Status
    # ============================================================
    
    def check_api_status(self) -> Dict[str, Any]:
        """بررسی وضعیت API"""
        try:
            status = self.api.get_status()
            api_ok = status and status.get("status") == "ok"
            
            credits = self.api.get_credits()
            remaining = 0
            
            if credits and "remainingCredits" in credits:
                remaining = credits.get("remainingCredits", 0)
                self.stats["credits_remaining"] = remaining
            
            self.stats["api_status"] = "ok" if api_ok else "error"
            
            return {
                "api_status": "ok" if api_ok else "error",
                "credits_remaining": remaining,
                "can_proceed": api_ok and remaining > 50,
                "message": "API سالم است" if api_ok else "API در دسترس نیست",
            }
        except Exception as e:
            self.stats["api_status"] = "error"
            self.stats["api_errors"] += 1
            return {
                "api_status": "error",
                "credits_remaining": 0,
                "can_proceed": False,
                "message": f"خطا: {str(e)[:80]}",
            }
    
    # ============================================================
    # Main: calibrate
    # ============================================================
    
    def calibrate(
        self,
        period: str = "1m",
        coins: Optional[List[str]] = None,
        profile_name: Optional[str] = None,
        strategy: Optional[str] = None,
        config_override: Optional[Dict[str, Any]] = None,
        save: bool = True,
    ) -> Dict[str, Any]:
        """
        کالیبراسیون وزن‌های RuleEngine
        
        لاگ کامل + خطایابی دقیق
        """
        # ============================================================
        # چک وضعیت
        # ============================================================
        
        if self.is_calibrating:
            self._add_log("⚠️ کالیبراسیون قبلاً در حال انجامه")
            return {
                "success": False,
                "message": "کالیبراسیون در حال انجام است",
            }
        
        self.is_calibrating = True
        self.is_training = True
        self.stats["is_calibrating"] = True
        self.stats["is_training"] = True
        self.stats["total_trainings"] += 1
        self.stats["total_calibrations"] += 1
        self.stats["training_period"] = period
        
        start_time = time.time()
        
        self._add_log("")
        self._add_log("=" * 60)
        self._add_log(f"🎯 شروع کالیبراسیون (profile={profile_name or 'balanced'})")
        self._add_log(f"   period={period}, strategy={strategy or 'auto'}")
        
        try:
            # ============================================================
            # ۱. چک API
            # ============================================================
            
            self._add_log("🔍 مرحله ۱: بررسی API...")
            status = self.check_api_status()
            
            if not status["can_proceed"]:
                msg = status["message"]
                self._add_log(f"❌ مرحله ۱ ناموفق: {msg}")
                self._mark_failed(msg)
                return {
                    "success": False,
                    "message": msg,
                    "api_status": status["api_status"],
                }
            
            self._add_log(
                f"✅ مرحله ۱ موفق: API سالم، "
                f"credits={status['credits_remaining']}"
            )
            
            # ============================================================
            # ۲. Profile
            # ============================================================
            
            self._add_log("🔍 مرحله ۲: بارگذاری profile...")
            profile = self._resolve_profile(profile_name, strategy)
            
            if profile is None:
                self._add_log(f"❌ مرحله ۲ ناموفق: profile یافت نشد")
                self._mark_failed("Profile not found")
                return {
                    "success": False,
                    "error": f"Profile '{profile_name}' not found",
                }
            
            profile_range = profile.get("range", "6mo")
            self._add_log(
                f"✅ مرحله ۲ موفق: profile={profile_name or 'balanced'}, "
                f"strategy={profile['strategy']}, range={profile_range}"
            )
            
            # ============================================================
            # ۳. Config پایه
            # ============================================================
            
            self._add_log("🔍 مرحله ۳: دریافت config فعلی...")
            base_config = config_override or self._get_current_config()
            rule_count = len(base_config.get("rules", {}))
            self._add_log(f"✅ مرحله ۳ موفق: {rule_count} rule در config")
            
            # ============================================================
            # ۴. Fetch داده تاریخی OHLCV
            # ============================================================
            
            coins_list = coins or self.coins
            interval = PERIOD_TO_INTERVAL.get(period, "4h")
            
            self._add_log(
                f"🔍 مرحله ۴: دریافت داده تاریخی "
                f"({len(coins_list)} coin, interval={interval}, range={profile_range})"
            )
            
            data_map = self._fetch_historical_data(
                coins=coins_list,
                interval=interval,
                data_range=profile_range,
            )
            
            if not data_map:
                msg = "داده تاریخی دریافت نشد"
                self._add_log(f"❌ مرحله ۴ ناموفق: {msg}")
                self._mark_failed(msg)
                return {
                    "success": False,
                    "error": msg,
                }
            
            total_candles = sum(len(df) for df in data_map.values())
            self.stats["total_candles_fetched"] = total_candles
            self.stats["coins_used"] = list(data_map.keys())
            
            self._add_log(
                f"✅ مرحله ۴ موفق: {len(data_map)} symbol, "
                f"{total_candles} کندل"
            )
            for symbol, df in data_map.items():
                self._add_log(f"   • {symbol}: {len(df)} کندل")
            
            # ============================================================
            # ۵. ارزیابی baseline
            # ============================================================
            
            self._add_log("🔍 مرحله ۵: ارزیابی baseline...")
            baseline_score = self._evaluate_config(base_config, data_map)
            self._add_log(f"✅ مرحله ۵ موفق: baseline score={baseline_score:.4f}")
            
            # ============================================================
            # ۶. اجرای استراتژی
            # ============================================================
            
            self._add_log(
                f"🔍 مرحله ۶: اجرای کالیبراسیون "
                f"(strategy={profile['strategy']})..."
            )
            
            if profile["strategy"] == "grid":
                result = self._calibrate_grid(base_config, data_map, profile)
            elif profile["strategy"] == "random":
                result = self._calibrate_random(base_config, data_map, profile)
            elif profile["strategy"] == "hill_climb":
                result = self._calibrate_hill_climb(base_config, data_map, profile)
            else:
                msg = f"Unknown strategy: {profile['strategy']}"
                self._add_log(f"❌ مرحله ۶ ناموفق: {msg}")
                self._mark_failed(msg)
                return {"success": False, "error": msg}
            
            if not result.get("success"):
                msg = result.get("error", "Unknown calibration error")
                self._add_log(f"❌ مرحله ۶ ناموفق: {msg}")
                self._mark_failed(msg)
                return result
            
            evaluations = result.get("evaluations", 0)
            self._add_log(
                f"✅ مرحله ۶ موفق: {evaluations} ارزیابی انجام شد، "
                f"best score={result['best_score']:.4f}"
            )
            
            # ============================================================
            # ۷. محاسبه improvement
            # ============================================================
            
            improvement = result["best_score"] - baseline_score
            
            result["baseline_score"] = round(baseline_score, 4)
            result["improvement"] = round(improvement, 4)
            result["improvement_percent"] = (
                round((improvement / baseline_score * 100), 2)
                if baseline_score > 0 else 0
            )
            
            self._add_log(
                f"📊 بهبود: {improvement:+.4f} "
                f"({result['improvement_percent']:+.2f}%)"
            )
            
            # ============================================================
            # ۸. ذخیره در DB
            # ============================================================
            
            if save and result.get("best_config"):
                self._add_log("🔍 مرحله ۷: ذخیره در DB...")
                save_result = self._save_best_config(
                    config=result["best_config"],
                    accuracy=result["best_score"],
                    description=f"Calibrated with {profile['strategy']}",
                )
                result["save_result"] = save_result
                result["version"] = save_result.get("version")
                
                if save_result.get("success"):
                    self._add_log(
                        f"✅ مرحله ۷ موفق: نسخه {save_result.get('version')}"
                    )
                else:
                    self._add_log(
                        f"⚠️ مرحله ۷: ذخیره ناموفق — "
                        f"{save_result.get('error', 'unknown')}"
                    )
            else:
                result["save_result"] = {"success": False, "reason": "save=False"}
                result["version"] = None
                self._add_log("⏭️ مرحله ۷ رد شد (save=False)")
            
            # ============================================================
            # ۹. آمار نهایی
            # ============================================================
            
            duration = time.time() - start_time
            result["duration_seconds"] = round(duration, 2)
            
            self._mark_success(
                score=result["best_score"],
                improvement=improvement,
                data_points=result.get("evaluations", 0),
            )
            
            self._add_log("")
            self._add_log("=" * 60)
            self._add_log("🎉 کالیبراسیون با موفقیت انجام شد!")
            self._add_log(f"   profile: {profile_name or 'balanced'}")
            self._add_log(f"   best_score: {result['best_score']:.4f}")
            self._add_log(f"   baseline: {baseline_score:.4f}")
            self._add_log(f"   improvement: {improvement:+.4f}")
            self._add_log(f"   version: {result.get('version', 'N/A')}")
            self._add_log(f"   duration: {duration:.1f}s")
            self._add_log("=" * 60)
            self._add_log("")
            
            return result
        
        except Exception as e:
            duration = time.time() - start_time
            self._add_log(f"❌ کالیبراسیون با خطا متوقف شد ({duration:.1f}s)")
            self._add_log(f"   error: {type(e).__name__}: {str(e)}")
            
            logger.error(f"Calibrate error: {e}", exc_info=True)
            self._mark_failed(str(e))
            
            return {
                "success": False,
                "error": str(e),
                "duration_seconds": round(duration, 2),
            }
        
        finally:
            self.is_calibrating = False
            self.is_training = False
            self.stats["is_calibrating"] = False
            self.stats["is_training"] = False
    
    # ============================================================
    # Calibration Strategies
    # ============================================================
    
    def _calibrate_grid(
        self,
        base_config: Dict[str, Any],
        data_map: Dict[str, pd.DataFrame],
        profile: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Grid Search روی وزن‌ها"""
        rules = list(base_config.get("rules", {}).keys())
        step = profile.get("weight_step", 0.05)
        max_iter = profile.get("max_iterations", 100)
        
        weight_values = [round(i * step, 4) for i in range(int(1 / step) + 1)]
        
        self._add_log(
            f"   🔍 Grid: {len(rules)} rules, step={step}, "
            f"max_iter={max_iter}, total_combos={len(weight_values) ** len(rules)}"
        )
        
        best_score = -1.0
        best_weights: Dict[str, float] = {}
        best_config: Optional[Dict[str, Any]] = None
        
        iterations = 0
        evaluations = 0
        total_combinations = len(weight_values) ** len(rules)
        
        if total_combinations <= max_iter:
            for weights in itertools.product(weight_values, repeat=len(rules)):
                if iterations >= max_iter:
                    break
                
                config = self._apply_weights(
                    base_config, dict(zip(rules, weights))
                )
                score = self._evaluate_config(config, data_map)
                evaluations += 1
                iterations += 1
                
                if score > best_score:
                    best_score = score
                    best_weights = dict(zip(rules, weights))
                    best_config = config
        else:
            self._add_log(
                f"   ⚠️ ترکیبات زیاد، نمونه‌گیری تصادفی از {max_iter}"
            )
            
            for _ in range(max_iter):
                weights = [random.choice(weight_values) for _ in rules]
                config = self._apply_weights(
                    base_config, dict(zip(rules, weights))
                )
                score = self._evaluate_config(config, data_map)
                evaluations += 1
                iterations += 1
                
                if score > best_score:
                    best_score = score
                    best_weights = dict(zip(rules, weights))
                    best_config = config
        
        return {
            "success": True,
            "strategy": "grid",
            "best_score": round(best_score, 4),
            "best_weights": {k: round(v, 4) for k, v in best_weights.items()},
            "best_config": best_config or base_config,
            "iterations": iterations,
            "evaluations": evaluations,
        }
    
    def _calibrate_random(
        self,
        base_config: Dict[str, Any],
        data_map: Dict[str, pd.DataFrame],
        profile: Dict[str, Any],
    ) -> Dict[str, Any]:
        """جستجوی تصادفی"""
        rules = list(base_config.get("rules", {}).keys())
        max_iter = profile.get("max_iterations", 100)
        
        self._add_log(f"   🎲 Random: {max_iter} iterations")
        
        best_score = -1.0
        best_weights: Dict[str, float] = {}
        best_config: Optional[Dict[str, Any]] = None
        
        for i in range(max_iter):
            weights_raw = [random.random() for _ in rules]
            total = sum(weights_raw) or 1.0
            weights = [w / total for w in weights_raw]
            
            config = self._apply_weights(base_config, dict(zip(rules, weights)))
            score = self._evaluate_config(config, data_map)
            
            if score > best_score:
                best_score = score
                best_weights = dict(zip(rules, weights))
                best_config = config
        
        return {
            "success": True,
            "strategy": "random",
            "best_score": round(best_score, 4),
            "best_weights": {k: round(v, 4) for k, v in best_weights.items()},
            "best_config": best_config or base_config,
            "iterations": max_iter,
            "evaluations": max_iter,
        }
    
    def _calibrate_hill_climb(
        self,
        base_config: Dict[str, Any],
        data_map: Dict[str, pd.DataFrame],
        profile: Dict[str, Any],
    ) -> Dict[str, Any]:
        """تپه‌نوردی"""
        rules = list(base_config.get("rules", {}).keys())
        max_iter = profile.get("max_iterations", 80)
        step = profile.get("weight_step", 0.05)
        
        self._add_log(f"   🏔️ Hill Climb: {max_iter} iterations, step={step}")
        
        current_weights = {
            r: float(base_config.get("rules", {}).get(r, {}).get("weight", 0.25))
            for r in rules
        }
        
        current_config = self._apply_weights(base_config, current_weights)
        current_score = self._evaluate_config(current_config, data_map)
        
        best_weights = current_weights.copy()
        best_score = current_score
        best_config = current_config
        
        evaluations = 1
        i = 0
        
        for i in range(max_iter):
            improved = False
            
            for rule_name in rules:
                for direction in [+step, -step]:
                    candidate = current_weights.copy()
                    new_val = candidate[rule_name] + direction
                    
                    if new_val < 0.0 or new_val > 1.0:
                        continue
                    
                    candidate[rule_name] = new_val
                    
                    total = sum(candidate.values())
                    if total > 0:
                        candidate = {k: v / total for k, v in candidate.items()}
                    
                    config = self._apply_weights(base_config, candidate)
                    score = self._evaluate_config(config, data_map)
                    evaluations += 1
                    
                    if score > current_score:
                        current_weights = candidate
                        current_score = score
                        current_config = config
                        improved = True
                        
                        if score > best_score:
                            best_score = score
                            best_weights = candidate.copy()
                            best_config = config
                        break
                
                if improved:
                    break
            
            if not improved:
                step = step * 0.7
                if step < 0.01:
                    break
        
        return {
            "success": True,
            "strategy": "hill_climb",
            "best_score": round(best_score, 4),
            "best_weights": {k: round(v, 4) for k, v in best_weights.items()},
            "best_config": best_config or base_config,
            "iterations": i + 1,
            "evaluations": evaluations,
        }
    
    # ============================================================
    # Config Evaluation (Backtest)
    # ============================================================
    
    def _evaluate_config(
        self,
        config: Dict[str, Any],
        data_map: Dict[str, pd.DataFrame],
    ) -> float:
        """
        ارزیابی config روی داده تاریخی
        
        معیار: Sharpe-like ratio
        
        منطق:
            ۱. برای هر symbol، RuleEngine رو روی چند نقطه اجرا کن
            ۲. اگه pass شد، بازده بعدی رو حساب کن
            ۳. Sharpe = mean(returns) / std(returns)
            ۴. Normalize به ۰-۱
        """
        try:
            temp_sm = StateMachine(
                cache=None,
                db=None,
                config={"enable_db_history": False},
            )
            
            engine = create_engine_from_config(
                rules_config=config.get("rules", {}),
                scoring_config=config.get("scoring", {}),
                state_machine=temp_sm,
            )
            
            signal_returns: List[float] = []
            
            for symbol, df in data_map.items():
                if df is None or len(df) < 50:
                    continue
                
                # نمونه‌گیری: هر N کندل یه نقطه
                step = max(1, len(df) // 30)
                
                for i in range(30, len(df) - 1, step):
                    df_slice = df.iloc[:i + 1]
                    
                    try:
                        prediction = engine.evaluate(
                            symbol=symbol,
                            coin_id=symbol.lower().split("/")[0],
                            df=df_slice,
                            update_state=False,
                        )
                        
                        if prediction is None:
                            continue
                        
                        if prediction.score >= engine.min_pass_score:
                            close_now = df["Close"].iloc[i]
                            close_next = df["Close"].iloc[i + 1]
                            
                            if close_now > 0:
                                ret = (close_next - close_now) / close_now
                                signal_returns.append(ret)
                    
                    except Exception:
                        continue
            
            if len(signal_returns) < 5:
                return 0.0
            
            returns_arr = np.array(signal_returns)
            mean_ret = float(np.mean(returns_arr))
            std_ret = float(np.std(returns_arr))
            
            if std_ret < 1e-6:
                return 0.0
            
            sharpe = mean_ret / std_ret
            normalized = (sharpe + 3.0) / 6.0
            return float(np.clip(normalized, 0.0, 1.0))
        
        except Exception as e:
            logger.debug(f"Evaluate config error: {e}")
            return 0.0
    
    # ============================================================
    # Data Fetching (OHLCV واقعی)
    # ============================================================
    
    def _fetch_historical_data(
        self,
        coins: List[str],
        interval: str,
        data_range: str,
    ) -> Dict[str, pd.DataFrame]:
        """
        دریافت داده OHLCV واقعی از CoinStats /ohlcv/candles
        
        Returns:
            {symbol: DataFrame}
        """
        data_map: Dict[str, pd.DataFrame] = {}
        
        for coin in coins:
            # تبدیل coin_id → pair
            pair = self.api.coin_id_to_pair(coin) if hasattr(
                self.api, "coin_id_to_pair"
            ) else None
            
            if not pair:
                self._add_log(f"   ⚠️ نمی‌توان '{coin}' را به pair تبدیل کرد")
                continue
            
            self._add_log(f"   📥 دریافت {pair} ({interval}, {data_range})...")
            
            try:
                result = self.api.get_ohlcv_candles(
                    exchange="Binance",
                    pair=pair,
                    interval=interval,
                    range=data_range,
                    use_cache=True,
                )
                
                self.stats["api_calls"] += 1
                
                if not result or "candles" not in result:
                    err = result.get("error") if result else "no response"
                    self._add_log(f"   ❌ {pair}: {err}")
                    self.stats["api_errors"] += 1
                    continue
                
                candles = result["candles"]
                
                # هشدار cap
                if result.get("warning"):
                    self._add_log(f"   ⚠️ {result['warning']}")
                
                df = self._candles_to_dataframe(candles)
                
                if df is None or len(df) < MIN_CANDLES:
                    df_len = len(df) if df is not None else 0
                    self._add_log(
                        f"   ⚠️ {pair}: داده کافی نیست "
                        f"({df_len} < {MIN_CANDLES})"
                    )
                    continue
                
                data_map[pair] = df
                self._add_log(f"   ✅ {pair}: {len(df)} کندل")
            
            except Exception as e:
                self.stats["api_errors"] += 1
                self._add_log(f"   ❌ {pair}: {type(e).__name__}: {str(e)[:80]}")
                logger.error(f"Fetch error for {coin}: {e}", exc_info=True)
        
        return data_map
    
    @staticmethod
    def _candles_to_dataframe(candles: List) -> Optional[pd.DataFrame]:
        """
        تبدیل candles به DataFrame OHLCV
        
        ساختار candle: [timestampMs, open, high, low, close, volume]
        """
        if not candles:
            return None
        
        rows = []
        for c in candles:
            if not isinstance(c, (list, tuple)) or len(c) < 6:
                continue
            
            try:
                ts = pd.to_datetime(c[0], unit="ms", errors="coerce")
                if pd.isna(ts):
                    continue
                
                volume = float(c[5]) if c[5] is not None else 0.0
                
                rows.append({
                    "timestamp": ts,
                    "Open": float(c[1]),
                    "High": float(c[2]),
                    "Low": float(c[3]),
                    "Close": float(c[4]),
                    "Volume": volume,
                })
            except (ValueError, TypeError, IndexError):
                continue
        
        if not rows:
            return None
        
        df = pd.DataFrame(rows).set_index("timestamp").sort_index().dropna()
        
        if len(df) < MIN_CANDLES:
            return None
        
        return df
    
    # ============================================================
    # Config Helpers
    # ============================================================
    
    def _resolve_profile(
        self,
        profile_name: Optional[str],
        strategy: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """دریافت profile"""
        name = profile_name or "balanced"
        
        if name in CALIBRATION_PROFILES:
            profile = CALIBRATION_PROFILES[name].copy()
        else:
            # fallback
            profile = CALIBRATION_PROFILES["balanced"].copy()
            profile["name"] = name
        
        if strategy:
            profile["strategy"] = strategy
        
        return profile
    
    def _get_current_config(self) -> Dict[str, Any]:
        """config فعلی"""
        try:
            if self.model_manager and hasattr(
                self.model_manager, "get_active_config"
            ):
                return self.model_manager.get_active_config()
        except Exception:
            pass
        
        return load_default_config()
    
    @staticmethod
    def _apply_weights(
        base_config: Dict[str, Any],
        weights: Dict[str, float],
    ) -> Dict[str, Any]:
        """اعمال وزن‌های جدید روی config"""
        import copy
        config = copy.deepcopy(base_config)
        
        for rule_name, weight in weights.items():
            if rule_name in config.get("rules", {}):
                config["rules"][rule_name]["weight"] = float(weight)
        
        return config
    
    def _save_best_config(
        self,
        config: Dict[str, Any],
        accuracy: float,
        description: str,
    ) -> Dict[str, Any]:
        """ذخیره best config"""
        try:
            if self.model_manager and hasattr(
                self.model_manager, "save_config_version"
            ):
                return self.model_manager.save_config_version(
                    config=config,
                    accuracy=accuracy,
                    description=description,
                    set_active=True,
                    backup=True,
                )
        except Exception as e:
            logger.error(f"Save best config failed: {e}")
        
        return {"success": False, "error": "ModelManager not available"}
    
    # ============================================================
    # Stats Helpers
    # ============================================================
    
    def _mark_success(
        self,
        score: float,
        improvement: Optional[float],
        data_points: int,
    ) -> None:
        """ثبت موفقیت"""
        self.stats["successful_trainings"] += 1
        self.stats["successful_calibrations"] += 1
        now_iso = datetime.now().isoformat()
        self.stats["last_training"] = now_iso
        self.stats["last_calibration"] = now_iso
        self.stats["last_error"] = None
        self.stats["last_score"] = float(score)
        self.stats["last_improvement"] = (
            float(improvement) if improvement is not None else None
        )
        self.stats["data_points_used"] = data_points
    
    def _mark_failed(self, error: str) -> None:
        """ثبت شکست"""
        self.stats["failed_trainings"] += 1
        self.stats["failed_calibrations"] += 1
        self.stats["last_error"] = str(error)[:200]
    
    # ============================================================
    # Auto Calibration (Scheduler)
    # ============================================================
    
    def start_auto_train(
        self,
        interval_hours: Optional[int] = None,
        period: Optional[str] = None,
        profile_name: Optional[str] = None,
        incremental: bool = False,
        coins: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """شروع کالیبراسیون خودکار"""
        if self.is_running:
            return {"success": False, "message": "سیستم در حال اجراست"}
        
        if interval_hours is None:
            interval_hours = self.auto_trainer_config.get("interval_hours", 6)
        if period is None:
            period = self.auto_trainer_config.get("period", "1m")
        if profile_name is None:
            profile_name = "balanced"
        
        self.is_running = True
        self.stats["is_running"] = True
        self.stats["training_period"] = period
        self.stop_event.clear()
        
        def run() -> None:
            self._add_log(
                f"🔄 کالیبراسیون خودکار شروع شد "
                f"(هر {interval_hours}h, profile={profile_name})"
            )
            
            while not self.stop_event.is_set():
                try:
                    result = self.calibrate(
                        period=period,
                        coins=coins,
                        profile_name=profile_name,
                        save=True,
                    )
                    
                    if result.get("success"):
                        self._add_log(
                            f"✅ چرخه موفق: score={result.get('best_score', 0):.4f}"
                        )
                    else:
                        self._add_log(
                            f"❌ چرخه ناموفق: {result.get('error', 'unknown')}"
                        )
                
                except Exception as e:
                    self._add_log(f"❌ خطای چرخه: {e}")
                    logger.error(f"Auto calibrate cycle error: {e}", exc_info=True)
                
                self.stop_event.wait(interval_hours * 3600)
            
            self.is_running = False
            self.stats["is_running"] = False
            self._add_log("⏹️ کالیبراسیون خودکار متوقف شد")
        
        self.thread = threading.Thread(target=run, daemon=True)
        self.thread.start()
        
        self._add_log(
            f"✅ کالیبراسیون خودکار فعال شد "
            f"(هر {interval_hours} ساعت, profile={profile_name})"
        )
        
        return {
            "success": True,
            "message": f"کالیبراسیون خودکار شروع شد (هر {interval_hours} ساعت)",
            "interval_hours": interval_hours,
            "period": period,
            "profile_name": profile_name,
        }
    
    def stop_auto_train(self) -> Dict[str, Any]:
        """متوقف کردن کالیبراسیون خودکار"""
        if not self.is_running:
            return {"success": False, "message": "سیستم در حال اجرا نیست"}
        
        self.stop_event.set()
        
        if self.thread:
            self.thread.join(timeout=5)
        
        self.is_running = False
        self.stats["is_running"] = False
        self._add_log("⏹️ کالیبراسیون توسط کاربر متوقف شد")
        
        return {"success": True, "message": "کالیبراسیون متوقف شد"}
    
    # ============================================================
    # Legacy Compatibility
    # ============================================================
    
    def train_model(self, *args, **kwargs) -> Dict[str, Any]:
        """سازگاری: redirect به calibrate"""
        logger.warning("⚠️ train_model called → redirecting to calibrate()")
        
        period = kwargs.get("period", "1m")
        coins = kwargs.get("coins")
        profile_name = kwargs.get("profile_name")
        strategy = kwargs.get("strategy")
        save = kwargs.get("save", True)
        
        return self.calibrate(
            period=period,
            coins=coins,
            profile_name=profile_name,
            strategy=strategy,
            save=save,
        )
    
    def train_batch(
        self,
        profiles: List[str],
        period: str = "1m",
        coins: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """A/B Testing کالیبراسیون"""
        self._add_log(f"🧪 A/B Calibration: {profiles}")
        
        results: Dict[str, Any] = {}
        best_score = -1.0
        best_profile: Optional[str] = None
        
        for profile_name in profiles:
            result = self.calibrate(
                period=period,
                coins=coins,
                profile_name=profile_name,
                save=False,
            )
            results[profile_name] = result
            
            if result.get("success"):
                score = result.get("best_score", 0)
                if score > best_score:
                    best_score = score
                    best_profile = profile_name
        
        if best_profile:
            final = self.calibrate(
                period=period,
                coins=coins,
                profile_name=best_profile,
                save=True,
            )
        else:
            final = {"success": False}
        
        return {
            "success": best_profile is not None,
            "best_profile": best_profile,
            "best_accuracy": best_score,
            "results": results,
            "final_model": final,
        }
    
    def incremental_train(self, *args, **kwargs) -> Dict[str, Any]:
        """سازگاری: کار نمی‌کنه"""
        return {
            "success": False,
            "error": "incremental_train is not supported. Use calibrate().",
        }
    
    # ============================================================
    # Stats
    # ============================================================
    
    def get_stats(self) -> Dict[str, Any]:
        """آمار کامل"""
        try:
            status = self.check_api_status()
        except Exception:
            status = {"api_status": "unknown", "credits_remaining": 0}
        
        try:
            model_stats = self.model_manager.get_stats() if self.model_manager else {}
        except Exception:
            model_stats = {}
        
        try:
            quota = self.model_manager.get_quota_status() if self.model_manager else {}
        except Exception:
            quota = {}
        
        return {
            "is_running": self.is_running,
            "is_training": self.is_training,
            "is_calibrating": self.is_calibrating,
            
            "stats": {
                **self.stats,
                "last_score": self.stats.get("last_score"),
                "last_improvement": self.stats.get("last_improvement"),
                "training_period": self.stats.get("training_period"),
                "coins_used": self.stats.get("coins_used", []),
                "total_candles_fetched": self.stats.get("total_candles_fetched", 0),
            },
            
            "api_status": status,
            "coins": self.coins,
            
            "model_exists": model_stats.get("loaded", False),
            "current_version": (
                self.model_manager.current_version
                if self.model_manager else None
            ),
            
            "quota": quota,
            "logs": self.logs[-50:],
            "points_config": self.historical_points_config,
            "timestamp": datetime.now().isoformat(),
        }
    
    def get_training_history(
        self,
        period: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """تاریخچه کالیبراسیون"""
        if not self.db or not self.db.is_connected():
            return []
        
        try:
            if period:
                result = self.db.execute(
                    """
                    SELECT
                        m.id, m.version, m.accuracy, m.training_date,
                        m.period, m.training_samples, m.is_ensemble,
                        h.action, h.old_accuracy, h.new_accuracy,
                        h.improvement_percent
                    FROM models m
                    LEFT JOIN model_training_history h ON m.id = h.model_id
                    WHERE m.period = %s
                    ORDER BY m.training_date DESC
                    LIMIT %s
                    """,
                    (period, limit),
                )
            else:
                result = self.db.execute(
                    """
                    SELECT
                        m.id, m.version, m.accuracy, m.training_date,
                        m.period, m.training_samples, m.is_ensemble,
                        h.action, h.old_accuracy, h.new_accuracy,
                        h.improvement_percent
                    FROM models m
                    LEFT JOIN model_training_history h ON m.id = h.model_id
                    ORDER BY m.training_date DESC
                    LIMIT %s
                    """,
                    (limit,),
                )
            
            return result or []
        except Exception as e:
            logger.error(f"❌ Training history error: {e}", exc_info=True)
            return []
    
    # ============================================================
    # Profile API
    # ============================================================
    
    def get_presets(self) -> List[Dict[str, Any]]:
        """لیست profileها"""
        presets = []
        for key, profile in CALIBRATION_PROFILES.items():
            presets.append({
                "id": key,
                "name": profile["name"],
                "description": profile["description"],
                "icon": profile["icon"],
                "color": profile["color"],
                "strategy": profile["strategy"],
                "range": profile.get("range", "6mo"),
                "estimated_time_seconds": profile.get("estimated_time_seconds", 120),
                "is_preset": True,
            })
        return presets
    
    def get_preset(self, preset_id: str) -> Optional[Dict[str, Any]]:
        """دریافت یک profile"""
        if preset_id not in CALIBRATION_PROFILES:
            return None
        
        profile = CALIBRATION_PROFILES[preset_id]
        return {
            "id": preset_id,
            **profile,
            "is_preset": True,
        }


__all__ = ["AutoTrainer", "CALIBRATION_PROFILES"]
