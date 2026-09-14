# models/manager/model_manager.py
# ============================================================
# مدیریت پیشرفته مدل XGBoost - نسخه ۵.۰
# Training Profiles + Learning Strategies + Repository + Cache
# ============================================================

import os
import json
import logging
import tempfile
import threading
import copy
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple, Callable
from datetime import datetime

import numpy as np
import xgboost as xgb

from infrastructure.database import (
    get_primary,
    get_cache,
    get_backup,
    get_quota,
    get_quota_status,
)
from infrastructure.repositories import repos
from config import get_model_config

logger = logging.getLogger(__name__)


# ============================================================
# Training Presets
# ============================================================

TRAINING_PRESETS: Dict[str, Dict[str, Any]] = {
    "fast": {
        "name": "سریع",
        "description": "برای تست و آزمایش سریع",
        "icon": "🚀",
        "color": "#f59e0b",
        "hyperparameters": {
            "n_estimators": 20,
            "max_depth": 3,
            "learning_rate": 0.1,
            "subsample": 0.8,
            "colsample_bytree": 0.8,
            "min_child_weight": 1,
            "gamma": 0,
            "reg_alpha": 0,
            "reg_lambda": 1,
            "objective": "binary:logistic",
            "tree_method": "hist",
        },
        "estimated_time_seconds": 10,
    },
    "balanced": {
        "name": "متعادل",
        "description": "تعادل بین سرعت و دقت (پیش‌فرض)",
        "icon": "⚖️",
        "color": "#10b981",
        "hyperparameters": {
            "n_estimators": 100,
            "max_depth": 5,
            "learning_rate": 0.05,
            "subsample": 0.8,
            "colsample_bytree": 0.8,
            "min_child_weight": 1,
            "gamma": 0,
            "reg_alpha": 0,
            "reg_lambda": 1,
            "objective": "binary:logistic",
            "tree_method": "hist",
        },
        "estimated_time_seconds": 45,
    },
    "accurate": {
        "name": "دقیق",
        "description": "دقت بالا، زمان بیشتر",
        "icon": "🎯",
        "color": "#8b5cf6",
        "hyperparameters": {
            "n_estimators": 300,
            "max_depth": 7,
            "learning_rate": 0.03,
            "subsample": 0.8,
            "colsample_bytree": 0.8,
            "min_child_weight": 3,
            "gamma": 0.1,
            "reg_alpha": 0.1,
            "reg_lambda": 1,
            "objective": "binary:logistic",
            "tree_method": "hist",
        },
        "estimated_time_seconds": 180,
    },
    "deep": {
        "name": "عمیق",
        "description": "برای الگوهای پیچیده",
        "icon": "🌊",
        "color": "#ec4899",
        "hyperparameters": {
            "n_estimators": 200,
            "max_depth": 10,
            "learning_rate": 0.01,
            "subsample": 0.7,
            "colsample_bytree": 0.7,
            "min_child_weight": 5,
            "gamma": 0.2,
            "reg_alpha": 0.5,
            "reg_lambda": 2,
            "objective": "binary:logistic",
            "tree_method": "hist",
        },
        "estimated_time_seconds": 240,
    },
    "shallow": {
        "name": "کم‌عمق",
        "description": "جلوگیری از overfit",
        "icon": "📏",
        "color": "#22d3ee",
        "hyperparameters": {
            "n_estimators": 150,
            "max_depth": 2,
            "learning_rate": 0.1,
            "subsample": 0.9,
            "colsample_bytree": 0.9,
            "min_child_weight": 1,
            "gamma": 0,
            "reg_alpha": 0,
            "reg_lambda": 1,
            "objective": "binary:logistic",
            "tree_method": "hist",
        },
        "estimated_time_seconds": 60,
    },
}


# ============================================================
# Learning Strategies
# ============================================================

LEARNING_STRATEGIES: Dict[str, Dict[str, Any]] = {
    "full": {
        "name": "آموزش کامل",
        "description": "آموزش از صفر با تمام داده‌ها",
        "icon": "🔄",
        "requires_existing_model": False,
    },
    "incremental": {
        "name": "آموزش افزایشی",
        "description": "افزودن درخت‌های جدید به مدل موجود",
        "icon": "➕",
        "requires_existing_model": True,
    },
    "transfer": {
        "name": "یادگیری انتقالی",
        "description": "شروع از مدل قبلی با learning_rate پایین",
        "icon": "🎓",
        "requires_existing_model": True,
    },
    "fine_tune": {
        "name": "تنظیم دقیق",
        "description": "تنظیم دقیق روی داده‌های خاص",
        "icon": "🎯",
        "requires_existing_model": True,
    },
    "ensemble": {
        "name": "ترکیب مدل‌ها",
        "description": "ترکیب چند مدل با وزن‌دهی",
        "icon": "🔗",
        "requires_existing_model": True,
    },
}


# ============================================================
# Hyperparameter Limits
# ============================================================

HYPERPARAMETER_LIMITS: Dict[str, Dict[str, Any]] = {
    "n_estimators": {"min": 10, "max": 1000, "type": "int", "step": 10},
    "max_depth": {"min": 1, "max": 15, "type": "int", "step": 1},
    "learning_rate": {"min": 0.001, "max": 1.0, "type": "float", "step": 0.001},
    "subsample": {"min": 0.1, "max": 1.0, "type": "float", "step": 0.05},
    "colsample_bytree": {"min": 0.1, "max": 1.0, "type": "float", "step": 0.05},
    "min_child_weight": {"min": 1, "max": 100, "type": "int", "step": 1},
    "gamma": {"min": 0, "max": 10, "type": "float", "step": 0.1},
    "reg_alpha": {"min": 0, "max": 10, "type": "float", "step": 0.1},
    "reg_lambda": {"min": 0, "max": 10, "type": "float", "step": 0.1},
}

DEFAULT_HYPERPARAMETERS = TRAINING_PRESETS["balanced"]["hyperparameters"].copy()


# ============================================================
# ModelManager
# ============================================================

