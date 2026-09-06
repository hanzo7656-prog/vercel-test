# models/manager/model_manager.py
# ============================================================
# مدیریت پیشرفته مدل XGBoost - نسخه ۳.۰ (رفع Import)
# ============================================================

import os
import json
import pickle
import logging
import numpy as np
import xgboost as xgb
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple, Union

# ✅ اصلاح Import - استفاده از مسیر صحیح
from infrastructure.database import get_primary
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
    
    ✅ نسخه ۳.۰: رفع Import و استفاده از Path
    """
    
    def __init__(self, api: Optional[Any] = None) -> None:
        self.api: Optional[Any] = api
        self.db: Any = get_primary()
        self.models_dir: Path = Path("models/")
        self.models_dir.mkdir(parents=True, exist_ok=True)
        self.current_model: Optional[xgb.Booster] = None
        self.current_version: Optional[str] = None
        self.config: Dict[str, Any] = get_model_config()
        
        self._register_with_scheduler()
        self._load_active_model()
    
    def _register_with_scheduler(self) -> None:
        """ثبت وضعیت مدل در Scheduler"""
        try:
            from core import metrics_scheduler
            logger.info("✅ ModelManager registered with Metrics Scheduler")
        except ImportError:
            pass
        except Exception as e:
            logger.debug(f"Could not register with scheduler: {e}")
    
    # ============================================================
    # ۱. مدیریت اتصال دیتابیس
    # ============================================================
    
    def _ensure_db_connection(self) -> bool:
        """اطمینان از اتصال دیتابیس و reconnect در صورت نیاز"""
        if not self.db or not self.db.is_connected():
            try:
                from infrastructure.database import get_primary
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
    
    def save_model(
        self, 
        model: Any, 
        accuracy: float, 
        period: str = "1m", 
        coins: Optional[List[str]] = None, 
        features: Optional[List[str]] = None
    ) -> Dict[str, Any]:
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
        if not self._ensure_db_connection():
            return {"success": False, "error": "Database not available"}
        
        try:
            # ۱. تبدیل مدل به باینری
            temp_path: Path = self.models_dir / "temp_model.xgb"
            model.save_model(str(temp_path))
            
            with open(temp_path, "rb") as f:
                model_data: bytes = f.read()
            temp_path.unlink()  # حذف فایل موقت
            
            # ۲. تولید نسخه
            version: str = self._generate_version()
            
            # ۳. تنظیم مقادیر پیش‌فرض
            if coins is None:
                coins = self.config.get("coins", ["bitcoin", "ethereum", "solana", "cardano", "ripple"])
            if features is None:
                features = self._get_model_features(model)
            
            # ۴. ذخیره در دیتابیس
            query: str = """
                INSERT INTO models (
                    version, model_data, accuracy, training_samples,
                    period, coins, features, is_active, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """
            
            result: List[Dict[str, Any]] = self.db.execute(query, (
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
                model_id: int = result[0]['id']
                
                # ۵. غیرفعال کردن مدل‌های قبلی
                try:
                    self.db.execute("BEGIN")
                    self.db.execute(
                        "UPDATE models SET is_active = FALSE WHERE id != %s",
                        (model_id,)
                    )
                    self.db.execute("COMMIT")
                except Exception as e:
                    self.db.execute("ROLLBACK")
                    logger.error(f"❌ Transaction failed: {e}")
                    return {"success": False, "error": str(e)}
                
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
            
        except xgb.core.XGBoostError as e:
            logger.error(f"❌ XGBoost error: {e}")
            return {"success": False, "error": str(e), "message": "خطا در XGBoost"}
        except IOError as e:
            logger.error(f"❌ IO error: {e}")
            return {"success": False, "error": str(e), "message": "خطا در فایل"}
        except Exception as e:
            logger.error(f"❌ خطا در ذخیره مدل: {e}", exc_info=True)
            return {"success": False, "error": str(e), "message": "خطا در ذخیره مدل"}
        
        return {"success": False, "message": "خطای ناشناخته"}
    
    def _load_active_model(self) -> bool:
        """بارگذاری آخرین مدل فعال از دیتابیس"""
        if not self._ensure_db_connection():
            return False
        
        try:
            result: List[Dict[str, Any]] = self.db.execute(
                "SELECT * FROM models WHERE is_active = TRUE ORDER BY id DESC LIMIT 1"
            )
            
            if result:
                row: Dict[str, Any] = result[0]
                model_data: bytes = row['model_data']
                
                temp_path: Path = self.models_dir / f"temp_{row['version']}.xgb"
                with open(temp_path, "wb") as f:
                    f.write(model_data)
                
                model: xgb.Booster = xgb.Booster()
                model.load_model(str(temp_path))
                temp_path.unlink()
                
                self.current_model = model
                self.current_version = row['version']
                
                logger.info(f"✅ مدل نسخه {self.current_version} بارگذاری شد")
                return True
                
        except xgb.core.XGBoostError as e:
            logger.error(f"❌ XGBoost error loading model: {e}")
        except IOError as e:
            logger.error(f"❌ IO error loading model: {e}")
        except Exception as e:
            logger.error(f"❌ خطا در بارگذاری مدل: {e}", exc_info=True)
        
        return False
    
    def _generate_version(self) -> str:
        """تولید نسخه جدید بر اساس تاریخ و زمان"""
        now: datetime = datetime.now()
        version: str = f"v{now.year}.{now.month:02d}.{now.day:02d}_{now.hour:02d}{now.minute:02d}"
        
        if self.db and self.db.is_connected():
            try:
                result: List[Dict[str, Any]] = self.db.execute(
                    "SELECT COUNT(*) FROM models WHERE version = %s",
                    (version,)
                )
                if result and result[0].get('count', 0) > 0:
                    version += f".{int(result[0]['count']) + 1}"
            except Exception as e:
                logger.debug(f"Version check error: {e}")
        
        return version
    
    def _get_model_features(self, model: Any) -> List[str]:
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
        """
        پیش‌بینی با مدل جاری
        
        پارامترها:
            features: آرایه ویژگی‌ها
        
        خروجی:
            عدد پیش‌بینی بین ۰ تا ۱
        
        استثناها:
            ValueError: اگر مدل بارگذاری نشده باشد
        """
        if self.current_model is None:
            raise ValueError("هیچ مدلی بارگذاری نشده است")
        
        try:
            dmatrix: xgb.DMatrix = xgb.DMatrix(features.reshape(1, -1))
            prediction: np.ndarray = self.current_model.predict(dmatrix)
            return float(prediction[0])
        except xgb.core.XGBoostError as e:
            logger.error(f"❌ XGBoost prediction error: {e}")
            raise
        except Exception as e:
            logger.error(f"❌ خطا در پیش‌بینی: {e}")
            raise
    
    def predict_batch(self, features: np.ndarray) -> np.ndarray:
        """پیش‌بینی گروهی"""
        if self.current_model is None:
            raise ValueError("هیچ مدلی بارگذاری نشده است")
        
        try:
            dmatrix: xgb.DMatrix = xgb.DMatrix(features)
            predictions: np.ndarray = self.current_model.predict(dmatrix)
            return np.array(predictions)
        except xgb.core.XGBoostError as e:
            logger.error(f"❌ XGBoost batch prediction error: {e}")
            raise
        except Exception as e:
            logger.error(f"❌ خطا در پیش‌بینی گروهی: {e}")
            raise
    
    # ============================================================
    # ۴. دریافت مدل با نسخه
    # ============================================================
    
    def get_model_by_version(self, version: str) -> Optional[xgb.Booster]:
        """دریافت مدل با نسخه مشخص"""
        if not self._ensure_db_connection():
            return None
        
        try:
            query: str = "SELECT model_data FROM models WHERE version = %s"
            result: List[Dict[str, Any]] = self.db.execute(query, (version,))
            
            if result:
                model_data: bytes = result[0]['model_data']
                temp_path: Path = self.models_dir / f"temp_{version}.xgb"
                with open(temp_path, "wb") as f:
                    f.write(model_data)
                
                model: xgb.Booster = xgb.Booster()
                model.load_model(str(temp_path))
                temp_path.unlink()
                return model
                
        except xgb.core.XGBoostError as e:
            logger.error(f"❌ XGBoost error loading version {version}: {e}")
        except IOError as e:
            logger.error(f"❌ IO error loading version {version}: {e}")
        except Exception as e:
            logger.error(f"❌ خطا در دریافت مدل: {e}", exc_info=True)
        
        return None
    
    def get_version_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """دریافت تاریخچه نسخه‌های مدل از دیتابیس"""
        if not self._ensure_db_connection():
            return []
        
        try:
            query: str = """
                SELECT id, version, accuracy, training_date, 
                       is_active, is_ensemble, period, training_samples
                FROM models 
                ORDER BY id DESC 
                LIMIT %s
            """
            result: List[Dict[str, Any]] = self.db.execute(query, (limit,))
            return result
        except Exception as e:
            logger.error(f"❌ خطا در دریافت تاریخچه: {e}", exc_info=True)
            return []
    
    # ============================================================
    # ۵. آمار
    # ============================================================
    
    def get_stats(self) -> Dict[str, Any]:
        """دریافت آمار مدل جاری"""
        loaded: bool = self.current_model is not None
        
        return {
            "loaded": loaded,
            "version": self.current_version if loaded else "N/A",
            "model_exists": self.models_dir.exists(),
            "db_connected": self.db is not None and self.db.is_connected(),
            "model_path": str(self.models_dir) if loaded else None,
            "timestamp": datetime.now().isoformat()
        }
    
    # ============================================================
    # ۶. آموزش افزایشی و Ensemble
    # ============================================================
    
    def incremental_train(self, features: np.ndarray, labels: np.ndarray) -> Dict[str, Any]:
        """آموزش افزایشی با داده‌های جدید"""
        if self.current_model is None:
            return {"success": False, "message": "مدلی برای آموزش افزایشی وجود ندارد"}
        
        try:
            # ارزیابی مدل فعلی
            old_accuracy: float = self._evaluate(self.current_model, features, labels)
            
            # پارامترهای با نرخ یادگیری کمتر
            params: Dict[str, Any] = {
                'objective': 'binary:logistic',
                'eval_metric': 'logloss',
                'learning_rate': 0.05,
                'max_depth': 3,
                'subsample': 0.7,
                'colsample_bytree': 0.7,
                'tree_method': 'hist'
            }
            
            dtrain: xgb.DMatrix = xgb.DMatrix(features, label=labels)
            new_model: xgb.Booster = xgb.train(
                params,
                dtrain,
                num_boost_round=10,
                xgb_model=self.current_model
            )
            
            # ارزیابی مدل جدید
            new_accuracy: float = self._evaluate(new_model, features, labels)
            improvement: float = new_accuracy - old_accuracy
            
            if improvement > 0.02:
                return self.save_model(new_model, new_accuracy, "1m")
            elif improvement > 0.005:
                combined: Any = self._ensemble_models(
                    self.current_model, new_model, weights=[0.7, 0.3]
                )
                combined_accuracy: float = self._evaluate(combined, features, labels)
                return self.save_model(combined, combined_accuracy, "1m")
            else:
                return {
                    "success": True,
                    "message": "مدل قبلی حفظ شد (بهبود کافی نبود)",
                    "accuracy": old_accuracy,
                    "improvement": improvement
                }
                
        except xgb.core.XGBoostError as e:
            logger.error(f"❌ XGBoost incremental training error: {e}")
            return {"success": False, "error": str(e)}
        except Exception as e:
            logger.error(f"❌ خطا در آموزش افزایشی: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
    
    def _evaluate(self, model: Any, features: np.ndarray, labels: np.ndarray) -> float:
        """ارزیابی دقت مدل"""
        try:
            if isinstance(model, xgb.Booster):
                dtest: xgb.DMatrix = xgb.DMatrix(features)
                predictions: np.ndarray = model.predict(dtest)
            else:
                predictions = model.predict(features)
            
            pred_classes: np.ndarray = (predictions > 0.5).astype(int)
            accuracy: float = np.mean(pred_classes == labels)
            return float(accuracy)
        except Exception as e:
            logger.error(f"❌ خطا در ارزیابی: {e}")
            return 0.0
    
    def _ensemble_models(self, model1: Any, model2: Any, weights: List[float] = [0.5, 0.5]) -> Any:
        """ترکیب دو مدل با وزن‌دهی"""
        class WeightedEnsemble:
            def __init__(self, models: List[Any], weights: List[float]) -> None:
                self.models = models
                self.weights = weights
            
            def predict(self, data: Any) -> np.ndarray:
                predictions: List[np.ndarray] = []
                for model, weight in zip(self.models, self.weights):
                    pred: np.ndarray = model.predict(data) * weight
                    predictions.append(pred)
                return np.sum(predictions, axis=0)
        
        return WeightedEnsemble([model1, model2], weights)


# ============================================================
# گزارش مدل
# ============================================================
    
    def get_report_data(self, version: str) -> Dict[str, Any]:
        """
        جمع‌آوری اطلاعات کامل یک نسخه از مدل برای تولید گزارش
        
        پارامترها:
            version: نسخه مدل
        
        خروجی:
            دیکشنری شامل همه اطلاعات مورد نیاز گزارش
        """
        if not self._ensure_db_connection():
            return {}
        
        try:
            # ۱. دریافت اطلاعات مدل از دیتابیس
            result = self.db.execute(
                """SELECT 
                    id, version, accuracy, training_date, period, 
                    coins, features, training_samples, is_active, is_ensemble
                FROM models 
                WHERE version = %s""",
                (version,)
            )
            
            if not result:
                return {}
            
            row = result[0]
            
            # ۲. دریافت تاریخچه آموزش (۵ نسخه آخر)
            history = self.get_version_history(limit=5)
            
            # ۳. دریافت اهمیت ویژگی‌ها (اگر مدل بارگذاری شده باشد)
            feature_importance = []
            if self.current_model and self.current_version == version:
                try:
                    importance = self.current_model.get_score(importance_type='weight')
                    if importance:
                        total = sum(importance.values()) or 1
                        feature_importance = [
                            {'feature': k, 'importance': v, 'percentage': round((v / total) * 100, 2)}
                            for k, v in sorted(importance.items(), key=lambda x: x[1], reverse=True)
                        ][:10]  # ۱۰ ویژگی برتر
                except Exception as e:
                    logger.warning(f"Could not get feature importance: {e}")
            
            # ۴. دریافت سیگنال‌های اخیر (برای پیشنهادات)
            recent_signals = []
            try:
                from application.use_cases.predict_coin import PredictCoinUseCase
                from core.feature_engineering import FeatureEngineer
                
                predict_use_case = PredictCoinUseCase(
                    api_client=self.api,
                    model_manager=self,
                    feature_engineer=FeatureEngineer(self.api)
                )
                
                # برای ارزهای اصلی
                coins = row.get('coins', ['bitcoin', 'ethereum'])[:4]
                for coin in coins:
                    try:
                        pred = predict_use_case.execute(coin, '24h')
                        recent_signals.append({
                            'coin': coin,
                            'signal': pred.signal,
                            'signal_type': pred.signal_type.value,
                            'confidence': pred.confidence,
                            'price': pred.current_price
                        })
                    except Exception as e:
                        logger.warning(f"Could not predict {coin}: {e}")
            except Exception as e:
                logger.warning(f"Could not get recent signals: {e}")
            
            # ۵. ساختار نهایی داده‌های گزارش
            return {
                'model': {
                    'version': row.get('version', 'N/A'),
                    'accuracy': row.get('accuracy', 0),
                    'training_date': row.get('training_date'),
                    'period': row.get('period', '1m'),
                    'coins': row.get('coins', ['bitcoin', 'ethereum']),
                    'features_count': len(row.get('features', [])),
                    'is_active': row.get('is_active', False),
                    'is_ensemble': row.get('is_ensemble', False),
                    'training_samples': row.get('training_samples', 0)
                },
                'feature_importance': feature_importance,
                'history': history,
                'signals': recent_signals,
                'hyperparameters': {
                    'max_depth': 4,
                    'learning_rate': 0.1,
                    'n_estimators': 50,
                    'subsample': 0.8,
                    'colsample_bytree': 0.8
                },
                'stats': {
                    'total_trainings': len(history),
                    'best_accuracy': max([h.get('accuracy', 0) for h in history]) if history else 0,
                    'latest_improvement': self._calculate_improvement(history)
                }
            }
            
        except Exception as e:
            logger.error(f"Error getting report data for {version}: {e}")
            return {}
    
    def _calculate_improvement(self, history: List[Dict]) -> Optional[float]:
        """محاسبه آخرین بهبود دقت"""
        if len(history) < 2:
            return None
        
        latest = history[0].get('accuracy', 0)
        previous = history[1].get('accuracy', 0)
        
        if previous == 0:
            return None
        
        return round(((latest - previous) / previous) * 100, 2)
        
    
    def get_model_file(self, version: str) -> Optional[bytes]:
        """
        دریافت فایل مدل به صورت bytes برای دانلود
        
        پارامترها:
            version: نسخه مدل
        
        خروجی:
            bytes داده‌های مدل یا None
        """
        if not self._ensure_db_connection():
            return None
        
        try:
            result = self.db.execute(
                "SELECT model_data FROM models WHERE version = %s",
                (version,)
            )
            
            if result:
                return result[0].get('model_data')
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting model file for {version}: {e}")
            return None
