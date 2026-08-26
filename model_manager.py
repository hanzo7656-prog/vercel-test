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
    # ۱. مدیریت اتصال دیتابیس (NEW)
    # ============================================================
    
    def _ensure_db_connection(self) -> bool:
        """اطمینان از اتصال دیتابیس و reconnect در صورت نیاز"""
        if not self.db or not self.db.is_connected():
            try:
                from database import get_primary
                self.db = get_primary()
                if self.db and self.db.is_connected():
                    logger.info("✅ دیتابیس reconnect شد")
                    return True
                else:
                    logger.warning("❌ reconnect دیتابیس ناموفق")
                    return False
            except Exception as e:
                logger.error(f"❌ خطا در reconnect: {e}")
                return False
        return True
    
    # ============================================================
    # ۲. ذخیره و بازیابی مدل
    # ============================================================
    
    def save_model(self, model, accuracy: float, period: str = "1m", 
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
        # ✅ قبل از هر کاری، اطمینان از اتصال
        if not self._ensure_db_connection():
            return self._save_local(model, accuracy, period)
        
        try:
            # ۱. تبدیل مدل به باینری (با فرمت JSON)
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
                
                logger.info(f"✅ مدل نسخه {version} با دقت {accuracy:.3f} ذخیره شد")
                
                return {
                    "success": True,
                    "version": version,
                    "model_id": model_id,
                    "accuracy": accuracy,
                    "message": f"مدل نسخه {version} ذخیره شد"
                }
            
        except Exception as e:
            logger.error(f"❌ خطا در ذخیره مدل: {e}")
            return {"success": False, "error": str(e), "message": "خطا در ذخیره مدل"}
        
        return {"success": False, "message": "خطای ناشناخته"}
    
    def _load_active_model(self) -> bool:
        """بارگذاری آخرین مدل فعال از دیتابیس"""
        if not self.db or not self.db.is_connected():
            return self._load_local()
        
        try:
            # ✅ اطمینان از اتصال قبل از کوئری
            if not self._ensure_db_connection():
                return self._load_local()
            
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
        
        # بررسی تکراری نبودن
        if self.db and self.db.is_connected():
            try:
                result = self.db.execute(
                    "SELECT COUNT(*) FROM models WHERE version = %s",
                    (version,)
                )
                if result and result[0].get('count', 0) > 0:
                    version += f".{int(result[0]['count']) + 1}"
            except:
                pass
        
        return version
    
    def _save_local(self, model, accuracy, period) -> Dict:
        """ذخیره محلی (در صورت عدم دسترسی به دیتابیس)"""
        version = f"local_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        path = f"{self.models_dir}{version}.xgb"
        model.save_model(path, format='json')
        
        self.current_model = model
        self.current_version = version
        
        logger.info(f"✅ مدل به صورت محلی ذخیره شد: {path}")
        
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
        return self.config.get("features", [
            "return_1", "return_3", "return_5", "return_10",
            "sma_5", "sma_10", "sma_20", "volatility",
            "fear_greed", "trend_5", "trend_10", "trend_20", "r2"
        ])
    
    # ============================================================
    # ۳. پیش‌بینی
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
    # ۴. دریافت مدل با نسخه
    # ============================================================
    
    def get_model_by_version(self, version: str) -> Optional[xgb.Booster]:
        """دریافت مدل با نسخه مشخص"""
        if not self.db or not self.db.is_connected():
            return None
        
        try:
            # ✅ اطمینان از اتصال
            if not self._ensure_db_connection():
                return None
            
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
    
    def get_version_history(self, limit: int = 10) -> List[Dict]:
        """دریافت تاریخچه نسخه‌های مدل از دیتابیس"""
        if not self.db or not self.db.is_connected():
            return []
        
        try:
            # ✅ اطمینان از اتصال
            if not self._ensure_db_connection():
                return []
            
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
    
    # ============================================================
    # ۵. آمار
    # ============================================================
    
    def get_stats(self) -> Dict[str, Any]:
        """دریافت آمار مدل جاری"""
        # ✅ استفاده از model_manager به جای model_loaded
        loaded = self.current_model is not None
        
        return {
            "loaded": loaded,
            "version": self.current_version if loaded else "N/A",
            "model_exists": os.path.exists(self.models_dir),
            "db_connected": self.db is not None and self.db.is_connected(),
            "timestamp": datetime.now().isoformat()
        }
    
    # ============================================================
    # ۶. آموزش افزایشی و Ensemble
    # ============================================================
    
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
                # بهبود > ۲٪ - جایگزینی کامل
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
            if isinstance(model, xgb.Booster):
                dtest = xgb.DMatrix(features)
                predictions = model.predict(dtest)
            else:
                predictions = model.predict(features)
            
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
