# infrastructure/repositories/model_repository.py
# ============================================================
# Repository: Model - نسخه ۴.۱
# Polymorphic (Rule Config) + Auto Schema + Transaction + Cache
# ============================================================
# 
# تغییرات نسخه ۴.۱:
#   - اصلاح default model_type (rule_config جای xgboost)
#   - اضافه ensure_schema خودکار (CREATE TABLE IF NOT EXISTS)
#   - حذف کد XGBoost (save_model, load_model)
#   - حفظ export_model_file (برای Rule Config)
# ============================================================

import json
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any

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


# ============================================================
# ModelRepository
# ============================================================

class ModelRepository(Repository):
    """
    Repository برای مدیریت Rule Configها
    
    نسخه ۴.۱:
        - فقط Rule Config (XGBoost حذف شد)
        - ensure_schema خودکار
        - model_type همیشه 'rule_config'
    """
    
    TABLE_NAME = "models"
    HISTORY_TABLE = "model_training_history"
    CACHE_PREFIX = "model:active"
    CACHE_TTL = 300  # ۵ دقیقه
    
    # ============================================================
    # Init
    # ============================================================
    
    def __init__(self) -> None:
        self._db = None
        self._cache = None
        self._schema_ensured: bool = False
        
        logger.info("✅ ModelRepository v4.1 initialized")
    
    # ============================================================
    # Lazy properties
    # ============================================================
    
    @property
    def db(self):
        """دیتابیس primary"""
        if self._db is None or not self._db.is_connected():
            self._db = get_primary()
        return self._db
    
    @property
    def cache(self):
        """cache"""
        if self._cache is None or not self._cache.is_connected():
            self._cache = get_cache()
        return self._cache
    
    def _ensure_db(self) -> bool:
        """اطمینان از اتصال DB"""
        if self._db is None or not self._db.is_connected():
            self._db = get_primary()
        return self._db is not None and self._db.is_connected()
    
    # ============================================================
    # Schema Ensure (خودکار)
    # ============================================================
    
    def _ensure_schema(self) -> None:
        """
        ساخت جدول models اگه نبود
        
        این تابع یه‌بار صدا زده می‌شه (کش می‌شه با _schema_ensured)
        """
        if self._schema_ensured:
            return
        
        if not self._ensure_db():
            return
        
        try:
            # ============================================================
            # جدول models
            # ============================================================
            self.db.execute("""
                CREATE TABLE IF NOT EXISTS models (
                    id SERIAL PRIMARY KEY,
                    version VARCHAR(50) UNIQUE NOT NULL,
                    model_data BYTEA NOT NULL,
                    accuracy FLOAT NOT NULL DEFAULT 0,
                    training_samples INTEGER DEFAULT 0,
                    period VARCHAR(30) DEFAULT 'rule_config',
                    coins TEXT[] DEFAULT ARRAY['bitcoin', 'ethereum'],
                    features TEXT[] DEFAULT ARRAY[]::TEXT[],
                    is_active BOOLEAN DEFAULT FALSE,
                    model_type VARCHAR(50) DEFAULT 'rule_config',
                    training_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    metadata JSONB DEFAULT '{}'::jsonb
                )
            """)
            
            # ایندکس‌ها
            self.db.execute(
                "CREATE INDEX IF NOT EXISTS idx_models_version ON models(version)"
            )
            self.db.execute(
                "CREATE INDEX IF NOT EXISTS idx_models_active ON models(is_active)"
            )
            self.db.execute(
                "CREATE INDEX IF NOT EXISTS idx_models_type ON models(model_type)"
            )
            self.db.execute(
                "CREATE INDEX IF NOT EXISTS idx_models_accuracy ON models(accuracy DESC)"
            )
            self.db.execute(
                "CREATE INDEX IF NOT EXISTS idx_models_training_date ON models(training_date DESC)"
            )
            
            # ============================================================
            # جدول model_training_history
            # ============================================================
            self.db.execute("""
                CREATE TABLE IF NOT EXISTS model_training_history (
                    id SERIAL PRIMARY KEY,
                    model_id INTEGER REFERENCES models(id) ON DELETE CASCADE,
                    action VARCHAR(50) NOT NULL,
                    old_accuracy FLOAT,
                    new_accuracy FLOAT,
                    improvement_percent FLOAT,
                    samples_used INTEGER,
                    training_time_seconds FLOAT,
                    reason TEXT,
                    status VARCHAR(20) DEFAULT 'success',
                    error_message TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    completed_at TIMESTAMP
                )
            """)
            
            self.db.execute(
                "CREATE INDEX IF NOT EXISTS idx_mth_model_id ON model_training_history(model_id)"
            )
            self.db.execute(
                "CREATE INDEX IF NOT EXISTS idx_mth_created_at ON model_training_history(created_at DESC)"
            )
            
            # ============================================================
            # Migration: اضافه کردن model_type اگه جدول قدیمی بود
            # ============================================================
            try:
                self.db.execute("""
                    DO $$
                    BEGIN
                        IF NOT EXISTS (
                            SELECT 1 FROM information_schema.columns
                            WHERE table_name = 'models'
                            AND column_name = 'model_type'
                        ) THEN
                            ALTER TABLE models
                            ADD COLUMN model_type VARCHAR(50)
                            DEFAULT 'rule_config';
                        END IF;
                    END $$;
                """)
            except Exception as e:
                logger.debug(f"model_type column check: {e}")
            
            self._schema_ensured = True
            logger.info("✅ ModelRepository: schema ensured")
        
        except Exception as e:
            logger.warning(f"⚠️ Schema ensure failed: {e}")
            # ولی _schema_ensured رو ست نمی‌کنیم تا دوباره تلاش بشه
    
    # ============================================================
    # Cache helpers
    # ============================================================
    
    def _get_active_cache_key(self) -> str:
        return f"{self.CACHE_PREFIX}:current"
    
    def _invalidate_cache(self) -> None:
        try:
            if self.cache and self.cache.is_connected():
                keys = self.cache.scan_keys(f"{self.CACHE_PREFIX}:*")
                if keys:
                    self.cache.delete_many(keys)
        except Exception as e:
            logger.debug(f"Cache invalidation error: {e}")
    
    # ============================================================
    # SAVE RULE CONFIG (اصلی)
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
            version: نسخه (v2026.09.30_1200)
            accuracy: دقت (از backtest)
            coins: لیست ارزها
            training_samples: تعداد نمونه‌های backtest
            is_active: فعال باشه؟
            metadata: اطلاعات اضافی
        
        Returns:
            {success, model_id, version, accuracy}
        """
        if not self._ensure_db():
            return {"success": False, "error": "Database not connected"}
        
        # اطمینان از جدول
        self._ensure_schema()
        
        try:
            # Serialize config به JSON bytes
            config_json = json.dumps(config, ensure_ascii=False)
            config_bytes = config_json.encode("utf-8")
            
            # لیست rule names
            rule_names = list(config.get("rules", {}).keys())
            
            with primary_transaction() as db:
                # درج
                query = """
                    INSERT INTO models (
                        version, model_data, accuracy, training_samples,
                        period, coins, features, is_active, created_at,
                        model_type, metadata
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                    RETURNING id, version, accuracy, created_at
                """
                
                result = db.execute(query, (
                    version,
                    config_bytes,
                    accuracy,
                    training_samples,
                    MODEL_TYPE_RULE_CONFIG,           # period
                    coins or [],
                    rule_names,                        # features = rule names
                    is_active,
                    datetime.now(),
                    MODEL_TYPE_RULE_CONFIG,           # model_type
                    json.dumps(metadata or {}),       # metadata
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
                    (
                        model_id,
                        "save_rule_config",
                        accuracy,
                        training_samples,
                        datetime.now(),
                    ),
                )
            
            self._invalidate_cache()
            
            logger.info(
                f"✅ Rule config saved: version={version}, "
                f"accuracy={accuracy:.3f}, id={model_id}, "
                f"rules={len(rule_names)}"
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
    
    # ============================================================
    # LOAD RULE CONFIG
    # ============================================================
    
    def load_rule_config(self, version: str) -> Optional[Dict[str, Any]]:
        """بارگذاری یک Rule Config با نسخه"""
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
            {config, version, accuracy, model_id, model_type}
        """
        if not self._ensure_db():
            return None
        
        self._ensure_schema()
        
        try:
            # از cache
            cache_key = self._get_active_cache_key()
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
                  AND (model_type = %s OR model_type IS NULL)
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
    # VERSION MANAGEMENT
    # ============================================================
    
    def get_version_history(
        self,
        limit: int = 10,
        include_inactive: bool = True,
        model_type: Optional[str] = MODEL_TYPE_RULE_CONFIG,
    ) -> List[Dict[str, Any]]:
        """دریافت تاریخچه نسخه‌ها"""
        if not self._ensure_db():
            return []
        
        self._ensure_schema()
        
        try:
            conditions = []
            params = []
            
            if not include_inactive:
                conditions.append("is_active = TRUE")
            
            if model_type:
                conditions.append("(model_type = %s OR model_type IS NULL)")
                params.append(model_type)
            
            where_clause = " AND ".join(conditions) if conditions else "1=1"
            
            query = f"""
                SELECT id, version, accuracy, period, coins, features,
                       training_samples, training_date, is_active,
                       created_at, model_type
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
        model_type: Optional[str] = MODEL_TYPE_RULE_CONFIG,
    ) -> Optional[Dict[str, Any]]:
        """بهترین نسخه از نظر دقت"""
        if not self._ensure_db():
            return None
        
        try:
            if model_type:
                result = self.db.execute(
                    """
                    SELECT id, version, accuracy, period, training_date, model_type
                    FROM models
                    WHERE model_type = %s OR model_type IS NULL
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
        """فعال‌سازی یک نسخه"""
        if not self._ensure_db():
            return False
        
        self._ensure_schema()
        
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
        """حذف با ID"""
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
        """پیدا کردن با ID"""
        if not self._ensure_db():
            return None
        
        try:
            result = self.db.execute(
                """
                SELECT id, version, accuracy, period, coins, features,
                       training_samples, training_date, is_active,
                       created_at, model_type
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
                       created_at, model_type
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
        """همه مدل‌ها"""
        if not self._ensure_db():
            return []
        
        try:
            result = self.db.execute(
                """
                SELECT id, version, accuracy, period, training_date,
                       is_active, model_type
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
                       created_at, model_type
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
        
        self._ensure_schema()
        
        try:
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
        خروجی config به‌صورت bytes (JSON)
        
        برای Rule Config: JSON bytes
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
            "Use save_rule_config instead"
        )


__all__ = ["ModelRepository", "MODEL_TYPE_RULE_CONFIG"]
