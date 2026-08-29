# infrastructure/repositories/model_repository.py
# ============================================================
# Repository: Model (مدل‌های XGBoost)
# ============================================================

import logging
import xgboost as xgb
from typing import Optional, List, Dict, Any
from datetime import datetime
from pathlib import Path

from domain.interfaces.repository import Repository
from infrastructure.database import get_primary

logger = logging.getLogger(__name__)


class ModelRepository(Repository):
    """
    Repository برای مدیریت مدل‌های XGBoost در دیتابیس
    
    مسئولیت:
        - ذخیره مدل‌ها
        - بارگذاری مدل‌ها
        - جستجوی مدل‌ها
        - مدیریت نسخه‌ها
    """
    
    def __init__(self):
        self.db = get_primary()
        self.models_dir: Path = Path("models/")
        self.models_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info("✅ ModelRepository initialized")
    
    def _ensure_db(self) -> bool:
        """اطمینان از اتصال دیتابیس"""
        if not self.db or not self.db.is_connected():
            self.db = get_primary()
            return self.db is not None and self.db.is_connected()
        return True
    
    def save_model(
        self,
        model: xgb.Booster,
        accuracy: float,
        version: str,
        period: str = "1m",
        coins: Optional[List[str]] = None,
        features: Optional[List[str]] = None,
        is_active: bool = True
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
            is_active: فعال بودن
        
        خروجی:
            دیکشنری نتیجه
        """
        if not self._ensure_db():
            return {"success": False, "error": "Database not connected"}
        
        try:
            # ذخیره موقت مدل
            temp_path: Path = self.models_dir / f"temp_{version}.xgb"
            model.save_model(str(temp_path), format='json')
            
            with open(temp_path, "rb") as f:
                model_data: bytes = f.read()
            temp_path.unlink()
            
            # کوئری ذخیره
            query: str = """
                INSERT INTO models (
                    version, model_data, accuracy, training_samples,
                    period, coins, features, is_active, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """
            
            result = self.db.execute(query, (
                version,
                model_data,
                accuracy,
                0,
                period,
                coins or ["bitcoin", "ethereum"],
                features or [],
                is_active,
                datetime.now()
            ))
            
            if result:
                model_id: int = result[0]['id']
                
                # غیرفعال کردن مدل‌های قبلی
                if is_active:
                    self.db.execute(
                        "UPDATE models SET is_active = FALSE WHERE id != %s",
                        (model_id,)
                    )
                
                return {
                    "success": True,
                    "model_id": model_id,
                    "version": version,
                    "accuracy": accuracy
                }
            
            return {"success": False, "error": "No result from insert"}
            
        except Exception as e:
            logger.error(f"❌ Save model error: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
    
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
        
        try:
            result = self.db.execute(
                "SELECT model_data FROM models WHERE version = %s",
                (version,)
            )
            
            if not result:
                return None
            
            model_data: bytes = result[0]['model_data']
            temp_path: Path = self.models_dir / f"temp_{version}.xgb"
            
            with open(temp_path, "wb") as f:
                f.write(model_data)
            
            model: xgb.Booster = xgb.Booster()
            model.load_model(str(temp_path))
            temp_path.unlink()
            
            return model
            
        except Exception as e:
            logger.error(f"❌ Load model error: {e}", exc_info=True)
            return None
    
    def load_active_model(self) -> Optional[Dict[str, Any]]:
        """بارگذاری آخرین مدل فعال"""
        if not self._ensure_db():
            return None
        
        try:
            result = self.db.execute(
                "SELECT * FROM models WHERE is_active = TRUE ORDER BY id DESC LIMIT 1"
            )
            
            if not result:
                return None
            
            row = result[0]
            model_data: bytes = row['model_data']
            temp_path: Path = self.models_dir / f"temp_{row['version']}.xgb"
            
            with open(temp_path, "wb") as f:
                f.write(model_data)
            
            model: xgb.Booster = xgb.Booster()
            model.load_model(str(temp_path))
            temp_path.unlink()
            
            return {
                "model": model,
                "version": row['version'],
                "accuracy": row['accuracy'],
                "period": row['period'],
                "coins": row['coins'],
                "features": row['features'],
                "training_date": row['training_date']
            }
            
        except Exception as e:
            logger.error(f"❌ Load active model error: {e}", exc_info=True)
            return None
    
    # ============================================================
    # پیاده‌سازی Interface Repository
    # ============================================================
    
    def save(self, entity: Any) -> Any:
        """ذخیره Entity (برای سازگاری با Interface)"""
        raise NotImplementedError("Use save_model instead")
    
    def find_by_id(self, entity_id: int) -> Optional[Any]:
        """پیدا کردن با ID"""
        if not self._ensure_db():
            return None
        
        try:
            result = self.db.execute(
                "SELECT * FROM models WHERE id = %s",
                (entity_id,)
            )
            return result[0] if result else None
        except Exception as e:
            logger.error(f"❌ Find by ID error: {e}")
            return None
    
    def find_all(self, limit: int = 100, offset: int = 0) -> List[Any]:
        """دریافت همه مدل‌ها"""
        if not self._ensure_db():
            return []
        
        try:
            result = self.db.execute(
                "SELECT id, version, accuracy, period, training_date, is_active "
                "FROM models ORDER BY id DESC LIMIT %s OFFSET %s",
                (limit, offset)
            )
            return result
        except Exception as e:
            logger.error(f"❌ Find all error: {e}")
            return []
    
    def delete(self, entity_id: int) -> bool:
        """حذف مدل با ID"""
        if not self._ensure_db():
            return False
        
        try:
            # بررسی اینکه مدل فعال نباشد
            check = self.db.execute(
                "SELECT is_active FROM models WHERE id = %s",
                (entity_id,)
            )
            if check and check[0].get('is_active', False):
                logger.warning(f"⚠️ Cannot delete active model {entity_id}")
                return False
            
            self.db.execute("DELETE FROM models WHERE id = %s", (entity_id,))
            return True
        except Exception as e:
            logger.error(f"❌ Delete error: {e}")
            return False
    
    def count(self) -> int:
        """تعداد کل مدل‌ها"""
        if not self._ensure_db():
            return 0
        
        try:
            result = self.db.execute("SELECT COUNT(*) as count FROM models")
            return result[0]['count'] if result else 0
        except Exception as e:
            logger.error(f"❌ Count error: {e}")
            return 0
    
    def find_by_criteria(self, criteria: Dict[str, Any]) -> List[Any]:
        """جستجوی مدل‌ها با معیارها"""
        if not self._ensure_db():
            return []
        
        try:
            conditions: List[str] = []
            params: List[Any] = []
            
            for key, value in criteria.items():
                if key in ['version', 'period', 'is_active']:
                    conditions.append(f"{key} = %s")
                    params.append(value)
                elif key == 'min_accuracy':
                    conditions.append("accuracy >= %s")
                    params.append(value)
                elif key == 'max_accuracy':
                    conditions.append("accuracy <= %s")
                    params.append(value)
            
            where_clause = " AND ".join(conditions) if conditions else "1=1"
            query = f"SELECT * FROM models WHERE {where_clause} ORDER BY accuracy DESC"
            
            result = self.db.execute(query, tuple(params))
            return result
        except Exception as e:
            logger.error(f"❌ Find by criteria error: {e}")
            return []
    
    def get_version_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """دریافت تاریخچه نسخه‌ها"""
        if not self._ensure_db():
            return []
        
        try:
            result = self.db.execute("""
                SELECT id, version, accuracy, training_date, is_active, is_ensemble, period
                FROM models 
                ORDER BY id DESC 
                LIMIT %s
            """, (limit,))
            return result
        except Exception as e:
            logger.error(f"❌ Get version history error: {e}")
            return []
    
    def set_active(self, version: str) -> bool:
        """تنظیم یک نسخه به عنوان فعال"""
        if not self._ensure_db():
            return False
        
        try:
            # غیرفعال کردن همه
            self.db.execute("UPDATE models SET is_active = FALSE")
            # فعال کردن نسخه مورد نظر
            self.db.execute(
                "UPDATE models SET is_active = TRUE WHERE version = %s",
                (version,)
            )
            return True
        except Exception as e:
            logger.error(f"❌ Set active error: {e}")
            return False