class ModelManager:
    """
    مدیریت پیشرفته مدل XGBoost با Training Profiles
    """

    CACHE_KEY_ACTIVE = "model:active"
    CACHE_KEY_STATS = "model:stats"
    CACHE_KEY_PROFILES = "model:profiles"
    CACHE_KEY_ACTIVE_PROFILE = "model:active_profile"

    CACHE_TTL_ACTIVE = 300
    CACHE_TTL_STATS = 60
    CACHE_TTL_PROFILES = 300

    DEFAULT_PROFILE_NAME = "balanced"
    MIN_BACKUP_ACCURACY = 0.0

    def __init__(self, api: Optional[Any] = None) -> None:
        self.api = api
        self.db = get_primary()
        self.repository = repos.model
        self.cache = get_cache()
        self.backup_db = get_backup()
        self.config = get_model_config()

        self.current_model: Optional[xgb.Booster] = None
        self.current_version: Optional[str] = None
        self._current_model_id: Optional[int] = None
        self._active_profile: Dict[str, Any] = self._get_default_profile()

        self._lock = threading.Lock()

        self._stats: Dict[str, int] = {
            "saves": 0,
            "loads": 0,
            "predictions": 0,
            "trainings": 0,
            "activations": 0,
            "deletions": 0,
            "backups": 0,
            "errors": 0,
        }

        self._register_with_scheduler()
        self._load_active_model()
        self._load_active_profile()

        logger.info(
            f"ModelManager v5.0 initialized "
            f"(model: {self.current_version}, "
            f"profile: {self._active_profile.get('name', 'default')})"
        )

    # ============================================================
    # Scheduler Registration
    # ============================================================

    def _register_with_scheduler(self) -> None:
        try:
            from core.metrics import metrics_scheduler
            logger.debug("ModelManager registered with Metrics Scheduler")
        except ImportError:
            pass
        except Exception as e:
            logger.debug(f"Could not register with scheduler: {e}")

    # ============================================================
    # Training Profiles - Public API
    # ============================================================

    def get_presets(self) -> List[Dict[str, Any]]:
        presets = []
        for key, preset in TRAINING_PRESETS.items():
            presets.append({
                "id": key,
                "name": preset["name"],
                "description": preset["description"],
                "icon": preset["icon"],
                "color": preset["color"],
                "hyperparameters": preset["hyperparameters"],
                "estimated_time_seconds": preset.get("estimated_time_seconds", 60),
                "is_preset": True,
            })
        return presets

    def get_preset(self, preset_id: str) -> Optional[Dict[str, Any]]:
        if preset_id not in TRAINING_PRESETS:
            return None

        preset = TRAINING_PRESETS[preset_id]
        return {
            "id": preset_id,
            "name": preset["name"],
            "description": preset["description"],
            "icon": preset["icon"],
            "color": preset["color"],
            "hyperparameters": preset["hyperparameters"].copy(),
            "estimated_time_seconds": preset.get("estimated_time_seconds", 60),
            "is_preset": True,
        }

    def get_strategies(self) -> List[Dict[str, Any]]:
        strategies = []
        for key, strategy in LEARNING_STRATEGIES.items():
            strategies.append({
                "id": key,
                "name": strategy["name"],
                "description": strategy["description"],
                "icon": strategy["icon"],
                "requires_existing_model": strategy["requires_existing_model"],
            })
        return strategies

    def get_hyperparameter_limits(self) -> Dict[str, Dict[str, Any]]:
        return copy.deepcopy(HYPERPARAMETER_LIMITS)

    def get_current_profile(self) -> Dict[str, Any]:
        return copy.deepcopy(self._active_profile)

    def set_current_profile(self, profile: Dict[str, Any]) -> Dict[str, Any]:
        validation = self.validate_profile(profile)
        if not validation["valid"]:
            return {
                "success": False,
                "error": "Invalid profile",
                "details": validation["errors"],
            }

        self._active_profile = validation["profile"]
        self._set_cache(self.CACHE_KEY_ACTIVE_PROFILE, self._active_profile)

        logger.info(f"Active profile set: {self._active_profile.get('name')}")

        return {
            "success": True,
            "profile": self._active_profile,
        }

    def validate_profile(self, profile: Dict[str, Any]) -> Dict[str, Any]:
        errors = []

        validated = {
            "name": profile.get("name", "custom"),
            "description": profile.get("description", ""),
            "icon": profile.get("icon", "⚙️"),
            "color": profile.get("color", "#94a3b8"),
            "learning_strategy": profile.get("learning_strategy", "full"),
            "hyperparameters": {},
            "data_config": profile.get("data_config", {}),
            "is_preset": False,
        }

        strategy = validated["learning_strategy"]
        if strategy not in LEARNING_STRATEGIES:
            errors.append(f"Invalid learning_strategy: {strategy}")

        hyperparams = profile.get("hyperparameters", {})

        for key, limits in HYPERPARAMETER_LIMITS.items():
            value = hyperparams.get(key, DEFAULT_HYPERPARAMETERS.get(key))

            if value is None:
                errors.append(f"Missing hyperparameter: {key}")
                continue

            if limits["type"] == "int":
                try:
                    value = int(value)
                except (ValueError, TypeError):
                    errors.append(f"{key} must be int")
                    continue
            elif limits["type"] == "float":
                try:
                    value = float(value)
                except (ValueError, TypeError):
                    errors.append(f"{key} must be float")
                    continue

            if value < limits["min"] or value > limits["max"]:
                errors.append(
                    f"{key} must be between "
                    f"{limits['min']} and {limits['max']}"
                )
                continue

            validated["hyperparameters"][key] = value

        for key in ["objective", "tree_method"]:
            if key in hyperparams:
                validated["hyperparameters"][key] = hyperparams[key]

        validated["hyperparameters"].setdefault("objective", "binary:logistic")
        validated["hyperparameters"].setdefault("tree_method", "hist")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "profile": validated,
        }

    def save_profile(self, profile: Dict[str, Any]) -> Dict[str, Any]:
        try:
            validation = self.validate_profile(profile)
            if not validation["valid"]:
                return {
                    "success": False,
                    "error": "Invalid profile",
                    "details": validation["errors"],
                }

            validated = validation["profile"]
            name = validated["name"]

            if not name or name == "custom":
                return {
                    "success": False,
                    "error": "Profile name is required",
                }

            if not self._ensure_db_connection():
                return {"success": False, "error": "Database not connected"}

            result = self.db.execute(
                """
                INSERT INTO training_profiles (
                    name, description, icon, color,
                    learning_strategy, hyperparameters, data_config,
                    created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (name) DO UPDATE
                SET description = EXCLUDED.description,
                    icon = EXCLUDED.icon,
                    color = EXCLUDED.color,
                    learning_strategy = EXCLUDED.learning_strategy,
                    hyperparameters = EXCLUDED.hyperparameters,
                    data_config = EXCLUDED.data_config,
                    updated_at = EXCLUDED.updated_at
                RETURNING id, name
                """,
                (
                    name,
                    validated["description"],
                    validated["icon"],
                    validated["color"],
                    validated["learning_strategy"],
                    json.dumps(validated["hyperparameters"]),
                    json.dumps(validated["data_config"]),
                    datetime.now(),
                    datetime.now(),
                ),
            )

            self._delete_cache(self.CACHE_KEY_PROFILES)

            logger.info(f"Profile saved: {name}")

            return {
                "success": True,
                "name": name,
                "id": result[0]["id"] if result else None,
            }

        except Exception as e:
            logger.error(f"Save profile error: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    def list_profiles(self) -> List[Dict[str, Any]]:
        cached = self._get_from_cache(self.CACHE_KEY_PROFILES)
        if cached and isinstance(cached, list):
            return cached

        try:
            if not self._ensure_db_connection():
                return []

            result = self.db.execute(
                """
                SELECT
                    id, name, description, icon, color,
                    learning_strategy, hyperparameters, data_config,
                    created_at, updated_at
                FROM training_profiles
                ORDER BY updated_at DESC
                """
            )

            profiles = []
            for row in result:
                profiles.append({
                    "id": row["id"],
                    "name": row["name"],
                    "description": row["description"],
                    "icon": row["icon"],
                    "color": row["color"],
                    "learning_strategy": row["learning_strategy"],
                    "hyperparameters": (
                        json.loads(row["hyperparameters"])
                        if isinstance(row["hyperparameters"], str)
                        else row["hyperparameters"]
                    ),
                    "data_config": (
                        json.loads(row["data_config"])
                        if isinstance(row["data_config"], str)
                        else row["data_config"]
                    ),
                    "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                    "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
                    "is_preset": False,
                })

            self._set_cache(
                self.CACHE_KEY_PROFILES,
                profiles,
                self.CACHE_TTL_PROFILES,
            )

            return profiles

        except Exception as e:
            logger.error(f"List profiles error: {e}", exc_info=True)
            return []

    def load_profile(self, name: str) -> Dict[str, Any]:
        if name in TRAINING_PRESETS:
            preset = self.get_preset(name)
            return {
                "success": True,
                "profile": preset,
            }

        try:
            if not self._ensure_db_connection():
                return {"success": False, "error": "Database not connected"}

            result = self.db.execute(
                """
                SELECT
                    id, name, description, icon, color,
                    learning_strategy, hyperparameters, data_config
                FROM training_profiles
                WHERE name = %s
                """,
                (name,),
            )

            if not result:
                return {"success": False, "error": f"Profile '{name}' not found"}

            row = result[0]
            profile = {
                "id": row["id"],
                "name": row["name"],
                "description": row["description"],
                "icon": row["icon"],
                "color": row["color"],
                "learning_strategy": row["learning_strategy"],
                "hyperparameters": (
                    json.loads(row["hyperparameters"])
                    if isinstance(row["hyperparameters"], str)
                    else row["hyperparameters"]
                ),
                "data_config": (
                    json.loads(row["data_config"])
                    if isinstance(row["data_config"], str)
                    else row["data_config"]
                ),
                "is_preset": False,
            }

            return {"success": True, "profile": profile}

        except Exception as e:
            logger.error(f"Load profile error: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    def delete_profile(self, name: str) -> bool:
        if name in TRAINING_PRESETS:
            logger.warning(f"Cannot delete preset: {name}")
            return False

        try:
            if not self._ensure_db_connection():
                return False

            self.db.execute(
                "DELETE FROM training_profiles WHERE name = %s",
                (name,),
            )

            self._delete_cache(self.CACHE_KEY_PROFILES)

            logger.info(f"Profile deleted: {name}")
            return True

        except Exception as e:
            logger.error(f"Delete profile error: {e}")
            return False

    def apply_profile(self, profile: Dict[str, Any]) -> Dict[str, Any]:
        return self.set_current_profile(profile)

    # ============================================================
    # Training - Public API
    # ============================================================

    def train(
        self,
        X: np.ndarray,
        y: np.ndarray,
        profile: Dict[str, Any],
        period: str = "1m",
        coins: Optional[List[str]] = None,
        save: bool = True,
        profile_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        with self._lock:
            self._stats["trainings"] += 1

            validation = self.validate_profile(profile)
            if not validation["valid"]:
                self._stats["errors"] += 1
                return {
                    "success": False,
                    "error": "Invalid profile",
                    "details": validation["errors"],
                }

            validated_profile = validation["profile"]
            strategy = validated_profile.get("learning_strategy", "full")

            if X is None or y is None:
                self._stats["errors"] += 1
                return {
                    "success": False,
                    "error": "Training data is None",
                }

            if len(X) == 0:
                self._stats["errors"] += 1
                return {
                    "success": False,
                    "error": "Empty training data",
                }

            if len(X) != len(y):
                self._stats["errors"] += 1
                return {
                    "success": False,
                    "error": f"X and y size mismatch: {len(X)} vs {len(y)}",
                }

            if strategy not in LEARNING_STRATEGIES:
                self._stats["errors"] += 1
                return {
                    "success": False,
                    "error": f"Invalid strategy: {strategy}",
                }

            if LEARNING_STRATEGIES[strategy]["requires_existing_model"]:
                if self.current_model is None:
                    self._stats["errors"] += 1
                    return {
                        "success": False,
                        "error": f"Strategy '{strategy}' requires existing model",
                    }

            logger.info(
                f"Training started "
                f"(strategy: {strategy}, "
                f"profile: {profile_name or validated_profile.get('name')}, "
                f"period: {period}, "
                f"samples: {len(X)})"
            )

            try:
                if strategy == "full":
                    return self._train_full(
                        X, y, validated_profile,
                        period, coins, save, profile_name,
                    )
                elif strategy == "incremental":
                    return self._train_incremental(
                        X, y, validated_profile,
                        period, coins, save, profile_name,
                    )
                elif strategy == "transfer":
                    return self._train_transfer(
                        X, y, validated_profile,
                        period, coins, save, profile_name,
                    )
                elif strategy == "fine_tune":
                    return self._train_fine_tune(
                        X, y, validated_profile,
                        period, coins, save, profile_name,
                    )
                elif strategy == "ensemble":
                    return self._train_ensemble(
                        X, y, validated_profile,
                        period, coins, save, profile_name,
                    )
                else:
                    self._stats["errors"] += 1
                    return {
                        "success": False,
                        "error": f"Strategy '{strategy}' not implemented",
                    }

            except Exception as e:
                self._stats["errors"] += 1
                logger.error(f"Training error: {e}", exc_info=True)
                return {"success": False, "error": str(e)}

    # ============================================================
    # _train_full
    # ============================================================

    def _train_full(
        self,
        X: np.ndarray,
        y: np.ndarray,
        profile: Dict[str, Any],
        period: str,
        coins: Optional[List[str]],
        save: bool,
        profile_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        try:
            quota_result = self._check_quota_before_training(profile)

            hyperparams = profile["hyperparameters"]

            params = {
                **hyperparams,
                "random_state": 42,
                "eval_metric": "logloss",
            }

            start_time = datetime.now()

            model = xgb.XGBClassifier(**params)
            model.fit(X, y)

            training_time = (datetime.now() - start_time).total_seconds()

            booster = model.get_booster()

            accuracy = self._evaluate(booster, X, y)

            if save:
                save_result = self.save_model(
                    model=booster,
                    accuracy=accuracy,
                    period=period,
                    coins=coins,
                    features=self.config.get("features", []),
                    training_samples=len(X),
                    set_active=True,
                    backup=True,
                    profile_name=profile_name or profile.get("name"),
                    strategy="full",
                )

                if not save_result.get("success"):
                    return save_result

                return {
                    "success": True,
                    "version": save_result["version"],
                    "model_id": save_result.get("model_id"),
                    "accuracy": accuracy,
                    "training_time": training_time,
                    "strategy_used": "full",
                    "profile_used": profile_name or profile.get("name"),
                    "samples": len(X),
                    "quota": quota_result,
                }
            else:
                self.current_model = booster
                return {
                    "success": True,
                    "accuracy": accuracy,
                    "training_time": training_time,
                    "strategy_used": "full",
                    "profile_used": profile_name or profile.get("name"),
                    "samples": len(X),
                    "saved": False,
                }

        except xgb.core.XGBoostError as e:
            logger.error(f"XGBoost error: {e}")
            self._stats["errors"] += 1
            return {"success": False, "error": f"XGBoost error: {str(e)}"}
        except Exception as e:
            logger.error(f"Full training error: {e}", exc_info=True)
            self._stats["errors"] += 1
            return {"success": False, "error": str(e)}

    # ============================================================
    # _train_incremental
    # ============================================================

    def _train_incremental(
        self,
        X: np.ndarray,
        y: np.ndarray,
        profile: Dict[str, Any],
        period: str,
        coins: Optional[List[str]],
        save: bool,
        profile_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        try:
            if self.current_model is None:
                return {
                    "success": False,
                    "error": "No existing model for incremental training",
                }

            old_accuracy = self._evaluate(self.current_model, X, y)

            hyperparams = profile["hyperparameters"].copy()
            hyperparams["learning_rate"] = min(
                hyperparams.get("learning_rate", 0.1),
                0.05,
            )

            params = {
                key: hyperparams[key]
                for key in [
                    "objective", "learning_rate", "max_depth",
                    "subsample", "colsample_bytree", "min_child_weight",
                    "gamma", "reg_alpha", "reg_lambda", "tree_method",
                ]
                if key in hyperparams
            }

            params.setdefault("objective", "binary:logistic")
            params.setdefault("tree_method", "hist")

            dtrain = xgb.DMatrix(X, label=y)

            start_time = datetime.now()

            new_model = xgb.train(
                params,
                dtrain,
                num_boost_round=hyperparams.get("n_estimators", 100),
                xgb_model=self.current_model,
            )

            training_time = (datetime.now() - start_time).total_seconds()

            new_accuracy = self._evaluate(new_model, X, y)
            improvement = new_accuracy - old_accuracy

            if improvement > 0.01:
                if save:
                    result = self.save_model(
                        model=new_model,
                        accuracy=new_accuracy,
                        period=period,
                        coins=coins,
                        training_samples=len(X),
                        set_active=True,
                        backup=True,
                        profile_name=profile_name or profile.get("name"),
                        strategy="incremental",
                    )

                    if not result.get("success"):
                        return result

                    return {
                        **result,
                        "old_accuracy": old_accuracy,
                        "improvement": improvement,
                        "strategy_used": "incremental",
                        "profile_used": profile_name or profile.get("name"),
                        "training_time": training_time,
                    }
                else:
                    self.current_model = new_model
                    return {
                        "success": True,
                        "accuracy": new_accuracy,
                        "old_accuracy": old_accuracy,
                        "improvement": improvement,
                        "strategy_used": "incremental",
                        "profile_used": profile_name or profile.get("name"),
                        "training_time": training_time,
                        "saved": False,
                    }
            else:
                return {
                    "success": True,
                    "message": "Improvement too small, keeping existing model",
                    "accuracy": old_accuracy,
                    "new_accuracy": new_accuracy,
                    "improvement": improvement,
                    "strategy_used": "incremental",
                    "profile_used": profile_name or profile.get("name"),
                    "training_time": training_time,
                    "saved": False,
                }

        except xgb.core.XGBoostError as e:
            logger.error(f"XGBoost incremental error: {e}")
            self._stats["errors"] += 1
            return {"success": False, "error": f"XGBoost error: {str(e)}"}
        except Exception as e:
            logger.error(f"Incremental training error: {e}", exc_info=True)
            self._stats["errors"] += 1
            return {"success": False, "error": str(e)}

    # ============================================================
    # _train_transfer
    # ============================================================

    def _train_transfer(
        self,
        X: np.ndarray,
        y: np.ndarray,
        profile: Dict[str, Any],
        period: str,
        coins: Optional[List[str]],
        save: bool,
        profile_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        try:
            if self.current_model is None:
                return {
                    "success": False,
                    "error": "No existing model for transfer learning",
                }

            old_accuracy = self._evaluate(self.current_model, X, y)

            hyperparams = profile["hyperparameters"].copy()
            hyperparams["learning_rate"] = 0.01

            params = {
                key: hyperparams[key]
                for key in [
                    "objective", "learning_rate", "max_depth",
                    "subsample", "colsample_bytree", "min_child_weight",
                    "gamma", "reg_alpha", "reg_lambda", "tree_method",
                ]
                if key in hyperparams
            }

            params.setdefault("objective", "binary:logistic")
            params.setdefault("tree_method", "hist")

            dtrain = xgb.DMatrix(X, label=y)

            start_time = datetime.now()

            new_model = xgb.train(
                params,
                dtrain,
                num_boost_round=hyperparams.get("n_estimators", 50),
                xgb_model=self.current_model,
            )

            training_time = (datetime.now() - start_time).total_seconds()

            new_accuracy = self._evaluate(new_model, X, y)
            improvement = new_accuracy - old_accuracy

            if save:
                result = self.save_model(
                    model=new_model,
                    accuracy=new_accuracy,
                    period=period,
                    coins=coins,
                    training_samples=len(X),
                    set_active=True,
                    backup=True,
                    profile_name=profile_name or profile.get("name"),
                    strategy="transfer",
                )

                if not result.get("success"):
                    return result

                return {
                    **result,
                    "old_accuracy": old_accuracy,
                    "improvement": improvement,
                    "strategy_used": "transfer",
                    "profile_used": profile_name or profile.get("name"),
                    "training_time": training_time,
                }
            else:
                self.current_model = new_model
                return {
                    "success": True,
                    "accuracy": new_accuracy,
                    "old_accuracy": old_accuracy,
                    "improvement": improvement,
                    "strategy_used": "transfer",
                    "profile_used": profile_name or profile.get("name"),
                    "training_time": training_time,
                    "saved": False,
                }

        except xgb.core.XGBoostError as e:
            logger.error(f"XGBoost transfer error: {e}")
            self._stats["errors"] += 1
            return {"success": False, "error": f"XGBoost error: {str(e)}"}
        except Exception as e:
            logger.error(f"Transfer learning error: {e}", exc_info=True)
            self._stats["errors"] += 1
            return {"success": False, "error": str(e)}

    # ============================================================
    # _train_fine_tune
    # ============================================================

    def _train_fine_tune(
        self,
        X: np.ndarray,
        y: np.ndarray,
        profile: Dict[str, Any],
        period: str,
        coins: Optional[List[str]],
        save: bool,
        profile_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        try:
            if self.current_model is None:
                return {
                    "success": False,
                    "error": "No existing model for fine-tuning",
                }

            max_samples = 500
            if len(X) > max_samples:
                indices = np.random.choice(len(X), max_samples, replace=False)
                X = X[indices]
                y = y[indices]

            old_accuracy = self._evaluate(self.current_model, X, y)

            hyperparams = profile["hyperparameters"].copy()
            hyperparams["learning_rate"] = 0.005
            hyperparams["n_estimators"] = min(
                hyperparams.get("n_estimators", 50),
                30,
            )

            params = {
                key: hyperparams[key]
                for key in [
                    "objective", "learning_rate", "max_depth",
                    "subsample", "colsample_bytree", "min_child_weight",
                    "gamma", "reg_alpha", "reg_lambda", "tree_method",
                ]
                if key in hyperparams
            }

            params.setdefault("objective", "binary:logistic")
            params.setdefault("tree_method", "hist")

            dtrain = xgb.DMatrix(X, label=y)

            start_time = datetime.now()

            new_model = xgb.train(
                params,
                dtrain,
                num_boost_round=hyperparams["n_estimators"],
                xgb_model=self.current_model,
            )

            training_time = (datetime.now() - start_time).total_seconds()

            new_accuracy = self._evaluate(new_model, X, y)
            improvement = new_accuracy - old_accuracy

            if save:
                result = self.save_model(
                    model=new_model,
                    accuracy=new_accuracy,
                    period=period,
                    coins=coins,
                    training_samples=len(X),
                    set_active=True,
                    backup=True,
                    profile_name=profile_name or profile.get("name"),
                    strategy="fine_tune",
                )

                if not result.get("success"):
                    return result

                return {
                    **result,
                    "old_accuracy": old_accuracy,
                    "improvement": improvement,
                    "strategy_used": "fine_tune",
                    "profile_used": profile_name or profile.get("name"),
                    "training_time": training_time,
                }
            else:
                self.current_model = new_model
                return {
                    "success": True,
                    "accuracy": new_accuracy,
                    "old_accuracy": old_accuracy,
                    "improvement": improvement,
                    "strategy_used": "fine_tune",
                    "profile_used": profile_name or profile.get("name"),
                    "training_time": training_time,
                    "saved": False,
                }

        except xgb.core.XGBoostError as e:
            logger.error(f"XGBoost fine-tune error: {e}")
            self._stats["errors"] += 1
            return {"success": False, "error": f"XGBoost error: {str(e)}"}
        except Exception as e:
            logger.error(f"Fine-tune error: {e}", exc_info=True)
            self._stats["errors"] += 1
            return {"success": False, "error": str(e)}

    # ============================================================
    # _train_ensemble
    # ============================================================

    def _train_ensemble(
        self,
        X: np.ndarray,
        y: np.ndarray,
        profile: Dict[str, Any],
        period: str,
        coins: Optional[List[str]],
        save: bool,
        profile_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        try:
            data_config = profile.get("data_config", {})
            versions = data_config.get("ensemble_versions", [])
            weights = data_config.get("ensemble_weights", [])

            if not versions or len(versions) < 2:
                return {
                    "success": False,
                    "error": "Ensemble needs at least 2 versions in data_config.ensemble_versions",
                }

            models = []
            for version in versions:
                model = self.repository.load_model(version)
                if model is None:
                    return {
                        "success": False,
                        "error": f"Could not load version '{version}'",
                    }
                models.append(model)

            if len(weights) != len(models):
                weights = [1.0 / len(models)] * len(models)

            ensemble = self._create_weighted_ensemble(models, weights)

            start_time = datetime.now()
            accuracy = self._evaluate(ensemble, X, y)
            training_time = (datetime.now() - start_time).total_seconds()

            if save:
                result = self.save_model(
                    model=ensemble,
                    accuracy=accuracy,
                    period=period,
                    coins=coins,
                    training_samples=len(X),
                    set_active=True,
                    backup=True,
                    profile_name=profile_name or profile.get("name"),
                    strategy="ensemble",
                    is_ensemble=True,
                )

                if not result.get("success"):
                    return result

                return {
                    **result,
                    "strategy_used": "ensemble",
                    "profile_used": profile_name or profile.get("name"),
                    "versions_used": versions,
                    "weights": weights,
                    "training_time": training_time,
                }
            else:
                self.current_model = ensemble
                return {
                    "success": True,
                    "accuracy": accuracy,
                    "strategy_used": "ensemble",
                    "profile_used": profile_name or profile.get("name"),
                    "versions_used": versions,
                    "weights": weights,
                    "training_time": training_time,
                    "saved": False,
                }

        except Exception as e:
            logger.error(f"Ensemble error: {e}", exc_info=True)
            self._stats["errors"] += 1
            return {"success": False, "error": str(e)}

    # ============================================================
    # Save Model
    # ============================================================

    def save_model(
        self,
        model: Any,
        accuracy: float,
        period: str = "1m",
        coins: Optional[List[str]] = None,
        features: Optional[List[str]] = None,
        training_samples: int = 0,
        version: Optional[str] = None,
        backup: bool = True,
        set_active: bool = True,
        profile_name: Optional[str] = None,
        strategy: str = "full",
        is_ensemble: bool = False,
    ) -> Dict[str, Any]:
        with self._lock:
            quota_check = self._check_quota_before_save(model)
            if not quota_check.get("can_save", True):
                self._stats["errors"] += 1
                return {
                    "success": False,
                    "error": "Quota exceeded",
                    "message": quota_check.get("message", "فضای دیتابیس کافی نیست"),
                    "quota": quota_check,
                }

            backup_done = False
            if backup and self.current_version and self.current_model:
                backup_done = self._backup_current_model()

            if version is None:
                version = self._generate_version()

            try:
                result = self.repository.save_model(
                    model=model,
                    accuracy=accuracy,
                    version=version,
                    period=period,
                    coins=coins,
                    features=features,
                    training_samples=training_samples,
                    is_active=set_active,
                )

                if not result.get("success"):
                    self._stats["errors"] += 1
                    return {
                        "success": False,
                        "error": result.get("error", "Save failed"),
                    }

                if set_active:
                    self.current_model = model
                    self.current_version = version
                    self._current_model_id = result.get("model_id")
                    self._stats["activations"] += 1

                self._stats["saves"] += 1

                self._delete_cache(self.CACHE_KEY_ACTIVE)
                self._delete_cache(self.CACHE_KEY_STATS)

                self._record_training_history(
                    model_id=result.get("model_id"),
                    accuracy=accuracy,
                    samples=training_samples,
                    profile_name=profile_name,
                    strategy=strategy,
                )

                logger.info(
                    f"Model saved: {version} "
                    f"(accuracy: {accuracy:.3f}, "
                    f"strategy: {strategy}, "
                    f"profile: {profile_name})"
                )

                return {
                    "success": True,
                    "version": version,
                    "model_id": result.get("model_id"),
                    "accuracy": accuracy,
                    "backup_done": backup_done,
                    "quota": quota_check,
                    "strategy": strategy,
                    "profile": profile_name,
                    "message": f"مدل {version} ذخیره شد",
                }

            except Exception as e:
                self._stats["errors"] += 1
                logger.error(f"Save model error: {e}", exc_info=True)
                return {"success": False, "error": str(e)}

    def _record_training_history(
        self,
        model_id: Optional[int],
        accuracy: float,
        samples: int,
        profile_name: Optional[str],
        strategy: str,
    ) -> None:
        try:
            if not self._ensure_db_connection():
                return

            reason = f"Profile: {profile_name}, Strategy: {strategy}"

            self.db.execute(
                """
                INSERT INTO model_training_history (
                    model_id, action, new_accuracy, samples_used,
                    reason, status, completed_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    model_id,
                    strategy,
                    accuracy,
                    samples,
                    reason,
                    "success",
                    datetime.now(),
                ),
            )
        except Exception as e:
            logger.warning(f"Could not record training history: {e}")

    # ============================================================
    # Backup & Quota
    # ============================================================

    def _backup_current_model(self) -> bool:
        if not self.current_model or not self.current_version:
            return False

        try:
            model_data = self.repository.export_model_file(self.current_version)

            if not model_data:
                return False

            if self.backup_db and self.backup_db.is_connected():
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
                        model_data,
                        self._get_current_accuracy(),
                        self._get_current_period(),
                        "auto_backup_before_override",
                    ),
                )

                self._stats["backups"] += 1
                logger.debug(f"Backup: {self.current_version}")
                return True

        except Exception as e:
            logger.warning(f"Backup failed: {e}")

        return False

    def _get_current_accuracy(self) -> float:
        try:
            if not self.current_version:
                return 0.0
            result = self.repository.db.execute(
                "SELECT accuracy FROM models WHERE version = %s",
                (self.current_version,),
            )
            return float(result[0]["accuracy"]) if result else 0.0
        except Exception:
            return 0.0

    def _get_current_period(self) -> str:
        try:
            if not self.current_version:
                return "1m"
            result = self.repository.db.execute(
                "SELECT period FROM models WHERE version = %s",
                (self.current_version,),
            )
            return result[0]["period"] if result else "1m"
        except Exception:
            return "1m"

    def _check_quota_before_save(self, model: Any) -> Dict[str, Any]:
        try:
            with tempfile.NamedTemporaryFile(suffix=".xgb", delete=True) as tmp:
                model.save_model(tmp.name, format="json")
                model_size_mb = os.path.getsize(tmp.name) / (1024 * 1024)

            quota_status = self.repository.db.check_quota()
            used_mb = quota_status.get("used_mb", 0)
            usable_mb = quota_status.get("usable_mb", 0)
            available_mb = usable_mb - used_mb

            can_save = available_mb > model_size_mb * 1.2

            return {
                "can_save": can_save,
                "model_size_mb": round(model_size_mb, 2),
                "used_mb": used_mb,
                "usable_mb": usable_mb,
                "available_mb": round(available_mb, 2),
                "status": quota_status.get("status", "unknown"),
                "message": (
                    f"فضا کافی است" if can_save
                    else f"فضا کافی نیست! نیاز: {model_size_mb:.2f} MB، "
                         f"موجود: {available_mb:.2f} MB"
                ),
            }
        except Exception as e:
            logger.warning(f"Quota check failed: {e}")
            return {"can_save": True, "error": str(e)}

    def _check_quota_before_training(self, profile: Dict[str, Any]) -> Dict[str, Any]:
        try:
            n_est = profile["hyperparameters"].get("n_estimators", 100)
            depth = profile["hyperparameters"].get("max_depth", 5)

            estimated_mb = (n_est * 50 * depth) / (1024 * 1024) * 10

            quota_status = self.repository.db.check_quota()
            available_mb = (
                quota_status.get("usable_mb", 0)
                - quota_status.get("used_mb", 0)
            )

            return {
                "can_proceed": available_mb > estimated_mb * 1.5,
                "estimated_model_size_mb": round(estimated_mb, 2),
                "available_mb": round(available_mb, 2),
            }
        except Exception as e:
            return {"can_proceed": True, "error": str(e)}

    # ============================================================
    # Predict
    # ============================================================

    def predict(self, features: np.ndarray) -> float:
        if self.current_model is None:
            raise ValueError("هیچ مدلی بارگذاری نشده است")

        try:
            dmatrix = xgb.DMatrix(features.reshape(1, -1))
            prediction = self.current_model.predict(dmatrix)
            self._stats["predictions"] += 1
            return float(prediction[0])
        except Exception as e:
            self._stats["errors"] += 1
            logger.error(f"Prediction error: {e}")
            raise

    def predict_batch(self, features: np.ndarray) -> np.ndarray:
        if self.current_model is None:
            raise ValueError("هیچ مدلی بارگذاری نشده است")

        try:
            dmatrix = xgb.DMatrix(features)
            predictions = self.current_model.predict(dmatrix)
            self._stats["predictions"] += len(features)
            return np.array(predictions)
        except Exception as e:
            self._stats["errors"] += 1
            logger.error(f"Batch prediction error: {e}")
            raise

    # ============================================================
    # Load & Get
    # ============================================================

    def _load_active_model(self) -> bool:
        cached_model = self._get_from_cache(self.CACHE_KEY_ACTIVE)

        if cached_model and isinstance(cached_model, dict):
            version = cached_model.get("version")
            if version:
                logger.debug(f"Loading from cache: {version}")
                return self._load_model_by_version(version, from_cache=True)

        try:
            active = self.repository.load_active_model()

            if not active:
                logger.info("No active model (DEMO mode)")
                return False

            self.current_model = active["model"]
            self.current_version = active["version"]
            self._current_model_id = active.get("id")
            self._stats["loads"] += 1

            self._set_cache(self.CACHE_KEY_ACTIVE, {
                "version": self.current_version,
                "accuracy": active.get("accuracy", 0),
            }, self.CACHE_TTL_ACTIVE)

            logger.info(f"Loaded model: {self.current_version}")
            return True

        except Exception as e:
            self._stats["errors"] += 1
            logger.error(f"Load active model error: {e}", exc_info=True)
            return False

    def _load_model_by_version(self, version: str, from_cache: bool = False) -> bool:
        try:
            model = self.repository.load_model(version)

            if model is None:
                if from_cache:
                    self._delete_cache(self.CACHE_KEY_ACTIVE)
                return False

            self.current_model = model
            self.current_version = version
            self._stats["loads"] += 1
            return True

        except Exception as e:
            self._stats["errors"] += 1
            logger.error(f"Load model error: {e}")
            return False

    def get_model_by_version(self, version: str) -> Optional[xgb.Booster]:
        try:
            return self.repository.load_model(version)
        except Exception as e:
            logger.error(f"Get model error: {e}")
            return None

    def get_version_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        try:
            return self.repository.get_version_history(limit=limit)
        except Exception as e:
            logger.error(f"Get history error: {e}")
            return []

    def get_all_versions(self) -> List[Dict[str, Any]]:
        try:
            return self.repository.find_all(limit=1000)
        except Exception as e:
            logger.error(f"Get all versions error: {e}")
            return []

    # ============================================================
    # Activation & Cleanup
    # ============================================================

    def set_active(self, version: str) -> bool:
        try:
            success = self.repository.set_active(version)

            if success:
                self._load_model_by_version(version)
                self._stats["activations"] += 1
                self._delete_cache(self.CACHE_KEY_ACTIVE)
                logger.info(f"Model {version} activated")

            return success

        except Exception as e:
            self._stats["errors"] += 1
            logger.error(f"Set active error: {e}")
            return False

    def delete_model(self, version: str) -> bool:
        try:
            success = self.repository.delete_by_version(version)

            if success:
                self._stats["deletions"] += 1
                self._delete_cache(self.CACHE_KEY_ACTIVE)
                self._delete_cache(self.CACHE_KEY_STATS)

            return success

        except Exception as e:
            logger.error(f"Delete error: {e}")
            return False

    def cleanup_old_versions(self, keep_last_n: int = 10) -> int:
        try:
            count = self.repository.cleanup_old_versions(keep_last_n=keep_last_n)

            if count > 0:
                self._stats["deletions"] += count
                self._delete_cache(self.CACHE_KEY_STATS)

            return count

        except Exception as e:
            logger.error(f"Cleanup error: {e}")
            return 0

    def compare_versions(self, v1: str, v2: str) -> Optional[Dict[str, Any]]:
        try:
            return self.repository.compare_versions(v1, v2)
        except Exception as e:
            logger.error(f"Compare error: {e}")
            return None

    # ============================================================
    # Stats & Reports
    # ============================================================

    def get_stats(self) -> Dict[str, Any]:
        cached = self._get_from_cache(self.CACHE_KEY_STATS)
        if cached and isinstance(cached, dict):
            cached["runtime_stats"] = dict(self._stats)
            cached["active_profile"] = self._active_profile.get("name")
            return cached

        try:
            repo_stats = self.repository.get_stats()
            quota = self._get_quota_summary()

            result = {
                "loaded": self.current_model is not None,
                "version": self.current_version or "N/A",
                "model_id": self._current_model_id,
                "db_connected": self.db is not None and self.db.is_connected(),
                "cache_connected": self.cache is not None and self.cache.is_connected(),
                "total_versions": repo_stats.get("total_models", 0),
                "avg_accuracy": repo_stats.get("avg_accuracy", 0),
                "max_accuracy": repo_stats.get("max_accuracy", 0),
                "active_model": repo_stats.get("active_model"),
                "by_period": repo_stats.get("by_period", []),
                "quota": quota,
                "active_profile": self._active_profile.get("name", "default"),
                "active_strategy": self._active_profile.get("learning_strategy", "full"),
                "runtime_stats": dict(self._stats),
                "timestamp": datetime.now().isoformat(),
            }

            self._set_cache(self.CACHE_KEY_STATS, result, self.CACHE_TTL_STATS)
            return result

        except Exception as e:
            logger.error(f"Stats error: {e}")
            return {
                "loaded": self.current_model is not None,
                "version": self.current_version or "N/A",
                "error": str(e),
                "runtime_stats": dict(self._stats),
            }

    def get_quota_status(self) -> Dict[str, Any]:
        return self._get_quota_summary()

    def _get_quota_summary(self) -> Dict[str, Any]:
        try:
            used_mb = self.repository.db._calculate_used_size()
            return get_quota_status("primary", used_mb)
        except Exception as e:
            return {"error": str(e)}

    def get_repository_stats(self) -> Dict[str, Any]:
        try:
            return self.repository.get_stats()
        except Exception as e:
            return {}

    def get_report_data(self, version: str) -> Dict[str, Any]:
        try:
            model_info = self.repository.find_by_version(version)
            if not model_info:
                return {}

            history = self.repository.get_version_history(limit=5)
            feature_importance = self._get_feature_importance(version)

            return {
                "model": {
                    "version": model_info.get("version", "N/A"),
                    "accuracy": model_info.get("accuracy", 0),
                    "training_date": model_info.get("training_date"),
                    "period": model_info.get("period", "1m"),
                    "coins": model_info.get("coins", []),
                    "features_count": len(model_info.get("features", [])),
                    "is_active": model_info.get("is_active", False),
                    "is_ensemble": model_info.get("is_ensemble", False),
                    "training_samples": model_info.get("training_samples", 0),
                },
                "feature_importance": feature_importance,
                "history": history,
                "hyperparameters": self._active_profile.get(
                    "hyperparameters",
                    DEFAULT_HYPERPARAMETERS,
                ),
                "active_profile": self._active_profile.get("name"),
                "active_strategy": self._active_profile.get("learning_strategy"),
                "stats": {
                    "total_trainings": len(history),
                    "best_accuracy": max(
                        [h.get("accuracy", 0) for h in history] or [0]
                    ),
                    "latest_improvement": self._calculate_improvement(history),
                },
                "quota": self.get_quota_status(),
            }

        except Exception as e:
            logger.error(f"Report error: {e}", exc_info=True)
            return {}

    def _get_feature_importance(self, version: str) -> List[Dict[str, Any]]:
        try:
            if not self.current_model or self.current_version != version:
                model = self.repository.load_model(version)
                if not model:
                    return []
            else:
                model = self.current_model

            if hasattr(model, "get_score"):
                importance = model.get_score(importance_type="weight")
            else:
                return []

            if not importance:
                return []

            total = sum(importance.values()) or 1

            return [
                {
                    "feature": k,
                    "importance": v,
                    "percentage": round((v / total) * 100, 2),
                }
                for k, v in sorted(
                    importance.items(),
                    key=lambda x: x[1],
                    reverse=True,
                )
            ][:15]

        except Exception as e:
            logger.warning(f"Feature importance error: {e}")
            return []

    def _calculate_improvement(self, history: List[Dict[str, Any]]) -> Optional[float]:
        if len(history) < 2:
            return None

        latest = history[0].get("accuracy", 0)
        previous = history[1].get("accuracy", 0)

        if previous == 0:
            return None

        return round(((latest - previous) / previous) * 100, 2)

    def get_model_file(self, version: str) -> Optional[bytes]:
        try:
            return self.repository.export_model_file(version)
        except Exception as e:
            logger.error(f"Get model file error: {e}")
            return None

    # ============================================================
    # Incremental Training (API قدیمی)
    # ============================================================

    def incremental_train(
        self,
        features: np.ndarray,
        labels: np.ndarray,
    ) -> Dict[str, Any]:
        if self.current_model is None:
            return {
                "success": False,
                "message": "مدلی برای آموزش افزایشی وجود ندارد",
            }

        try:
            old_accuracy = self._evaluate(self.current_model, features, labels)

            params = {
                "objective": "binary:logistic",
                "eval_metric": "logloss",
                "learning_rate": 0.05,
                "max_depth": 3,
                "subsample": 0.7,
                "colsample_bytree": 0.7,
                "tree_method": "hist",
            }

            dtrain = xgb.DMatrix(features, label=labels)
            new_model = xgb.train(
                params,
                dtrain,
                num_boost_round=10,
                xgb_model=self.current_model,
            )

            new_accuracy = self._evaluate(new_model, features, labels)
            improvement = new_accuracy - old_accuracy

            if improvement > 0.02:
                return self.save_model(
                    new_model, new_accuracy,
                    set_active=True, backup=True,
                    strategy="incremental",
                )
            elif improvement > 0.005:
                combined = self._create_weighted_ensemble(
                    [self.current_model, new_model],
                    [0.7, 0.3],
                )
                combined_accuracy = self._evaluate(combined, features, labels)
                return self.save_model(
                    combined, combined_accuracy,
                    set_active=True, backup=True,
                    strategy="ensemble",
                    is_ensemble=True,
                )
            else:
                return {
                    "success": True,
                    "message": "مدل قبلی حفظ شد (بهبود کافی نبود)",
                    "accuracy": old_accuracy,
                    "improvement": improvement,
                }

        except Exception as e:
            logger.error(f"Incremental training error: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    # ============================================================
    # Helpers
    # ============================================================

    def _evaluate(
        self,
        model: Any,
        features: np.ndarray,
        labels: np.ndarray,
    ) -> float:
        try:
            if isinstance(model, xgb.Booster):
                dtest = xgb.DMatrix(features)
                predictions = model.predict(dtest)
            elif hasattr(model, "predict_proba"):
                predictions = model.predict_proba(features)[:, 1]
            else:
                predictions = model.predict(features)

            predictions = np.array(predictions).flatten()

            pred_classes = (predictions > 0.5).astype(int)
            accuracy = np.mean(pred_classes == labels)
            return float(accuracy)

        except Exception as e:
            logger.error(f"Evaluation error: {e}")
            return 0.0

    def _create_weighted_ensemble(
        self,
        models: List[Any],
        weights: List[float],
    ) -> Any:
        class WeightedEnsemble:
            def __init__(self, models, weights):
                self.models = models
                self.weights = weights
                self._is_ensemble = True

            def predict(self, data):
                predictions = []
                for model, weight in zip(self.models, self.weights):
                    if isinstance(model, xgb.Booster):
                        dmatrix = xgb.DMatrix(data) if not isinstance(data, xgb.DMatrix) else data
                        pred = model.predict(dmatrix)
                    elif hasattr(model, "predict"):
                        pred = model.predict(data)
                    else:
                        pred = model.predict(data)

                    predictions.append(np.array(pred).flatten() * weight)

                return np.sum(predictions, axis=0)

            def get_score(self, importance_type="weight"):
                for model in self.models:
                    if isinstance(model, xgb.Booster):
                        return model.get_score(importance_type=importance_type)
                return {}

            def save_model(self, path, format="json"):
                for model in self.models:
                    if isinstance(model, xgb.Booster):
                        model.save_model(path, format=format)
                        return
                raise ValueError("No XGBoost model in ensemble")

        return WeightedEnsemble(models, weights)

    def _generate_version(self) -> str:
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

    def _get_model_features(self, model: Any) -> List[str]:
        return self.config.get("features", [
            "return_1", "return_3", "return_5", "return_10",
            "sma_5", "sma_10", "sma_20", "volatility",
            "fear_greed", "trend_5", "trend_10", "trend_20", "r2"
        ])

    def _ensure_db_connection(self) -> bool:
        if not self.db or not self.db.is_connected():
            try:
                self.db = get_primary()
                if self.db and self.db.is_connected():
                    return True
                return False
            except Exception as e:
                logger.error(f"DB reconnect error: {e}")
                return False
        return True

    # ============================================================
    # Profile Helpers
    # ============================================================

    def _get_default_profile(self) -> Dict[str, Any]:
        preset = TRAINING_PRESETS[self.DEFAULT_PROFILE_NAME]
        return {
            "name": preset["name"],
            "description": preset["description"],
            "icon": preset["icon"],
            "color": preset["color"],
            "learning_strategy": "full",
            "hyperparameters": preset["hyperparameters"].copy(),
            "data_config": {},
            "is_preset": True,
        }

    def _load_active_profile(self) -> None:
        cached = self._get_from_cache(self.CACHE_KEY_ACTIVE_PROFILE)
        if cached and isinstance(cached, dict):
            self._active_profile = cached
            logger.debug(f"Loaded active profile: {cached.get('name')}")

    # ============================================================
    # Cache Helpers
    # ============================================================

    def _get_from_cache(self, key: str) -> Optional[Any]:
        if not self.cache or not self.cache.is_connected():
            return None
        try:
            return self.cache.get(key)
        except Exception:
            return None

    def _set_cache(self, key: str, value: Any, ttl: int = 300) -> bool:
        if not self.cache or not self.cache.is_connected():
            return False
        try:
            return self.cache.set(key, value, ttl=ttl)
        except Exception:
            return False

    def _delete_cache(self, key: str) -> bool:
        if not self.cache or not self.cache.is_connected():
            return False
        try:
            return self.cache.delete(key)
        except Exception:
            return False
