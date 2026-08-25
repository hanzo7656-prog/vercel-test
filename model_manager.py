# model_manager.py
# ============================================================
# مدیریت پیشرفته مدل XGBoost با نسخه‌سازی و دیتابیس
# ============================================================

import os
import json
import pickle
import logging
import numpy as np
import xgboost as xgb
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple

from database import get_primary
from config import get_model_config

logger = logging.getLogger(__name__)


class ModelManager:
    """
    مدیریت پیشرفته مدل XGBoost:
    - ذخیره و بارگذاری در دیتابیس
    - نسخه‌سازی خودکار
    - آموزش افزایشی
    - Ensemble
    - ارزیابی خودکار
    """
    
    def __init__(self, api=None):
        self.api = api
        self.db = get_primary()
        self.models_dir = "models/"
        self.current_model = None
        self.current_version = None
        self.config = get_model_config()
        
        # ایجاد پوشه مدل‌ها
        os.makedirs(self.models_dir, exist_ok=True)
        
        # بارگذاری آخرین مدل فعال
        self._load_active_model()
    
    # ============================================================
    # ۱. ذخیره و بازیابی مدل
    # ============================================================
    
    def save_model(self, model, accuracy: float, period: str = "1m") -> Dict:
        """ذخیره مدل در دیتابیس با متادیتا"""
        if not self.db or not self.db.is_connected():
            return self._save_local(model, accuracy, period)
        
        try:
            # تبدیل مدل به باینری
            temp_path = f"{self.models_dir}temp_model.xgb"
            model.save_model(temp_path)
            
            with open(temp_path, "rb") as f:
                model_data = f.read()
            os.remove(temp_path)
            
            # تولید نسخه
            version = self._generate_version()
            
            # ذخیره در دیتابیس
            query = """
                INSERT INTO models (
                    version, model_data, accuracy, training_samples,
                    period, coins, features, is_active, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """
            
            # اینجا باید ویژگی‌ها و ارزها رو از مدل استخراج کنید
            features = self._get_model_features(model)
            coins = self.config.get("coins", ["bitcoin", "ethereum"])
            
            result = self.db.execute(query, (
                version,
                model_data,
                accuracy,
                0,  # training_samples (بعداً محاسبه میشه)
                period,
                coins,
                features,
                True,
                datetime.now()
            ))
            
            if result:
                model_id = result[0]['id']
                
                # غیرفعال کردن مدل‌های قبلی
                self.db.execute(
                    "UPDATE models SET is_active = FALSE WHERE id != %s",
                    (model_id,)
                )
                
                # ثبت در تاریخچه
                self.db.execute(
                    """INSERT INTO model_training_history 
                       (model_id, action, new_accuracy, created_at) 
                       VALUES (%s, %s, %s, %s)""",
                    (model_id, 'train', accuracy, datetime.now())
                )
                
                self.current_model = model
                self.current_version = version
                
                return {
                    "success": True,
                    "version": version,
                    "model_id": model_id,
                    "accuracy": accuracy,
                    "message": f"مدل نسخه {version} ذخیره شد"
                }
            
        except Exception as e:
            logger.error(f"❌ خطا در ذخیره مدل: {e}")
            return {"success": False, "error": str(e)}
        
        return {"success": False, "message": "خطای ناشناخته"}
    
    def _load_active_model(self) -> bool:
        """بارگذاری آخرین مدل فعال از دیتابیس"""
        if not self.db or not self.db.is_connected():
            return self._load_local()
        
        try:
            result = self.db.execute(
                "SELECT * FROM models WHERE is_active = TRUE ORDER BY id DESC LIMIT 1"
            )
            
            if result:
                row = result[0]
                model_data = row['model_data']
                
                # ذخیره موقت و بارگذاری
                temp_path = f"{self.models_dir}temp_{row['version']}.xgb"
                with open(temp_path, "wb") as f:
                    f.write(model_data)
                
                model = xgb.Booster()
                model.load_model(temp_path)
                os.remove(temp_path)
                
                self.current_model = model
                self.current_version = row['version']
                
                logger.info(f"✅ مدل نسخه {self.current_version} بارگذاری شد")
                return True
                
        except Exception as e:
            logger.error(f"❌ خطا در بارگذاری مدل: {e}")
        
        return self._load_local()
    
    def _generate_version(self) -> str:
        """تولید نسخه جدید بر اساس تاریخ و زمان"""
        now = datetime.now()
        version = f"v{now.year}.{now.month:02d}.{now.day:02d}_{now.hour:02d}{now.minute:02d}"
        return version
    
    def _save_local(self, model, accuracy, period) -> Dict:
        """ذخیره محلی (در صورت عدم دسترسی به دیتابیس)"""
        version = f"local_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        path = f"{self.models_dir}{version}.xgb"
        model.save_model(path, format='json')
        
        self.current_model = model
        self.current_version = version
        
        return {
            "success": True,
            "version": version,
            "path": path,
            "accuracy": accuracy,
            "message": "مدل به صورت محلی ذخیره شد"
        }
    
    def _load_local(self) -> bool:
        """بارگذاری آخرین مدل محلی"""
        try:
            files = [f for f in os.listdir(self.models_dir) if f.endswith('.xgb')]
            if files:
                latest = sorted(files)[-1]
                path = os.path.join(self.models_dir, latest)
                model = xgb.Booster()
                model.load_model(path)
                self.current_model = model
                self.current_version = latest.replace('.xgb', '')
                logger.info(f"✅ مدل محلی بارگذاری شد: {latest}")
                return True
        except Exception as e:
            logger.error(f"❌ خطا در بارگذاری مدل محلی: {e}")
        return False
    
    def _get_model_features(self, model) -> List[str]:
        """دریافت لیست ویژگی‌های مدل"""
        # اینجا باید از تنظیمات یا خود مدل ویژگی‌ها رو استخراج کنید
        return self.config.get("features", [
            "return_1", "return_3", "return_5", "return_10",
            "sma_5", "sma_10", "sma_20", "volatility",
            "fear_greed", "trend_5", "trend_10", "trend_20", "r2"
        ])
    
    # ============================================================
    # ۲. پیش‌بینی با مدل جاری
    # ============================================================
    
    def predict(self, features: np.ndarray) -> float:
        """پیش‌بینی با مدل جاری"""
        if self.current_model is None:
            raise ValueError("هیچ مدلی بارگذاری نشده است")
        
        try:
            dmatrix = xgb.DMatrix(features.reshape(1, -1))
            prediction = self.current_model.predict(dmatrix)[0]
            return float(prediction)
        except Exception as e:
            logger.error(f"❌ خطا در پیش‌بینی: {e}")
            raise
    
    def predict_batch(self, features: np.ndarray) -> np.ndarray:
        """پیش‌بینی گروهی"""
        if self.current_model is None:
            raise ValueError("هیچ مدلی بارگذاری نشده است")
        
        try:
            dmatrix = xgb.DMatrix(features)
            predictions = self.current_model.predict(dmatrix)
            return np.array(predictions)
        except Exception as e:
            logger.error(f"❌ خطا در پیش‌بینی گروهی: {e}")
            raise
    
    # ============================================================
    # ۳. آموزش افزایشی (Incremental Learning)
    # ============================================================
    # ============================================================
