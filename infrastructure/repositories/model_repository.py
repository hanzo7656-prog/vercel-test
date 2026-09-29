# infrastructure/repositories/model_repository.py
# ============================================================
# Repository: Model - نسخه ۴.۰
# Polymorphic (XGBoost → Rule Config) + Transaction + Cache
# ============================================================
# 
# تغییرات نسخه ۴.۰:
#   - پشتیبانی از model_type (rule_config / xgboost)
#   - save_rule_config و load_rule_config اضافه شد
#   - _detect_model_type برای تشخیص خودکار
#   - حفظ سازگاری با XGBoost (برای rollback)
# ============================================================

import json
import logging
import tempfile
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple, Union
from datetime import datetime, timedelta

from domain.interfaces.repository import Repository
from infrastructure.database import (
    get_primary,
    get_cache,
    primary_transaction,
)

logger = logging.getLogger(__name__)


# ============================================================
# Constants
# ============================================================

MODEL_TYPE_RULE_CONFIG = "rule_config"
MODEL_TYPE_XGBOOST = "xgboost"


class ModelRepository(Repository):
    """
    Repository برای مدیریت مدل‌ها (Rule Config + XGBoost)
    
    ویژگی‌ها:
        - Polymorphic: پشتیبانی از دو نوع مدل
        - Transaction support
        - Bulk operations
        - Redis Cache برای مدل‌های فعال
        - Version comparison
        - Auto-cleanup نسخه‌های قدیمی
    """
    
    # ============================================================
    # Constants
    # ============================================================
    
    TABLE_NAME = "models"
    HISTORY_TABLE = "model_training_history"
    CACHE_PREFIX = "model:active"
    CACHE_TTL = 300  # ۵ دقیقه
    MODELS_DIR = Path("models/")
    
    # ============================================================
    # Init
    # ============================================================
    
    def __init__(self) -> None:
        self._db = None
        self._cache = None
        self.MODELS_DIR.mkdir(parents=True, exist_ok=True)
        
        logger.info("✅ ModelRepository v4.0 initialized")
    
    # ============================================================
    # Lazy properties
    # ============================================================
    
    @property
    def db(self):
        """دریافت دیتابیس primary"""
        if self._db is None or not self._db.is_connected():
            self._db = get_primary()
        return self._db
    
    @property
    def cache(self):
        """دریافت cache"""
        if self._cache is None or not self._cache.is_connected():
            self._cache = get_cache()
        return self._cache
    
    def _ensure_db(self) -> bool:
        """اطمینان از اتصال دیتابیس"""
        if self._db is None or not self._db.is_connected():
            self._db = get_primary()
        
        return self._db is not None and self._db.is_connected()
    
    def _ensure_model_type_column(self) -> None:
        """
        اطمینان از وجود ستون model_type
        
        این migration رو در runtime انجام می‌ده
        (بدون نیاز به Alembic)
        """
        if not self._ensure_db():
            return
        
        try:
            self.db.execute(
                """
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'models'
                        AND column_name = 'model_type'
                    ) THEN
                        ALTER TABLE models
                        ADD COLUMN model_type VARCHAR(50)
                        DEFAULT 'xgboost';
                    END IF;
                END $$;
                """
            )
        except Exception as e:
            logger.debug(f"model_type column check: {e}")
    
    # ============================================================
    # Cache helpers
    # ============================================================
    
    def _get_active_model_cache_key(self) -> str:
        """کلید cache برای مدل فعال"""
        return f"{self.CACHE_PREFIX}:current"
    
    def _get_version_cache_key(self, version: str) -> str:
        """کلید cache برای نسخه خاص"""
        return f"{self.CACHE_PREFIX}:version:{version}"
    
    def _invalidate_cache(self) -> None:
        """پاک کردن cache مدل"""
        try:
            if self.cache and self.cache.is_connected():
                keys = self.cache.scan_keys(f"{self.CACHE_PREFIX}:*")
                if keys:
                    self.cache.delete_many(keys)
                    logger.debug(f"✅ Invalidated {len(keys)} cache keys")
        except Exception as e:
            logger.warning(f"⚠️ Cache invalidation error: {e}")
    
    # ============================================================
    # SAVE: Rule Config (جدید - اصلی)
    # ============================================================
    
    def save_rule_config(
        self,
        config: Dict[str, Any],
        version: str,
        accuracy: float = 0.0,
        coins: Optional[List[str]] = None,
        training_samples: int = 0,
        is_active: bool = True,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        ذخیره یک Rule Config به‌عنوان مدل جدید
        
        Args:
            config: دیکشنری کامل config
            version: نسخه (مثلاً v2026.09.29_1430)
            accuracy: دقت (بعد از backtest)
            coins: لیست ارزها
            training_samples: تعداد نمونه‌ها (۰ برای Rule Config)
            is_active: فعال باشه؟
            metadata: اطلاعات اضافی
        
        Returns:
            {success, model_id, version, accuracy}
        """
        if not self._ensure_db():
            return {"success": False, "error": "Database not connected"}
        
        self._ensure_model_type_column()
        
        try:
            # Serialize config
            config_json = json.dumps(config, ensure_ascii=False)
            
            with primary_transaction() as db:
                # درج
                query = """
                    INSERT INTO models (
                        version, model_data, accuracy, training_samples,
                        period, coins, features, is_active, created_at,
                        model_type
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                    RETURNING id, version, accuracy, created_at
                """
                
                result = db.execute(query, (
                    version,
                    config_json.encode("utf-8"),  # به‌عنوان bytes برای سازگاری
                    accuracy,
                    training_samples,
                    "rule_config",
                    coins or [],
                    list(config.get("rules", {}).keys()),
                    is_active,
                    datetime.now(),
                    MODEL_TYPE_RULE_CONFIG,
                ))
                
                if not result:
                    raise RuntimeError("Insert returned no result")
                
                model_id = result[0]["id"]
                
                # غیرفعال‌سازی قبلی‌ها
                if is_active:
                    db.execute(
                        "UPDATE models SET is_active = FALSE WHERE id != %s",
                        (model_id,),
                    )
                
                # ثبت در تاریخچه
                db.execute(
                    """
                    INSERT INTO model_training_history
                    (model_id, action, new_accuracy, samples_used, created_at)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (model_id, "save_rule_config", accuracy, training_samples, datetime.now()),
                )
            
            self._invalidate_cache()
            
            logger.info(
                f"✅ Rule config saved: version={version}, "
                f"accuracy={accuracy:.3f}, id={model_id}"
            )
            
            return {
                "success": True,
                "model_id": model_id,
                "version": version,
                "accuracy": accuracy,
                "model_type": MODEL_TYPE_RULE_CONFIG,
                "is_active": is_active,
            }
        
        except Exception as e:
            logger.error(f"❌ Save rule config error: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
    
    def load_rule_config(self, version: str) -> Optional[Dict[str, Any]]:
        """
        بارگذاری یک Rule Config با نسخه
        
        Returns:
            دیکشنری config یا None
        """
        if not self._ensure_db():
            return None
        
        try:
            result = self.db.execute(
                """
                SELECT model_data, model_type
                FROM models
                WHERE version = %s
                """,
                (version,),
            )
            
            if not result:
                logger.warning(f"⚠️ Rule config '{version}' not found")
                return None
            
            row = result[0]
            
            # اگه XGBoost باشه، رد کن
            model_type = row.get("model_type", MODEL_TYPE_XGBOOST)
            if model_type != MODEL_TYPE_RULE_CONFIG:
                logger.warning(
                    f"⚠️ Version '{version}' is {model_type}, not rule_config"
                )
                return None
            
            # Decode
            model_data = row["model_data"]
            if isinstance(model_data, bytes):
                model_data = model_data.decode("utf-8")
            
            config = json.loads(model_data)
            return config
        
        except Exception as e:
            logger.error(f"❌ Load rule config error: {e}", exc_info=True)
            return None
    
    def load_active_rule_config(self) -> Optional[Dict[str, Any]]:
        """
        بارگذاری آخرین Rule Config فعال
        
        Returns:
            {config, version, accuracy, ...} یا None
        """
        if not self._ensure_db():
            return None
        
        try:
            # از cache
            cache_key = self._get_active_model_cache_key()
            if self.cache and self.cache.is_connected():
                cached = self.cache.get(cache_key)
                if cached and isinstance(cached, dict):
                    version = cached.get("version")
                    if version:
                        config = self.load_rule_config(version)
                        if config:
                            return {
                                "config": config,
                                "version": version,
                                "accuracy": cached.get("accuracy", 0.0),
                                "model_type": MODEL_TYPE_RULE_CONFIG,
                            }
            
            # از DB
            result = self.db.execute(
                """
                SELECT id, version, accuracy, model_data, model_type
                FROM models
                WHERE is_active = TRUE
                  AND model_type = %s
                ORDER BY id DESC
                LIMIT 1
                """,
                (MODEL_TYPE_RULE_CONFIG,),
            )
            
            if not result:
                return None
            
            row = result[0]
            version = row["version"]
            
            # Decode
            model_data = row["model_data"]
            if isinstance(model_data, bytes):
                model_data = model_data.decode("utf-8")
            
            config = json.loads(model_data)
            
            # کش
            if self.cache and self.cache.is_connected():
                self.cache.set(
                    cache_key,
                    {
                        "version": version,
                        "accuracy": row["accuracy"],
                        "model_type": MODEL_TYPE_RULE_CONFIG,
                    },
                    ttl=self.CACHE_TTL,
                )
            
            return {
                "config": config,
                "version": version,
                "accuracy": row["accuracy"],
                "model_id": row["id"],
                "model_type": MODEL_TYPE_RULE_CONFIG,
            }
        
        except Exception as e:
            logger.error(f"❌ Load active rule config error: {e}", exc_info=True)
            return None
    
    # ============================================================
    # SAVE: Legacy XGBoost (نگه‌داشته برای rollback)
    # ============================================================
    
    def save_model(
        self,
        model: Any,
        accuracy: float,
        version: str,
        period: str = "1m",
        coins: Optional[List[str]] = None,
        features: Optional[List[str]] = None,
        training_samples: int = 0,
        is_active: bool = True,
    ) -> Dict[str, Any]:
        """
        ذخیره مدل XGBoost (legacy — نگه‌داشته برای rollback)
        
        برای Rule Config، از save_rule_config استفاده کن.
        """
        if not self._ensure_db():
            return {"success": False, "error": "Database not connected"}
        
        self._ensure_model_type_column()
        
        temp_path: Optional[Path] = None
        
        try:
            # تبدیل مدل به binary
            temp_path = self.MODELS_DIR / f"temp_{version}.xgb"
            model.save_model(str(temp_path), format="json")
            
            with open(temp_path, "rb") as f:
                model_data: bytes = f.read()
            
            coins = coins or ["bitcoin", "ethereum"]
            features = features or []
            
            with primary_transaction() as db:
                query = """
                    INSERT INTO models (
                        version, model_data, accuracy, training_samples,
                        period, coins, features, is_active, created_at,
                        model_type
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                    RETURNING id, version, accuracy, created_at
                """
                
                result = db.execute(query, (
                    version,
                    model_data,
                    accuracy,
                    training_samples,
                    period,
                    coins,
                    features,
                    is_active,
                    datetime.now(),
                    MODEL_TYPE_XGBOOST,
                ))
                
                if not result:
                    raise RuntimeError("Insert returned no result")
                
                model_id = result[0]["id"]
                
                if is_active:
                    db.execute(
                        "UPDATE models SET is_active = FALSE WHERE id != %s",
                        (model_id,),
                    )
                
                db.execute(
                    """
                    INSERT INTO model_training_history
                    (model_id, action, new_accuracy, samples_used, created_at)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (model_id, "train", accuracy, training_samples, datetime.now()),
                )
            
            self._invalidate_cache()
            
            logger.info(
                f"✅ XGBoost model saved: version={version}, "
                f"accuracy={accuracy:.3f}"
            )
            
            return {
                "success": True,
                "model_id": model_id,
                "version": version,
                "accuracy": accuracy,
                "model_type": MODEL_TYPE_XGBOOST,
                "is_active": is_active,
            }
        
        except Exception as e:
            logger.error(f"❌ Save XGBoost model error: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
        
        finally:
            if temp_path and temp_path.exists():
                try:
                    temp_path.unlink()
                except Exception:
                    pass
    
    def load_model(self, version: str) -> Optional[Any]:
        """
        بارگذاری مدل XGBoost (legacy)
        
        برای Rule Config از load_rule_config استفاده کن.
        """
        if not self._ensure_db():
            return None
        
        try:
            import xgboost as xgb
        except ImportError:
            logger.error("❌ XGBoost not installed")
            return None
        
        temp_path: Optional[Path] = None
        
        try:
            result = self.db.execute(
                """
                SELECT model_data, model_type
                FROM models
                WHERE version = %s
                """,
                (version,),
            )
            
            if not result:
                logger.warning(f"⚠️ Model '{version}' not found")
                return None
            
            row = result[0]
            model_type = row.get("model_type", MODEL_TYPE_XGBOOST)
            
            if model_type != MODEL_TYPE_XGBOOST:
                logger.warning(
                    f"⚠️ Version '{version}' is {model_type}, not xgboost"
                )
                return None
            
            model_data: bytes = row["model_data"]
            
            temp_path = self.MODELS_DIR / f"load_{version}.xgb"
            with open(temp_path, "wb") as f:
                f.write(model_data)
            
            model = xgb.Booster()
            model.load_model(str(temp_path))
            
            return model
        
        except Exception as e:
            logger.error(f"❌ Load XGBoost error: {e}")
            return None
        
        finally:
            if temp_path and temp_path.exists():
                try:
                    temp_path.unlink()
                except Exception:
                    pass
    
    # ============================================================
    # HISTORY & VERSIONS
    # ============================================================
    
    def get_version_history(
        self,
        limit: int = 10,
        include_inactive: bool = True,
        model_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        دریافت تاریخچه نسخه‌ها
        
        Args:
            limit: تعداد
            include_inactive: شامل غیرفعال‌ها
            model_type: فیلتر بر اساس نوع (اختیاری)
        """
        if not self._ensure_db():
            return []
        
        self._ensure_model_type_column()
        
        try:
            conditions = []
            params = []
            
            if not include_inactive:
                conditions.append("is_active = TRUE")
            
            if model_type:
                conditions.append("model_type = %s")
                params.append(model_type)
            
            where_clause = " AND ".join(conditions) if conditions else "1=1"
            
            query = f"""
                SELECT id, version, accuracy, period, coins, features,
                       training_samples, training_date, is_active,
                       is_ensemble, created_at, model_type
                FROM models
                WHERE {where_clause}
                ORDER BY id DESC
                LIMIT %s
            """
            
            params.append(limit)
            result = self.db.execute(query, tuple(params))
            
            return result or []
        
        except Exception as e:
            logger.error(f"❌ Get version history error: {e}")
            return []
    
    def get_best_version(
        self,
        metric: str = "accuracy",
        model_type: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """دریافت بهترین نسخه"""
        if not self._ensure_db():
            return None
        
        try:
            if model_type:
                result = self.db.execute(
                    """
                    SELECT id, version, accuracy, period, training_date, model_type
                    FROM models
                    WHERE model_type = %s
                    ORDER BY accuracy DESC
                    LIMIT 1
                    """,
                    (model_type,),
                )
            else:
                result = self.db.execute(
                    """
                    SELECT id, version, accuracy, period, training_date, model_type
                    FROM models
                    ORDER BY accuracy DESC
                    LIMIT 1
                    """
                )
            
            return result[0] if result else None
        
        except Exception as e:
            logger.error(f"❌ Get best version error: {e}")
            return None
    
    def get_version_count(self) -> int:
        """تعداد نسخه‌ها"""
        if not self._ensure_db():
            return 0
        
        try:
            result = self.db.execute("SELECT COUNT(*) as count FROM models")
            return result[0]["count"] if result else 0
        except Exception as e:
            logger.error(f"❌ Get version count error: {e}")
            return 0
    
    def compare_versions(
        self,
        version1: str,
        version2: str,
    ) -> Optional[Dict[str, Any]]:
        """مقایسه دو نسخه"""
        if not self._ensure_db():
            return None
        
        try:
            result = self.db.execute(
                """
                SELECT version, accuracy, training_samples, period,
                       training_date, model_type
                FROM models
                WHERE version IN (%s, %s)
                """,
                (version1, version2),
            )
            
            if len(result) != 2:
                return None
            
            v1_data = next((r for r in result if r["version"] == version1), None)
            v2_data = next((r for r in result if r["version"] == version2), None)
            
            if not v1_data or not v2_data:
                return None
            
            return {
                "version1": v1_data,
                "version2": v2_data,
                "accuracy_diff": v1_data["accuracy"] - v2_data["accuracy"],
                "winner": (
                    version1 if v1_data["accuracy"] > v2_data["accuracy"]
                    else version2
                ),
            }
        
        except Exception as e:
            logger.error(f"❌ Compare versions error: {e}")
            return None
    
    # ============================================================
    # ACTIVATION
    # ============================================================
    
    def set_active(self, version: str) -> bool:
        """تنظیم یک نسخه به‌عنوان فعال"""
        if not self._ensure_db():
            return False
        
        try:
            with primary_transaction() as db:
                db.execute("UPDATE models SET is_active = FALSE")
                db.execute(
                    "UPDATE models SET is_active = TRUE WHERE version = %s",
                    (version,),
                )
            
            self._invalidate_cache()
            logger.info(f"✅ Model {version} activated")
            return True
        
        except Exception as e:
            logger.error(f"❌ Set active error: {e}")
            return False
    
    def deactivate(self, version: str) -> bool:
        """غیرفعال کردن یک نسخه"""
        if not self._ensure_db():
            return False
        
        try:
            self.db.execute(
                "UPDATE models SET is_active = FALSE WHERE version = %s",
                (version,),
            )
            self._invalidate_cache()
            return True
        except Exception as e:
            logger.error(f"❌ Deactivate error: {e}")
            return False
    
    # ============================================================
    # DELETE & CLEANUP
    # ============================================================
    
    def delete(self, entity_id: int) -> bool:
        """حذف مدل با ID"""
        if not self._ensure_db():
            return False
        
        try:
            check = self.db.execute(
                "SELECT is_active FROM models WHERE id = %s",
                (entity_id,),
            )
            
            if check and check[0].get("is_active", False):
                logger.warning(f"⚠️ Cannot delete active model {entity_id}")
                return False
            
            self.db.execute("DELETE FROM models WHERE id = %s", (entity_id,))
            self._invalidate_cache()
            
            logger.info(f"✅ Model {entity_id} deleted")
            return True
        
        except Exception as e:
            logger.error(f"❌ Delete error: {e}")
            return False
    
    def delete_by_version(self, version: str) -> bool:
        """حذف با نسخه"""
        if not self._ensure_db():
            return False
        
        try:
            check = self.db.execute(
                "SELECT is_active FROM models WHERE version = %s",
                (version,),
            )
            
            if check and check[0].get("is_active", False):
                logger.warning(f"⚠️ Cannot delete active model {version}")
                return False
            
            self.db.execute(
                "DELETE FROM models WHERE version = %s", (version,)
            )
            self._invalidate_cache()
            logger.info(f"✅ Model {version} deleted")
            return True
        
        except Exception as e:
            logger.error(f"❌ Delete by version error: {e}")
            return False
    
    def cleanup_old_versions(self, keep_last_n: int = 10) -> int:
        """پاک کردن نسخه‌های قدیمی"""
        if not self._ensure_db():
            return 0
        
        try:
            result = self.db.execute(
                """
                WITH recent AS (
                    SELECT id FROM models
                    ORDER BY id DESC
                    LIMIT %s
                )
                SELECT id, version FROM models
                WHERE is_active = FALSE
                  AND id NOT IN (SELECT id FROM recent)
                """,
                (keep_last_n,),
            )
            
            if not result:
                return 0
            
            ids_to_delete = [r["id"] for r in result]
            
            with primary_transaction() as db:
                db.execute(
                    "DELETE FROM models WHERE id = ANY(%s)",
                    (ids_to_delete,),
                )
            
            self._invalidate_cache()
            
            logger.info(f"✅ Cleaned up {len(ids_to_delete)} old versions")
            return len(ids_to_delete)
        
        except Exception as e:
            logger.error(f"❌ Cleanup error: {e}")
            return 0
    
    # ============================================================
    # FIND
    # ============================================================
    
    def find_by_id(self, entity_id: int) -> Optional[Dict[str, Any]]:
        """پیدا کردن با ID (بدون model_data)"""
        if not self._ensure_db():
            return None
        
        try:
            result = self.db.execute(
                """
                SELECT id, version, accuracy, period, coins, features,
                       training_samples, training_date, is_active,
                       is_ensemble, created_at, model_type
                FROM models
                WHERE id = %s
                """,
                (entity_id,),
            )
            return result[0] if result else None
        except Exception as e:
            logger.error(f"❌ Find by ID error: {e}")
            return None
    
    def find_by_version(self, version: str) -> Optional[Dict[str, Any]]:
        """پیدا کردن با نسخه"""
        if not self._ensure_db():
            return None
        
        try:
            result = self.db.execute(
                """
                SELECT id, version, accuracy, period, coins, features,
                       training_samples, training_date, is_active,
                       is_ensemble, created_at, model_type
                FROM models
                WHERE version = %s
                """,
                (version,),
            )
            return result[0] if result else None
        except Exception as e:
            logger.error(f"❌ Find by version error: {e}")
            return None
    
    def find_all(
        self,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """دریافت همه مدل‌ها"""
        if not self._ensure_db():
            return []
        
        try:
            result = self.db.execute(
                """
                SELECT id, version, accuracy, period, training_date,
                       is_active, is_ensemble, model_type
                FROM models
                ORDER BY id DESC
                LIMIT %s OFFSET %s
                """,
                (limit, offset),
            )
            return result or []
        except Exception as e:
            logger.error(f"❌ Find all error: {e}")
            return []
    
    def find_by_criteria(
        self,
        criteria: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """جستجو با معیارها"""
        if not self._ensure_db():
            return []
        
        try:
            conditions = []
            params = []
            
            if "version" in criteria:
                conditions.append("version = %s")
                params.append(criteria["version"])
            
            if "period" in criteria:
                conditions.append("period = %s")
                params.append(criteria["period"])
            
            if "is_active" in criteria:
                conditions.append("is_active = %s")
                params.append(criteria["is_active"])
            
            if "model_type" in criteria:
                conditions.append("model_type = %s")
                params.append(criteria["model_type"])
            
            if "min_accuracy" in criteria:
                conditions.append("accuracy >= %s")
                params.append(criteria["min_accuracy"])
            
            if "max_accuracy" in criteria:
                conditions.append("accuracy <= %s")
                params.append(criteria["max_accuracy"])
            
            where_clause = " AND ".join(conditions) if conditions else "1=1"
            limit = criteria.get("limit", 100)
            
            query = f"""
                SELECT id, version, accuracy, period, coins, features,
                       training_samples, training_date, is_active,
                       is_ensemble, created_at, model_type
                FROM models
                WHERE {where_clause}
                ORDER BY accuracy DESC
                LIMIT %s
            """
            
            params.append(limit)
            
            return self.db.execute(query, tuple(params)) or []
        
        except Exception as e:
            logger.error(f"❌ Find by criteria error: {e}")
            return []
    
    def count(self) -> int:
        """تعداد کل"""
        if not self._ensure_db():
            return 0
        
        try:
            result = self.db.execute("SELECT COUNT(*) as count FROM models")
            return result[0]["count"] if result else 0
        except Exception as e:
            logger.error(f"❌ Count error: {e}")
            return 0
    
    # ============================================================
    # STATS
    # ============================================================
    
    def get_stats(self) -> Dict[str, Any]:
        """آمار Repository"""
        if not self._ensure_db():
            return {}
        
        self._ensure_model_type_column()
        
        try:
            # آمار کلی
            result = self.db.execute(
                """
                SELECT
                    COUNT(*) as total,
                    AVG(accuracy) as avg_accuracy,
                    MAX(accuracy) as max_accuracy,
                    MIN(accuracy) as min_accuracy
                FROM models
                """
            )
            
            stats = result[0] if result else {}
            
            # توسط model_type
            by_type = self.db.execute(
                """
                SELECT model_type, COUNT(*) as count
                FROM models
                GROUP BY model_type
                """
            )
            
            type_counts = {
                row["model_type"] or "unknown": row["count"]
                for row in (by_type or [])
            }
            
            # توسط period
            by_period = self.db.execute(
                """
                SELECT period, COUNT(*) as count, AVG(accuracy) as avg_acc
                FROM models
                GROUP BY period
                """
            )
            
            # مدل فعال
            active = self.db.execute(
                """
                SELECT version, accuracy, model_type
                FROM models
                WHERE is_active = TRUE
                LIMIT 1
                """
            )
            
            return {
                "total_models": stats.get("total", 0),
                "avg_accuracy": round(stats.get("avg_accuracy", 0) or 0, 4),
                "max_accuracy": round(stats.get("max_accuracy", 0) or 0, 4),
                "min_accuracy": round(stats.get("min_accuracy", 0) or 0, 4),
                "by_type": type_counts,
                "active_model": (
                    {
                        "version": active[0]["version"],
                        "accuracy": active[0]["accuracy"],
                        "model_type": active[0].get("model_type", "unknown"),
                    }
                    if active else None
                ),
                "by_period": by_period or [],
            }
        
        except Exception as e:
            logger.error(f"❌ Get stats error: {e}")
            return {}
    
    # ============================================================
    # EXPORT
    # ============================================================
    
    def export_model_file(self, version: str) -> Optional[bytes]:
        """
        دریافت فایل مدل به‌صورت bytes
        
        برای XGBoost: فایل binary
        برای Rule Config: JSON
        """
        if not self._ensure_db():
            return None
        
        try:
            result = self.db.execute(
                "SELECT model_data FROM models WHERE version = %s",
                (version,),
            )
            
            if result:
                return result[0].get("model_data")
            
            return None
        
        except Exception as e:
            logger.error(f"❌ Export error: {e}")
            return None
    
    # ============================================================
    # Repository Interface
    # ============================================================
    
    def save(self, entity: Any) -> Any:
        """ذخیره Entity (الزامی)"""
        raise NotImplementedError(
            "Use save_rule_config or save_model instead"
        )
