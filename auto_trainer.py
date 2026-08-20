# auto_trainer.py
# ============================================================
# سیستم آموزش خودکار مدل XGBoost
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


class AutoTrainer:
    def __init__(self, api: CoinStatsAPI, model_path: str = "model.json"):
        self.api = api
        self.model_path = model_path
        self.is_running = False
        self.is_training = False
        self.stop_event = Event()
        self.thread: Optional[Thread] = None
        self.logs: List[str] = []
        
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
            "training_period": "1m"
        }
        
        self.coins = ["bitcoin", "ethereum", "solana", "cardano", "ripple"]
        
        self.feature_names = [
            "return_1", "return_3", "return_5", "return_10",
            "sma_5", "sma_10", "sma_20",
            "volatility",
            "fear_greed",
            "trend_5", "trend_10", "trend_20",
            "r2"
        ]

        self.training_history: List[Dict[str, Any]] = []
        self._add_log("✅ AutoTrainer initialized")
    
    def _add_log(self, message: str):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.logs.append(f"[{timestamp}] {message}")
        if len(self.logs) > 200:
            self.logs = self.logs[-200:]
        logger.info(message)
    
    # ============================================================
    # مدیریت وضعیت API
    # ============================================================
    
    def check_api_status(self) -> Dict[str, Any]:
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
        try:
            data = self.api.get_chart(coin_id, period)
            if data and isinstance(data, list) and len(data) > 0:
                self._add_log(f"✅ Fetched {len(data)} points for {coin_id} ({period})")
                return data
            return []
        except Exception as e:
            self._add_log(f"❌ Error fetching data for {coin_id}: {e}")
            return []
    
    def extract_features_for_training(self, chart_data: List[List]) -> tuple:
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
            
            for lag in [1, 3, 5]:
                if len(window) > lag:
                    ret = (window[-1] - window[-lag-1]) / (window[-lag-1] + 1e-8)
                    features.append(np.clip(ret, -0.5, 0.5))
                else:
                    features.append(0.0)
            
            for w in [5, 10]:
                if len(window) >= w:
                    sma = np.mean(window[-w:])
                    ratio = window[-1] / (sma + 1e-8) - 1
                    features.append(np.clip(ratio, -0.5, 0.5))
                else:
                    features.append(0.0)
            
            if len(window) >= 10:
                returns = np.diff(window[-10:]) / (window[-10:-1] + 1e-8)
                volatility = np.std(returns)
                features.append(np.clip(volatility, 0, 0.5))
            else:
                features.append(0.0)
            
            try:
                fg = self.api.get_fear_greed(use_cache=True)
                if fg and 'now' in fg:
                    fear_value = fg['now'].get('value', 50)
                    features.append(fear_value / 100.0)
                else:
                    features.append(0.5)
            except:
                features.append(0.5)
            
            for w in [5, 10]:
                if len(window) >= w:
                    slope = np.polyfit(range(w), window[-w:], 1)[0]
                    slope_norm = slope / (window[-1] + 1e-8) * 100
                    features.append(np.clip(slope_norm, -10, 10))
                else:
                    features.append(0.0)
            
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
    
    def train_model(self, period: str = "1m") -> Dict[str, Any]:
        if self.is_training:
            return {"success": False, "message": "آموزش در حال انجام است"}
        
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
        self._add_log(f"📚 Starting training with period: {period}")
        
        try:
            all_features = []
            all_labels = []
            total_points = 0
            
            for coin in self.coins:
                self._add_log(f"🪙 Fetching {coin} ({period})...")
                chart_data = self.fetch_data_for_coin(coin, period)
                if not chart_data:
                    self._add_log(f"   ⚠️ No data for {coin}")
                    continue
                
                features, labels = self.extract_features_for_training(chart_data)
                if features is not None and len(features) > 0:
                    all_features.append(features)
                    all_labels.append(labels)
                    total_points += len(features)
                    self._add_log(f"   ✅ {len(features)} samples from {coin}")
            
            if not all_features:
                self.is_training = False
                self.stats["failed_trainings"] += 1
                self._add_log("❌ No data found for training")
                return {"success": False, "message": "داده‌ای برای آموزش یافت نشد"}
            
            X = np.vstack(all_features)
            y = np.concatenate(all_labels)
            
            self._add_log(f"📊 Total training samples: {len(X)}")
            self.stats["data_points_used"] = len(X)
            
            self._add_log("🧠 Training XGBoost model...")
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
            
            start_time = time.time()
            model.fit(X, y)
            training_time = time.time() - start_time
            
            score = model.score(X, y)
            self.stats["last_score"] = round(score, 3)
            
            model.save_model(self.model_path)
            
            self.stats["successful_trainings"] += 1
            self.stats["last_training"] = datetime.now().isoformat()
            self.stats["last_error"] = None
            
            self._add_log(f"✅ Model saved! Accuracy: {score:.3f}, Time: {training_time:.2f}s")
            
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
            self._add_log(f"❌ Training failed: {e}")
            self.stats["failed_trainings"] += 1
            self.stats["last_error"] = str(e)
            return {
                "success": False,
                "message": f"خطا در آموزش: {str(e)}"
            }
        finally:
            self.is_training = False
        
        # بعد از آموزش موفق، سابقه رو ذخیره کن
        if result["success"]:
            self.training_history.append({
                "timestamp": datetime.now().isoformat(),
                "period": period,
                "accuracy": result["accuracy"],
                "samples": result["samples"],
                "training_time": result["training_time"],
                "status": "success"
            })
            # نگه‌داشتن فقط ۱۰۰ رکورد آخر
            if len(self.training_history) > 100:
                self.training_history = self.training_history[-100:]
        
        return result
    
    def get_training_history(self, period: str = None) -> List[Dict[str, Any]]:
        """دریافت سابقه آموزش با فیلتر دوره زمانی"""
        if period:
            return [h for h in self.training_history if h.get("period") == period]
        return self.training_history
    
    def get_stats(self) -> Dict[str, Any]:
        status = self.check_api_status()
        return {
            "is_running": self.is_running,
            "is_training": self.is_training,
            "stats": self.stats,
            "api_status": status,
            "coins": self.coins,
            "model_exists": os.path.exists(self.model_path),
            "logs": self.logs[-30:],
            "training_history": self.training_history[-50:],
            "timestamp": datetime.now().isoformat()
        }
    
    # ============================================================
    # اجرای خودکار
    # ============================================================
    
    def start_auto_train(self, interval_hours: int = 6, period: str = "1m"):
        if self.is_running:
            return {"success": False, "message": "سیستم در حال اجراست"}
        
        self.is_running = True
        self.stop_event.clear()
        self.stats["training_period"] = period
        
        def run():
            self._add_log(f"🔄 Auto-training started (interval: {interval_hours}h, period: {period})")
            while not self.stop_event.is_set():
                result = self.train_model(period)
                self._add_log(f"📊 Training result: {result}")
                for _ in range(interval_hours * 60 * 60):
                    if self.stop_event.is_set():
                        break
                    time.sleep(1)
            self.is_running = False
            self._add_log("⏹️ Auto-training stopped")
        
        self.thread = Thread(target=run, daemon=True)
        self.thread.start()
        
        return {
            "success": True,
            "message": f"آموزش خودکار شروع شد (هر {interval_hours} ساعت)",
            "interval_hours": interval_hours,
            "period": period
        }
    
    def stop_auto_train(self):
        if not self.is_running:
            return {"success": False, "message": "سیستم در حال اجرا نیست"}
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=5)
        self.is_running = False
        self._add_log("⏹️ Auto-training stopped by user")
        return {"success": True, "message": "آموزش خودکار متوقف شد"}
    
    def get_stats(self) -> Dict[str, Any]:
        status = self.check_api_status()
        return {
            "is_running": self.is_running,
            "is_training": self.is_training,
            "stats": self.stats,
            "api_status": status,
            "coins": self.coins,
            "model_exists": os.path.exists(self.model_path),
            "logs": self.logs[-30:],
            "timestamp": datetime.now().isoformat()
        }
