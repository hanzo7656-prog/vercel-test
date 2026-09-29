# models/trainer/auto_trainer.py
# ============================================================
# AutoTrainer → WeightCalibrator - نسخه ۵.۰
# کالیبراسیون وزن‌های RuleEngine از طریق Backtest
# ============================================================
# 
# تغییرات نسخه ۵.۰:
#   - جایگزینی کامل XGBoost با Weight Calibration
#   - حذف _fetch_*، extract_features_for_training، train_model
#   - اضافه calibrate() با grid search
#   - اضافه evaluate_config() برای backtest
#   - حفظ start_auto_train، stop_auto_train، get_stats
# ============================================================

import itertools
import json
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
# Calibration Profiles (جایگزین TRAINING_PRESETS سابق)
# ============================================================

CALIBRATION_PROFILES: Dict[str, Dict[str, Any]] = {
    "fast": {
        "name": "سریع",
        "description": "Grid Search کوچک — برای تست",
        "icon": "🚀",
        "color": "#f59e0b",
        "strategy": "grid",
        "max_iterations": 20,
        "weight_step": 0.10,
        "estimated_time_seconds": 30,
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
    },
    "accurate": {
        "name": "دقیق",
        "description": "Grid Search دقیق — زمان بیشتر",
        "icon": "🎯",
        "color": "#8b5cf6",
        "strategy": "grid",
        "max_iterations": 500,
        "weight_step": 0.025,
        "estimated_time_seconds": 600,
    },
    "hill_climb": {
        "name": "تپه‌نوردی",
        "description": "بهینه‌سازی تکاملی — هوشمندتر",
        "icon": "🏔️",
        "color": "#22d3ee",
        "strategy": "hill_climb",
        "max_iterations": 80,
        "weight_step": 0.05,
        "estimated_time_seconds": 240,
    },
    "random": {
        "name": "تصادفی",
        "description": "جستجوی تصادفی — تنوع بالا",
        "icon": "🎲",
        "color": "#ec4899",
        "strategy": "random",
        "max_iterations": 150,
        "weight_step": 0.05,
        "estimated_time_seconds": 300,
    },
}


# ============================================================
# AutoTrainer (WeightCalibrator)
# ============================================================

