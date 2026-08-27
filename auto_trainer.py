# auto_trainer.py
# ============================================================
# سیستم آموزش خودکار مدل XGBoost - نسخه ۲.۱
# یکپارچه با Metrics Scheduler جدید
# ============================================================

import os
import sys
import time
import json
import logging
import numpy as np
import xgboost as xgb
from datetime import datetime, timedelta
from threading import Thread, Event
from typing import Dict, Any, Optional, List, Tuple

from api_handler import CoinStatsAPI
from model.manager.model_manager import ModelManager
from database import get_primary

logger = logging.getLogger(__name__)


class AutoTrainer:
    """
    سیستم آموزش خودکار مدل XGBoost با ذخیره‌سازی در دیتابیس
    
    ویژگی‌های جدید:
    - اتصال به ModelManager برای ذخیره در دیتابیس
    - نسخه‌سازی خودکار
    - آموزش افزایشی (Incremental Learning)
    - ترکیب با وزن‌دهی (Ensemble)
    - ارزیابی خودکار
    - ✅ یکپارچه با Metrics Scheduler
    """
    
    def __init__(self, api: CoinStatsAPI, model_manager: ModelManager):
        """
        راه‌اندازی سیستم آموزش خودکار
        
        پارامترها:
            api: نمونه CoinStatsAPI برای دریافت داده
            model_manager: نمونه ModelManager برای مدیریت مدل
        """
        self.api = api
        self.model_manager = model_manager
        self.db = get_primary()
        
        # وضعیت اجرا
        self.is_running = False
        self.is_training = False
        self.stop_event = Event()
        self.thread: Optional[Thread] = None
        
        # لیست لاگ‌ها
        self.logs: List[str] = []
        
        # ✅ رفع باگ: مسیر مدل
        self.model_path = "models/current_model.xgb"
        os.makedirs(os.path.dirname(self.model_path), exist_ok=True)
        
        # آمار سیستم
        self.stats = {
            "total_trainings": 0,
            "successful_trainings": 0,
            "failed_trainings": 0,
            "last_training": None,
            "last_error": None,
            "last_score": None,
            "data_points_used": 0,
            "api_status": "unknown",
            "credits_remaining": 0,
            "training_period": "1m",
            "mode": "DEMO"  # BETA یا DEMO
        }
        
        # ارزهای مورد استفاده برای آموزش
        self.coins = ["bitcoin", "ethereum", "solana", "cardano", "ripple"]
        
        # نام ویژگی‌ها
        self.feature_names = [
            "return_1", "return_3", "return_5", "return_10",
            "sma_5", "sma_10", "sma_20",
            "volatility",
            "fear_greed",
            "trend_5", "trend_10", "trend_20",
            "r2"
        ]
        
        # ✅ جدید: ثبت در Scheduler
        self._register_with_scheduler()
        
        # بروزرسانی وضعیت از ModelManager
        if self.model_manager.current_model is not None:
            self.stats["mode"] = "BETA"
            self._add_log(f"✅ مدل موجود است (حالت BETA) - نسخه: {self.model_manager.current_version}")
        else:
            self._add_log(f"📦 مدل یافت نشد (حالت DEMO)")
        
        self._add_log("✅ AutoTrainer ۲.۱ راه‌اندازی شد")
    
    def _register_with_scheduler(self):
        """✅ جدید: ثبت وضعیت مدل در Scheduler"""
        try:
            from core import metrics_scheduler
            # Scheduler به صورت خودکار model_status را جمع‌آوری می‌کند
            logger.info("✅ AutoTrainer registered with Metrics Scheduler")
        except ImportError:
            pass
        except Exception as e:
            logger.debug(f"Could not register with scheduler: {e}")
    
    # ============================================================
    # مدیریت لاگ‌ها
    # ============================================================
    
    def _add_log(self, message: str):
        """ثبت لاگ با زمان"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] {message}"
        self.logs.append(log_entry)
        if len(self.logs) > 200:
            self.logs = self.logs[-200:]
        logger.info(message)
    
    def clear_logs(self):
        """پاک کردن لاگ‌ها"""
        self.logs = []
        self._add_log("🗑️ لاگ‌ها پاک شدند")
    
    def get_logs(self) -> List[str]:
        """دریافت لاگ‌ها"""
        return self.logs
    
    # ============================================================
    # مدیریت وضعیت API
    # ============================================================
    
    def check_api_status(self) -> Dict[str, Any]:
        """بررسی وضعیت API و اعتبار باقیمانده"""
        try:
            status = self.api.get_status()
            api_ok = status and status.get('status') == 'ok'
            
            credits = self.api.get_credits()
            if credits and 'remainingCredits' in credits:
                remaining = credits.get('remainingCredits', 0)
                self.stats["credits_remaining"] = remaining
                if remaining < 100:
                    self._add_log(f"⚠️ اعتبار باقیمانده کم است: {remaining}")
            else:
                remaining = 0
            
            self.stats["api_status"] = "ok" if api_ok else "error"
            
            return {
                "api_status": "ok" if api_ok else "error",
                "credits_remaining": remaining,
                "can_train": api_ok and remaining > 100,
                "message": "API سالم است" if api_ok else "API در دسترس نیست"
            }
        except Exception as e:
            self.stats["api_status"] = "error"
            self._add_log(f"❌ Error checking API: {e}")
            return {
                "api_status": "error",
                "credits_remaining": 0,
                "can_train": False,
                "message": f"خطا: {str(e)}"
            }
    
    # ============================================================
    # دریافت و پردازش داده
    # ============================================================
    
    def fetch_data_for_coin(self, coin_id: str, period: str = "1m") -> List[List]:
        """دریافت داده‌های تاریخی برای یک ارز"""
        try:
            data = self.api.get_chart(coin_id, period)
            if data and isinstance(data, list) and len(data) > 0:
                self._add_log(f"✅ دریافت {len(data)} نقطه برای {coin_id} ({period})")
                return data
            return []
        except Exception as e:
            self._add_log(f"❌ خطا در دریافت داده برای {coin_id}: {e}")
            return []
    
    def extract_features_for_training(self, chart_data: List[List]) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
        """استخراج ویژگی‌ها و لیبل‌ها از داده‌های قیمت"""
        if not chart_data or len(chart_data) < 30:
            return None, None
        
        prices = []
        for point in chart_data:
            if isinstance(point, list) and len(point) >= 2:
                prices.append(float(point[1]))
        
        if len(prices) < 30:
            return None, None
        
        prices = np.array(prices, dtype=np.float32)
        features_list = []
        labels_list = []
        
        for i in range(20, len(prices) - 5):
            window = prices[i-20:i+1]
            current_price = prices[i]
            future_price = prices[i+3]
            
            label = 1 if future_price > current_price else 0
            features = []
            
            # 1. بازده‌ها
            for lag in [1, 3, 5]:
                if len(window) > lag:
                    ret = (window[-1] - window[-lag-1]) / (window[-lag-1] + 1e-8)
                    features.append(np.clip(ret, -0.5, 0.5))
                else:
                    features.append(0.0)
            
            # 2. میانگین متحرک
            for w in [5, 10]:
                if len(window) >= w:
                    sma = np.mean(window[-w:])
                    ratio = window[-1] / (sma + 1e-8) - 1
                    features.append(np.clip(ratio, -0.5, 0.5))
                else:
                    features.append(0.0)
            
            # 3. نوسان
            if len(window) >= 10:
                returns = np.diff(window[-10:]) / (window[-10:-1] + 1e-8)
                volatility = np.std(returns)
                features.append(np.clip(volatility, 0, 0.5))
            else:
                features.append(0.0)
            
            # 4. شاخص ترس و طمع
            try:
                fg = self.api.get_fear_greed(use_cache=True)
                if fg and 'now' in fg:
                    fear_value = fg['now'].get('value', 50)
                    features.append(fear_value / 100.0)
                else:
                    features.append(0.5)
            except:
                features.append(0.5)
            
            # 5. شیب قیمت (روند)
            for w in [5, 10]:
                if len(window) >= w:
                    slope = np.polyfit(range(w), window[-w:], 1)[0]
                    slope_norm = slope / (window[-1] + 1e-8) * 100
                    features.append(np.clip(slope_norm, -10, 10))
                else:
                    features.append(0.0)
            
            # 6. قدرت روند (R-squared)
            if len(window) >= 10:
                x = np.arange(10)
                y = window[-10:]
                slope, intercept = np.polyfit(x, y, 1)
                y_pred = slope * x + intercept
                ss_tot = np.sum((y - np.mean(y)) ** 2)
                ss_res = np.sum((y - y_pred) ** 2)
                r2 = 1 - (ss_res / (ss_tot + 1e-8))
                features.append(np.clip(r2, -1, 1))
            else:
                features.append(0.0)
            
            features_list.append(features)
            labels_list.append(label)
        
        return np.array(features_list, dtype=np.float32), np.array(labels_list, dtype=np.int32)
    
    def _get_training_coins(self) -> List[str]:
        """دریافت لیست ارزهای مورد استفاده برای آموزش"""
        return self.coins
    
    # ============================================================
    # ارزیابی مدل
    # ============================================================
    
    def _evaluate_model(self, model, features, labels) -> float:
        """ارزیابی دقت مدل روی داده‌های تست"""
        try:
            if isinstance(model, xgb.Booster):
                dtest = xgb.DMatrix(features)
                predictions = model.predict(dtest)
            else:
                # Ensemble یا مدل سفارشی
                predictions = model.predict(features)
            
            pred_classes = (predictions > 0.5).astype(int)
            accuracy = np.mean(pred_classes == labels)
            return float(accuracy)
        except Exception as e:
            logger.error(f"❌ خطا در ارزیابی: {e}")
            return 0.0
    
    # ============================================================
    # آموزش مدل
    # ============================================================
    
    def train_model(self, period: str = "1m") -> Dict[str, Any]:
        """
        آموزش مدل XGBoost با داده‌های جدید و ذخیره در دیتابیس
        
        پارامترها:
            period: بازه زمانی (1w, 1m, 3m, 6m)
        
        خروجی:
            دیکشنری شامل نتایج آموزش
        """
        if self.is_training:
            return {"success": False, "message": "آموزش در حال انجام است"}
        
        # بررسی وضعیت API
        status = self.check_api_status()
        if not status["can_train"]:
            return {
                "success": False,
                "message": status["message"],
                "api_status": status["api_status"],
                "credits_remaining": status["credits_remaining"]
            }
        
        self.is_training = True
        self.stats["total_trainings"] += 1
        self.stats["training_period"] = period
        self._add_log(f"📚 شروع آموزش با بازه: {period}")
        
        result = {"success": False, "message": "خطای ناشناخته"}
        
        try:
            all_features = []
            all_labels = []
            total_points = 0
            
            # دریافت داده از همه ارزها
            for coin in self.coins:
                self._add_log(f"🪙 دریافت {coin} ({period})...")
                chart_data = self.fetch_data_for_coin(coin, period)
                if not chart_data:
                    self._add_log(f"   ⚠️ داده‌ای برای {coin} یافت نشد")
                    continue
                
                features, labels = self.extract_features_for_training(chart_data)
                if features is not None and len(features) > 0:
                    all_features.append(features)
                    all_labels.append(labels)
                    total_points += len(features)
                    self._add_log(f"   ✅ {len(features)} نمونه از {coin}")
            
            if not all_features:
                result = {
                    "success": False,
                    "message": "داده‌ای برای آموزش یافت نشد"
                }
                self.stats["failed_trainings"] += 1
                self._add_log("❌ داده‌ای برای آموزش یافت نشد")
                return result
            
            # ترکیب داده‌ها
            X = np.vstack(all_features)
            y = np.concatenate(all_labels)
            
            self._add_log(f"📊 کل نمونه‌های آموزش: {len(X)}")
            self.stats["data_points_used"] = len(X)
            
            # آموزش مدل جدید
            self._add_log("🧠 آموزش مدل XGBoost...")
            start_time = time.time()
            
            model = xgb.XGBClassifier(
                n_estimators=50,
                max_depth=4,
                learning_rate=0.1,
                tree_method='hist',
                random_state=42,
                objective='binary:logistic',
                eval_metric='logloss',
                subsample=0.8,
                colsample_bytree=0.8,
            )
            
            model.fit(X, y)
            training_time = time.time() - start_time
            
            # ✅ رفع باگ: ذخیره مدل با مسیر صحیح
            model.save_model(self.model_path, format='json')
            
            # ارزیابی
            score = model.score(X, y)
            self.stats["last_score"] = round(score, 3)
            self._add_log(f"📊 دقت مدل جدید: {score:.3f}")
            
            # مقایسه با مدل قبلی (اگر وجود داشته باشد)
            old_score = None
            if self.model_manager.current_model is not None:
                old_score = self._evaluate_model(
                    self.model_manager.current_model, 
                    X, 
                    y
                )
                self._add_log(f"📊 دقت مدل قبلی: {old_score:.3f}")
            
            # تصمیم‌گیری: ذخیره یا نگهداری
            if old_score is not None and (score - old_score) < 0.01:
                # بهبود کمتر از ۱٪ - نگهداری مدل قبلی
                self._add_log(f"⚠️ بهبود ناچیز ({((score - old_score)*100):.1f}%) - مدل قبلی حفظ می‌شود")
                result = {
                    "success": True,
                    "message": "مدل قبلی حفظ شد (بهبود کافی نبود)",
                    "accuracy": old_score,
                    "new_accuracy": score,
                    "improvement": score - old_score,
                    "samples": len(X),
                    "training_time": round(training_time, 2)
                }
                self.stats["successful_trainings"] += 1
                return result
            
            # ذخیره مدل در دیتابیس
            self._add_log(f"💾 ذخیره مدل در دیتابیس...")
            save_result = self.model_manager.save_model(
                model,
                score,
                period
            )
            
            if save_result.get("success"):
                self.stats["successful_trainings"] += 1
                self.stats["last_training"] = datetime.now().isoformat()
                self.stats["last_error"] = None
                self.stats["mode"] = "BETA"
                
                self._add_log(f"✅ مدل ذخیره شد! نسخه: {save_result.get('version')}")
                
                result = {
                    "success": True,
                    "message": "مدل با موفقیت آموزش دید و ذخیره شد",
                    "accuracy": score,
                    "old_accuracy": old_score,
                    "improvement": score - old_score if old_score else None,
                    "samples": len(X),
                    "training_time": round(training_time, 2),
                    "version": save_result.get('version'),
                    "model_id": save_result.get('model_id')
                }
            else:
                self.stats["failed_trainings"] += 1
                self.stats["last_error"] = save_result.get('error', 'خطای ناشناخته')
                result = {
                    "success": False,
                    "message": f"خطا در ذخیره مدل: {save_result.get('error', 'ناشناخته')}"
                }
            
        except Exception as e:
            self._add_log(f"❌ آموزش ناموفق: {e}")
            self.stats["failed_trainings"] += 1
            self.stats["last_error"] = str(e)
            result = {
                "success": False,
                "message": f"خطا در آموزش: {str(e)}"
            }
        finally:
            self.is_training = False
        
        return result
    
    # ============================================================
    # آموزش افزایشی (Incremental Learning)
    # ============================================================
    
    def incremental_train(self, period: str = "1m") -> Dict[str, Any]:
        """
        آموزش افزایشی: مدل فعلی را با داده‌های جدید به‌روز می‌کند
        
        استراتژی:
        1. داده‌های جدید را دریافت کن
        2. مدل فعلی را با داده‌های جدید آموزش بده (با نرخ یادگیری کمتر)
        3. دقت مدل جدید رو با قبلی مقایسه کن
        4. اگر بهتر شد، جایگزین کن
        """
        if not self.model_manager.current_model:
            self._add_log("⚠️ مدلی برای آموزش افزایشی وجود ندارد - انجام آموزش کامل")
            return self.train_model(period)
        
        if self.is_training:
            return {"success": False, "message": "آموزش در حال انجام است"}
        
        self.is_training = True
        self._add_log(f"📚 شروع آموزش افزایشی با بازه: {period}")
        
        try:
            # دریافت داده‌های جدید
            all_features = []
            all_labels = []
            
            for coin in self.coins:
                chart_data = self.fetch_data_for_coin(coin, period)
                if not chart_data:
                    continue
                features, labels = self.extract_features_for_training(chart_data)
                if features is not None and len(features) > 0:
                    all_features.append(features)
                    all_labels.append(labels)
            
            if not all_features:
                self.is_training = False
                return {"success": False, "message": "داده‌ای برای آموزش افزایشی یافت نشد"}
            
            X = np.vstack(all_features)
            y = np.concatenate(all_labels)
            
            # ارزیابی مدل فعلی
            old_accuracy = self._evaluate_model(self.model_manager.current_model, X, y)
            self._add_log(f"📊 دقت مدل فعلی روی داده‌های جدید: {old_accuracy:.3f}")
            
            # آموزش افزایشی با نرخ یادگیری کمتر
            dtrain = xgb.DMatrix(X, label=y)
            params = {
                'objective': 'binary:logistic',
                'eval_metric': 'logloss',
                'learning_rate': 0.05,  # کمتر از حالت عادی
                'max_depth': 3,
                'subsample': 0.7,
                'colsample_bytree': 0.7,
                'tree_method': 'hist'
            }
            
            new_model = xgb.train(
                params,
                dtrain,
                num_boost_round=10,
                xgb_model=self.model_manager.current_model
            )
            
            # ارزیابی مدل جدید
            new_accuracy = self._evaluate_model(new_model, X, y)
            improvement = new_accuracy - old_accuracy
            self._add_log(f"📊 دقت مدل جدید: {new_accuracy:.3f} (بهبود: {improvement*100:.1f}%)")
            
            if improvement > 0.02:
                # بهبود > ۲٪ - جایگزینی کامل
                self._add_log(f"✅ بهبود قابل توجه! ذخیره مدل جدید")
                result = self.model_manager.save_model(new_model, new_accuracy, period)
                self.is_training = False
                return {
                    "success": True,
                    "message": "مدل جدید با بهبود قابل توجه ذخیره شد",
                    "accuracy": new_accuracy,
                    "old_accuracy": old_accuracy,
                    "improvement": improvement,
                    "version": result.get('version')
                }
            elif improvement > 0.005:
                # بهبود ۰.۵-۲٪ - ترکیب با وزن‌دهی
                self._add_log(f"🔄 بهبود متوسط - ترکیب با مدل قبلی")
                combined_model = self._create_weighted_ensemble(
                    self.model_manager.current_model, 
                    new_model, 
                    weights=[0.7, 0.3]
                )
                combined_accuracy = self._evaluate_model(combined_model, X, y)
                result = self.model_manager.save_model(combined_model, combined_accuracy, period)
                self.is_training = False
                return {
                    "success": True,
                    "message": "مدل ترکیبی (Ensemble) ذخیره شد",
                    "accuracy": combined_accuracy,
                    "old_accuracy": old_accuracy,
                    "improvement": combined_accuracy - old_accuracy,
                    "version": result.get('version')
                }
            else:
                self._add_log(f"⚠️ بهبود ناچیز - مدل قبلی حفظ می‌شود")
                self.is_training = False
                return {
                    "success": True,
                    "message": "مدل قبلی حفظ شد (بهبود کافی نبود)",
                    "accuracy": old_accuracy,
                    "new_accuracy": new_accuracy,
                    "improvement": improvement
                }
                
        except Exception as e:
            self._add_log(f"❌ خطا در آموزش افزایشی: {e}")
            self.is_training = False
            return {"success": False, "error": str(e)}
    
    def _create_weighted_ensemble(self, model1, model2, weights=[0.5, 0.5]):
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
    # دریافت آمار و اطلاعات
    # ============================================================
    
    def get_stats(self) -> Dict[str, Any]:
        """دریافت آمار کامل سیستم"""
        status = self.check_api_status()
        
        # دریافت اطلاعات از ModelManager
        model_stats = self.model_manager.get_stats() if self.model_manager else {}
        
        return {
            "is_running": self.is_running,
            "is_training": self.is_training,
            "stats": self.stats,
            "api_status": status,
            "coins": self.coins,
            "model_exists": model_stats.get('loaded', False),
            "current_version": self.model_manager.current_version if self.model_manager else None,
            "logs": self.logs[-30:],
            "timestamp": datetime.now().isoformat()
        }
    
    def get_training_history(self, period: str = None) -> List[Dict[str, Any]]:
        """دریافت سابقه آموزش از دیتابیس"""
        if not self.db or not self.db.is_connected():
            return []
        
        try:
            query = """
                SELECT 
                    m.id, m.version, m.accuracy, m.training_date,
                    m.period, m.training_samples, m.is_ensemble,
                    h.action, h.old_accuracy, h.new_accuracy, h.improvement_percent
                FROM models m
                LEFT JOIN model_training_history h ON m.id = h.model_id
                WHERE m.is_ensemble = FALSE
                ORDER BY m.training_date DESC
                LIMIT 50
            """
            
            if period:
                query = query.replace("WHERE", f"WHERE m.period = '{period}' AND")
            
            result = self.db.execute(query)
            return result
        except Exception as e:
            logger.error(f"❌ خطا در دریافت تاریخچه: {e}")
            return []
    
    # ============================================================
    # اجرای خودکار
    # ============================================================
    
    def start_auto_train(self, interval_hours: int = 6, period: str = "1m", incremental: bool = True):
        """
        شروع آموزش خودکار با فاصله زمانی مشخص
        
        پارامترها:
            interval_hours: فاصله زمانی بین آموزش‌ها (ساعت)
            period: بازه زمانی داده‌ها
            incremental: آیا از آموزش افزایشی استفاده شود؟
        """
        if self.is_running:
            return {"success": False, "message": "سیستم در حال اجراست"}
        
        self.is_running = True
        self.stop_event.clear()
        self.stats["training_period"] = period
        
        def run():
            self._add_log(f"🔄 آموزش خودکار شروع شد (فاصله: {interval_hours}h, بازه: {period})")
            
            while not self.stop_event.is_set():
                try:
                    # آموزش با روش انتخابی
                    if incremental and self.model_manager.current_model is not None:
                        result = self.incremental_train(period)
                    else:
                        result = self.train_model(period)
                    
                    self._add_log(f"📊 نتیجه آموزش: {result.get('message', 'نامشخص')}")
                    
                except Exception as e:
                    self._add_log(f"❌ خطا در چرخه آموزش: {e}")
                
                # ✅ بهبود: استفاده از Event.wait به جای حلقه ۶ ساعته
                # انتظار به مدت interval_hours ساعت یا تا زمان توقف
                wait_seconds = interval_hours * 3600
                self.stop_event.wait(wait_seconds)
            
            self.is_running = False
            self._add_log("⏹️ آموزش خودکار متوقف شد")
        
        self.thread = Thread(target=run, daemon=True)
        self.thread.start()
        
        return {
            "success": True,
            "message": f"آموزش خودکار شروع شد (هر {interval_hours} ساعت)",
            "interval_hours": interval_hours,
            "period": period,
            "incremental": incremental
        }
    
    def stop_auto_train(self):
        """متوقف کردن آموزش خودکار"""
        if not self.is_running:
            return {"success": False, "message": "سیستم در حال اجرا نیست"}
        
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=5)
        self.is_running = False
        self._add_log("⏹️ آموزش خودکار توسط کاربر متوقف شد")
        return {"success": True, "message": "آموزش خودکار متوقف شد"}
