# application/use_cases/predict_coin.py
# ============================================================
# Use Case: Predict Coin - نسخه ۳.۰
# RuleEngine Integration + Cache + Repository
# ============================================================
# 
# تغییرات نسخه ۳.۰:
#   - حذف _demo_predict (RuleEngine جایگزین شده)
#   - حذف وابستگی به feature_engineer.extract_features
#   - اتکا به model_manager.predict_full()
#   - حفظ ساختار execute و execute_multiple
#   - حفظ Cache و Repository integration
# ============================================================

import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from domain.entities.prediction import Prediction as PredictionEntity, SignalType
from domain.value_objects.signal import Signal
from domain.interfaces.api_client import APIClient
from models.manager.model_manager import ModelManager
from infrastructure.repositories import repos

logger = logging.getLogger(__name__)


# ============================================================
# PredictCoinUseCase v3.0
# ============================================================

class PredictCoinUseCase:
    """
    Use Case پیش‌بینی یک ارز
    
    تغییرات نسخه ۳.۰:
        - حذف feature_engineer.extract_features
        - استفاده مستقیم از OHLCV
        - model_manager.predict_full() → Prediction
        - ذخیره در Repository حفظ شد
        - Cache حفظ شد
    
    معماری:
        ۱. Cache check
        ۲. دریافت OHLCV از API
        ۳. تبدیل به DataFrame
        ۴. model_manager.predict_full()
        ۵. ساخت Entity
        ۶. ذخیره در DB
        ۷. کش کردن
    """
    
    # Cache TTL
    CACHE_TTL = 300  # ۵ دقیقه
    
    # بازه‌های معتبر
    VALID_PERIODS: List[str] = ["24h", "1w", "1m", "3m", "6m"]
    
    # حداقل کندل لازم
    MIN_CANDLES = 50
    
    def __init__(
        self,
        api_client: APIClient,
        model_manager: ModelManager,
        feature_engineer: Any = None,  # ← حفظ برای سازگاری (استفاده نمی‌شه)
    ) -> None:
        """
        Args:
            api_client: کلاینت API
            model_manager: ModelManager
            feature_engineer: (deprecated) حفظ برای سازگاری امضای قدیمی
        """
        self.api_client = api_client
        self.model_manager = model_manager
        self.feature_engineer = feature_engineer  # ← نگه داشته ولی استفاده نمی‌شه
        
        # Prediction Repository
        self.prediction_repo = repos.prediction
        
        # Cache
        try:
            from infrastructure.database import get_cache
            self.cache = get_cache()
        except Exception:
            self.cache = None
        
        logger.info("✅ PredictCoinUseCase v3.0 initialized")
    
    # ============================================================
    # Execute - Single
    # ============================================================
    
    def execute(
        self,
        coin_id: str,
        period: str = "24h",
        save: bool = True,
        use_cache: bool = True,
    ) -> PredictionEntity:
        """
        اجرای Use Case
        
        Args:
            coin_id: شناسه ارز (bitcoin)
            period: بازه زمانی
            save: ذخیره در DB؟
            use_cache: استفاده از cache؟
        
        Returns:
            PredictionEntity
        
        Raises:
            ValueError: بازه نامعتبر
            RuntimeError: داده یا مدل در دسترس نیست
        """
        start_time = time.time()
        
        # ============================================================
        # ۱. اعتبارسنجی
        # ============================================================
        if period not in self.VALID_PERIODS:
            raise ValueError(
                f"Invalid period: {period}. "
                f"Must be one of {self.VALID_PERIODS}"
            )
        
        # ============================================================
        # ۲. Cache Check
        # ============================================================
        cache_key = f"prediction:{coin_id}:{period}"
        
        if use_cache and self.cache and self.cache.is_connected():
            cached = self.cache.get(cache_key)
            if cached and isinstance(cached, dict):
                logger.debug(f"⚡ Prediction from cache: {coin_id}")
                return self._dict_to_prediction(cached)
        
        # ============================================================
        # ۳. دریافت داده
        # ============================================================
        chart_data = self.api_client.get_chart(coin_id, period)
        
        if not chart_data or (
            isinstance(chart_data, dict) and "error" in chart_data
        ):
            error_msg = (
                chart_data.get("error", "No data")
                if isinstance(chart_data, dict) else "No data"
            )
            logger.error(f"Chart data failed for {coin_id}: {error_msg}")
            raise RuntimeError(f"Failed to get chart data: {error_msg}")
        
        # ============================================================
        # ۴. تبدیل به DataFrame
        # ============================================================
        df = self._list_to_dataframe(chart_data)
        
        if df is None or len(df) < self.MIN_CANDLES:
            raise RuntimeError(
                f"Insufficient data for {coin_id} "
                f"(need {self.MIN_CANDLES}+ candles, "
                f"got {len(df) if df is not None else 0})"
            )
        
        # ============================================================
        # ۵. پیش‌بینی از ModelManager
        # ============================================================
        if self.model_manager.engine is None:
            logger.warning(
                f"⚠️ RuleEngine not loaded, using neutral score"
            )
            # Fallback: neutral score
            prediction_score = 0.5
            prediction = None
            model_mode = "NEUTRAL"
        else:
            # ساخت symbol از coin_id
            symbol = self._coin_to_symbol(coin_id)
            
            # پیش‌بینی کامل
            prediction = self.model_manager.predict_full(
                df=df,
                symbol=symbol,
                coin_id=coin_id,
                update_state=True,
            )
            
            if prediction is None:
                prediction_score = 0.5
                model_mode = "FALLBACK"
            else:
                prediction_score = float(prediction.score)
                model_mode = "RULE_ENGINE"
        
        # ============================================================
        # ۶. Signal
        # ============================================================
        signal = Signal.from_score(prediction_score)
        
        # ============================================================
        # ۷. اطلاعات ارز
        # ============================================================
        coin_info = self.api_client.get_coin(coin_id)
        current_price = coin_info.get("price", 0) if coin_info else 0
        coin_name = coin_info.get("name", coin_id) if coin_info else coin_id
        
        # ============================================================
        # ۸. ساخت Entity
        # ============================================================
        processing_time = (time.time() - start_time) * 1000
        
        # دلایل (اگه prediction داشتیم)
        reasons: List[str] = []
        if prediction and hasattr(prediction, "reasons"):
            reasons = prediction.reasons
        elif not reasons:
            reasons = [f"امتیاز: {prediction_score:.3f}"]
        
        # state
        state = "UNKNOWN"
        if prediction and hasattr(prediction, "state"):
            state = prediction.state.value
        
        entity = PredictionEntity(
            coin=coin_id,
            coin_name=coin_name,
            current_price=float(current_price),
            signal=signal.get_text(),
            signal_type=signal.type,
            confidence=signal.confidence,
            confidence_score=signal.confidence,
            prediction_score=float(prediction_score),
            period=period,
            model_mode=model_mode,
            timestamp=datetime.now(),
            processing_time_ms=round(processing_time, 2),
            data_points=len(df) if df is not None else 0,
            extra={
                "state": state,
                "reasons": reasons,
            },
        )
        
        # ============================================================
        # ۹. ذخیره در Repository
        # ============================================================
        if save:
            try:
                self.prediction_repo.save(entity)
                logger.debug(
                    f"✅ Prediction saved: {coin_id} "
                    f"({signal.type.value}, score={prediction_score:.3f})"
                )
            except Exception as e:
                logger.warning(f"⚠️ Could not save prediction: {e}")
        
        # ============================================================
        # ۱۰. Cache
        # ============================================================
        if use_cache and self.cache and self.cache.is_connected():
            try:
                self.cache.set(
                    cache_key,
                    entity.to_dict(),
                    ttl=self.CACHE_TTL,
                )
            except Exception as e:
                logger.debug(f"Cache set error: {e}")
        
        logger.info(
            f"✅ Prediction for {coin_id}: "
            f"{signal.type.value} ({signal.confidence}%) "
            f"score={prediction_score:.3f} state={state}"
        )
        
        return entity
    
    # ============================================================
    # Execute - Multiple
    # ============================================================
    
    def execute_multiple(
        self,
        coins: List[str],
        period: str = "24h",
        save: bool = True,
    ) -> List[PredictionEntity]:
        """
        اجرای پیش‌بینی برای چند ارز
        
        Args:
            coins: لیست ارزها
            period: بازه
            save: ذخیره؟
        
        Returns:
            لیست PredictionEntity
        """
        predictions: List[PredictionEntity] = []
        
        for coin in coins:
            try:
                entity = self.execute(
                    coin,
                    period,
                    save=save,
                    use_cache=True,
                )
                predictions.append(entity)
            except Exception as e:
                logger.error(f"Failed to predict {coin}: {e}")
                
                # Prediction خطا
                predictions.append(PredictionEntity(
                    coin=coin,
                    coin_name=coin,
                    current_price=0,
                    signal="خطا در پیش‌بینی",
                    signal_type=SignalType.ERROR,
                    confidence=0,
                    confidence_score=0,
                    prediction_score=0.0,
                    period=period,
                    model_mode="ERROR",
                    timestamp=datetime.now(),
                    processing_time_ms=0,
                    data_points=0,
                    extra={"error": str(e)},
                ))
        
        return predictions
    
    # ============================================================
    # Helpers - Data Conversion
    # ============================================================
    
    @staticmethod
    def _list_to_dataframe(data: List) -> Optional[pd.DataFrame]:
        """
        تبدیل لیست API به DataFrame OHLCV
        
        ساختار API: [[timestamp, price], ...]
        چون OHLCV کامل نداریم، از price برای همه ستون‌ها استفاده می‌کنیم.
        
        ⚠️ محدودیت: این یه تقریبه.
        بعداً که Kline واقعی اضافه شد، این تابع رو replace می‌کنیم.
        """
        if not data:
            return None
        
        rows = []
        for point in data:
            if isinstance(point, (list, tuple)) and len(point) >= 2:
                try:
                    ts = point[0]
                    price = float(point[1])
                    
                    # اگه داده OHLCV کامل هست (۶ ستون)
                    if len(point) >= 6:
                        rows.append({
                            "timestamp": pd.to_datetime(ts, unit="ms", errors="coerce"),
                            "Open": float(point[1]),
                            "High": float(point[2]),
                            "Low": float(point[3]),
                            "Close": float(point[4]),
                            "Volume": float(point[5]),
                        })
                    else:
                        # فقط price داریم
                        rows.append({
                            "timestamp": pd.to_datetime(ts, unit="ms", errors="coerce"),
                            "Open": price,
                            "High": price,
                            "Low": price,
                            "Close": price,
                            "Volume": 1.0,
                        })
                except (ValueError, TypeError, IndexError):
                    continue
        
        if not rows:
            return None
        
        df = pd.DataFrame(rows)
        df = df.set_index("timestamp").sort_index()
        df = df.dropna()
        
        return df
    
    # ============================================================
    # Helpers - Symbol Mapping
    # ============================================================
    
    @staticmethod
    def _coin_to_symbol(coin_id: str) -> str:
        """bitcoin → BTC/USDT"""
        mapping = {
            "bitcoin": "BTC/USDT",
            "ethereum": "ETH/USDT",
            "solana": "SOL/USDT",
            "binancecoin": "BNB/USDT",
            "ripple": "XRP/USDT",
            "cardano": "ADA/USDT",
            "dogecoin": "DOGE/USDT",
            "avalanche-2": "AVAX/USDT",
            "polkadot": "DOT/USDT",
            "chainlink": "LINK/USDT",
            "polygon": "MATIC/USDT",
            "tron": "TRX/USDT",
            "shiba-inu": "SHIB/USDT",
            "litecoin": "LTC/USDT",
            "uniswap": "UNI/USDT",
        }
        cid = coin_id.lower()
        if cid in mapping:
            return mapping[cid]
        return f"{coin_id.upper()}/USDT"
    
    # ============================================================
    # Helpers - Cache
    # ============================================================
    
    def _dict_to_prediction(self, data: Dict[str, Any]) -> PredictionEntity:
        """تبدیل dict به PredictionEntity"""
        signal_type_str = data.get("signal_type", "NEUTRAL")
        try:
            signal_type = SignalType(signal_type_str)
        except ValueError:
            signal_type = SignalType.NEUTRAL
        
        timestamp_str = data.get("timestamp", datetime.now().isoformat())
        try:
            timestamp = datetime.fromisoformat(timestamp_str)
        except (ValueError, TypeError):
            timestamp = datetime.now()
        
        return PredictionEntity(
            coin=data.get("coin", ""),
            coin_name=data.get("coin_name", ""),
            current_price=float(data.get("current_price", 0)),
            signal=data.get("signal", ""),
            signal_type=signal_type,
            confidence=int(data.get("confidence", 50)),
            confidence_score=int(data.get("confidence_score", 50)),
            prediction_score=float(data.get("prediction_score", 0.5)),
            period=data.get("period", "24h"),
            model_mode=data.get("model_mode", "RULE_ENGINE"),
            timestamp=timestamp,
            processing_time_ms=float(data.get("processing_time_ms", 0)),
            data_points=int(data.get("data_points", 0)),
            extra=data.get("extra"),
        )
    
    # ============================================================
    # Stats
    # ============================================================
    
    def get_stats(self) -> Dict[str, Any]:
        """آمار Use Case"""
        return {
            "cache_connected": (
                self.cache is not None and self.cache.is_connected()
            ),
            "model_loaded": self.model_manager.engine is not None,
            "model_version": self.model_manager.current_version or "default",
            "valid_periods": self.VALID_PERIODS,
            "min_candles": self.MIN_CANDLES,
        }


__all__ = ["PredictCoinUseCase"]
