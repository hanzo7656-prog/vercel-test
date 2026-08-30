# models/trainer/auto_trainer.py
# ============================================================
# سیستم آموزش خودکار مدل XGBoost - نسخه ۳.۰ (رفع Import)
# ============================================================

import os
# models/trainer/auto_trainer.py
# ============================================================
# فقط بخش Import - نسخه اصلاح شده
# ============================================================

import os
import sys
import time
import json
import logging
import numpy as np
import xgboost as xgb
from pathlib import Path
from datetime import datetime, timedelta
from threading import Thread, Event
from typing import Dict, Any, Optional, List, Tuple, Union

# ✅ اصلاح Import - استفاده از مسیر جدید
from infrastructure.api.coinstats_client import coinstats_client
from models.manager.model_manager import ModelManager
from infrastructure.database import get_primary
from config.config_manager import get_historical_points, get_auto_trainer_config

logger = logging.getLogger(__name__)


class AutoTrainer:
    """
    سیستم آموزش خودکار مدل XGBoost با ذخیره‌سازی در دیتابیس
    
    ویژگی‌ها:
    - اتصال به ModelManager برای ذخیره در دیتابیس
    - نسخه‌سازی خودکار
    - آموزش افزایشی (Incremental Learning)
    - ترکیب با وزن‌دهی (Ensemble)
    - ارزیابی خودکار
    - قابلیت تنظیم تعداد نقاط تاریخی
    - یکپارچه با Metrics Scheduler
    
    ✅ نسخه ۳.۰: حذف print، استفاده از logger، Type Hints کامل
    """
    
    def __init__(self, api: Any, model_manager: ModelManager) -> None:
        self.api: Any = api
        self.model_manager: ModelManager = model_manager
        self.db: Any = get_primary()
        
        # بارگذاری تنظیمات از ConfigManager
        self.auto_trainer_config: Dict[str, Any] = get_auto_trainer_config()
        self.historical_points_config: Dict[str, int] = {
            "fear_greed": get_historical_points("fear_greed"),
            "btc_dominance": get_historical_points("btc_dominance"),
            "global_market": get_historical_points("global_market"),
            "chart": get_historical_points("chart")
        }
        
        # وضعیت اجرا
        self.is_running: bool = False
        self.is_training: bool = False
        self.stop_event: Event = Event()
        self.thread: Optional[Thread] = None
        
        # لیست لاگ‌ها
        self.logs: List[str] = []
        
        # مسیر مدل
        self.model_path: Path = Path("models/current_model.xgb")
        self.model_path.parent.mkdir(parents=True, exist_ok=True)
        
        # آمار سیستم
        self.stats: Dict[str, Any] = {
            "total_trainings": 0,
            "successful_trainings": 0,
            "failed_trainings": 0,
            "last_training": None,
            "last_error": None,
            "last_score": None,
            "data_points_used": 0,
            "api_status": "unknown",
            "credits_remaining": 0,
            "training_period": self.auto_trainer_config.get("period", "1m"),
            "mode": "DEMO",
            "points_used": {
                "fear_greed": self.historical_points_config["fear_greed"],
                "btc_dominance": self.historical_points_config["btc_dominance"],
                "global_market": self.historical_points_config["global_market"],
                "chart": self.historical_points_config["chart"]
            }
        }
        
        # ✅ فقط ۲ ارز اصلی (کاهش مصرف API)
        self.coins: List[str] = self.auto_trainer_config.get("coins", ["bitcoin", "ethereum"])
        
        # نام ویژگی‌ها
        self.feature_names: List[str] = [
            "return_1", "return_3", "return_5", "return_10",
            "sma_5", "sma_10", "sma_20",
            "volatility",
            "fear_greed",
            "trend_5", "trend_10", "trend_20",
            "r2",
            "btc_dominance",
            "market_cap",
            "total_volume"
        ]
        
        # ثبت در Scheduler
        self._register_with_scheduler()
        
        # بروزرسانی وضعیت از ModelManager
        if self.model_manager.current_model is not None:
            self.stats["mode"] = "BETA"
            self._add_log(f"✅ مدل موجود است (حالت BETA) - نسخه: {self.model_manager.current_version}")
        else:
            self._add_log(f"📦 مدل یافت نشد (حالت DEMO)")
        
        self._add_log(f"✅ AutoTrainer ۳.۰ راه‌اندازی شد")
        self._add_log(f"📊 تعداد نقاط: ترس و طمع={self.historical_points_config['fear_greed']}, "
                      f"سلطه={self.historical_points_config['btc_dominance']}, "
                      f"بازار={self.historical_points_config['global_market']}")
        self._add_log(f"🪙 ارزهای فعال: {self.coins}")

    def _register_with_scheduler(self) -> None:
        """ثبت در Scheduler"""
        try:
            from core.metrics import metrics_scheduler
            logger.info("✅ AutoTrainer registered with Metrics Scheduler")
        except ImportError:
            pass
        except Exception as e:
            logger.debug(f"Could not register with scheduler: {e}")
    
    # ============================================================
    # مدیریت لاگ‌ها
    # ============================================================
    
    def _add_log(self, message: str) -> None:
        """افزودن پیام به لاگ"""
        timestamp: str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry: str = f"[{timestamp}] {message}"
        self.logs.append(log_entry)
        if len(self.logs) > 200:
            self.logs = self.logs[-200:]
        logger.info(message)
    
    def clear_logs(self) -> None:
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
        """بررسی وضعیت API"""
        try:
            status: Optional[Dict[str, Any]] = self.api.get_status()
            api_ok: bool = status and status.get('status') == 'ok'
            
            credits: Optional[Dict[str, Any]] = self.api.get_credits()
            if credits and 'remainingCredits' in credits:
                remaining: int = credits.get('remainingCredits', 0)
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
        except requests.exceptions.Timeout as e:
            logger.error(f"API timeout: {e}")
            self.stats["api_status"] = "error"
            return {
                "api_status": "error",
                "credits_remaining": 0,
                "can_train": False,
                "message": f"Timeout: {str(e)}"
            }
        except requests.exceptions.ConnectionError as e:
            logger.error(f"API connection error: {e}")
            self.stats["api_status"] = "error"
            return {
                "api_status": "error",
                "credits_remaining": 0,
                "can_train": False,
                "message": f"Connection Error: {str(e)}"
            }
        except Exception as e:
            logger.error(f"API check error: {e}", exc_info=True)
            self.stats["api_status"] = "error"
            return {
                "api_status": "error",
                "credits_remaining": 0,
                "can_train": False,
                "message": f"خطا: {str(e)}"
            }
    
    # ============================================================
    # دریافت داده‌های تاریخی
    # ============================================================
    
    def _get_fear_greed_history(self, points: int) -> List[Dict[str, Any]]:
        """دریافت تاریخچه ترس و طمع"""
        if not self.db or not self.db.is_connected():
            return []
        
        try:
            result: List[Dict[str, Any]] = self.db.execute("""
                SELECT value, classification, timestamp
                FROM fear_greed_history
                ORDER BY timestamp DESC
                LIMIT %s
            """, (points,))
            
            if len(result) < points:
                self._add_log(f"🔄 دریافت ترس و طمع از API (نیاز به {points} نقطه)")
                current: Optional[Dict[str, Any]] = self.api.get_fear_greed()
                if current and 'now' in current:
                    now: Dict[str, Any] = current['now']
                    self.db.execute("""
                        INSERT INTO fear_greed_history (value, classification, timestamp)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (timestamp) DO UPDATE SET value = EXCLUDED.value
                    """, (
                        now.get('value'),
                        now.get('value_classification'),
                        datetime.now().isoformat()
                    ))
                    result = self.db.execute("""
                        SELECT value, classification, timestamp
                        FROM fear_greed_history
                        ORDER BY timestamp DESC
                        LIMIT %s
                    """, (points,))
            
            return result
        except Exception as e:
            logger.error(f"خطا در دریافت ترس و طمع: {e}", exc_info=True)
            return []
    
    def _get_btc_dominance_history(self, points: int) -> List[Dict[str, Any]]:
        """دریافت تاریخچه سلطه بیت‌کوین"""
        if not self.db or not self.db.is_connected():
            return []
        
        try:
            result: List[Dict[str, Any]] = self.db.execute("""
                SELECT value, timestamp
                FROM btc_dominance_history
                ORDER BY timestamp DESC
                LIMIT %s
            """, (points,))
            
            if len(result) < points:
                self._add_log(f"🔄 دریافت سلطه بیت‌کوین از API (نیاز به {points} نقطه)")
                current: Optional[Dict[str, Any]] = self.api.get_btc_dominance(use_cache=False)
                if current:
                    self.db.execute("""
                        INSERT INTO btc_dominance_history (value, timestamp)
                        VALUES (%s, %s)
                        ON CONFLICT (timestamp) DO UPDATE SET value = EXCLUDED.value
                    """, (
                        current.get('dominance'),
                        datetime.now().isoformat()
                    ))
                    result = self.db.execute("""
                        SELECT value, timestamp
                        FROM btc_dominance_history
                        ORDER BY timestamp DESC
                        LIMIT %s
                    """, (points,))
            
            return result
        except Exception as e:
            logger.error(f"خطا در دریافت سلطه بیت‌کوین: {e}", exc_info=True)
            return []
    
    def _get_global_market_history(self, points: int) -> List[Dict[str, Any]]:
        """دریافت تاریخچه وضعیت بازار"""
        if not self.db or not self.db.is_connected():
            return []
        
        try:
            result: List[Dict[str, Any]] = self.db.execute("""
                SELECT market_cap, volume, timestamp
                FROM global_market_history
                ORDER BY timestamp DESC
                LIMIT %s
            """, (points,))
            
            if len(result) < points:
                self._add_log(f"🔄 دریافت وضعیت بازار از API (نیاز به {points} نقطه)")
                current: Optional[Dict[str, Any]] = self.api.get_global_market()
                if current:
                    self.db.execute("""
                        INSERT INTO global_market_history (market_cap, volume, timestamp)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (timestamp) DO UPDATE SET 
                            market_cap = EXCLUDED.market_cap,
                            volume = EXCLUDED.volume
                    """, (
                        current.get('totalMarketCap'),
                        current.get('totalVolume'),
                        datetime.now().isoformat()
                    ))
                    result = self.db.execute("""
                        SELECT market_cap, volume, timestamp
                        FROM global_market_history
                        ORDER BY timestamp DESC
                        LIMIT %s
                    """, (points,))
            
            return result
        except Exception as e:
            logger.error(f"خطا در دریافت وضعیت بازار: {e}", exc_info=True)
            return []
    
    def fetch_data_for_coin(self, coin_id: str, period: str = "1m") -> List[List]:
        """دریافت داده‌های یک ارز"""
        try:
            data: Union[List[List], Dict] = self.api.get_chart(coin_id, period)
            if data and isinstance(data, list) and len(data) > 0:
                self._add_log(f"✅ دریافت {len(data)} نقطه برای {coin_id} ({period})")
                return data
            logger.warning(f"No data received for {coin_id}")
            return []
        except requests.exceptions.Timeout as e:
            logger.error(f"Timeout fetching data for {coin_id}: {e}")
            return []
        except requests.exceptions.ConnectionError as e:
            logger.error(f"Connection error fetching data for {coin_id}: {e}")
            return []
        except Exception as e:
            logger.error(f"خطا در دریافت داده برای {coin_id}: {e}", exc_info=True)
            return []
    
    def extract_features_for_training(self, chart_data: List[List]) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
        """استخراج ویژگی‌ها برای آموزش"""
        if not chart_data or len(chart_data) < 30:
            return None, None
        
        prices: List[float] = []
        for point in chart_data:
            if isinstance(point, list) and len(point) >= 2:
                prices.append(float(point[1]))
        
        if len(prices) < 30:
            return None, None
        
        prices_arr: np.ndarray = np.array(prices, dtype=np.float32)
        features_list: List[List[float]] = []
        labels_list: List[int] = []
        
        for i in range(20, len(prices) - 5):
            window: np.ndarray = prices_arr[i-20:i+1]
            current_price: float = prices_arr[i]
            future_price: float = prices_arr[i+3]
            
            label: int = 1 if future_price > current_price else 0           
            features: List[float] = []
            
            # 1. بازده‌ها
            for lag in [1, 3, 5]:
                if len(window) > lag:
                    ret: float = (window[-1] - window[-lag-1]) / (window[-lag-1] + 1e-8)
                    features.append(np.clip(ret, -0.5, 0.5))
                else:
                    features.append(0.0)
            
            # 2. میانگین متحرک
            for w in [5, 10]:
                if len(window) >= w:
                    sma: float = np.mean(window[-w:])
                    ratio: float = window[-1] / (sma + 1e-8) - 1
                    features.append(np.clip(ratio, -0.5, 0.5))
                else:
                    features.append(0.0)
            
            # 3. نوسان
            if len(window) >= 10:
                returns: np.ndarray = np.diff(window[-10:]) / (window[-10:-1] + 1e-8)
                volatility: float = np.std(returns)
                features.append(np.clip(volatility, 0, 0.5))
            else:
                features.append(0.0)
            
            # 4. شاخص ترس و طمع
            try:
                fear_data: List[Dict[str, Any]] = self._get_fear_greed_history(1)
                if fear_data:
                    features.append(fear_data[0].get('value', 50) / 100.0)
                else:
                    features.append(0.5)
            except Exception as e:
                logger.debug(f"Fear & Greed error in feature extraction: {e}")
                features.append(0.5)
            
            # 5. شیب قیمت
            for w in [5, 10]:
                if len(window) >= w:
                    slope: float = np.polyfit(range(w), window[-w:], 1)[0]
                    slope_norm: float = slope / (window[-1] + 1e-8) * 100
                    features.append(np.clip(slope_norm, -10, 10))
                else:
                    features.append(0.0)
            
            # 6. قدرت روند
            if len(window) >= 10:
                x: np.ndarray = np.arange(10)
                y: np.ndarray = window[-10:]
                slope, intercept = np.polyfit(x, y, 1)
                y_pred: np.ndarray = slope * x + intercept
                ss_tot: float = np.sum((y - np.mean(y)) ** 2)
                ss_res: float = np.sum((y - y_pred) ** 2)
                r2: float = 1 - (ss_res / (ss_tot + 1e-8))
                features.append(np.clip(r2, -1, 1))
            else:
                features.append(0.0)
            
            # 7. سلطه بیت‌کوین
            try:
                dominance_data: List[Dict[str, Any]] = self._get_btc_dominance_history(1)
                if dominance_data:
                    features.append(dominance_data[0].get('value', 50) / 100.0)
                else:
                    features.append(0.5)
            except Exception as e:
                logger.debug(f"BTC Dominance error in feature extraction: {e}")
                features.append(0.5)
            
            features_list.append(features)
            labels_list.append(label)
        
        if not features_list:
            return None, None
        
        return np.array(features_list, dtype=np.float32), np.array(labels_list, dtype=np.int32)
    
    def _get_training_coins(self) -> List[str]:
        """دریافت لیست ارزهای آموزش"""
        return self.coins
    
    # ============================================================
    # ارزیابی مدل
    # ============================================================
    
    def _evaluate_model(self, model: Any, features: np.ndarray, labels: np.ndarray) -> float:
        """ارزیابی مدل"""
        try:
            if isinstance(model, xgb.Booster):
                dtest: xgb.DMatrix = xgb.DMatrix(features)
                predictions: np.ndarray = model.predict(dtest)
            else:
                predictions = model.predict(features)
            
            pred_classes: np.ndarray = (predictions > 0.5).astype(int)
            accuracy: float = np.mean(pred_classes == labels)
            return float(accuracy)
        except xgb.core.XGBoostError as e:
            logger.error(f"XGBoost evaluation error: {e}")
            return 0.0
        except Exception as e:
            logger.error(f"خطا در ارزیابی: {e}")
            return 0.0
    
    # ============================================================
    # آموزش مدل
    # ============================================================
    
    def train_model(self, period: str = "1m") -> Dict[str, Any]:
        """آموزش مدل"""
        if self.is_training:
            return {"success": False, "message": "آموزش در حال انجام است"}
        
        status: Dict[str, Any] = self.check_api_status()
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
        
        result: Dict[str, Any] = {"success": False, "message": "خطای ناشناخته"}
        
        try:
            all_features: List[np.ndarray] = []
            all_labels: List[np.ndarray] = []
            total_points: int = 0
            
            for coin in self.coins:
                self._add_log(f"🪙 دریافت {coin} ({period})...")
                chart_data: List[List] = self.fetch_data_for_coin(coin, period)
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
            
            X: np.ndarray = np.vstack(all_features)
            y: np.ndarray = np.concatenate(all_labels)
            
            self._add_log(f"📊 کل نمونه‌های آموزش: {len(X)}")
            self.stats["data_points_used"] = len(X)
            
            self._add_log("🧠 آموزش مدل XGBoost...")
            start_time: float = time.time()
            
            model: xgb.XGBClassifier = xgb.XGBClassifier(
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
            training_time: float = time.time() - start_time
            
            model.save_model(str(self.model_path), format='json')
            
            score: float = model.score(X, y)
            self.stats["last_score"] = round(score, 3)
            self._add_log(f"📊 دقت مدل جدید: {score:.3f}")
            
            old_score: Optional[float] = None
            if self.model_manager.current_model is not None:
                old_score = self._evaluate_model(
                    self.model_manager.current_model, 
                    X, 
                    y
                )
                self._add_log(f"📊 دقت مدل قبلی: {old_score:.3f}")
            
            if old_score is not None and (score - old_score) < 0.01:
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
            
            self._add_log(f"💾 ذخیره مدل در دیتابیس...")
            save_result: Dict[str, Any] = self.model_manager.save_model(
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
                error_msg: str = save_result.get('error', 'خطای ناشناخته')
                self.stats["last_error"] = error_msg
                result = {
                    "success": False,
                    "message": f"خطا در ذخیره مدل: {error_msg}"
                }
            
        except xgb.core.XGBoostError as e:
            self._add_log(f"❌ XGBoost error: {e}")
            self.stats["failed_trainings"] += 1
            self.stats["last_error"] = str(e)
            result = {"success": False, "message": f"XGBoost error: {str(e)}"}
        except ValueError as e:
            self._add_log(f"❌ ValueError: {e}")
            self.stats["failed_trainings"] += 1
            self.stats["last_error"] = str(e)
            result = {"success": False, "message": f"خطا در داده: {str(e)}"}
        except Exception as e:
            self._add_log(f"❌ آموزش ناموفق: {e}")
            logger.error(f"Training error: {e}", exc_info=True)
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
    # آموزش افزایشی
    # ============================================================
    
    def incremental_train(self, period: str = "1m") -> Dict[str, Any]:
        """آموزش افزایشی با داده‌های جدید"""
        if not self.model_manager.current_model:
            self._add_log("⚠️ مدلی برای آموزش افزایشی وجود ندارد - انجام آموزش کامل")
            return self.train_model(period)
        
        if self.is_training:
            return {"success": False, "message": "آموزش در حال انجام است"}
        
        self.is_training = True
        self._add_log(f"📚 شروع آموزش افزایشی با بازه: {period}")
        
        try:
            all_features: List[np.ndarray] = []
            all_labels: List[np.ndarray] = []
            
            for coin in self.coins:
                chart_data: List[List] = self.fetch_data_for_coin(coin, period)
                if not chart_data:
                    continue
                features, labels = self.extract_features_for_training(chart_data)
                if features is not None and len(features) > 0:
                    all_features.append(features)
                    all_labels.append(labels)
            
            if not all_features:
                self.is_training = False
                return {"success": False, "message": "داده‌ای برای آموزش افزایشی یافت نشد"}
            
            X: np.ndarray = np.vstack(all_features)
            y: np.ndarray = np.concatenate(all_labels)
            
            old_accuracy: float = self._evaluate_model(self.model_manager.current_model, X, y)
            self._add_log(f"📊 دقت مدل فعلی روی داده‌های جدید: {old_accuracy:.3f}")
            
            dtrain: xgb.DMatrix = xgb.DMatrix(X, label=y)
            params: Dict[str, Any] = {
                'objective': 'binary:logistic',
                'eval_metric': 'logloss',
                'learning_rate': 0.05,
                'max_depth': 3,
                'subsample': 0.7,
                'colsample_bytree': 0.7,
                'tree_method': 'hist'
            }
            
            new_model: xgb.Booster = xgb.train(
                params,
                dtrain,
                num_boost_round=10,
                xgb_model=self.model_manager.current_model
            )
            
            new_accuracy: float = self._evaluate_model(new_model, X, y)
            improvement: float = new_accuracy - old_accuracy
            self._add_log(f"📊 دقت مدل جدید: {new_accuracy:.3f} (بهبود: {improvement*100:.1f}%)")
            
            if improvement > 0.02:
                self._add_log(f"✅ بهبود قابل توجه! ذخیره مدل جدید")
                result: Dict[str, Any] = self.model_manager.save_model(new_model, new_accuracy, period)
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
                self._add_log(f"🔄 بهبود متوسط - ترکیب با مدل قبلی")
                combined_model: Any = self._create_weighted_ensemble(
                    self.model_manager.current_model, 
                    new_model, 
                    weights=[0.7, 0.3]
                )
                combined_accuracy: float = self._evaluate_model(combined_model, X, y)
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
                
        except xgb.core.XGBoostError as e:
            self._add_log(f"❌ XGBoost error in incremental training: {e}")
            logger.error(f"Incremental XGBoost error: {e}", exc_info=True)
            self.is_training = False
            return {"success": False, "error": f"XGBoost error: {str(e)}"}
        except Exception as e:
            self._add_log(f"❌ خطا در آموزش افزایشی: {e}")
            logger.error(f"Incremental training error: {e}", exc_info=True)
            self.is_training = False
            return {"success": False, "error": str(e)}
    
    def _create_weighted_ensemble(self, model1: Any, model2: Any, weights: List[float] = [0.5, 0.5]) -> Any:
        """ایجاد مدل ترکیبی با وزن‌دهی"""
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
    # دریافت آمار و اطلاعات
    # ============================================================
    
    def get_stats(self) -> Dict[str, Any]:
        """دریافت آمار"""
        status: Dict[str, Any] = self.check_api_status()
        model_stats: Dict[str, Any] = self.model_manager.get_stats() if self.model_manager else {}
        
        return {
            "is_running": self.is_running,
            "is_training": self.is_training,
            "stats": self.stats,
            "api_status": status,
            "coins": self.coins,
            "model_exists": model_stats.get('loaded', False),
            "current_version": self.model_manager.current_version if self.model_manager else None,
            "logs": self.logs[-30:],
            "timestamp": datetime.now().isoformat(),
            "points_config": self.historical_points_config
        }
    
    def get_training_history(self, period: Optional[str] = None) -> List[Dict[str, Any]]:
        """دریافت تاریخچه آموزش"""
        if not self.db or not self.db.is_connected():
            return []
        
        try:
            query: str = """
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
            
            result: List[Dict[str, Any]] = self.db.execute(query)
            return result
        except Exception as e:
            logger.error(f"خطا در دریافت تاریخچه: {e}", exc_info=True)
            return []
    
    # ============================================================
    # اجرای خودکار
    # ============================================================
    
    def start_auto_train(self, interval_hours: Optional[int] = None, period: Optional[str] = None, incremental: bool = True) -> Dict[str, Any]:
        """شروع آموزش خودکار"""
        if self.is_running:
            return {"success": False, "message": "سیستم در حال اجراست"}
        
        if interval_hours is None:
            interval_hours = self.auto_trainer_config.get("interval_hours", 6)
        if period is None:
            period = self.auto_trainer_config.get("period", "1m")
        
        self.is_running = True
        self.stop_event.clear()
        self.stats["training_period"] = period
        
        def run() -> None:
            self._add_log(f"🔄 آموزش خودکار شروع شد (فاصله: {interval_hours}h, بازه: {period})")
            
            while not self.stop_event.is_set():
                try:
                    if incremental and self.model_manager.current_model is not None:
                        result: Dict[str, Any] = self.incremental_train(period)
                    else:
                        result = self.train_model(period)
                    
                    self._add_log(f"📊 نتیجه آموزش: {result.get('message', 'نامشخص')}")
                    
                except Exception as e:
                    self._add_log(f"❌ خطا در چرخه آموزش: {e}")
                    logger.error(f"Auto train cycle error: {e}", exc_info=True)
                
                wait_seconds: int = interval_hours * 3600
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
    
    def stop_auto_train(self) -> Dict[str, Any]:
        """متوقف کردن آموزش خودکار"""
        if not self.is_running:
            return {"success": False, "message": "سیستم در حال اجرا نیست"}
        
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=5)
        self.is_running = False
        self._add_log("⏹️ آموزش خودکار توسط کاربر متوقف شد")
        return {"success": True, "message": "آموزش خودکار متوقف شد"}
