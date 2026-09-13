# infrastructure/repositories/model_repository.py
# ============================================================
# Repository: Model (مدل‌های XGBoost) - نسخه ۳.۰
# Transaction + Bulk + Cache + Version mgmt
# ============================================================

import logging
import pickle
import tempfile
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, timedelta
from contextlib import contextmanager

import xgboost as xgb

from domain.interfaces.repository import Repository
from infrastructure.database import (
    get_primary,
    get_cache,
    primary_transaction,
)

logger = logging.getLogger(__name__)


class ModelRepository(Repository):
    """
    Repository برای مدیریت مدل‌های XGBoost
    
    ویژگی‌ها:
        - Transaction support
        - Bulk operations
        - Redis Cache برای مدل‌های فعال
        - Version comparison
        - Auto-cleanup نسخه‌های قدیمی
        - Stats aggregation
    
    رفع باگ‌ها:
        - بدون transaction → اضافه شد
        - بدون cache → اضافه شد
        - بدون cleanup → اضافه شد
        - `save_model` بدون rollback → اضافه شد
    
    ارتقاها:
        - Cache integration
        - Bulk save
        - Version comparison
        - Auto-cleanup
        - Stats aggregation
        - Export helpers
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
        
        logger.info("✅ ModelRepository v3.0 initialized")
    
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
    # Save Model
    # ============================================================
    
    def save_model(
        self,
        model: xgb.Booster,
        accuracy: float,
        version: str,
        period: str = "1m",
        coins: Optional[List[str]] = None,
        features: Optional[List[str]] = None,
        training_samples: int = 0,
        is_active: bool = True,
    ) -> Dict[str, Any]:
        """
        ذخیره مدل در دیتابیس
        
        پارامترها:
            model: مدل XGBoost
            accuracy: دقت
            version: نسخه
            period: بازه زمانی
            coins: لیست ارزها
            features: لیست ویژگی‌ها
            training_samples: تعداد نمونه‌های آموزشی
            is_active: فعال بودن
        
        خروجی:
            دیکشنری نتیجه
        
        ارتقا:
            - Transaction support
            - Rollback خودکار
            - Stats
        """
        if not self._ensure_db():
            return {"success": False, "error": "Database not connected"}
        
        temp_path: Optional[Path] = None
        
        try:
            # ۱. تبدیل مدل به binary
            temp_path = self.MODELS_DIR / f"temp_{version}.xgb"
            model.save_model(str(temp_path), format="json")
            
            with open(temp_path, "rb") as f:
                model_data: bytes = f.read()
            
            # ۲. مقادیر پیش‌فرض
            coins = coins or ["bitcoin", "ethereum"]
            features = features or []
            
            # ۳. Transaction
            with primary_transaction() as db:
                # درج مدل
                query = """
                    INSERT INTO models (
                        version, model_data, accuracy, training_samples,
                        period, coins, features, is_active, created_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s
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
                ))
                
                if not result:
                    raise RuntimeError("Insert returned no result")
                
                model_id = result[0]["id"]
                
                # غیرفعال‌سازی مدل‌های قبلی
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
                    (model_id, "train", accuracy, training_samples, datetime.now()),
                )
            
            # ۴. Cache invalidation
            self._invalidate_cache()
            
            logger.info(
                f"✅ Model saved: version={version}, "
                f"accuracy={accuracy:.3f}, id={model_id}"
            )
            
            return {
                "success": True,
                "model_id": model_id,
                "version": version,
                "accuracy": accuracy,
                "is_active": is_active,
            }
            
        except Exception as e:
            logger.error(f"❌ Save model error: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
            
        finally:
            # حذف فایل موقت
            if temp_path and temp_path.exists():
                try:
                    temp_path.unlink()
                except Exception:
                    pass
    
    def save_models_bulk(
        self,
        models: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        ذخیره چند مدل به صورت bulk
        
        پارامترها:
            models: لیست دیکشنری‌های مدل
        
        خروجی:
            دیکشنری {saved: count, failed: count, errors: [...]}
        """
        if not self._ensure_db():
            return {"success": False, "error": "Database not connected"}
        
        saved = 0
        failed = 0
        errors = []
        
        for model_data in models:
            try:
                result = self.save_model(**model_data)
                if result.get("success"):
                    saved += 1
                else:
                    failed += 1
                    errors.append(result.get("error"))
            except Exception as e:
                failed += 1
                errors.append(str(e))
        
        return {
            "success": True,
            "saved": saved,
            "failed": failed,
            "errors": errors[:10],  # فقط ۱۰ خطا
        }
    
    # ============================================================
    # Load Model
    # ============================================================
    
    def load_model(self, version: str) -> Optional[xgb.Booster]:
        """
        بارگذاری مدل با نسخه مشخص
        
        پارامترها:
            version: نسخه مدل
        
        خروجی:
            مدل XGBoost یا None
        """
        if not self._ensure_db():
            return None
        
        temp_path: Optional[Path] = None
        
        try:
            # جستجو در دیتابیس
            result = self.db.execute(
                "SELECT model_data FROM models WHERE version = %s",
                (version,),
            )
            
            if not result:
                logger.warning(f"⚠️ Model version '{version}' not found")
                return None
            
            model_data: bytes = result[0]["model_data"]
            
            # نوشتن در فایل موقت
            temp_path = self.MODELS_DIR / f"load_{version}.xgb"
            with open(temp_path, "wb") as f:
                f.write(model_data)
            
            # بارگذاری
            model = xgb.Booster()
            model.load_model(str(temp_path))
            
            return model
            
        except Exception as e:
            logger.error(f"❌ Load model error: {e}")
            return None
            
        finally:
            if temp_path and temp_path.exists():
                try:
                    temp_path.unlink()
                except Exception:
                    pass
    
    def load_active_model(self) -> Optional[Dict[str, Any]]:
        """
        بارگذاری آخرین مدل فعال
        
        خروجی:
            دیکشنری {model, version, accuracy, ...} یا None
        
        ارتقا:
            - Cache integration
        """
        if not self._ensure_db():
            return None
        
        try:
            # ابتدا از cache
            cache_key = self._get_active_model_cache_key()
            
            if self.cache and self.cache.is_connected():
                cached = self.cache.get(cache_key)
                if cached and isinstance(cached, dict):
                    version = cached.get("version")
                    if version:
                        model = self.load_model(version)
                        if model:
                            return {
                                "model": model,
                                "version": version,
                                "accuracy": cached.get("accuracy", 0),
                                "period": cached.get("period", "1m"),
                                "coins": cached.get("coins", []),
                                "features": cached.get("features", []),
                                "training_date": cached.get("training_date"),
                            }
            
            # از دیتابیس
            result = self.db.execute(
                """
                SELECT id, version, accuracy, period, coins, features,
                       training_samples, training_date, model_data
                FROM models
                WHERE is_active = TRUE
                ORDER BY id DESC
                LIMIT 1
                """
            )
            
            if not result:
                return None
            
            row = result[0]
            version = row["version"]
            
            # بارگذاری مدل
            model_data: bytes = row["model_data"]
            temp_path = self.MODELS_DIR / f"active_{version}.xgb"
            
            with open(temp_path, "wb") as f:
                f.write(model_data)
            
            model = xgb.Booster()
            model.load_model(str(temp_path))
            temp_path.unlink()
            
            result_data = {
                "model": model,
                "id": row["id"],
                "version": version,
                "accuracy": row["accuracy"],
                "period": row["period"],
                "coins": row["coins"] or [],
                "features": row["features"] or [],
                "training_samples": row["training_samples"],
                "training_date": row["training_date"],
            }
            
            # ذخیره در cache
            if self.cache and self.cache.is_connected():
                cache_data = {
                    "version": version,
                    "accuracy": row["accuracy"],
                    "period": row["period"],
                    "coins": row["coins"] or [],
                    "features": row["features"] or [],
                    "training_date": (
                        row["training_date"].isoformat()
                        if row["training_date"] else None
                    ),
                }
                self.cache.set(cache_key, cache_data, ttl=self.CACHE_TTL)
            
            return result_data
            
        except Exception as e:
            logger.error(f"❌ Load active model error: {e}", exc_info=True)
            return None
    
    # ============================================================
    # Version Management
    # ============================================================
    
    def get_version_history(
        self,
        limit: int = 10,
        include_inactive: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        دریافت تاریخچه نسخه‌ها
        
        پارامترها:
            limit: تعداد
            include_inactive: شامل غیرفعال‌ها
        
        خروجی:
            لیست دیکشنری‌ها
        """
        if not self._ensure_db():
            return []
        
        try:
            if include_inactive:
                result = self.db.execute(
                    """
                    SELECT id, version, accuracy, period, coins, features,
                           training_samples, training_date, is_active,
                           is_ensemble, created_at
                    FROM models
                    ORDER BY id DESC
                    LIMIT %s
                    """,
                    (limit,),
                )
            else:
                result = self.db.execute(
                    """
                    SELECT id, version, accuracy, period, coins, features,
                           training_samples, training_date, is_active,
                           is_ensemble, created_at
                    FROM models
                    WHERE is_active = TRUE
                    ORDER BY id DESC
                    LIMIT %s
                    """,
                    (limit,),
                )
            
            return result or []
            
        except Exception as e:
            logger.error(f"❌ Get version history error: {e}")
            return []
    
    def get_best_version(self, metric: str = "accuracy") -> Optional[Dict[str, Any]]:
        """
        دریافت بهترین نسخه
        
        پارامترها:
            metric: معیار (accuracy)
        
        خروجی:
            دیکشنری نسخه یا None
        """
        if not self._ensure_db():
            return None
        
        try:
            result = self.db.execute(
                """
                SELECT id, version, accuracy, period, training_date
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
        """دریافت تعداد نسخه‌ها"""
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
        """
        مقایسه دو نسخه
        
        پارامترها:
            version1: نسخه اول
            version2: نسخه دوم
        
        خروجی:
            دیکشنری مقایسه یا None
        """
        if not self._ensure_db():
            return None
        
        try:
            result = self.db.execute(
                """
                SELECT version, accuracy, training_samples, period,
                       training_date
                FROM models
                WHERE version IN (%s, %s)
                """,
                (version1, version2),
            )
            
            if len(result) != 2:
                return None
            
            v1_data = next(
                (r for r in result if r["version"] == version1), None
            )
            v2_data = next(
                (r for r in result if r["version"] == version2), None
            )
            
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
    # Activation
    # ============================================================
    
    def set_active(self, version: str) -> bool:
        """
        تنظیم یک نسخه به عنوان فعال
        
        پارامترها:
            version: نسخه
        
        خروجی:
            True اگر موفق
        """
        if not self._ensure_db():
            return False
        
        try:
            with primary_transaction() as db:
                # غیرفعال کردن همه
                db.execute("UPDATE models SET is_active = FALSE")
                
                # فعال کردن نسخه مورد نظر
                result = db.execute(
                    "UPDATE models SET is_active = TRUE WHERE version = %s",
                    (version,),
                )
            
            # Cache invalidation
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
    # Delete & Cleanup
    # ============================================================
    
    def delete(self, entity_id: int) -> bool:
        """
        حذف مدل با ID
        
        پارامترها:
            entity_id: ID مدل
        
        خروجی:
            True اگر موفق
        """
        if not self._ensure_db():
            return False
        
        try:
            # بررسی فعال نبودن
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
        """
        پاک کردن نسخه‌های قدیمی
        
        پارامترها:
            keep_last_n: تعداد نسخه‌های اخیر که باید بمانند
        
        خروجی:
            تعداد حذف شده
        """
        if not self._ensure_db():
            return 0
        
        try:
            # پیدا کردن نسخه‌های قدیمی (به جز فعال‌ها و n تای اخیر)
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
    # Find Methods
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
                       is_ensemble, created_at
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
                       is_ensemble, created_at
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
        """دریافت همه مدل‌ها (بدون model_data)"""
        if not self._ensure_db():
            return []
        
        try:
            result = self.db.execute(
                """
                SELECT id, version, accuracy, period, training_date,
                       is_active, is_ensemble
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
        """
        جستجو با معیارها
        
        پارامترها:
            criteria: دیکشنری معیارها
                - version: str
                - period: str
                - is_active: bool
                - min_accuracy: float
                - max_accuracy: float
                - limit: int
        
        خروجی:
            لیست نتایج
        """
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
            
            if "min_accuracy" in criteria:
                conditions.append("accuracy >= %s")
                params.append(criteria["min_accuracy"])
            
            if "max_accuracy" in criteria:
                conditions.append("accuracy <= %s")
                params.append(criteria["max_accuracy"])
            
            where_clause = (
                " AND ".join(conditions) if conditions else "1=1"
            )
            
            limit = criteria.get("limit", 100)
            
            query = f"""
                SELECT id, version, accuracy, period, coins, features,
                       training_samples, training_date, is_active,
                       is_ensemble, created_at
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
    # Stats
    # ============================================================
    
    def get_stats(self) -> Dict[str, Any]:
        """
        دریافت آمار Repository
        
        خروجی:
            دیکشنری شامل:
                - total_models
                - active_model
                - best_accuracy
                - avg_accuracy
                - by_period
        """
        if not self._ensure_db():
            return {}
        
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
                SELECT version, accuracy
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
                "active_model": (
                    {
                        "version": active[0]["version"],
                        "accuracy": active[0]["accuracy"],
                    }
                    if active else None
                ),
                "by_period": by_period or [],
            }
            
        except Exception as e:
            logger.error(f"❌ Get stats error: {e}")
            return {}
    
    # ============================================================
    # Export
    # ============================================================
    
    def export_model_file(
        self,
        version: str,
    ) -> Optional[bytes]:
        """
        دریافت فایل مدل به صورت bytes
        
        پارامترها:
            version: نسخه مدل
        
        خروجی:
            bytes یا None
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
    # Repository Interface (الزامی)
    # ============================================================
    
    def save(self, entity: Any) -> Any:
        """ذخیره Entity (استفاده از save_model)"""
        raise NotImplementedError("Use save_model instead")
