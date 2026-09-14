# models/trainer/auto_trainer.py
# ============================================================
# آموزش‌دهنده خودکار - Data Provider
# نسخه ۴.۰
# ============================================================

import os
import sys
import time
import json
import logging
import threading
import requests
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Tuple, Union

import numpy as np
import xgboost as xgb

from infrastructure.api.coinstats_client import coinstats_client
from infrastructure.database import (
    get_primary,
    get_analytics,
    get_cache,
)
from config import get_historical_points, get_auto_trainer_config

logger = logging.getLogger(__name__)


# ============================================================
# AutoTrainer
# ============================================================

class AutoTrainer:
    """
    آموزش‌دهنده خودکار مدل - لایه داده
    
    نقش:
        - Data Provider برای ModelManager
        - fetch داده از API
        - Feature extraction (X, y)
        - Scheduler دوره‌ای
    
    معماری:
        AutoTrainer (fetch data)
            ↓
        ModelManager.train(X, y, profile)
            ↓
        Model (model_manager)
    
    ویژگی‌های جدید (v4.0):
        - Training Profiles support
        - Learning Strategies support
        - Analytics DB recording
        - Quota check
        - Retry هوشمند
        - train_batch (A/B testing)
        - get_analytics_stats
    """
    
    # ============================================================
    # Init
    # ============================================================
    
    def __init__(self, api: Any, model_manager: Any) -> None:
        """
        راه‌اندازی
        
        پارامترها:
            api: کلاینت API (CoinStatsClient)
            model_manager: ModelManager instance
        """
        self.api: Any = api
        self.model_manager: Any = model_manager
        self.db: Any = get_primary()
        self.analytics_db: Any = get_analytics()
        self.cache: Any = get_cache()
        
        # تنظیمات
        self.auto_trainer_config: Dict[str, Any] = get_auto_trainer_config()
        self.historical_points_config: Dict[str, int] = {
            "fear_greed": get_historical_points("fear_greed"),
            "btc_dominance": get_historical_points("btc_dominance"),
            "global_market": get_historical_points("global_market"),
            "chart": get_historical_points("chart"),
        }
        
        # State
        self.is_running: bool = False
        self.is_training: bool = False
        self.stop_event: threading.Event = threading.Event()
        self.thread: Optional[threading.Thread] = None
        self._lock: threading.Lock = threading.Lock()
        
        # لاگ‌ها
        self.logs: List[str] = []
        
        # ارزها
        self.coins: List[str] = self.auto_trainer_config.get(
            "coins", ["bitcoin", "ethereum"]
        )
        
        # نام ویژگی‌ها
        self.feature_names: List[str] = [
            "return_1", "return_3", "return_5", "return_10",
            "sma_5", "sma_10", "sma_20",
            "volatility",
            "fear_greed",
            "trend_5", "trend_10", "trend_20",
            "r2",
        ]
        
        # آمار
        self.stats: Dict[str, Any] = {
            # وضعیت
            "is_running": False,
            "is_training": False,
            
            # آموزش
            "total_trainings": 0,
            "successful_trainings": 0,
            "failed_trainings": 0,
            "last_training": None,
            "last_error": None,
            "last_score": None,
            "data_points_used": 0,
            "training_period": self.auto_trainer_config.get("period", "1m"),
            
            # API
            "api_status": "unknown",
            "credits_remaining": 0,
            "api_calls": 0,
            "api_errors": 0,
            
            # حالت
            "mode": "DEMO",
            "points_used": {
                "fear_greed": self.historical_points_config["fear_greed"],
                "btc_dominance": self.historical_points_config["btc_dominance"],
                "global_market": self.historical_points_config["global_market"],
                "chart": self.historical_points_config["chart"],
            },
        }
        
        # ثبت در scheduler
        self._register_with_scheduler()
        
        # بروزرسانی وضعیت از ModelManager
        if self.model_manager.current_model is not None:
            self.stats["mode"] = "BETA"
            self._add_log(
                f"✅ مدل موجود است (حالت BETA) - "
                f"نسخه: {self.model_manager.current_version}"
            )
        else:
            self._add_log(f"📦 مدل یافت نشد (حالت DEMO)")
        
        self._add_log(f"✅ AutoTrainer v4.0 راه‌اندازی شد")
        self._add_log(
            f"📊 تعداد نقاط: "
            f"ترس و طمع={self.historical_points_config['fear_greed']}, "
            f"سلطه={self.historical_points_config['btc_dominance']}, "
            f"بازار={self.historical_points_config['global_market']}"
        )
        self._add_log(f"🪙 ارزهای فعال: {self.coins}")
    
    # ============================================================
    # Scheduler Registration
    # ============================================================
    
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
    # Log Management
    # ============================================================
    
    def _add_log(self, message: str) -> None:
        """افزودن پیام به لاگ"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] {message}"
        self.logs.append(log_entry)
        
        # محدودیت ۲۰۰ خط
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
    # API Status
    # ============================================================
    
    def check_api_status(self) -> Dict[str, Any]:
        """
        بررسی وضعیت API
        
        خروجی:
            دیکشنری وضعیت
        """
        try:
            # Status
            status = self.api.get_status()
            api_ok = status and status.get("status") == "ok"
            
            # Credits
            credits = self.api.get_credits()
            remaining = 0
            
            if credits and "remainingCredits" in credits:
                remaining = credits.get("remainingCredits", 0)
                self.stats["credits_remaining"] = remaining
                
                if remaining < 100:
                    self._add_log(f"⚠️ اعتبار باقیمانده کم است: {remaining}")
            
            self.stats["api_status"] = "ok" if api_ok else "error"
            
            return {
                "api_status": "ok" if api_ok else "error",
                "credits_remaining": remaining,
                "can_train": api_ok and remaining > 100,
                "message": "API سالم است" if api_ok else "API در دسترس نیست",
            }
            
        except requests.exceptions.Timeout as e:
            logger.error(f"API timeout: {e}")
            self.stats["api_status"] = "error"
            self.stats["api_errors"] += 1
            return {
                "api_status": "error",
                "credits_remaining": 0,
                "can_train": False,
                "message": f"Timeout: {str(e)}",
            }
        except requests.exceptions.ConnectionError as e:
            logger.error(f"API connection error: {e}")
            self.stats["api_status"] = "error"
            self.stats["api_errors"] += 1
            return {
                "api_status": "error",
                "credits_remaining": 0,
                "can_train": False,
                "message": f"Connection Error: {str(e)}",
            }
        except Exception as e:
            logger.error(f"API check error: {e}", exc_info=True)
            self.stats["api_status"] = "error"
            self.stats["api_errors"] += 1
            return {
                "api_status": "error",
                "credits_remaining": 0,
                "can_train": False,
                "message": f"خطا: {str(e)}",
            }
    
    # ============================================================
    # Data Fetching
    # ============================================================
    
    def _fetch_with_retry(
        self,
        coin: str,
        period: str,
        max_attempts: int = 3,
    ) -> Optional[List[List]]:
        """
        دریافت داده با retry هوشمند
        
        پارامترها:
            coin: شناسه ارز
            period: بازه
            max_attempts: حداکثر تلاش
        
        خروجی:
            لیست داده‌ها یا None
        """
        for attempt in range(max_attempts):
            try:
                data = self.api.get_chart(coin, period)
                self.stats["api_calls"] += 1
                
                # چک داده معتبر
                if data and isinstance(data, list) and len(data) > 0:
                    return data
                
                # داده dict با error
                if isinstance(data, dict) and "error" in data:
                    logger.warning(
                        f"API error for {coin} (attempt {attempt + 1}): "
                        f"{data.get('error')}"
                    )
                
            except requests.exceptions.Timeout:
                logger.warning(
                    f"Timeout fetching {coin} (attempt {attempt + 1})"
                )
            except requests.exceptions.ConnectionError:
                logger.warning(
                    f"Connection error fetching {coin} (attempt {attempt + 1})"
                )
            except Exception as e:
                logger.error(
                    f"Error fetching {coin} (attempt {attempt + 1}): {e}"
                )
            
            self.stats["api_errors"] += 1
            
            # تأخیر بین تلاش‌ها
            if attempt < max_attempts - 1:
                delay = 2 ** attempt
                time.sleep(delay)
        
        return None
    
    def fetch_data_for_coin(
        self,
        coin_id: str,
        period: str = "1m",
    ) -> List[List]:
        """
        دریافت داده‌های یک ارز
        
        پارامترها:
            coin_id: شناسه ارز
            period: بازه
        
        خروجی:
            لیست داده‌ها یا []
        """
        data = self._fetch_with_retry(coin_id, period)
        
        if data:
            self._add_log(f"✅ دریافت {len(data)} نقطه برای {coin_id} ({period})")
            return data
        
        logger.warning(f"No data received for {coin_id}")
        return []
    
    def extract_features_for_training(
        self,
        chart_data: List[List],
    ) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
        """
        استخراج ویژگی‌ها برای آموزش (X, y)
        
        پارامترها:
            chart_data: لیست [timestamp, price]
        
        خروجی:
            (X, y) — X: ویژگی‌ها، y: برچسب‌ها
        """
        if not chart_data or len(chart_data) < 30:
            return None, None
        
        # استخراج قیمت‌ها
        prices: List[float] = []
        for point in chart_data:
            if isinstance(point, list) and len(point) >= 2:
                prices.append(float(point[1]))
        
        if len(prices) < 30:
            return None, None
        
        prices_arr = np.array(prices, dtype=np.float32)
        features_list: List[List[float]] = []
        labels_list: List[int] = []
        
        # داده‌های کمکی (یک بار بگیر)
        fear_greed_data = self._get_fear_greed_history(1)
        dominance_data = self._get_btc_dominance_history(1)
        
        for i in range(20, len(prices) - 3):
            window = prices_arr[i - 20:i + 1]
            current_price = prices_arr[i]
            future_price = prices_arr[i + 3]
            
            # برچسب: 1 اگه فردا بالا
            label = 1 if future_price > current_price else 0
            
            features: List[float] = []
            
            # ۱. بازده‌ها
            for lag in [1, 3, 5]:
                if len(window) > lag:
                    ret = (window[-1] - window[-lag - 1]) / (window[-lag - 1] + 1e-8)
                    features.append(float(np.clip(ret, -0.5, 0.5)))
                else:
                    features.append(0.0)
            
            # ۲. میانگین متحرک
            for w in [5, 10]:
                if len(window) >= w:
                    sma = float(np.mean(window[-w:]))
                    ratio = window[-1] / (sma + 1e-8) - 1
                    features.append(float(np.clip(ratio, -0.5, 0.5)))
                else:
                    features.append(0.0)
            
            # ۳. نوسان
            if len(window) >= 10:
                returns = np.diff(window[-10:]) / (window[-10:-1] + 1e-8)
                volatility = float(np.std(returns))
                features.append(float(np.clip(volatility, 0, 0.5)))
            else:
                features.append(0.0)
            
            # ۴. ترس و طمع
            if fear_greed_data:
                features.append(float(fear_greed_data[0].get("value", 50)) / 100.0)
            else:
                features.append(0.5)
            
            # ۵. روند
            for w in [5, 10]:
                if len(window) >= w:
                    slope = float(np.polyfit(range(w), window[-w:], 1)[0])
                    slope_norm = slope / (window[-1] + 1e-8) * 100
                    features.append(float(np.clip(slope_norm, -10, 10)))
                else:
                    features.append(0.0)
            
            # ۶. R²
            if len(window) >= 10:
                x = np.arange(10)
                y_window = window[-10:]
                slope, intercept = np.polyfit(x, y_window, 1)
                y_pred = slope * x + intercept
                ss_tot = float(np.sum((y_window - np.mean(y_window)) ** 2))
                ss_res = float(np.sum((y_window - y_pred) ** 2))
                r2 = 1 - (ss_res / (ss_tot + 1e-8))
                features.append(float(np.clip(r2, -1, 1)))
            else:
                features.append(0.0)
            
            # ۷. سلطه BTC
            if dominance_data:
                features.append(float(dominance_data[0].get("value", 50)) / 100.0)
            else:
                features.append(0.5)
            
            features_list.append(features)
            labels_list.append(label)
        
        if not features_list:
            return None, None
        
        X = np.array(features_list, dtype=np.float32)
        y = np.array(labels_list, dtype=np.int32)
        
        return X, y
    
    # ============================================================
    # Historical Data Fetching
    # ============================================================
    
    def _get_fear_greed_history(self, points: int) -> List[Dict[str, Any]]:
        """دریافت تاریخچه ترس و طمع"""
        if not self.db or not self.db.is_connected():
            return []
        
        try:
            result = self.db.execute("""
                SELECT value, classification, timestamp
                FROM fear_greed_history
                ORDER BY timestamp DESC
                LIMIT %s
            """, (points,))
            
            if len(result) < points:
                self._add_log(f"🔄 دریافت ترس و طمع از API (نیاز به {points} نقطه)")
                current = self.api.get_fear_greed()
                
                if current and "now" in current:
                    now = current["now"]
                    self.db.execute("""
                        INSERT INTO fear_greed_history (value, classification, timestamp)
                        VALUES (%s, %s, %s)
                    """, (
                        now.get("value"),
                        now.get("value_classification"),
                        datetime.now().isoformat(),
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
            result = self.db.execute("""
                SELECT value, timestamp
                FROM btc_dominance_history
                ORDER BY timestamp DESC
                LIMIT %s
            """, (points,))
            
            if len(result) < points:
                self._add_log(f"🔄 دریافت سلطه بیت‌کوین از API")
                current = self.api.get_btc_dominance(use_cache=False)
                
                if current:
                    self.db.execute("""
                        INSERT INTO btc_dominance_history (value, timestamp)
                        VALUES (%s, %s)
                    """, (
                        current.get("dominance"),
                        datetime.now().isoformat(),
                    ))
                    
                    result = self.db.execute("""
                        SELECT value, timestamp
                        FROM btc_dominance_history
                        ORDER BY timestamp DESC
                        LIMIT %s
                    """, (points,))
            
            return result
            
        except Exception as e:
            logger.error(f"خطا در دریافت سلطه: {e}", exc_info=True)
            return []
    
    def _get_global_market_history(self, points: int) -> List[Dict[str, Any]]:
        """دریافت تاریخچه وضعیت بازار"""
        if not self.db or not self.db.is_connected():
            return []
        
        try:
            result = self.db.execute("""
                SELECT market_cap, volume, timestamp
                FROM global_market_history
                ORDER BY timestamp DESC
                LIMIT %s
            """, (points,))
            
            if len(result) < points:
                self._add_log(f"🔄 دریافت وضعیت بازار از API")
                current = self.api.get_global_market()
                
                if current:
                    self.db.execute("""
                        INSERT INTO global_market_history (market_cap, volume, timestamp)
                        VALUES (%s, %s, %s)
                    """, (
                        current.get("totalMarketCap"),
                        current.get("totalVolume"),
                        datetime.now().isoformat(),
                    ))
                    
                    result = self.db.execute("""
                        SELECT market_cap, volume, timestamp
                        FROM global_market_history
                        ORDER BY timestamp DESC
                        LIMIT %s
                    """, (points,))
            
            return result
            
        except Exception as e:
            logger.error(f"خطا در دریافت بازار: {e}", exc_info=True)
            return []
    
    # ============================================================
    # Training Data Collection
    # ============================================================
    
    def _collect_training_data(
        self,
        period: str,
        coins: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        جمع‌آوری X, y از چند ارز
        
        پارامترها:
            period: بازه
            coins: لیست ارزها (اگه None، از self.coins)
        
        خروجی:
            دیکشنری {X, y, samples, coins_used, errors}
        """
        coins = coins or self.coins
        
        all_features = []
        all_labels = []
        coins_used = []
        errors = []
        total_points = 0
        
        for coin in coins:
            self._add_log(f"🪙 دریافت {coin} ({period})...")
            
            chart_data = self.fetch_data_for_coin(coin, period)
            
            if not chart_data:
                self._add_log(f"   ⚠️ داده‌ای برای {coin} یافت نشد")
                errors.append(f"{coin}: no data")
                continue
            
            X_coin, y_coin = self.extract_features_for_training(chart_data)
            
            if X_coin is not None and len(X_coin) > 0:
                all_features.append(X_coin)
                all_labels.append(y_coin)
                coins_used.append(coin)
                total_points += len(X_coin)
                self._add_log(f"   ✅ {len(X_coin)} نمونه از {coin}")
            else:
                errors.append(f"{coin}: insufficient data")
        
        if not all_features:
            return {
                "error": "No training data available",
                "X": None,
                "y": None,
                "samples": 0,
                "coins_used": [],
                "errors": errors,
            }
        
        X = np.vstack(all_features)
        y = np.concatenate(all_labels)
        
        return {
            "X": X,
            "y": y,
            "samples": len(X),
            "coins_used": coins_used,
            "errors": errors,
        }
    
    # ============================================================
    # Public API: train_model
    # ============================================================
    
    def train_model(
        self,
        period: str = "1m",
        coins: Optional[List[str]] = None,
        profile_name: Optional[str] = None,
        profile: Optional[Dict[str, Any]] = None,
        strategy: Optional[str] = None,
        save: bool = True,
    ) -> Dict[str, Any]:
        """
        آموزش مدل (fetch داده + پاس دادن به ModelManager)
        
        پارامترها:
            period: بازه داده
            coins: لیست ارزها
            profile_name: نام پروفایل (از presets یا DB)
            profile: پروفایل مستقیم (dict)
            strategy: استراتژی (اگه می‌خوای override کنی)
            save: آیا ذخیره بشه؟
        
        خروجی:
            دیکشنری نتیجه از ModelManager
        """
        if self.is_training:
            return {"success": False, "message": "آموزش در حال انجام است"}
        
        self.is_training = True
        self.stats["is_training"] = True
        self.stats["total_trainings"] += 1
        self.stats["training_period"] = period
        
        try:
            # ===== ۱. چک API =====
            status = self.check_api_status()
            if not status["can_train"]:
                self.stats["failed_trainings"] += 1
                self.stats["last_error"] = status["message"]
                self._add_log(f"❌ آموزش ناموفق: {status['message']}")
                return {
                    "success": False,
                    "message": status["message"],
                    "api_status": status["api_status"],
                    "credits_remaining": status["credits_remaining"],
                }
            
            # ===== ۲. بارگذاری پروفایل =====
            if profile is None:
                if profile_name:
                    load_result = self.model_manager.load_profile(profile_name)
                    if not load_result.get("success"):
                        self.stats["failed_trainings"] += 1
                        return {
                            "success": False,
                            "error": f"Profile '{profile_name}' not found",
                        }
                    profile = load_result["profile"]
                else:
                    # پروفایل فعال
                    profile = self.model_manager.get_current_profile()
            
            # Override strategy اگه داده شده
            if strategy:
                profile = {**profile, "learning_strategy": strategy}
            
            # ===== ۳. چک Quota =====
            quota_check = self._check_quota(profile)
            if not quota_check.get("can_proceed", True):
                self.stats["failed_trainings"] += 1
                self.stats["last_error"] = quota_check.get("message")
                self._add_log(f"❌ Quota: {quota_check.get('message')}")
                return {
                    "success": False,
                    "error": "Quota exceeded",
                    "message": quota_check.get("message"),
                    "quota": quota_check,
                }
            
            # ===== ۴. جمع‌آوری X, y =====
            self._add_log(f"📚 شروع آموزش (بازه: {period}, profile: {profile.get('name')})")
            
            data = self._collect_training_data(period, coins)
            
            if data.get("error"):
                self.stats["failed_trainings"] += 1
                self.stats["last_error"] = data["error"]
                self._add_log(f"❌ {data['error']}")
                return {
                    "success": False,
                    "message": data["error"],
                    "errors": data.get("errors", []),
                }
            
            X = data["X"]
            y = data["y"]
            
            self._add_log(f"📊 کل نمونه‌های آموزش: {len(X)}")
            self.stats["data_points_used"] = len(X)
            
            # ===== ۵. آموزش از طریق ModelManager =====
            result = self.model_manager.train(
                X=X,
                y=y,
                profile=profile,
                period=period,
                coins=data["coins_used"],
                save=save,
                profile_name=profile_name or profile.get("name"),
            )
            
            # ===== ۶. آپدیت آمار =====
            if result.get("success"):
                self.stats["successful_trainings"] += 1
                self.stats["last_training"] = datetime.now().isoformat()
                self.stats["last_error"] = None
                self.stats["last_score"] = result.get("accuracy")
                self.stats["mode"] = "BETA"
                
                self._add_log(
                    f"✅ آموزش موفق! "
                    f"نسخه: {result.get('version')}, "
                    f"دقت: {result.get('accuracy', 0):.3f}, "
                    f"استراتژی: {result.get('strategy_used')}"
                )
                
                # ===== ۷. ثبت در Analytics =====
                self._record_analytics(result, profile, period)
                
            else:
                self.stats["failed_trainings"] += 1
                self.stats["last_error"] = result.get("error", "Unknown")
                self._add_log(
                    f"❌ آموزش ناموفق: {result.get('error', 'خطای ناشناخته')}"
                )
            
            return result
            
        except Exception as e:
            self.stats["failed_trainings"] += 1
            self.stats["last_error"] = str(e)
            self._add_log(f"❌ آموزش ناموفق: {e}")
            logger.error(f"Training error: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
        
        finally:
            self.is_training = False
            self.stats["is_training"] = False
    
    # ============================================================
    # Public API: incremental_train
    # ============================================================
    
    def incremental_train(
        self,
        period: str = "1m",
        coins: Optional[List[str]] = None,
        profile_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        آموزش افزایشی (fetch + پاس دادن با strategy=incremental)
        """
        return self.train_model(
            period=period,
            coins=coins,
            profile_name=profile_name,
            strategy="incremental",
        )
    
    # ============================================================
    # Public API: train_batch (A/B Testing)
    # ============================================================
    
    def train_batch(
        self,
        profiles: List[str],
        period: str = "1m",
        coins: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        آموزش با چند پروفایل (A/B Testing)
        
        پارامترها:
            profiles: لیست نام پروفایل‌ها
            period: بازه
            coins: ارزها
        
        خروجی:
            دیکشنری شامل:
                - success
                - best_profile
                - best_accuracy
                - results
                - summary
        """
        self._add_log(
            f"🧪 A/B Testing شروع شد "
            f"({len(profiles)} پروفایل: {profiles})"
        )
        
        results = {}
        best_accuracy = 0.0
        best_profile = None
        
        for profile_name in profiles:
            self._add_log(f"🔄 آموزش با پروفایل: {profile_name}")
            
            result = self.train_model(
                period=period,
                coins=coins,
                profile_name=profile_name,
                save=False,  # ← ذخیره نکن برای A/B test
            )
            
            results[profile_name] = result
            
            if result.get("success"):
                acc = result.get("accuracy", 0)
                if acc > best_accuracy:
                    best_accuracy = acc
                    best_profile = profile_name
        
        # ===== ذخیره بهترین =====
        if best_profile:
            self._add_log(
                f"🏆 بهترین پروفایل: {best_profile} "
                f"(دقت: {best_accuracy:.3f})"
            )
            
            # آموزش مجدد با بهترین و ذخیره
            final = self.train_model(
                period=period,
                coins=coins,
                profile_name=best_profile,
                save=True,
            )
            
            return {
                "success": True,
                "best_profile": best_profile,
                "best_accuracy": best_accuracy,
                "results": results,
                "final_model": final,
                "summary": {
                    "profiles_tested": len(profiles),
                    "profiles_successful": sum(
                        1 for r in results.values() if r.get("success")
                    ),
                },
            }
        
        return {
            "success": False,
            "error": "All profiles failed",
            "results": results,
        }
    
    # ============================================================
    # Quota Check
    # ============================================================
    
    def _check_quota(self, profile: Dict[str, Any]) -> Dict[str, Any]:
        """بررسی Quota قبل از آموزش"""
        try:
            if hasattr(self.model_manager, "analyze_training"):
                analysis = self.model_manager.analyze_training(
                    profile=profile,
                    coins_count=len(self.coins),
                    period=self.stats.get("training_period", "1m"),
                )
                
                return {
                    "can_proceed": analysis.get("can_proceed", True),
                    "estimated_size_mb": analysis.get("estimated_model_size_mb", 0),
                    "available_mb": analysis.get("available_mb", 0),
                    "message": analysis.get("warning") or "فضا کافی است",
                    "analysis": analysis,
                }
            
            return {"can_proceed": True, "message": "Quota check skipped"}
            
        except Exception as e:
            logger.warning(f"⚠️ Quota check failed: {e}")
            return {"can_proceed": True, "error": str(e)}
    
    # ============================================================
    # Analytics Recording
    # ============================================================
    
    def _record_analytics(
        self,
        result: Dict[str, Any],
        profile: Dict[str, Any],
        period: str,
    ) -> None:
        """
        ثبت آموزش در Analytics DB
        
        جدول: model_performance
        """
        if not self.analytics_db or not self.analytics_db.is_connected():
            return
        
        try:
            version = result.get("version")
            accuracy = result.get("accuracy", 0)
            samples = result.get("samples", 0)
            
            # امروز
            today = datetime.now().date()
            
            # Insert/Update
            self.analytics_db.execute("""
                INSERT INTO model_performance (
                    model_version, date, predictions_made,
                    correct_predictions, accuracy, avg_confidence
                ) VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (model_version, date) DO UPDATE
                SET accuracy = EXCLUDED.accuracy,
                    avg_confidence = EXCLUDED.avg_confidence
            """, (
                version,
                today,
                0,  # predictions_made (بعداً آپدیت)
                0,  # correct_predictions
                accuracy,
                0.0,  # avg_confidence
            ))
            
            self._add_log(f"📊 ثبت در Analytics: {version}")
            
        except Exception as e:
            logger.warning(f"⚠️ Analytics recording failed: {e}")
    
    def get_analytics_stats(self, days: int = 30) -> Dict[str, Any]:
        """
        دریافت آمار از Analytics DB
        
        پارامترها:
            days: تعداد روز
        
        خروجی:
            دیکشنری آمار
        """
        if not self.analytics_db or not self.analytics_db.is_connected():
            return {"error": "Analytics DB not connected"}
        
        try:
            # آمار کلی
            stats = self.analytics_db.execute("""
                SELECT
                    COUNT(*) as total_records,
                    AVG(accuracy) as avg_accuracy,
                    MAX(accuracy) as max_accuracy,
                    MIN(accuracy) as min_accuracy
                FROM model_performance
                WHERE date >= NOW() - (%s * INTERVAL '1 day')
            """, (days,))
            
            # تاریخچه روزانه
            daily = self.analytics_db.execute("""
                SELECT
                    date,
                    AVG(accuracy) as avg_accuracy,
                    COUNT(*) as models_count
                FROM model_performance
                WHERE date >= NOW() - (%s * INTERVAL '1 day')
                GROUP BY date
                ORDER BY date DESC
            """, (days,))
            
            return {
                "success": True,
                "summary": stats[0] if stats else {},
                "daily": daily or [],
                "period_days": days,
            }
            
        except Exception as e:
            logger.error(f"❌ Analytics stats error: {e}")
            return {"error": str(e)}
    
    # ============================================================
    # Auto Training (Scheduler)
    # ============================================================
    
    def start_auto_train(
        self,
        interval_hours: Optional[int] = None,
        period: Optional[str] = None,
        profile_name: Optional[str] = None,
        incremental: bool = False,
        coins: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        شروع آموزش خودکار
        
        پارامترها:
            interval_hours: فاصله (ساعت)
            period: بازه
            profile_name: نام پروفایل
            incremental: آیا افزایشی؟
            coins: ارزها
        
        خروجی:
            دیکشنری وضعیت
        """
        if self.is_running:
            return {"success": False, "message": "سیستم در حال اجراست"}
        
        # پیش‌فرض‌ها
        if interval_hours is None:
            interval_hours = self.auto_trainer_config.get("interval_hours", 6)
        if period is None:
            period = self.auto_trainer_config.get("period", "1m")
        if profile_name is None:
            profile_name = "balanced"
        
        self.is_running = True
        self.stats["is_running"] = True
        self.stats["training_period"] = period
        self.stop_event.clear()
        
        def run() -> None:
            self._add_log(
                f"🔄 آموزش خودکار شروع شد "
                f"(فاصله: {interval_hours}h, بازه: {period}, "
                f"profile: {profile_name})"
            )
            
            while not self.stop_event.is_set():
                try:
                    # اجرای آموزش
                    result = self.train_model(
                        period=period,
                        coins=coins,
                        profile_name=profile_name,
                        strategy="incremental" if incremental else None,
                        save=True,
                    )
                    
                    self._add_log(
                        f"📊 نتیجه: {result.get('message', 'نامشخص')}"
                    )
                    
                except Exception as e:
                    self._add_log(f"❌ خطا در چرخه آموزش: {e}")
                    logger.error(f"Auto train cycle error: {e}", exc_info=True)
                
                # صبر تا cycle بعدی
                wait_seconds = interval_hours * 3600
                self.stop_event.wait(wait_seconds)
            
            self.is_running = False
            self.stats["is_running"] = False
            self._add_log("⏹️ آموزش خودکار متوقف شد")
        
        self.thread = threading.Thread(target=run, daemon=True)
        self.thread.start()
        
        return {
            "success": True,
            "message": f"آموزش خودکار شروع شد (هر {interval_hours} ساعت)",
            "interval_hours": interval_hours,
            "period": period,
            "profile_name": profile_name,
            "incremental": incremental,
        }
    
    def stop_auto_train(self) -> Dict[str, Any]:
        """متوقف کردن آموزش خودکار"""
        if not self.is_running:
            return {"success": False, "message": "سیستم در حال اجرا نیست"}
        
        self.stop_event.set()
        
        if self.thread:
            self.thread.join(timeout=5)
        
        self.is_running = False
        self.stats["is_running"] = False
        self._add_log("⏹️ آموزش خودکار توسط کاربر متوقف شد")
        
        return {"success": True, "message": "آموزش خودکار متوقف شد"}
    
    # ============================================================
    # Stats
    # ============================================================
    
    def get_stats(self) -> Dict[str, Any]:
        """
        دریافت آمار کامل
        
        خروجی:
            دیکشنری شامل همه آمار
        """
        # وضعیت API
        try:
            status = self.check_api_status()
        except Exception:
            status = {"api_status": "unknown", "credits_remaining": 0}
        
        # آمار ModelManager
        try:
            model_stats = self.model_manager.get_stats()
        except Exception:
            model_stats = {}
        
        # وضعیت Quota
        try:
            quota = self.model_manager.get_quota_status()
        except Exception:
            quota = {}
        
        return {
            # وضعیت کلی
            "is_running": self.is_running,
            "is_training": self.is_training,
            
            # آمار training
            "stats": {
                **self.stats,
                "last_score": self.stats.get("last_score"),
                "training_period": self.stats.get("training_period"),
            },
            
            # API
            "api_status": status,
            
            # ارزها
            "coins": self.coins,
            
            # مدل
            "model_exists": model_stats.get("loaded", False),
            "current_version": (
                self.model_manager.current_version
                if self.model_manager else None
            ),
            
            # Quota
            "quota": quota,
            
            # لاگ‌ها
            "logs": self.logs[-30:],
            
            # تنظیمات
            "points_config": self.historical_points_config,
            
            # Timestamp
            "timestamp": datetime.now().isoformat(),
        }
    
    # ============================================================
    # Training History
    # ============================================================
    
    def get_training_history(
        self,
        period: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        دریافت تاریخچه آموزش
        
        پارامترها:
            period: فیلتر بازه
            limit: تعداد
        
        خروجی:
            لیست تاریخچه
        """
        if not self.db or not self.db.is_connected():
            return []
        
        try:
            # کوئری پایه
            if period:
                query = """
                    SELECT
                        m.id, m.version, m.accuracy, m.training_date,
                        m.period, m.training_samples, m.is_ensemble,
                        h.action, h.old_accuracy, h.new_accuracy,
                        h.improvement_percent
                    FROM models m
                    LEFT JOIN model_training_history h ON m.id = h.model_id
                    WHERE m.period = %s
                    ORDER BY m.training_date DESC
                    LIMIT %s
                """
                result = self.db.execute(query, (period, limit))
            else:
                query = """
                    SELECT
                        m.id, m.version, m.accuracy, m.training_date,
                        m.period, m.training_samples, m.is_ensemble,
                        h.action, h.old_accuracy, h.new_accuracy,
                        h.improvement_percent
                    FROM models m
                    LEFT JOIN model_training_history h ON m.id = h.model_id
                    ORDER BY m.training_date DESC
                    LIMIT %s
                """
                result = self.db.execute(query, (limit,))
            
            return result or []
            
        except Exception as e:
            logger.error(f"❌ Training history error: {e}", exc_info=True)
            return []
