# auto_trainer.py
# ============================================================
# سیستم آموزش خودکار مدل XGBoost
# شامل: دریافت داده، ساخت ویژگی، آموزش، ذخیره مدل، مدیریت اعتبار و وضعیت API
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
from typing import Dict, Any, Optional, List

from api_handler import CoinStatsAPI

logger = logging.getLogger(__name__)


# ============================================================
# آموزش‌دهنده خودکار
# ============================================================

class AutoTrainer:
    """
    سیستم آموزش خودکار مدل XGBoost
    
    ویژگی‌ها:
    - دریافت داده از API
    - ساخت ویژگی‌ها
    - ساخت برچسب هدف
    - آموزش مدل
    - ذخیره مدل
    - مدیریت اعتبار
    - بررسی وضعیت API
    - دکمه روشن/خاموش
    """
    
    def __init__(self, api: CoinStatsAPI, model_path: str = "model.json"):
        self.api = api
        self.model_path = model_path
        self.is_running = False
        self.is_training = False
        self.stop_event = Event()
        self.thread: Optional[Thread] = None
        
        # آمار
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
        }
        
        # ارزهای مورد نظر برای آموزش
        self.coins = ["bitcoin", "ethereum", "solana", "cardano", "ripple"]
        
        # ویژگی‌های مدل
        self.feature_names = [
            "return_1", "return_3", "return_5", "return_10",
            "sma_5", "sma_10", "sma_20",
            "volatility",
            "fear_greed",
            "trend_5", "trend_10", "trend_20",
            "r2"
        ]
        
        logger.info("✅ AutoTrainer initialized")
    
    # ============================================================
    # مدیریت وضعیت API و اعتبار
    # ============================================================
    
    def check_api_status(self) -> Dict[str, Any]:
        """بررسی وضعیت API و اعتبار باقیمانده"""
        try:
            # 1. وضعیت API
            status = self.api.get_status()
            api_ok = status and status.get('status') == 'ok'
            
            # 2. اعتبار
            credits = self.api.get_credits()
            if credits and 'remainingCredits' in credits:
                remaining = credits.get('remainingCredits', 0)
                total = credits.get('totalCredits', 0)
                used = credits.get('usedCredits', 0)
                
                self.stats["credits_remaining"] = remaining
                
                # هشدار کمبود اعتبار
                if remaining < 100:
                    logger.warning(f"⚠️ اعتبار باقیمانده کم است: {remaining}")
            else:
                remaining = 0
                total = 0
                used = 0
            
            self.stats["api_status"] = "ok" if api_ok else "error"
            
            return {
                "api_status": "ok" if api_ok else "error",
                "credits_remaining": remaining,
                "credits_total": total,
                "credits_used": used,
                "can_train": api_ok and remaining > 100,
                "message": "API سالم است" if api_ok else "API در دسترس نیست"
            }
            
        except Exception as e:
            logger.error(f"❌ Error checking API status: {e}")
            self.stats["api_status"] = "error"
            return {
                "api_status": "error",
                "credits_remaining": 0,
                "credits_total": 0,
                "credits_used": 0,
                "can_train": False,
                "message": f"خطا: {str(e)}"
            }
    
    # ============================================================
    # دریافت و پردازش داده
    # ============================================================
    
    def fetch_data_for_coin(self, coin_id: str, period: str = "1m") -> List[List]:
        """
        دریافت داده‌های تاریخی برای یک ارز
        period: 1m, 3m, 6m, 1y, all
        """
        try:
            data = self.api.get_chart(coin_id, period)
            if data and isinstance(data, list) and len(data) > 0:
                logger.info(f"✅ Fetched {len(data)} points for {coin_id}")
                return data
            return []
        except Exception as e:
            logger.error(f"❌ Error fetching data for {coin_id}: {e}")
            return []
    
    def extract_features_for_training(self, chart_data: List[List]) -> tuple:
        """
        استخراج ویژگی‌ها و برچسب‌ها برای آموزش
        """
        if not chart_data or len(chart_data) < 50:
            return None, None
        
        prices = []
        for point in chart_data:
            if isinstance(point, list) and len(point) >= 2:
                prices.append(float(point[1]))
        
        if len(prices) < 50:
            return None, None
        
        prices = np.array(prices, dtype=np.float32)
        features_list = []
        labels_list = []
        
        # برای هر نقطه، ویژگی‌ها و برچسب رو بساز
        for i in range(30, len(prices) - 10):
            window = prices[i-30:i]
            current_price = prices[i]
            future_price = prices[i+5]  # ۵ قدم بعد
            
            # برچسب: ۱ اگر قیمت بالا رفته، ۰ اگر پایین
            label = 1 if future_price > current_price else 0
            
            # ویژگی‌ها
            features = []
            
            # 1. بازده‌ها
            for lag in [1, 3, 5, 10]:
                if len(window) > lag:
                    ret = (window[-1] - window[-lag-1]) / (window[-lag-1] + 1e-8)
                    features.append(np.clip(ret, -0.5, 0.5))
                else:
                    features.append(0.0)
            
            # 2. میانگین متحرک
            for w in [5, 10, 20]:
                if len(window) >= w:
                    sma = np.mean(window[-w:])
                    ratio = window[-1] / (sma + 1e-8) - 1
                    features.append(np.clip(ratio, -0.5, 0.5))
                else:
                    features.append(0.0)
            
            # 3. نوسان
            if len(window) >= 15:
                returns = np.diff(window[-15:]) / (window[-15:-1] + 1e-8)
                volatility = np.std(returns)
                features.append(np.clip(volatility, 0, 0.5))
            else:
                features.append(0.0)
            
            # 4. ترس و طمع (میانگین)
            try:
                fg = self.api.get_fear_greed(use_cache=True)
                if fg and 'now' in fg:
                    fear_value = fg['now'].get('value', 50)
                    features.append(fear_value / 100.0)
                else:
                    features.append(0.5)
            except:
                features.append(0.5)
            
            # 5. روند
            for w in [5, 10, 20]:
                if len(window) >= w:
                    slope = np.polyfit(range(w), window[-w:], 1)[0]
                    slope_norm = slope / (window[-1] + 1e-8) * 100
                    features.append(np.clip(slope_norm, -10, 10))
                else:
                    features.append(0.0)
            
            # 6. R-squared
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
    
    # ============================================================
    # آموزش مدل
    # ============================================================
    
    def train_model(self) -> Dict[str, Any]:
        """
        اجرای فرآیند آموزش کامل
        """
        if self.is_training:
            return {"success": False, "message": "آموزش در حال انجام است"}
        
        # بررسی وضعیت API و اعتبار
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
        
        try:
            logger.info("📚 Starting training process...")
            
            all_features = []
            all_labels = []
            total_points = 0
            
            # 1. دریافت داده برای همه ارزها
            for coin in self.coins:
                logger.info(f"🪙 Fetching data for {coin}...")
                chart_data = self.fetch_data_for_coin(coin, "1m")
                
                if not chart_data:
                    continue
                
                features, labels = self.extract_features_for_training(chart_data)
                
                if features is not None and len(features) > 0:
                    all_features.append(features)
                    all_labels.append(labels)
                    total_points += len(features)
                    logger.info(f"   ✅ {len(features)} samples from {coin}")
            
            if not all_features:
                self.is_training = False
                self.stats["failed_trainings"] += 1
                return {"success": False, "message": "داده‌ای برای آموزش یافت نشد"}
            
            # 2. ترکیب داده‌ها
            X = np.vstack(all_features)
            y = np.concatenate(all_labels)
            
            logger.info(f"📊 Total training samples: {len(X)}")
            self.stats["data_points_used"] = len(X)
            
            # 3. آموزش مدل
            logger.info("🧠 Training XGBoost model...")
            model = xgb.XGBClassifier(
                n_estimators=50,        # ۵۰ درخت
                max_depth=4,            # عمق ۴
                learning_rate=0.1,
                tree_method='hist',     # سبک و سریع
                random_state=42,
                objective='binary:logistic',
                eval_metric='logloss',
                subsample=0.8,
                colsample_bytree=0.8,
            )
            
            start_time = time.time()
            model.fit(X, y)
            training_time = time.time() - start_time
            
            # 4. ارزیابی ساده
            score = model.score(X, y)  # دقت روی داده‌های آموزشی
            self.stats["last_score"] = round(score, 3)
            
            # 5. ذخیره مدل
            model.save_model(self.model_path)
            
            # 6. به‌روزرسانی آمار
            self.stats["successful_trainings"] += 1
            self.stats["last_training"] = datetime.now().isoformat()
            self.stats["last_error"] = None
            
            logger.info(f"✅ Model saved successfully! Accuracy: {score:.3f}, Time: {training_time:.2f}s")
            
            return {
                "success": True,
                "message": f"مدل با موفقیت آموزش دید",
                "accuracy": round(score, 3),
                "samples": len(X),
                "training_time": round(training_time, 2),
                "model_path": self.model_path,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"❌ Training failed: {e}")
            self.stats["failed_trainings"] += 1
            self.stats["last_error"] = str(e)
            return {
                "success": False,
                "message": f"خطا در آموزش: {str(e)}"
            }
        finally:
            self.is_training = False
    
    # ============================================================
    # اجرای خودکار
    # ============================================================
    
    def start_auto_train(self, interval_hours: int = 6):
        """
        شروع آموزش خودکار در بازه‌های زمانی مشخص
        """
        if self.is_running:
            return {"success": False, "message": "سیستم در حال اجراست"}
        
        self.is_running = True
        self.stop_event.clear()
        
        def run():
            logger.info(f"🔄 Auto-training started (interval: {interval_hours}h)")
            
            while not self.stop_event.is_set():
                # 1. آموزش
                result = self.train_model()
                logger.info(f"📊 Training result: {result}")
                
                # 2. منتظر ماندن تا زمان بعدی
                for _ in range(interval_hours * 60 * 60):
                    if self.stop_event.is_set():
                        break
                    time.sleep(1)
            
            self.is_running = False
            logger.info("⏹️ Auto-training stopped")
        
        self.thread = Thread(target=run, daemon=True)
        self.thread.start()
        
        return {
            "success": True,
            "message": f"آموزش خودکار شروع شد (هر {interval_hours} ساعت)",
            "interval_hours": interval_hours
        }
    
    def stop_auto_train(self):
        """متوقف کردن آموزش خودکار"""
        if not self.is_running:
            return {"success": False, "message": "سیستم در حال اجرا نیست"}
        
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=5)
        
        self.is_running = False
        return {"success": True, "message": "آموزش خودکار متوقف شد"}
    
    def get_stats(self) -> Dict[str, Any]:
        """دریافت آمار سیستم"""
        status = self.check_api_status()
        
        return {
            "is_running": self.is_running,
            "is_training": self.is_training,
            "stats": self.stats,
            "api_status": status,
            "coins": self.coins,
            "model_exists": os.path.exists(self.model_path),
            "timestamp": datetime.now().isoformat()
        }
    
    def is_model_healthy(self) -> bool:
        """بررسی سلامت مدل"""
        if not os.path.exists(self.model_path):
            return False
        try:
            model = xgb.Booster()
            model.load_model(self.model_path)
            return True
        except:
            return False
