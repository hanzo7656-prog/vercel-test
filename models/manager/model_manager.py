# models/manager/model_manager.py
# ============================================================
# مدیریت مدل - نسخه ۶.۰
# RuleEngine Adapter + Runtime Config + Version Management
# ============================================================
# 
# تغییرات نسخه ۶.۰:
#   - جایگزینی XGBoost با RuleEngine
#   - predict() با DataFrame (نه ndarray)
#   - predict_legacy() برای سازگاری
#   - calibrate() جای train()
#   - runtime_config برای تغییرات از فرانت
#   - get_active_config() و update_active_config()
#   - حذف همه _train_* (به WeightCalibrator منتقل شد)
# ============================================================

import copy
import json
import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from infrastructure.database import (
    get_primary,
    get_cache,
    get_backup,
    get_quota_status,
)
from infrastructure.repositories import repos
from config import get_model_config

# Rule Engine imports
from core.rule_engine import (
    MarketState,
    Prediction,
    RuleEngine,
    StateMachine,
    create_engine_from_config,
    load_default_config,
)

logger = logging.getLogger(__name__)


# ============================================================
# Constants
# ============================================================

DEFAULT_PROFILE_NAME = "balanced"
CACHE_KEY_ACTIVE = "model:active"
CACHE_KEY_STATS = "model:stats"
CACHE_KEY_ACTIVE_PROFILE = "model:active_profile"
CACHE_KEY_ACTIVE_CONFIG = "model:active_config"

CACHE_TTL_ACTIVE = 300
CACHE_TTL_STATS = 60
CACHE_TTL_CONFIG = 300


# ============================================================
# ModelManager v6.0
# ============================================================

