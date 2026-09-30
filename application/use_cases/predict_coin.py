# application/use_cases/predict_coin.py
# ============================================================
# Use Case: Predict Coin - نسخه ۴.۰
# OHLCV واقعی + لاگ کامل + خطایابی
# ============================================================

import logging
import time
from datetime import datetime, timedelta
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
# Constants
# ============================================================

# period → interval (برای get_ohlcv_candles)
PERIOD_TO_INTERVAL: Dict[str, str] = {
    "24h": "1h",
    "1w":  "4h",
    "1m":  "4h",
    "3m":  "1d",
    "6m":  "1d",
}

# period → range (چند وقت داده)
PERIOD_TO_RANGE: Dict[str, str] = {
    "24h": "1w",
    "1w":  "1mo",
    "1m":  "3mo",
    "3m":  "6mo",
    "6m":  "1y",
}

# حداقل کندل لازم
MIN_CANDLES = 50

# Cache TTL
CACHE_TTL = 300  # ۵ دقیقه

# Periods معتبر
VALID_PERIODS: List[str] = ["24h", "1w", "1m", "3m", "6m"]


# ============================================================
# PredictCoinUseCase v4.0
# ============================================================

class PredictCoinUseCase:
    """
    Use Case پیش‌بینی یک ارز
    
    تغییرات نسخه ۴.۰:
        - OHLCV واقعی از get_ohlcv_candles
        - لاگ کامل هر مرحله
        - حذف OHLCV قلابی
        - Smart interval/range بر اساس period
    """
    
    def __init__(
        self,
        api_client: APIClient,
        model_manager: ModelManager,
        feature_engineer: Any = None,
    ) -> None:
        self.api_client = api_client
        self.model_manager = model_manager
        self.feature_engineer = feature_engineer  # برای سازگاری
        self.prediction_repo = repos.prediction
        
        # Cache
        try:
            from infrastructure.database import get_cache
            self.cache = get_cache()
        except Exception:
            self.cache = None
        
        logger.info("✅ PredictCoinUseCase v4.0 initialized")
    
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
        اجرای Use Case پیش‌بینی
        
        لاگ کامل:
            ✅ Predict: شروع
            ✅ مرحله ۱: cache
            ✅ مرحله ۲: OHLCV fetch
            ✅ مرحله ۳: predict
            ✅ Predict: موفق
        """
        start_time = time.time()
        
        # ============================================================
        # لاگ شروع
        # ============================================================
        
        logger.info(
            f"🎯 Predict START: coin_id={coin_id}, period={period}, "
            f"save={save}"
        )
        
        # ============================================================
        # ۱. اعتبارسنجی
        # ============================================================
        
        if period not in VALID_PERIODS:
            msg = (
                f"Invalid period: {period}. "
                f"Must be one of {VALID_PERIODS}"
            )
            logger.error(f"❌ Predict FAILED: {msg}")
            raise ValueError(msg)
        
        # ============================================================
        # ۲. Cache Check
        # ============================================================
        
        cache_key = f"prediction:{coin_id}:{period}"
        
        if use_cache and self.cache and self.cache.is_connected():
            try:
                cached = self.cache.get(cache_key)
                if cached and isinstance(cached, dict):
                    logger.info(f"⚡ Predict CACHE HIT: {coin_id} ({period})")
                    return self._dict_to_prediction(cached)
            except Exception as e:
                logger.debug(f"Cache read error: {e}")
        
        # ============================================================
        # ۳. OHLCV Fetch
        # ============================================================
        
        logger.info(f"📥 Predict STEP-2: Fetching OHLCV for {coin_id}...")
        
        df = self._fetch_ohlcv(coin_id, period)
        
        if df is None or len(df) < MIN_CANDLES:
            df_len = len(df) if df is not None else 0
            msg = (
                f"Insufficient OHLCV data for {coin_id} "
                f"(need {MIN_CANDLES}+ candles, got {df_len})"
            )
            logger.error(f"❌ Predict FAILED (STEP-2): {msg}")
            raise RuntimeError(msg)
        
        logger.info(
            f"✅ Predict STEP-2 OK: {coin_id} → {len(df)} candles "
            f"({df.index[0].strftime('%Y-%m-%d')} to "
            f"{df.index[-1].strftime('%Y-%m-%d')})"
        )
        
        # ============================================================
        # ۴. Predict
        # ============================================================
        
        logger.info(f"🔮 Predict STEP-3: Running RuleEngine...")
        
        if self.model_manager.engine is None:
            logger.warning(
                f"⚠️ Predict STEP-3: RuleEngine not loaded, using neutral score"
            )
            prediction_score = 0.5
            prediction = None
            model_mode = "NEUTRAL"
        else:
            symbol = self._coin_to_symbol(coin_id)
            
            prediction = self.model_manager.predict_full(
                df=df,
                symbol=symbol,
                coin_id=coin_id,
                update_state=True,
            )
            
            if prediction is None:
                logger.warning(
                    f"⚠️ Predict STEP-3: predict_full returned None, using fallback"
                )
                prediction_score = 0.5
                model_mode = "FALLBACK"
            else:
                prediction_score = float(prediction.score)
                model_mode = "RULE_ENGINE"
                
                logger.info(
                    f"✅ Predict STEP-3 OK: score={prediction_score:.4f}, "
                    f"state={prediction.state.value}, "
                    f"rules_passed={sum(1 for r in prediction.rule_results if r.passed)}"
                    f"/{len(prediction.rule_results)}"
                )
        
        # ============================================================
        # ۵. Signal
        # ============================================================
        
        signal = Signal.from_score(prediction_score)
        
        # ============================================================
        # ۶. Coin Info
        # ============================================================
        
        try:
            coin_info = self.api_client.get_coin(coin_id)
            current_price = coin_info.get("price", 0) if coin_info else 0
            coin_name = coin_info.get("name", coin_id) if coin_info else coin_id
        except Exception as e:
            logger.debug(f"Coin info fetch failed: {e}")
            current_price = 0
            coin_name = coin_id
        
        # ============================================================
        # ۷. ساخت Entity
        # ============================================================
        
        processing_time = (time.time() - start_time) * 1000
        
        # دلایل
        reasons: List[str] = []
        if prediction and hasattr(prediction, "reasons"):
            reasons = prediction.reasons
        if not reasons:
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
            data_points=len(df),
            extra={
                "state": state,
                "reasons": reasons,
            },
        )
        
        # ============================================================
        # ۸. Save
        # ============================================================
        
        if save:
            try:
                self.prediction_repo.save(entity)
                logger.debug(
                    f"✅ Predict STEP-4: Saved to DB "
                    f"(id={entity.id}, signal={signal.type.value})"
                )
            except Exception as e:
                logger.warning(f"⚠️ Predict STEP-4: Save failed: {e}")
        
        # ============================================================
        # ۹. Cache
        # ============================================================
        
        if use_cache and self.cache and self.cache.is_connected():
            try:
                self.cache.set(cache_key, entity.to_dict(), ttl=CACHE_TTL)
            except Exception as e:
                logger.debug(f"Cache set error: {e}")
        
        # ============================================================
        # ✅ لاگ موفقیت
        # ============================================================
        
        logger.info(
            f"🎉 Predict SUCCESS: {coin_id} ({period}) — "
            f"signal={signal.type.value}, "
            f"confidence={signal.confidence}%, "
            f"score={prediction_score:.4f}, "
            f"state={state}, "
            f"duration={processing_time:.0f}ms"
        )
        
        return entity
    
    # ============================================================
    # Execute Multiple
    # ============================================================
    
    def execute_multiple(
        self,
        coins: List[str],
        period: str = "24h",
        save: bool = True,
    ) -> List[PredictionEntity]:
        """پیش‌بینی چند ارز"""
        logger.info(f"🎯 Predict MULTIPLE START: {len(coins)} coins, period={period}")
        
        predictions: List[PredictionEntity] = []
        success = 0
        failed = 0
        
        for coin in coins:
            try:
                entity = self.execute(coin, period, save=save, use_cache=True)
                predictions.append(entity)
                success += 1
            except Exception as e:
                failed += 1
                logger.error(f"❌ Predict failed for {coin}: {e}")
                
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
                    extra={"error": str(e)[:200]},
                ))
        
        logger.info(
            f"🎉 Predict MULTIPLE SUCCESS: "
            f"{success} ok, {failed} failed, total={len(coins)}"
        )
        
        return predictions
    
    # ============================================================
    # OHLCV Fetch (جدید v4.0)
    # ============================================================
    
    def _fetch_ohlcv(
        self,
        coin_id: str,
        period: str,
    ) -> Optional[pd.DataFrame]:
        """
        دریافت OHLCV واقعی از CoinStats /ohlcv/candles
        
        Returns:
            DataFrame یا None
        """
        # تبدیل coin_id → pair
        try:
            if hasattr(self.api_client, "coin_id_to_pair"):
                pair = self.api_client.coin_id_to_pair(coin_id)
            else:
                pair = f"{coin_id.upper()}/USDT"
            
            if not pair:
                logger.error(f"❌ Cannot map {coin_id} to pair")
                return None
        except Exception as e:
            logger.error(f"❌ coin_id_to_pair error: {e}")
            return None
        
        # interval و range
        interval = PERIOD_TO_INTERVAL.get(period, "4h")
        data_range = PERIOD_TO_RANGE.get(period, "3mo")
        
        logger.debug(
            f"📥 Fetching OHLCV: pair={pair}, "
            f"interval={interval}, range={data_range}"
        )
        
        try:
            result = self.api_client.get_ohlcv_candles(
                exchange="Binance",
                pair=pair,
                interval=interval,
                range=data_range,
                use_cache=True,
            )
            
            if not result or "candles" not in result:
                err = result.get("error") if result else "no response"
                logger.warning(f"⚠️ OHLCV failed for {pair}: {err}")
                return None
            
            # هشدار cap
            if result.get("warning"):
                logger.warning(f"⚠️ {result['warning']}")
            
            candles = result["candles"]
            
            df = self._candles_to_dataframe(candles)
            
            if df is None or len(df) < MIN_CANDLES:
                df_len = len(df) if df is not None else 0
                logger.warning(
                    f"⚠️ Insufficient candles for {pair}: "
                    f"{df_len} < {MIN_CANDLES}"
                )
                return None
            
            return df
        
        except Exception as e:
            logger.error(f"❌ OHLCV fetch error for {pair}: {e}", exc_info=True)
            return None
    
    @staticmethod
    def _candles_to_dataframe(candles: List) -> Optional[pd.DataFrame]:
        """
        تبدیل candles به DataFrame OHLCV
        
        ساختار: [timestampMs, open, high, low, close, volume]
        """
        if not candles:
            return None
        
        rows = []
        for c in candles:
            if not isinstance(c, (list, tuple)) or len(c) < 6:
                continue
            
            try:
                ts = pd.to_datetime(c[0], unit="ms", errors="coerce")
                if pd.isna(ts):
                    continue
                
                volume = float(c[5]) if c[5] is not None else 0.0
                
                rows.append({
                    "timestamp": ts,
                    "Open": float(c[1]),
                    "High": float(c[2]),
                    "Low": float(c[3]),
                    "Close": float(c[4]),
                    "Volume": volume,
                })
            except (ValueError, TypeError, IndexError):
                continue
        
        if not rows:
            return None
        
        df = pd.DataFrame(rows).set_index("timestamp").sort_index().dropna()
        return df
    
    # ============================================================
    # Symbol Mapping
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
    # Cache Helpers
    # ============================================================
    
    def _dict_to_prediction(self, data: Dict[str, Any]) -> PredictionEntity:
        """تبدیل dict به Entity"""
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
            "valid_periods": VALID_PERIODS,
            "min_candles": MIN_CANDLES,
            "period_to_interval": PERIOD_TO_INTERVAL,
            "period_to_range": PERIOD_TO_RANGE,
        }


__all__ = ["PredictCoinUseCase"]