# متدهای جدید برای اتصال به دیتابیس
# ============================================================

    def save_model_to_db(self, model, accuracy: float, period: str = "1m", 
                          coins: List[str] = None, features: List[str] = None) -> Dict:
        """
        ذخیره مدل در دیتابیس PostgreSQL
    
        پارامترها:
            model: مدل XGBoost
            accuracy: دقت مدل
            period: بازه زمانی (1w, 1m, 3m, 6m)
            coins: لیست ارزهای استفاده شده
            features: لیست ویژگی‌ها
    
        خروجی:
            دیکشنری شامل نسخه، آیدی و وضعیت
        """
        if not self.db or not self.db.is_connected():
            return self._save_local(model, accuracy, period)
    
        try:
            # ۱. تبدیل مدل به باینری
            temp_path = f"{self.models_dir}temp_model.xgb"
            model.save_model(temp_path, format='json')
        
            with open(temp_path, "rb") as f:
                model_data = f.read()
            os.remove(temp_path)
        
            # ۲. تولید نسخه
            version = self._generate_version()
        
            # ۳. تنظیم مقادیر پیش‌فرض
            if coins is None:
                coins = self.config.get("coins", ["bitcoin", "ethereum", "solana", "cardano", "ripple"])
            if features is None:
                features = self._get_model_features(model)
        
            # ۴. ذخیره در دیتابیس
            query = """
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
                0,  # training_samples (بعداً محاسبه میشه)
                period,
                coins,
                features,
                True,
                datetime.now()
            ))
        
            if result:
                model_id = result[0]['id']
            
                # ۵. غیرفعال کردن مدل‌های قبلی
                self.db.execute(
                    "UPDATE models SET is_active = FALSE WHERE id != %s",
                    (model_id,)
                )
            
                # ۶. ثبت در تاریخچه
                self.db.execute(
                    """INSERT INTO model_training_history 
                       (model_id, action, new_accuracy, created_at) 
                       VALUES (%s, %s, %s, %s)""",
                    (model_id, 'train', accuracy, datetime.now())
                )
            
                # ۷. به‌روزرسانی مدل جاری
                self.current_model = model
                self.current_version = version
            
                return {
                    "success": True,
                    "version": version,
                    "model_id": model_id,
                    "accuracy": accuracy,
                    "message": f"مدل نسخه {version} ذخیره شد"
                }
        
        except Exception as e:
            logger.error(f"❌ خطا در ذخیره مدل: {e}")
            return {"success": False, "error": str(e)}
    
        return {"success": False, "message": "خطای ناشناخته"}


    def load_model_from_db(self, version: str = None) -> Optional[xgb.Booster]:
        """
        بارگذاری مدل از دیتابیس با نسخه مشخص
    
        پارامترها:
            version: نسخه مدل (اگر None باشد، آخرین مدل فعال بارگذاری می‌شود)
    
        خروجی:
            مدل XGBoost یا None در صورت خطا
        """
        if not self.db or not self.db.is_connected():
            return self._load_local()
    
        try:
            if version:
                query = "SELECT * FROM models WHERE version = %s"
                result = self.db.execute(query, (version,))
            else:
                query = "SELECT * FROM models WHERE is_active = TRUE ORDER BY id DESC LIMIT 1"
                result = self.db.execute(query)
        
            if result:
                row = result[0]
                model_data = row['model_data']
            
                # ذخیره موقت و بارگذاری
                temp_path = f"{self.models_dir}temp_{row['version']}.xgb"
                with open(temp_path, "wb") as f:
                    f.write(model_data)
            
                model = xgb.Booster()
                model.load_model(temp_path)
                os.remove(temp_path)
            
                self.current_model = model
                self.current_version = row['version']
            
                logger.info(f"✅ مدل نسخه {self.current_version} از دیتابیس بارگذاری شد")
                return model
        
        except Exception as e:
            logger.error(f"❌ خطا در بارگذاری مدل از دیتابیس: {e}")
    
        return None


    def get_version_history(self, limit: int = 10) -> List[Dict]:
        """
        دریافت تاریخچه نسخه‌های مدل از دیتابیس
    
        پارامترها:
            limit: تعداد رکوردها
    
        خروجی:
            لیست دیکشنری‌های شامل اطلاعات نسخه‌ها
        """
        if not self.db or not self.db.is_connected():
            return []
    
        try:
            query = """
                SELECT id, version, accuracy, training_date, 
                       is_active, is_ensemble, period, training_samples
                FROM models 
                ORDER BY id DESC 
                LIMIT %s
            """
            result = self.db.execute(query, (limit,))
            return result
        except Exception as e:
            logger.error(f"❌ خطا در دریافت تاریخچه: {e}")
            return []


    def get_model_by_version(self, version: str) -> Optional[xgb.Booster]:
        """
        دریافت مدل با نسخه مشخص
    
        پارامترها:
            version: نسخه مدل
    
        خروجی:
            مدل XGBoost یا None
        """
        if not self.db or not self.db.is_connected():
            return None
    
        try:
            query = "SELECT model_data FROM models WHERE version = %s"
            result = self.db.execute(query, (version,))
        
            if result:
                model_data = result[0]['model_data']
                temp_path = f"{self.models_dir}temp_{version}.xgb"
                with open(temp_path, "wb") as f:
                    f.write(model_data)
            
                model = xgb.Booster()
                model.load_model(temp_path)
                os.remove(temp_path)
                return model
            
        except Exception as e:
            logger.error(f"❌ خطا در دریافت مدل: {e}")
        return None


    def delete_old_models(self, days_to_keep: int = 30) -> int:
        """
        حذف مدل‌های قدیمی از دیتابیس
      
        پارامترها:
            days_to_keep: تعداد روزهایی که مدل‌ها نگهداری شوند
    
        خروجی:
            تعداد مدل‌های حذف شده
        """
        if not self.db or not self.db.is_connected():
            return 0
    
        try:
            query = """
                DELETE FROM models
                WHERE is_active = FALSE
                  AND is_ensemble = FALSE
                  AND training_date < NOW() - (%s || ' days')::INTERVAL
                  AND id NOT IN (
                      SELECT parent_id FROM model_training_history
                  )
            """
            self.db.execute(query, (days_to_keep,))
            return 0  # number of deleted rows
        except Exception as e:
            logger.error(f"❌ خطا در حذف مدل‌های قدیمی: {e}")
            return 0


    def get_stats(self) -> Dict[str, Any]:
        """دریافت آمار مدل جاری"""
        return {
            "loaded": self.current_model is not None,
            "version": self.current_version,
            "model_exists": os.path.exists(self.models_dir),
            "db_connected": self.db is not None and self.db.is_connected(),
            "timestamp": datetime.now().isoformat()
        }

    def incremental_train(self, features: np.ndarray, labels: np.ndarray) -> Dict:
        """آموزش افزایشی با داده‌های جدید"""
        if self.current_model is None:
            return {"success": False, "message": "مدلی برای آموزش افزایشی وجود ندارد"}
        
        try:
            # ارزیابی مدل فعلی
            old_accuracy = self._evaluate(self.current_model, features, labels)
            
            # پارامترهای با نرخ یادگیری کمتر
            params = {
                'objective': 'binary:logistic',
                'eval_metric': 'logloss',
                'learning_rate': 0.05,
                'max_depth': 3,
                'subsample': 0.7,
                'colsample_bytree': 0.7,
                'tree_method': 'hist'
            }
            
            dtrain = xgb.DMatrix(features, label=labels)
            new_model = xgb.train(
                params,
                dtrain,
                num_boost_round=10,
                xgb_model=self.current_model
            )
            
            # ارزیابی مدل جدید
            new_accuracy = self._evaluate(new_model, features, labels)
            improvement = new_accuracy - old_accuracy
            
            if improvement > 0.02:
                # بهبود قابل توجه → جایگزینی
                return self.save_model(new_model, new_accuracy, "1m")
            elif improvement > 0.005:
                # بهبود کوچک → ترکیب
                combined = self._ensemble_models(
                    self.current_model, new_model, weights=[0.7, 0.3]
                )
                combined_accuracy = self._evaluate(combined, features, labels)
                return self.save_model(combined, combined_accuracy, "1m")
            else:
                return {
                    "success": True,
                    "message": "مدل قبلی حفظ شد (بهبود کافی نبود)",
                    "accuracy": old_accuracy,
                    "improvement": improvement
                }
                
        except Exception as e:
            logger.error(f"❌ خطا در آموزش افزایشی: {e}")
            return {"success": False, "error": str(e)}
    
    def _evaluate(self, model, features, labels) -> float:
        """ارزیابی دقت مدل"""
        try:
            dtest = xgb.DMatrix(features)
            predictions = model.predict(dtest)
            pred_classes = (predictions > 0.5).astype(int)
            accuracy = np.mean(pred_classes == labels)
            return float(accuracy)
        except Exception as e:
            logger.error(f"❌ خطا در ارزیابی: {e}")
            return 0.0
    
    def _ensemble_models(self, model1, model2, weights=[0.5, 0.5]):
        """ترکیب دو مدل با وزن‌دهی"""
        class WeightedEnsemble:
            def __init__(self, models, weights):
                self.models = models
                self.weights = weights
            
            def predict(self, data):
                predictions = []
                for model, weight in zip(self.models, self.weights):
                    pred = model.predict(data) * weight
                    predictions.append(pred)
                return np.sum(predictions, axis=0)
        
        return WeightedEnsemble([model1, model2], weights)
    
    # ============================================================
    # ۴. مدیریت و آمار
    # ============================================================
    
    def get_stats(self) -> Dict:
        """دریافت آمار مدل جاری"""
        return {
            "loaded": self.current_model is not None,
            "version": self.current_version,
            "model_exists": os.path.exists(self.models_dir),
            "timestamp": datetime.now().isoformat()
        }
    
    def get_version_history(self, limit: int = 10) -> List[Dict]:
        """دریافت تاریخچه نسخه‌ها"""
        if not self.db or not self.db.is_connected():
            return []
        
        try:
            result = self.db.execute(
                """SELECT id, version, accuracy, training_date, is_active, is_ensemble
                   FROM models ORDER BY id DESC LIMIT %s""",
                (limit,)
            )
            return result
        except Exception as e:
            logger.error(f"❌ خطا در دریافت تاریخچه: {e}")
            return []
    
    def get_model_by_version(self, version: str) -> Optional[xgb.Booster]:
        """دریافت مدل با نسخه مشخص"""
        if not self.db or not self.db.is_connected():
            return None
        
        try:
            result = self.db.execute(
                "SELECT model_data FROM models WHERE version = %s",
                (version,)
            )
            if result:
                model_data = result[0]['model_data']
                temp_path = f"{self.models_dir}temp_{version}.xgb"
                with open(temp_path, "wb") as f:
                    f.write(model_data)
                model = xgb.Booster()
                model.load_model(temp_path)
                os.remove(temp_path)
                return model
        except Exception as e:
            logger.error(f"❌ خطا در دریافت مدل: {e}")
        return None