class ModelManager:
    """
    مدیریت مدل - Adapter روی RuleEngine
    
    مسئولیت‌ها:
        ۱. بارگذاری RuleEngine از config فعال
        ۲. مدیریت نسخه‌ها (version)
        ۳. predict (single + batch)
        ۴. runtime_config برای تغییرات لحظه‌ای
        ۵. calibrate (delegate به AutoTrainer)
        ۶. آمار و stats
    
    نکته مهم:
        ModelManager دیگه XGBoost رو نمی‌شناسه.
        ولی متدهای سازگاری (predict_legacy، save_model) داره.
    """
    
    def __init__(self, api: Optional[Any] = None) -> None:
        # ============================================================
        # ۱. Dependencies
        # ============================================================
        self.api = api
        self.db = get_primary()
        self.repository = repos.model
        self.cache = get_cache()
        self.backup_db = get_backup()
        self.config = get_model_config()
        self.config_repo = repos.rule_config  # 🆕
        
        # ============================================================
        # ۲. State
        # ============================================================
        self.engine: Optional[RuleEngine] = None
        self.state_machine: Optional[StateMachine] = None
        self.current_version: Optional[str] = None
        self._current_model_id: Optional[int] = None
        
        # Runtime config (از فرانت قابل تغییر)
        self.runtime_config: Dict[str, Any] = {}
        
        # فعال‌ترین config (default + overrideها)
        self._active_config: Dict[str, Any] = {}
        
        # Lock
        self._lock = threading.Lock()
        
        # آمار
        self._stats: Dict[str, int] = {
            "saves": 0,
            "loads": 0,
            "predictions": 0,
            "calibrations": 0,
            "activations": 0,
            "deletions": 0,
            "backups": 0,
            "errors": 0,
            "config_updates": 0,
        }
        
        # ============================================================
        # ۳. Initialize
        # ============================================================
        self._register_with_scheduler()
        self._initialize_engine()
        
        logger.info(
            f"✅ ModelManager v6.0 initialized "
            f"(version={self.current_version or 'default'}, "
            f"engine={'loaded' if self.engine else 'none'})"
        )
    
    # ============================================================
    # Scheduler
    # ============================================================
    
    def _register_with_scheduler(self) -> None:
        """ثبت در Metrics Scheduler (اختیاری)"""
        try:
            from core.metrics import metrics_scheduler
            logger.debug("ModelManager registered with Metrics Scheduler")
        except ImportError:
            pass
        except Exception as e:
            logger.debug(f"Could not register with scheduler: {e}")
    
    # ============================================================
    # Initialize Engine
    # ============================================================
    
    def _initialize_engine(self) -> None:
        """
        راه‌اندازی RuleEngine از config فعال
        
        ترتیب:
            ۱. تلاش برای بارگذاری از DB (نسخه فعال)
            ۲. اگه نبود → بارگذاری از default_rules.json
            ۳. merge با overrideهای کاربر
            ۴. ساخت RuleEngine
        """
        try:
            # ۱. تلاش از DB
            active = self.repository.load_active_rule_config()
            
            if active:
                self._active_config = active["config"]
                self.current_version = active["version"]
                self._current_model_id = active.get("model_id")
                self._stats["loads"] += 1
                logger.info(f"✅ Loaded active config from DB: {self.current_version}")
            else:
                # ۲. از default + override
                self._active_config = self._load_effective_config()
                self.current_version = None
                logger.info("📄 Using default config (no active version in DB)")
            
            # ۳. ساخت RuleEngine
            self._rebuild_engine()
            
        except Exception as e:
            self._stats["errors"] += 1
            logger.error(f"❌ Engine init error: {e}", exc_info=True)
            
            # fallback: default
            try:
                self._active_config = load_default_config()
                self._rebuild_engine()
            except Exception as e2:
                logger.error(f"❌ Fallback engine init failed: {e2}")
    
    def _load_effective_config(self) -> Dict[str, Any]:
        """
        بارگذاری config نهایی (default + overrideهای DB)
        """
        default_config = load_default_config()
        
        try:
            effective = self.config_repo.get_effective_config(default_config)
            return effective
        except Exception as e:
            logger.warning(f"⚠️ Override merge failed: {e}")
            return default_config
    
    def _rebuild_engine(self) -> None:
        """
        ساخت/بازسازی RuleEngine از `_active_config`
        """
        if not self._active_config:
            logger.warning("⚠️ No active config to build engine")
            self.engine = None
            return
        
        try:
            # StateMachine
            sm_config = self._active_config.get("state_machine", {})
            self.state_machine = StateMachine(
                cache=self.cache,
                db=self.db,
                config=sm_config,
            )
            
            # RuleEngine
            self.engine = create_engine_from_config(
                rules_config=self._active_config.get("rules", {}),
                scoring_config=self._active_config.get("scoring", {}),
                state_machine=self.state_machine,
            )
            
            # اعمال runtime_config (اگه داریم)
            if self.runtime_config:
                self._apply_runtime_config()
            
            logger.info(
                f"🔧 RuleEngine rebuilt "
                f"({len(self.engine.rules)} rules)"
            )
        except Exception as e:
            logger.error(f"❌ Engine rebuild failed: {e}", exc_info=True)
            self.engine = None
    
    # ============================================================
    # Predict (جدید)
    # ============================================================
    
    def predict(
        self,
        df: pd.DataFrame,
        symbol: str = "UNKNOWN",
        coin_id: str = "unknown",
        update_state: bool = False,
    ) -> float:
        """
        پیش‌بینی برای یک DataFrame
        
        Args:
            df: DataFrame با OHLCV (و اندیکاتورهای اختیاری)
            symbol: نماد (BTC/USDT)
            coin_id: شناسه (bitcoin)
            update_state: آپدیت StateMachine؟
        
        Returns:
            score ۰-۱
        
        Raises:
            ValueError: اگه engine آماده نباشه
        """
        if self.engine is None:
            raise ValueError("RuleEngine بارگذاری نشده است")
        
        if df is None or df.empty:
            raise ValueError("DataFrame خالی است")
        
        try:
            prediction = self.engine.evaluate(
                symbol=symbol,
                coin_id=coin_id,
                df=df,
                update_state=update_state,
            )
            
            self._stats["predictions"] += 1
            
            if prediction is None:
                return 0.5  # neutral fallback
            
            return float(prediction.score)
        
        except Exception as e:
            self._stats["errors"] += 1
            logger.error(f"❌ Predict error: {e}", exc_info=True)
            raise
    
    def predict_full(
        self,
        df: pd.DataFrame,
        symbol: str = "UNKNOWN",
        coin_id: str = "unknown",
        update_state: bool = False,
    ) -> Optional[Prediction]:
        """
        پیش‌بینی کامل (Prediction object با reasons)
        
        برای API که می‌خواد دلایل رو ببینه
        """
        if self.engine is None:
            return None
        
        try:
            prediction = self.engine.evaluate(
                symbol=symbol,
                coin_id=coin_id,
                df=df,
                update_state=update_state,
            )
            self._stats["predictions"] += 1
            return prediction
        except Exception as e:
            self._stats["errors"] += 1
            logger.error(f"❌ predict_full error: {e}")
            return None
    
    # ============================================================
    # Predict Legacy (سازگاری با کد قدیمی)
    # ============================================================
    
    def predict_legacy(self, features: np.ndarray) -> float:
        """
        پیش‌بینی با ndarray (برای سازگاری)
        
        ⚠️ توجه: features باید یا ۱۳ ستون استاندارد باشه،
        یا یک DataFrame مقادیر با نام‌های پیش‌فرض.
        
        Args:
            features: ndarray از ویژگی‌ها
        
        Returns:
            score ۰-۱
        """
        try:
            # تبدیل ndarray → DataFrame
            if isinstance(features, np.ndarray):
                if features.ndim == 1:
                    features = features.reshape(1, -1)
                
                # نام‌های پیش‌فرض ستون‌ها
                feature_names = self.config.get("features", [
                    "return_1", "return_3", "return_5", "return_10",
                    "sma_5", "sma_10", "sma_20",
                    "volatility", "fear_greed",
                    "trend_5", "trend_10", "trend_20", "r2",
                ])
                
                n_cols = features.shape[1]
                if n_cols <= len(feature_names):
                    cols = feature_names[:n_cols]
                else:
                    cols = [f"f{i}" for i in range(n_cols)]
                
                df = pd.DataFrame(features, columns=cols)
                
                # ساخت DataFrame سازگار با RuleEngine
                # (Close و Volume رو از return_1 و ... تقریب می‌زنیم)
                df_ohlcv = self._features_to_ohlcv(df)
                
                return self.predict(
                    df=df_ohlcv,
                    symbol="legacy",
                    coin_id="legacy",
                    update_state=False,
                )
            
            # اگه DataFrame هست، مستقیم
            if isinstance(features, pd.DataFrame):
                return self.predict(
                    df=features,
                    symbol="legacy",
                    coin_id="legacy",
                    update_state=False,
                )
            
            return 0.5
        
        except Exception as e:
            logger.error(f"❌ predict_legacy error: {e}")
            return 0.5
    
    def _features_to_ohlcv(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        تبدیل DataFrame ویژگی‌های قدیمی به OHLCV
        
        این یه تابع تقریبی برای سازگاریه.
        کد جدید باید مستقیم OHLCV بده.
        """
        n = len(df)
        
        # اگه return_1 داریم، ازش قیمت بساز
        if "return_1" in df.columns:
            base_price = 100.0
            returns = df["return_1"].fillna(0).values
            prices = base_price * np.cumprod(1 + returns)
        else:
            # fallback: قیمت ثابت
            prices = np.full(n, 100.0)
        
        # OHLCV تقریبی
        ohlcv = pd.DataFrame({
            "Open": prices,
            "High": prices * 1.005,  # تقریب
            "Low": prices * 0.995,
            "Close": prices,
            "Volume": np.full(n, 1.0),
        })
        
        # ایندکس زمانی
        ohlcv.index = pd.date_range(
            end=datetime.now(),
            periods=n,
            freq="4h",
        )
        
        return ohlcv
    
    # ============================================================
    # Evaluate Batch
    # ============================================================
    
    def evaluate_batch(
        self,
        symbols: List[Dict[str, str]],
        data_map: Dict[str, pd.DataFrame],
        update_state: bool = True,
    ) -> List[Prediction]:
        """
        ارزیابی گروهی
        
        Args:
            symbols: [{symbol, coin_id}, ...]
            data_map: {symbol: df}
            update_state: آپدیت state؟
        
        Returns:
            لیست Prediction
        """
        if self.engine is None:
            logger.warning("⚠️ Engine not available for batch")
            return []
        
        try:
            return self.engine.evaluate_batch(
                symbols=symbols,
                data_map=data_map,
                update_state=update_state,
            )
        except Exception as e:
            self._stats["errors"] += 1
            logger.error(f"❌ Batch eval error: {e}")
            return []
    
    # ============================================================
    # Runtime Config (ویژگی جدید)
    # ============================================================
    
    def get_active_config(self) -> Dict[str, Any]:
        """
        دریافت config فعال فعلی
        
        شامل:
            - default config
            - overrideهای DB
            - runtime_config (اگه هست)
        """
        with self._lock:
            # merge runtime روی active
            result = copy.deepcopy(self._active_config)
            
            if self.runtime_config:
                result = self._deep_merge(result, self.runtime_config)
            
            return result
    
    def update_active_config(
        self,
        updates: Dict[str, Any],
        persist: bool = False,
        updated_by: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        آپدیت config فعال از فرانت
        
        Args:
            updates: بخش‌های config که باید عوض بشه
                مثال: {
                    "rules": {
                        "rsi": {"weight": 0.40, "min": 30}
                    },
                    "scoring": {"min_pass_score": 0.60}
                }
            persist: آیا در DB ذخیره بشه؟
            updated_by: کاربر
        
        Returns:
            {success, config, applied_keys}
        """
        with self._lock:
            try:
                # اگه persist، در DB ذخیره کن
                if persist:
                    # ذخیره در rules override
                    if "rules" in updates:
                        self.config_repo.save_rules_override(
                            rules_config=updates["rules"],
                            updated_by=updated_by,
                        )
                    
                    # ذخیره در scoring override
                    if "scoring" in updates:
                        self.config_repo.save_scoring_override(
                            scoring_config=updates["scoring"],
                            updated_by=updated_by,
                        )
                    
                    # بارگذاری مجدد از DB
                    self._active_config = self._load_effective_config()
                    self.runtime_config = {}  # چون در DB ذخیره شد
                else:
                    # فقط runtime
                    self.runtime_config = self._deep_merge(
                        self.runtime_config,
                        updates,
                    )
                
                # بازسازی Engine
                self._rebuild_engine()
                
                self._stats["config_updates"] += 1
                
                logger.info(
                    f"🔧 Config updated "
                    f"(persist={persist}, "
                    f"keys={list(updates.keys())})"
                )
                
                return {
                    "success": True,
                    "config": self.get_active_config(),
                    "applied_keys": list(updates.keys()),
                    "persisted": persist,
                }
            
            except Exception as e:
                self._stats["errors"] += 1
                logger.error(f"❌ Config update error: {e}", exc_info=True)
                return {
                    "success": False,
                    "error": str(e),
                }
    
    def reset_runtime_config(self) -> Dict[str, Any]:
        """
        پاک کردن runtime_config (برگشت به config پایه)
        """
        with self._lock:
            self.runtime_config = {}
            self._rebuild_engine()
            
            logger.info("🔄 Runtime config reset")
            
            return {
                "success": True,
                "config": self.get_active_config(),
            }
    
    def _apply_runtime_config(self) -> None:
        """
        اعمال runtime_config روی engine فعلی
        
        (بدون rebuild کامل — برای کارایی)
        """
        if not self.engine or not self.runtime_config:
            return
        
        try:
            # rules
            if "rules" in self.runtime_config:
                self.engine.update_rules_config(self.runtime_config["rules"])
            
            # scoring
            if "scoring" in self.runtime_config:
                scoring = self.runtime_config["scoring"]
                if "min_pass_score" in scoring:
                    self.engine.min_pass_score = float(scoring["min_pass_score"])
                if "aggregation" in scoring:
                    self.engine.aggregation = scoring["aggregation"]
        
        except Exception as e:
            logger.warning(f"⚠️ Apply runtime config failed: {e}")
    
    @staticmethod
    def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        """
        merge عمیق دو دیکشنری
        override روی base اعمال می‌شه (بدون تغییر base)
        """
        result = copy.deepcopy(base)
        
        for key, value in override.items():
            if (
                key in result
                and isinstance(result[key], dict)
                and isinstance(value, dict)
            ):
                result[key] = ModelManager._deep_merge(result[key], value)
            else:
                result[key] = copy.deepcopy(value)
        
        return result
    
    # ============================================================
    # Calibrate (جای train)
    # ============================================================
    
    def calibrate(
        self,
        period: str = "1m",
        coins: Optional[List[str]] = None,
        profile_name: Optional[str] = None,
        save: bool = True,
        strategy: Optional[str] = None,
        config_override: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        کالیبراسیون وزن‌ها (جای train)
        
        این متد به AutoTrainer (که به WeightCalibrator تبدیل شده) delegate می‌کنه.
        
        Args:
            period: بازه داده تاریخی
            coins: لیست ارزها
            profile_name: نام پروفایل (fast/balanced/accurate)
            save: ذخیره در DB؟
            strategy: استراتژی کالیبراسیون (grid/random/hill_climb)
            config_override: config دستی برای شروع کالیبراسیون
        
        Returns:
            {success, version, best_weights, improvement, ...}
        """
        self._stats["calibrations"] += 1
        
        try:
            # تلاش از container
            from container import container
            trainer = container.get("trainer")
        except (ImportError, KeyError):
            trainer = None
        
        if trainer is None or not hasattr(trainer, "calibrate"):
            return {
                "success": False,
                "error": "AutoTrainer (calibrator) not available",
            }
        
        try:
            result = trainer.calibrate(
                period=period,
                coins=coins,
                profile_name=profile_name,
                strategy=strategy,
                config_override=config_override,
                save=save,
            )
            
            # اگه موفق بود، engine رو reload کن
            if result.get("success") and save:
                self._initialize_engine()
            
            return result
        
        except Exception as e:
            self._stats["errors"] += 1
            logger.error(f"❌ Calibrate error: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
            }
    
    # ============================================================
    # Save Config as Version
    # ============================================================
    
    def save_config_version(
        self,
        config: Dict[str, Any],
        accuracy: float = 0.0,
        version: Optional[str] = None,
        description: Optional[str] = None,
        set_active: bool = True,
        backup: bool = True,
    ) -> Dict[str, Any]:
        """
        ذخیره config فعلی به‌عنوان یک نسخه جدید
        
        Args:
            config: config برای ذخیره
            accuracy: دقت (از backtest)
            version: نسخه (اگه None، خودکار)
            description: توضیح
            set_active: فعال بشه؟
            backup: نسخه قبلی بکاپ بشه؟
        
        Returns:
            {success, version, model_id, ...}
        """
        with self._lock:
            # بکاپ
            backup_done = False
            if backup and self.current_version:
                backup_done = self._backup_current_config()
            
            # نسخه
            if version is None:
                version = self._generate_version()
            
            # ذخیره
            try:
                result = self.repository.save_rule_config(
                    config=config,
                    version=version,
                    accuracy=accuracy,
                    coins=None,
                    training_samples=0,
                    is_active=set_active,
                )
                
                if not result.get("success"):
                    self._stats["errors"] += 1
                    return result
                
                if set_active:
                    self._active_config = config
                    self.current_version = version
                    self._current_model_id = result.get("model_id")
                    self._stats["activations"] += 1
                    self._rebuild_engine()
                
                self._stats["saves"] += 1
                
                # پاکسازی cache
                self._delete_cache(CACHE_KEY_ACTIVE)
                self._delete_cache(CACHE_KEY_STATS)
                self._delete_cache(CACHE_KEY_ACTIVE_CONFIG)
                
                logger.info(
                    f"✅ Config version saved: {version} "
                    f"(accuracy={accuracy:.3f}, active={set_active})"
                )
                
                return {
                    "success": True,
                    "version": version,
                    "model_id": result.get("model_id"),
                    "accuracy": accuracy,
                    "backup_done": backup_done,
                    "is_active": set_active,
                    "description": description,
                }
            
            except Exception as e:
                self._stats["errors"] += 1
                logger.error(f"❌ Save config version error: {e}", exc_info=True)
                return {"success": False, "error": str(e)}
    
    # ============================================================
    # Activate Version
    # ============================================================
    
    def set_active(self, version: str) -> bool:
        """فعال‌سازی یک نسخه"""
        try:
            success = self.repository.set_active(version)
            
            if success:
                # Reload engine
                self._initialize_engine()
                self._stats["activations"] += 1
                self._delete_cache(CACHE_KEY_ACTIVE)
                self._delete_cache(CACHE_KEY_ACTIVE_CONFIG)
                logger.info(f"✅ Model {version} activated")
            
            return success
        
        except Exception as e:
            self._stats["errors"] += 1
            logger.error(f"❌ Set active error: {e}")
            return False
    
    # ============================================================
    # Version History
    # ============================================================
    
    def get_version_history(
        self,
        limit: int = 20,
        model_type: Optional[str] = "rule_config",
    ) -> List[Dict[str, Any]]:
        """دریافت تاریخچه نسخه‌ها"""
        try:
            return self.repository.get_version_history(
                limit=limit,
                model_type=model_type,
            )
        except Exception as e:
            logger.error(f"❌ Get version history error: {e}")
            return []
    
    def get_all_versions(self) -> List[Dict[str, Any]]:
        """همه نسخه‌ها"""
        try:
            return self.repository.find_all(limit=1000)
        except Exception as e:
            logger.error(f"❌ Get all versions error: {e}")
            return []
    
    def delete_version(self, version: str) -> bool:
        """حذف یک نسخه"""
        try:
            success = self.repository.delete_by_version(version)
            
            if success:
                self._stats["deletions"] += 1
                self._delete_cache(CACHE_KEY_ACTIVE)
                self._delete_cache(CACHE_KEY_STATS)
            
            return success
        
        except Exception as e:
            logger.error(f"❌ Delete version error: {e}")
            return False
    
    def cleanup_old_versions(self, keep_last_n: int = 10) -> int:
        """پاک کردن نسخه‌های قدیمی"""
        try:
            count = self.repository.cleanup_old_versions(keep_last_n=keep_last_n)
            
            if count > 0:
                self._stats["deletions"] += count
                self._delete_cache(CACHE_KEY_STATS)
            
            return count
        
        except Exception as e:
            logger.error(f"❌ Cleanup error: {e}")
            return 0
    
    def compare_versions(
        self,
        v1: str,
        v2: str,
    ) -> Optional[Dict[str, Any]]:
        """مقایسه دو نسخه"""
        try:
            return self.repository.compare_versions(v1, v2)
        except Exception as e:
            logger.error(f"❌ Compare error: {e}")
            return None
    
    # ============================================================
    # Stats
    # ============================================================
    
    def get_stats(self) -> Dict[str, Any]:
        """
        آمار کامل مدل
        """
        # از cache
        cached = self._get_from_cache(CACHE_KEY_STATS)
        if cached and isinstance(cached, dict):
            cached["runtime_stats"] = dict(self._stats)
            cached["engine_loaded"] = self.engine is not None
            return cached
        
        try:
            repo_stats = self.repository.get_stats()
            quota = self._get_quota_summary()
            
            engine_stats = {}
            if self.engine:
                engine_stats = self.engine.get_stats()
            
            result = {
                # وضعیت
                "loaded": self.engine is not None,
                "version": self.current_version or "default",
                "model_id": self._current_model_id,
                "model_type": "rule_config",
                
                # اتصال‌ها
                "db_connected": self.db is not None and self.db.is_connected(),
                "cache_connected": self.cache is not None and self.cache.is_connected(),
                
                # Repository stats
                "total_versions": repo_stats.get("total_models", 0),
                "avg_accuracy": repo_stats.get("avg_accuracy", 0),
                "max_accuracy": repo_stats.get("max_accuracy", 0),
                "active_model": repo_stats.get("active_model"),
                "by_type": repo_stats.get("by_type", {}),
                
                # Engine stats
                "engine": engine_stats,
                "rule_count": len(self.engine.rules) if self.engine else 0,
                
                # Runtime
                "runtime_config_active": bool(self.runtime_config),
                "runtime_keys": list(self.runtime_config.keys()),
                
                # Quota
                "quota": quota,
                
                # Stats داخلی
                "runtime_stats": dict(self._stats),
                
                "timestamp": datetime.now().isoformat(),
            }
            
            self._set_cache(CACHE_KEY_STATS, result, CACHE_TTL_STATS)
            return result
        
        except Exception as e:
            logger.error(f"❌ Stats error: {e}")
            return {
                "loaded": self.engine is not None,
                "version": self.current_version or "default",
                "error": str(e),
                "runtime_stats": dict(self._stats),
            }
    
    def get_quota_status(self) -> Dict[str, Any]:
        """وضعیت quota"""
        return self._get_quota_summary()
    
    def _get_quota_summary(self) -> Dict[str, Any]:
        """محاسبه quota"""
        try:
            used_mb = self.repository.db._calculate_used_size()
            return get_quota_status("primary", used_mb)
        except Exception as e:
            return {"error": str(e)}
    
    def get_repository_stats(self) -> Dict[str, Any]:
        """آمار Repository"""
        try:
            return self.repository.get_stats()
        except Exception as e:
            return {}
    
    # ============================================================
    # Report
    # ============================================================
    
    def get_report_data(self, version: str) -> Dict[str, Any]:
        """
        داده‌های گزارش برای فرانت
        """
        try:
            model_info = self.repository.find_by_version(version)
            if not model_info:
                return {}
            
            history = self.repository.get_version_history(limit=5)
            
            # config از DB
            config = self.repository.load_rule_config(version)
            
            return {
                "model": {
                    "version": model_info.get("version", "N/A"),
                    "accuracy": model_info.get("accuracy", 0),
                    "training_date": model_info.get("training_date"),
                    "period": model_info.get("period", "rule_config"),
                    "model_type": model_info.get("model_type", "unknown"),
                    "is_active": model_info.get("is_active", False),
                    "training_samples": model_info.get("training_samples", 0),
                },
                "config": config or {},
                "rules_config": (config or {}).get("rules", {}),
                "scoring_config": (config or {}).get("scoring", {}),
                "history": history,
                "stats": {
                    "total_versions": len(history),
                    "best_accuracy": max(
                        [h.get("accuracy", 0) for h in history] or [0]
                    ),
                },
                "runtime": {
                    "runtime_config_active": bool(self.runtime_config),
                    "runtime_keys": list(self.runtime_config.keys()),
                },
                "quota": self.get_quota_status(),
            }
        
        except Exception as e:
            logger.error(f"❌ Report error: {e}", exc_info=True)
            return {}
    
    # ============================================================
    # Get Config Version File (Export)
    # ============================================================
    
    def get_config_file(self, version: str) -> Optional[bytes]:
        """دریافت config به‌صورت JSON bytes"""
        try:
            return self.repository.export_model_file(version)
        except Exception as e:
            logger.error(f"❌ Get config file error: {e}")
            return None
    
    # ============================================================
    # Helpers - Version
    # ============================================================
    
    def _generate_version(self) -> str:
        """ساخت نسخه جدید"""
        now = datetime.now()
        base = f"v{now.year}.{now.month:02d}.{now.day:02d}_{now.hour:02d}{now.minute:02d}"
        
        if not self._ensure_db_connection():
            return base
        
        try:
            result = self.repository.db.execute(
                "SELECT version FROM models WHERE version LIKE %s ORDER BY version DESC LIMIT 1",
                (f"{base}%",)
            )
            
            if not result:
                return base
            
            existing = result[0]["version"]
            
            if existing == base:
                return f"{base}_2"
            
            if "_" in existing[len(base):]:
                try:
                    counter = int(existing.split("_")[-1])
                    return f"{base}_{counter + 1}"
                except (ValueError, IndexError):
                    pass
            
            return f"{base}_2"
        
        except Exception as e:
            logger.debug(f"Version generation error: {e}")
            return f"{base}_{int(now.timestamp())}"
    
    def _ensure_db_connection(self) -> bool:
        """اطمینان از اتصال DB"""
        if not self.db or not self.db.is_connected():
            try:
                self.db = get_primary()
                return self.db is not None and self.db.is_connected()
            except Exception as e:
                logger.error(f"DB reconnect error: {e}")
                return False
        return True
    
    # ============================================================
    # Helpers - Backup
    # ============================================================
    
    def _backup_current_config(self) -> bool:
        """
        بکاپ config فعلی قبل از تغییر
        
        این یه بکاپ داخلیه (نه DB)
        """
        if not self.current_version or not self._active_config:
            return False
        
        try:
            # اگه backup_db موجوده
            if self.backup_db and self.backup_db.is_connected():
                config_bytes = json.dumps(self._active_config).encode("utf-8")
                
                self.backup_db.execute(
                    """
                    INSERT INTO models_backup (
                        original_id, version, model_data, accuracy,
                        period, backup_reason
                    ) VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        self._current_model_id,
                        self.current_version,
                        config_bytes,
                        0.0,
                        "rule_config",
                        "auto_backup_before_override",
                    ),
                )
                
                self._stats["backups"] += 1
                logger.debug(f"✅ Backup: {self.current_version}")
                return True
        
        except Exception as e:
            logger.warning(f"⚠️ Backup failed: {e}")
        
        return False
    
    # ============================================================
    # Helpers - Cache
    # ============================================================
    
    def _get_from_cache(self, key: str) -> Optional[Any]:
        """خواندن از cache"""
        if not self.cache or not self.cache.is_connected():
            return None
        try:
            return self.cache.get(key)
        except Exception:
            return None
    
    def _set_cache(self, key: str, value: Any, ttl: int = 300) -> bool:
        """نوشتن در cache"""
        if not self.cache or not self.cache.is_connected():
            return False
        try:
            return self.cache.set(key, value, ttl=ttl)
        except Exception:
            return False
    
    def _delete_cache(self, key: str) -> bool:
        """حذف از cache"""
        if not self.cache or not self.cache.is_connected():
            return False
        try:
            return self.cache.delete(key)
        except Exception:
            return False
    
    # ============================================================
    # Legacy Compatibility
    # ============================================================
    
    @property
    def current_model(self) -> Optional[RuleEngine]:
        """
        سازگاری با کد قدیمی که `current_model` چک می‌کرد
        
        Returns:
            RuleEngine (به‌جای XGBoost Booster قدیم)
        """
        return self.engine
    
    def get_model_by_version(self, version: str) -> Optional[Dict[str, Any]]:
        """
        دریافت config یک نسخه خاص
        
        Returns:
            config dict یا None
            (به‌جای XGBoost Booster قدیم)
        """
        try:
            return self.repository.load_rule_config(version)
        except Exception as e:
            logger.error(f"❌ Get model by version error: {e}")
            return None
    
    def incremental_train(self, features: np.ndarray, labels: np.ndarray) -> Dict[str, Any]:
        """
        سازگاری: تقریبی به calibrate
        
        ⚠️ این متد نگه داشته شده ولی در عمل کار نمی‌کنه چون
        RuleEngine نیازی به train با features/labels نداره.
        """
        logger.warning(
            "⚠️ incremental_train called but RuleEngine doesn't support it. "
            "Use calibrate() instead."
        )
        return {
            "success": False,
            "error": "RuleEngine does not support incremental_train. Use calibrate().",
        }


__all__ = ["ModelManager"]