class AutoTrainer:
    """
    AutoTrainer → WeightCalibrator
    
    نقش جدید:
        - Backtest روی داده تاریخی
        - Grid/Random/Hill-Climb برای یافتن بهترین وزن‌ها
        - ذخیره بهترین config در DB
        - زمان‌بندی خودکار (همون API سابق)
    
    نکته:
        متدهای train_model, incremental_train, train_batch حذف شدن.
        به‌جاشون calibrate, evaluate_config اضافه شدن.
    """
    
    # ============================================================
    # Init
    # ============================================================
    
    def __init__(self, api: Any, model_manager: Any) -> None:
        """
        Args:
            api: کلاینت API (CoinStatsClient یا مشابه)
            model_manager: ModelManager instance
        """
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
        self.is_training: bool = False  # ← حفظ اسم قدیمی (سازگاری)
        self.is_calibrating: bool = False  # ← اسم جدید
        self.stop_event: threading.Event = threading.Event()
        self.thread: Optional[threading.Thread] = None
        self._lock: threading.Lock = threading.Lock()
        
        # لاگ‌ها
        self.logs: List[str] = []
        
        # ارزها
        self.coins: List[str] = self.auto_trainer_config.get(
            "coins", ["bitcoin", "ethereum"]
        )
        
        # آمار (حفظ ساختار قدیمی برای سازگاری)
        self.stats: Dict[str, Any] = {
            # وضعیت
            "is_running": False,
            "is_training": False,
            "is_calibrating": False,
            
            # کالیبراسیون
            "total_trainings": 0,       # ← حفظ اسم قدیمی
            "successful_trainings": 0,   # ← حفظ اسم قدیمی
            "failed_trainings": 0,       # ← حفظ اسم قدیمی
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
            
            # API
            "api_status": "unknown",
            "credits_remaining": 0,
            "api_calls": 0,
            "api_errors": 0,
            
            # حالت
            "mode": "RULE_ENGINE",
            
            # Points config
            "points_used": {
                "fear_greed": self.historical_points_config["fear_greed"],
                "btc_dominance": self.historical_points_config["btc_dominance"],
                "global_market": self.historical_points_config["global_market"],
                "chart": self.historical_points_config["chart"],
            },
        }
        
        # ثبت در scheduler
        self._register_with_scheduler()
        
        # وضعیت از ModelManager
        if model_manager and model_manager.engine is not None:
            self.stats["mode"] = "RULE_ENGINE"
            self._add_log(
                f"✅ RuleEngine موجود است - "
                f"نسخه: {model_manager.current_version or 'default'}"
            )
        else:
            self._add_log("📦 RuleEngine بارگذاری نشده")
        
        self._add_log(f"✅ AutoTrainer v5.0 (WeightCalibrator) راه‌اندازی شد")
        self._add_log(f"🪙 ارزهای فعال: {self.coins}")
    
    # ============================================================
    # Scheduler Registration
    # ============================================================
    
    def _register_with_scheduler(self) -> None:
        """ثبت در Scheduler"""
        try:
            from core.metrics import metrics_scheduler
            logger.info("✅ AutoTrainer registered with Metrics Scheduler")
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
        
        if len(self.logs) > 200:
            self.logs = self.logs[-200:]
        
        logger.info(message)
    
    def clear_logs(self) -> None:
        """پاک کردن لاگ‌ها"""
        self.logs = []
        self._add_log("🗑️ لاگ‌ها پاک شدند")
    
    def get_logs(self) -> List[str]:
        """دریافت لاگ‌ها"""
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
                
                if remaining < 100:
                    self._add_log(f"⚠️ اعتبار کم: {remaining}")
            
            self.stats["api_status"] = "ok" if api_ok else "error"
            
            return {
                "api_status": "ok" if api_ok else "error",
                "credits_remaining": remaining,
                "can_proceed": api_ok and remaining > 100,
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
        
        Args:
            period: بازه داده تاریخی
            coins: لیست ارزها
            profile_name: نام profile (fast/balanced/accurate/hill_climb/random)
            strategy: استراتژی override
            config_override: config شروع (اگه None، از default)
            save: ذخیره در DB؟
        
        Returns:
            {
                success,
                version,
                best_weights,
                best_score,
                improvement,
                iterations,
                duration_seconds,
                ...
            }
        """
        if self.is_calibrating:
            return {
                "success": False,
                "message": "کالیبراسیون در حال انجام است",
            }
        
        self.is_calibrating = True
        self.is_training = True  # ← حفظ سازگاری
        self.stats["is_calibrating"] = True
        self.stats["is_training"] = True
        self.stats["total_trainings"] += 1
        self.stats["total_calibrations"] += 1
        self.stats["training_period"] = period
        
        start_time = time.time()
        
        try:
            # ============================================================
            # ۱. چک API
            # ============================================================
            status = self.check_api_status()
            if not status["can_proceed"]:
                self._mark_failed(status["message"])
                return {
                    "success": False,
                    "message": status["message"],
                    "api_status": status["api_status"],
                }
            
            # ============================================================
            # ۲. Profile
            # ============================================================
            profile = self._resolve_profile(profile_name, strategy)
            if profile is None:
                self._mark_failed("Profile not found")
                return {
                    "success": False,
                    "error": f"Profile '{profile_name}' not found",
                }
            
            self._add_log(
                f"🎯 شروع کالیبراسیون "
                f"(profile={profile_name or 'balanced'}, "
                f"strategy={profile['strategy']}, "
                f"period={period})"
            )
            
            # ============================================================
            # ۳. config پایه
            # ============================================================
            base_config = (
                config_override
                or self._get_current_config()
            )
            
            # ============================================================
            # ۴. دریافت داده تاریخی
            # ============================================================
            coins_list = coins or self.coins
            data_map = self._fetch_historical_data(coins_list, period)
            
            if not data_map:
                self._mark_failed("No historical data")
                return {
                    "success": False,
                    "error": "داده تاریخی دریافت نشد",
                }
            
            self._add_log(
                f"📊 داده: {len(data_map)} symbol، "
                f"{sum(len(df) for df in data_map.values())} کندل"
            )
            
            # ============================================================
            # ۵. اجرای استراتژی
            # ============================================================
            if profile["strategy"] == "grid":
                result = self._calibrate_grid(
                    base_config=base_config,
                    data_map=data_map,
                    profile=profile,
                )
            elif profile["strategy"] == "random":
                result = self._calibrate_random(
                    base_config=base_config,
                    data_map=data_map,
                    profile=profile,
                )
            elif profile["strategy"] == "hill_climb":
                result = self._calibrate_hill_climb(
                    base_config=base_config,
                    data_map=data_map,
                    profile=profile,
                )
            else:
                self._mark_failed(f"Unknown strategy: {profile['strategy']}")
                return {
                    "success": False,
                    "error": f"Strategy '{profile['strategy']}' not implemented",
                }
            
            # ============================================================
            # ۶. محاسبه improvement
            # ============================================================
            baseline_score = self._evaluate_config(base_config, data_map)
            improvement = result["best_score"] - baseline_score
            
            result["baseline_score"] = round(baseline_score, 4)
            result["improvement"] = round(improvement, 4)
            result["improvement_percent"] = (
                round((improvement / baseline_score * 100), 2)
                if baseline_score > 0 else 0
            )
            
            # ============================================================
            # ۷. ذخیره در DB
            # ============================================================
            if save and result.get("best_config"):
                save_result = self._save_best_config(
                    config=result["best_config"],
                    accuracy=result["best_score"],
                    description=f"Calibrated with {profile['strategy']}",
                )
                result["save_result"] = save_result
                result["version"] = save_result.get("version")
            else:
                result["save_result"] = {"success": False, "reason": "save=False"}
                result["version"] = None
            
            # ============================================================
            # ۸. آمار نهایی
            # ============================================================
            duration = time.time() - start_time
            result["duration_seconds"] = round(duration, 2)
            
            self._mark_success(
                score=result["best_score"],
                improvement=improvement,
                data_points=result.get("evaluations", 0),
            )
            
            self._add_log(
                f"✅ کالیبراسیون موفق "
                f"(best_score={result['best_score']:.4f}, "
                f"improvement={improvement:+.4f}, "
                f"{duration:.1f}s)"
            )
            
            return result
        
        except Exception as e:
            logger.error(f"❌ Calibrate error: {e}", exc_info=True)
            self._mark_failed(str(e))
            return {
                "success": False,
                "error": str(e),
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
        """
        Grid Search روی وزن‌ها
        
        برای هر rule، مقادیر weight رو در گام‌های مشخص امتحان می‌کنه
        """
        rules = list(base_config.get("rules", {}).keys())
        step = profile.get("weight_step", 0.05)
        max_iter = profile.get("max_iterations", 100)
        
        # ساخت مقادیر ممکن برای هر weight
        weight_values = np.arange(0.0, 1.01, step).tolist()
        
        self._add_log(
            f"🔍 Grid Search: {len(rules)} rules, "
            f"step={step}, max_iter={max_iter}"
        )
        
        best_score = -1.0
        best_weights: Dict[str, float] = {}
        best_config: Optional[Dict[str, Any]] = None
        
        iterations = 0
        evaluations = 0
        
        # اگه rules کمه، همه ترکیب‌ها
        # اگه زیاده، نمونه‌گیری
        total_combinations = len(weight_values) ** len(rules)
        
        if total_combinations <= max_iter:
            # کامل
            for weights in itertools.product(weight_values, repeat=len(rules)):
                if iterations >= max_iter:
                    break
                
                config = self._apply_weights(base_config, dict(zip(rules, weights)))
                score = self._evaluate_config(config, data_map)
                evaluations += 1
                iterations += 1
                
                if score > best_score:
                    best_score = score
                    best_weights = dict(zip(rules, weights))
                    best_config = config
        else:
            # نمونه‌گیری تصادفی
            self._add_log(
                f"⚠️ ترکیبات زیاد ({total_combinations}), "
                f"نمونه‌گیری تصادفی"
            )
            
            for _ in range(max_iter):
                weights = [random.choice(weight_values) for _ in rules]
                config = self._apply_weights(base_config, dict(zip(rules, weights)))
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
        
        self._add_log(f"🎲 Random Search: {max_iter} iterations")
        
        best_score = -1.0
        best_weights: Dict[str, float] = {}
        best_config: Optional[Dict[str, Any]] = None
        
        for i in range(max_iter):
            # وزن‌های تصادفی که مجموعشون ۱ بشه
            weights_raw = [random.random() for _ in rules]
            total = sum(weights_raw)
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
        """تپه‌نوردی (تکاملی ساده)"""
        rules = list(base_config.get("rules", {}).keys())
        max_iter = profile.get("max_iterations", 80)
        step = profile.get("weight_step", 0.05)
        
        self._add_log(f"🏔️ Hill Climb: {max_iter} iterations")
        
        # نقطه شروع
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
        
        for i in range(max_iter):
            # برای هر rule، یه کم تغییر بده
            improved = False
            
            for rule_name in rules:
                for direction in [+step, -step]:
                    candidate = current_weights.copy()
                    new_val = candidate[rule_name] + direction
                    
                    if new_val < 0.0 or new_val > 1.0:
                        continue
                    
                    candidate[rule_name] = new_val
                    
                    # نرمالایز
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
                # کاهش step
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
        ارزیابی یک config روی داده تاریخی
        
        معیار: Sharpe-like ratio
        
        منطق:
            ۱. برای هر symbol، RuleEngine رو روی آخرین کندل اجرا کن
            ۲. اگه pass شد، «سیگنال» بگیر
            ۳. سیگنال رو با بازده کندل بعدی مقایسه کن
            ۴. Sharpe = mean(returns) / std(returns)
        
        Returns:
            امتیاز ۰-۱ (بالاتر = بهتر)
        """
        try:
            # ساخت engine موقت
            temp_sm = StateMachine(
                cache=None,  # بدون state در backtest
                db=None,
                config={"enable_db_history": False},
            )
            
            engine = create_engine_from_config(
                rules_config=config.get("rules", {}),
                scoring_config=config.get("scoring", {}),
                state_machine=temp_sm,
            )
            
            # جمع‌آوری سیگنال‌ها
            signal_returns: List[float] = []
            
            for symbol, df in data_map.items():
                if df is None or len(df) < 50:
                    continue
                
                # آخرین کندل‌ها رو امتحان کن (شبیه‌سازی historical)
                # از چند نقطه مختلف
                for i in range(30, len(df), max(1, len(df) // 10)):
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
                        
                        # اگه pass شد، بازده بعدی رو حساب کن
                        if prediction.score >= engine.min_pass_score:
                            if i + 1 < len(df):
                                close_now = df["Close"].iloc[i]
                                close_next = df["Close"].iloc[i + 1]
                                ret = (close_next - close_now) / close_now
                                signal_returns.append(ret)
                    
                    except Exception:
                        continue
            
            # محاسبه Sharpe
            if len(signal_returns) < 3:
                return 0.0
            
            returns_arr = np.array(signal_returns)
            mean_ret = np.mean(returns_arr)
            std_ret = np.std(returns_arr)
            
            if std_ret < 1e-6:
                return 0.0
            
            sharpe = mean_ret / std_ret
            
            # نرمالایز به ۰-۱
            # sharpe از -3 تا +3 → ۰ تا ۱
            normalized = (sharpe + 3.0) / 6.0
            return float(np.clip(normalized, 0.0, 1.0))
        
        except Exception as e:
            logger.debug(f"Evaluate config error: {e}")
            return 0.0
    
    # ============================================================
    # Data Fetching
    # ============================================================
    
    def _fetch_historical_data(
        self,
        coins: List[str],
        period: str,
    ) -> Dict[str, pd.DataFrame]:
        """
        دریافت داده تاریخی برای کالیبراسیون
        
        Returns:
            {symbol: DataFrame}
        """
        data_map: Dict[str, pd.DataFrame] = {}
        
        for coin in coins:
            self._add_log(f"📥 دریافت {coin} ({period})")
            
            try:
                chart_data = self._fetch_with_retry(coin, period)
                if not chart_data:
                    self._add_log(f"   ⚠️ داده‌ای برای {coin} نیست")
                    continue
                
                df = self._list_to_dataframe(chart_data)
                if df is not None and len(df) >= 50:
                    symbol = f"{coin.upper()}/USDT"
                    data_map[symbol] = df
                    self._add_log(f"   ✅ {len(df)} کندل از {coin}")
                else:
                    self._add_log(f"   ⚠️ داده کافی نیست برای {coin}")
            
            except Exception as e:
                logger.warning(f"Fetch error for {coin}: {e}")
        
        return data_map
    
    def _fetch_with_retry(
        self,
        coin: str,
        period: str,
        max_attempts: int = 3,
    ) -> Optional[List]:
        """دریافت با retry"""
        for attempt in range(max_attempts):
            try:
                data = self.api.get_chart(coin, period)
                self.stats["api_calls"] += 1
                
                if data and isinstance(data, list) and len(data) > 0:
                    return data
                
                if isinstance(data, dict) and "error" in data:
                    logger.warning(
                        f"API error for {coin} (attempt {attempt + 1}): "
                        f"{data.get('error')}"
                    )
            except Exception as e:
                logger.warning(f"Fetch error (attempt {attempt + 1}): {e}")
            
            self.stats["api_errors"] += 1
            
            if attempt < max_attempts - 1:
                time.sleep(2 ** attempt)
        
        return None
    
    @staticmethod
    def _list_to_dataframe(data: List) -> Optional[pd.DataFrame]:
        """تبدیل لیست به DataFrame OHLCV"""
        if not data:
            return None
        
        rows = []
        for point in data:
            if isinstance(point, (list, tuple)) and len(point) >= 2:
                ts = point[0]
                price = float(point[1])
                
                rows.append({
                    "timestamp": pd.to_datetime(ts, unit="ms", errors="coerce"),
                    "Open": price,
                    "High": price,
                    "Low": price,
                    "Close": price,
                    "Volume": 1.0,
                })
        
        if not rows:
            return None
        
        df = pd.DataFrame(rows).set_index("timestamp").sort_index().dropna()
        
        if len(df) < 30:
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
            # از DB
            result = self.model_manager.load_profile(name) if hasattr(
                self.model_manager, "load_profile"
            ) else None
            
            if not result or not result.get("success"):
                # fallback به balanced
                profile = CALIBRATION_PROFILES["balanced"].copy()
            else:
                profile = result["profile"]
        
        # override strategy
        if strategy:
            profile["strategy"] = strategy
        
        return profile
    
    def _get_current_config(self) -> Dict[str, Any]:
        """دریافت config فعلی"""
        try:
            if self.model_manager and hasattr(self.model_manager, "get_active_config"):
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
        """ذخیره best config در DB"""
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
        self.stats["last_training"] = datetime.now().isoformat()
        self.stats["last_calibration"] = datetime.now().isoformat()
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
        """
        شروع کالیبراسیون خودکار
        
        (حفظ API قدیمی — ولی حالا calibrate صدا می‌زنه)
        """
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
                f"(فاصله: {interval_hours}h, بازه: {period}, "
                f"profile: {profile_name})"
            )
            
            while not self.stop_event.is_set():
                try:
                    result = self.calibrate(
                        period=period,
                        coins=coins,
                        profile_name=profile_name,
                        save=True,
                    )
                    
                    self._add_log(
                        f"📊 نتیجه: "
                        f"{'✅' if result.get('success') else '❌'} "
                        f"{result.get('best_score', 'N/A')}"
                    )
                except Exception as e:
                    self._add_log(f"❌ خطا: {e}")
                    logger.error(f"Auto calibrate cycle error: {e}", exc_info=True)
                
                wait_seconds = interval_hours * 3600
                self.stop_event.wait(wait_seconds)
            
            self.is_running = False
            self.stats["is_running"] = False
            self._add_log("⏹️ کالیبراسیون خودکار متوقف شد")
        
        self.thread = threading.Thread(target=run, daemon=True)
        self.thread.start()
        
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
    # Legacy Compatibility (بازگردانده‌شده با خطا)
    # ============================================================
    
    def train_model(self, *args, **kwargs) -> Dict[str, Any]:
        """
        سازگاری: به calibrate redirect می‌کنه
        
        ⚠️ در نسخه ۵.۰، train_model معنی نداره.
        """
        logger.warning("⚠️ train_model called — redirecting to calibrate()")
        
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
        """
        سازگاری: آموزش با چند profile (A/B Testing کالیبراسیون)
        """
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
        
        # ذخیره بهترین
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
            "summary": {
                "profiles_tested": len(profiles),
                "profiles_successful": sum(
                    1 for r in results.values() if r.get("success")
                ),
            },
        }
    
    def incremental_train(self, *args, **kwargs) -> Dict[str, Any]:
        """سازگاری: کار نمی‌کنه"""
        logger.warning("⚠️ incremental_train called — not supported")
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
            },
            
            "api_status": status,
            "coins": self.coins,
            
            "model_exists": model_stats.get("loaded", False),
            "current_version": (
                self.model_manager.current_version
                if self.model_manager else None
            ),
            
            "quota": quota,
            "logs": self.logs[-30:],
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
    # Calibration Profiles API
    # ============================================================
    
    def get_presets(self) -> List[Dict[str, Any]]:
        """لیست profileهای کالیبراسیون"""
        presets = []
        for key, profile in CALIBRATION_PROFILES.items():
            presets.append({
                "id": key,
                "name": profile["name"],
                "description": profile["description"],
                "icon": profile["icon"],
                "color": profile["color"],
                "strategy": profile["strategy"],
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
