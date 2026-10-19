# application/use_cases/predict_coin_gemini.py
# ============================================================
# Use Case: Predict Coin (Gemini) - تحلیل با Gemini
# نسخه ۲.۰ - آزادتر + JSON مقاوم
# ============================================================
# 
# مسئولیت:
#   - دریافت OHLCV از CoinStats
#   - محاسبه شاخص‌های تکنیکال پایه
#   - ساخت prompt آزاد برای Gemini
#   - پارس پاسخ JSON به PredictionEntity
# ============================================================

import json
import logging
import re
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from domain.entities.prediction import Prediction as PredictionEntity, SignalType
from domain.value_objects.signal import Signal
from infrastructure.ai.gemini_service import GeminiService, GeminiError
from prompts.system_prompt import SYSTEM_PROMPT_PREDICT

logger = logging.getLogger(__name__)


# ============================================================
# Constants
# ============================================================

VALID_PERIODS: List[str] = ["24h", "1w", "1m", "3m", "6m"]

PERIOD_TO_INTERVAL: Dict[str, str] = {
    "24h": "1h",
    "1w":  "4h",
    "1m":  "4h",
    "3m":  "1d",
    "6m":  "1d",
}

PERIOD_TO_RANGE: Dict[str, str] = {
    "24h": "1w",
    "1w":  "1mo",
    "1m":  "3mo",
    "3m":  "6mo",
    "6m":  "1y",
}

MIN_CANDLES = 50
CACHE_TTL = 300


# ============================================================
# Prompt Template — آزاد و بدون محدودیت الکی
# ============================================================

ANALYSIS_PROMPT_TEMPLATE = """تو یک تحلیلگر حرفه‌ای تکنیکال هستی.

## داده‌های بازار {coin} ({period})
- قیمت فعلی: ${current_price:,.2f}
- تعداد کندل: {candle_count}
- بازه زمانی: {start_date} تا {end_date}

### آخرین کندل‌ها (۵ کندل آخر)
{recent_candles}

### شاخص‌های تکنیکال محاسبه‌شده
- RSI(14): {rsi}
- SMA(20): {sma_20}
- SMA(50): {sma_50}
- EMA(20): {ema_20}
- MACD line: {macd_line}
- MACD signal: {macd_signal}
- MACD histogram: {macd_hist}
- Volatility (std): {volatility:.4f}
- Trend (10-candle slope): {trend_slope:.4f}

### نوسان قیمت
- تغییر {period}: {price_change:.2f}%
- بالاترین: ${high:.2f}
- پایین‌ترین: ${low:.2f}

## وظیفه
این داده‌ها رو **هرطور که می‌خوای** تحلیل کن. آزادی کامل داری:
- اگه الگویی می‌بینی (سقف دوقلو، واگرایی، فشردگی، پرچم، ...)، بگو
- اگه همبستگی با شاخص‌های دیگه یا context بازار می‌بینی، مطرح کن
- اگه رویکردت با تحلیل کلاسیک متفاوته ولی منطق داری، آزادی
- اگه مبهمه، صادقانه NEUTRAL بده
- اگه سیگنال قوی هست، با اطمینان بده

## خروجی — فقط JSON خالص
بدون ```json و بدون توضیح اضافی، فقط این ساختار:

{{
  "signal_type": "BUY" | "SELL" | "NEUTRAL",
  "confidence": 0-100,
  "score": 0.0-1.0,
  "reasons": ["دلیل ۱", "دلیل ۲", "دلیل ۳"],
  "summary": "خلاصه ۲-۳ جمله‌ای به فارسی"
}}

راهنما:
- score نزدیک ۱ = قوی خرید، نزدیک ۰ = قوی فروش، ۰.۵ = خنثی
- confidence = اطمینان تو به تحلیل (نه احتمال سود)
- reasons: حداکثر ۵ مورد، هر کدوم ۱ جمله کوتاه
"""


# ============================================================
# PredictCoinGeminiUseCase
# ============================================================

class PredictCoinGeminiUseCase:
    """
    Use Case پیش‌بینی با Gemini.
    
    این کلاس معادل PredictCoinUseCase قدیمی است ولی با Gemini.
    خروجی: PredictionEntity (همون entity قبلی برای سازگاری)
    """
    
    def __init__(
        self,
        gemini_service: GeminiService,
        api_client: Any,
        cache: Optional[Any] = None,
    ) -> None:
        self.gemini_service = gemini_service
        self.api_client = api_client
        self.cache = cache
        
        self._stats = {
            "total_requests": 0,
            "successful": 0,
            "failed": 0,
            "cache_hits": 0,
        }
        
        logger.info("✅ PredictCoinGeminiUseCase initialized")
    
    # ============================================================
    # Execute
    # ============================================================
    
    def execute(
        self,
        coin_id: str,
        period: str = "24h",
        save: bool = True,
        use_cache: bool = True,
    ) -> PredictionEntity:
        """
        اجرای پیش‌بینی با Gemini.
        
        Args:
            coin_id: "bitcoin"
            period: "24h" | "1w" | ...
            save: ذخیره در DB
            use_cache: استفاده از cache
        
        Returns:
            PredictionEntity
        """
        start_time = time.time()
        self._stats["total_requests"] += 1
        
        logger.info(f"🤖 Gemini Predict START: {coin_id} ({period})")
        
        # ============================================================
        # Validation
        # ============================================================
        
        if period not in VALID_PERIODS:
            raise ValueError(
                f"Invalid period: {period}. Must be one of {VALID_PERIODS}"
            )
        
        # ============================================================
        # Cache check
        # ============================================================
        
        cache_key = f"gemini_predict:{coin_id}:{period}"
        
        if use_cache and self.cache is not None:
            try:
                cached = self.cache.get(cache_key)
                if cached and isinstance(cached, dict):
                    self._stats["cache_hits"] += 1
                    logger.info(f"⚡ Gemini Predict CACHE HIT: {coin_id}")
                    return self._dict_to_entity(cached, period)
            except Exception as e:
                logger.debug(f"Cache read error: {e}")
        
        # ============================================================
        # OHLCV
        # ============================================================
        
        df = self._fetch_ohlcv(coin_id, period)
        
        if df is None or len(df) < MIN_CANDLES:
            df_len = len(df) if df is not None else 0
            raise RuntimeError(
                f"داده کافی نیست ({df_len} کندل، حداقل {MIN_CANDLES})"
            )
        
        # ============================================================
        # Technical indicators
        # ============================================================
        
        indicators = self._compute_indicators(df)
        
        # ============================================================
        # Coin info
        # ============================================================
        
        try:
            coin_info = self.api_client.get_coin(coin_id)
            current_price = coin_info.get("price", 0) if coin_info else 0
            coin_name = coin_info.get("name", coin_id) if coin_info else coin_id
        except Exception as e:
            logger.debug(f"Coin info error: {e}")
            current_price = float(df["Close"].iloc[-1])
            coin_name = coin_id
        
        if not current_price:
            current_price = float(df["Close"].iloc[-1])
        
        # ============================================================
        # Prompt
        # ============================================================
        
        prompt = self._build_prompt(
            coin=coin_id,
            period=period,
            df=df,
            indicators=indicators,
            current_price=current_price,
        )
        
        # ============================================================
        # Call Gemini — آزادتر
        # ============================================================
        
        try:
            gemini_result = self.gemini_service.client.generate(
                prompt=prompt,
                system=SYSTEM_PROMPT_PREDICT,
                temperature=0.4,
                top_p=0.95,
                top_k=40,
            )
        except GeminiError as e:
            self._stats["failed"] += 1
            raise RuntimeError(f"Gemini error: {e}") from e
        
        raw_text = gemini_result.get("text", "").strip()
        analysis = self._parse_json_response(raw_text)
        
        if analysis is None:
            self._stats["failed"] += 1
            raise RuntimeError(
                f"پاسخ Gemini قابل پارس نیست: {raw_text[:200]}"
            )
        
        # ============================================================
        # ساخت Entity
        # ============================================================
        
        processing_time = (time.time() - start_time) * 1000
        
        signal_type_str = analysis.get("signal_type", "NEUTRAL")
        score = float(analysis.get("score", 0.5))
        confidence = int(analysis.get("confidence", 50))
        reasons = analysis.get("reasons", [])
        summary = analysis.get("summary", "")
        
        # اطمینان از سازگاری
        try:
            signal_type = SignalType(signal_type_str)
        except ValueError:
            signal_type = SignalType.NEUTRAL
        
        # Signal از score
        signal = Signal.from_score(score)
        
        entity = PredictionEntity(
            coin=coin_id,
            coin_name=coin_name,
            current_price=float(current_price),
            signal=signal.get_text(),
            signal_type=signal_type,
            confidence=confidence,
            confidence_score=confidence,
            prediction_score=score,
            period=period,
            model_mode="GEMINI",
            timestamp=datetime.now(),
            processing_time_ms=round(processing_time, 2),
            data_points=len(df),
            extra={
                "reasons": reasons,
                "summary": summary,
                "indicators": {
                    k: (round(v, 4) if isinstance(v, float) else v)
                    for k, v in indicators.items()
                    if isinstance(v, (int, float))
                },
                "gemini_usage": gemini_result.get("usage", {}),
                "engine": "gemini",
            },
        )
        
        # ============================================================
        # Save
        # ============================================================
        
        if save:
            try:
                from infrastructure.repositories import repos
                repos.prediction.save(entity)
                logger.debug(f"✅ Gemini prediction saved: {entity.coin}")
            except Exception as e:
                logger.warning(f"⚠️ Save failed: {e}")
        
        # ============================================================
        # Cache
        # ============================================================
        
        if use_cache and self.cache is not None:
            try:
                self.cache.set(cache_key, entity.to_dict(), CACHE_TTL)
            except Exception as e:
                logger.debug(f"Cache set error: {e}")
        
        self._stats["successful"] += 1
        
        logger.info(
            f"🎉 Gemini Predict SUCCESS: {coin_id} "
            f"({signal_type.value}, conf={confidence}%, {processing_time:.0f}ms)"
        )
        
        return entity
    
    # ============================================================
    # OHLCV
    # ============================================================
    
    def _fetch_ohlcv(
        self,
        coin_id: str,
        period: str,
    ) -> Optional[pd.DataFrame]:
        """دریافت OHLCV از CoinStats."""
        try:
            if hasattr(self.api_client, "coin_id_to_pair"):
                pair = self.api_client.coin_id_to_pair(coin_id)
            else:
                pair = f"{coin_id.upper()}/USDT"
            
            if not pair:
                return None
        except Exception as e:
            logger.error(f"coin_id_to_pair error: {e}")
            return None
        
        interval = PERIOD_TO_INTERVAL.get(period, "4h")
        data_range = PERIOD_TO_RANGE.get(period, "3mo")
        
        try:
            result = self.api_client.get_ohlcv_candles(
                exchange="Binance",
                pair=pair,
                interval=interval,
                range=data_range,
                use_cache=True,
            )
            
            if not result or "candles" not in result:
                return None
            
            candles = result["candles"]
            return self._candles_to_df(candles)
        except Exception as e:
            logger.error(f"OHLCV fetch error: {e}")
            return None
    
    @staticmethod
    def _candles_to_df(candles: List) -> Optional[pd.DataFrame]:
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
                rows.append({
                    "timestamp": ts,
                    "Open": float(c[1]),
                    "High": float(c[2]),
                    "Low": float(c[3]),
                    "Close": float(c[4]),
                    "Volume": float(c[5]) if c[5] is not None else 0.0,
                })
            except (ValueError, TypeError, IndexError):
                continue
        
        if not rows:
            return None
        
        return pd.DataFrame(rows).set_index("timestamp").sort_index().dropna()
    
    # ============================================================
    # Indicators
    # ============================================================
    
    @classmethod
    def _compute_indicators(cls, df: pd.DataFrame) -> Dict[str, Any]:
        """محاسبه شاخص‌های تکنیکال پایه."""
        result: Dict[str, Any] = {}
        
        closes = df["Close"].values
        
        # RSI(14)
        result["rsi"] = cls._rsi(closes, 14)
        
        # SMA
        result["sma_20"] = float(np.mean(closes[-20:])) if len(closes) >= 20 else None
        result["sma_50"] = float(np.mean(closes[-50:])) if len(closes) >= 50 else None
        
        # EMA(20)
        result["ema_20"] = cls._ema(closes, 20)
        
        # MACD
        macd, signal, hist = cls._macd(closes)
        result["macd_line"] = macd
        result["macd_signal"] = signal
        result["macd_hist"] = hist
        
        # Volatility
        if len(closes) >= 2:
            returns = np.diff(closes) / closes[:-1]
            result["volatility"] = float(np.std(returns))
        else:
            result["volatility"] = 0.0
        
        # Trend slope (10-candle)
        if len(closes) >= 10:
            x = np.arange(10)
            y = closes[-10:]
            slope = float(np.polyfit(x, y, 1)[0])
            result["trend_slope"] = slope / closes[-1] * 100 if closes[-1] else 0
        else:
            result["trend_slope"] = 0.0
        
        # Price change
        if len(closes) >= 2:
            result["price_change"] = (closes[-1] - closes[0]) / closes[0] * 100
        else:
            result["price_change"] = 0.0
        
        result["high"] = float(df["High"].max())
        result["low"] = float(df["Low"].min())
        
        return result
    
    @staticmethod
    def _rsi(closes: np.ndarray, period: int = 14) -> Optional[float]:
        if len(closes) < period + 1:
            return None
        try:
            deltas = np.diff(closes[-(period + 1):])
            gains = deltas[deltas > 0]
            losses = -deltas[deltas < 0]
            avg_gain = np.mean(gains) if len(gains) else 0
            avg_loss = np.mean(losses) if len(losses) else 0
            if avg_loss == 0:
                return 100.0
            rs = avg_gain / avg_loss
            return float(100 - (100 / (1 + rs)))
        except Exception:
            return None
    
    @staticmethod
    def _ema(values: np.ndarray, period: int) -> Optional[float]:
        if len(values) < period:
            return None
        try:
            multiplier = 2 / (period + 1)
            ema = float(values[-period])
            for v in values[-period + 1:]:
                ema = (v * multiplier) + (ema * (1 - multiplier))
            return ema
        except Exception:
            return None
    
    @staticmethod
    def _macd(closes: np.ndarray) -> tuple:
        """MACD با signal واقعی (EMA 9 روی MACD series)."""
        if len(closes) < 26:
            return None, None, None
        try:
            ema_12 = PredictCoinGeminiUseCase._ema_series(closes, 12)
            ema_26 = PredictCoinGeminiUseCase._ema_series(closes, 26)
            if ema_12 is None or ema_26 is None:
                return None, None, None
            
            # MACD line = EMA12 - EMA26
            macd_series = ema_12 - ema_26
            macd = float(macd_series[-1])
            
            # Signal line = EMA(9) از MACD series
            signal_arr = PredictCoinGeminiUseCase._ema_series(macd_series, 9)
            signal = float(signal_arr[-1]) if signal_arr is not None else macd
            
            # Histogram
            hist = macd - signal
            
            return macd, signal, hist
        except Exception:
            return None, None, None
    
    @staticmethod
    def _ema_series(values: np.ndarray, period: int) -> Optional[np.ndarray]:
        """EMA به‌صورت series (نه فقط آخرین مقدار)."""
        if len(values) < period:
            return None
        try:
            multiplier = 2 / (period + 1)
            ema = np.zeros(len(values))
            ema[:period] = np.nan
            ema[period - 1] = float(np.mean(values[:period]))
            
            for i in range(period, len(values)):
                ema[i] = (values[i] * multiplier) + (ema[i - 1] * (1 - multiplier))
            
            return ema
        except Exception:
            return None
    
    # ============================================================
    # Prompt Builder
    # ============================================================
    
    def _build_prompt(
        self,
        coin: str,
        period: str,
        df: pd.DataFrame,
        indicators: Dict[str, Any],
        current_price: float,
    ) -> str:
        # آخرین ۵ کندل
        recent = df.tail(5)
        recent_lines = []
        for ts, row in recent.iterrows():
            recent_lines.append(
                f"  {ts.strftime('%Y-%m-%d %H:%M')} | "
                f"O={row['Open']:.2f} H={row['High']:.2f} "
                f"L={row['Low']:.2f} C={row['Close']:.2f} "
                f"V={row['Volume']:.0f}"
            )
        
        rsi = indicators.get("rsi")
        sma_20 = indicators.get("sma_20")
        sma_50 = indicators.get("sma_50")
        ema_20 = indicators.get("ema_20")
        macd_line = indicators.get("macd_line")
        macd_signal = indicators.get("macd_signal")
        macd_hist = indicators.get("macd_hist")
        volatility = indicators.get("volatility", 0)
        trend_slope = indicators.get("trend_slope", 0)
        price_change = indicators.get("price_change", 0)
        high = indicators.get("high", 0)
        low = indicators.get("low", 0)
        
        def fmt(v, dp=2):
            if v is None:
                return "N/A"
            if isinstance(v, float):
                return f"{v:.{dp}f}"
            return str(v)
        
        return ANALYSIS_PROMPT_TEMPLATE.format(
            coin=coin,
            period=period,
            current_price=current_price,
            candle_count=len(df),
            start_date=df.index[0].strftime("%Y-%m-%d"),
            end_date=df.index[-1].strftime("%Y-%m-%d"),
            recent_candles="\n".join(recent_lines),
            rsi=fmt(rsi, 1),
            sma_20=fmt(sma_20),
            sma_50=fmt(sma_50),
            ema_20=fmt(ema_20),
            macd_line=fmt(macd_line, 4),
            macd_signal=fmt(macd_signal, 4),
            macd_hist=fmt(macd_hist, 4),
            volatility=volatility if isinstance(volatility, float) else 0,
            trend_slope=trend_slope if isinstance(trend_slope, float) else 0,
            price_change=price_change if isinstance(price_change, float) else 0,
            high=high,
            low=low,
        )
    
    # ============================================================
    # JSON Parser
    # ============================================================
    
    @staticmethod
    def _parse_json_response(text: str) -> Optional[Dict[str, Any]]:
        """پارس JSON از پاسخ Gemini (با تحمل کثیفی)."""
        if not text:
            return None
        
        # حذف markdown fences
        cleaned = text.strip()
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        
        # تلاش مستقیم
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass
        
        # جستجوی {...}
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
        
        return None
    
    def _dict_to_entity(
        self,
        data: Dict[str, Any],
        period: str,
    ) -> PredictionEntity:
        """تبدیل dict cache شده به Entity."""
        signal_type_str = data.get("signal_type", "NEUTRAL")
        try:
            signal_type = SignalType(signal_type_str)
        except ValueError:
            signal_type = SignalType.NEUTRAL
        
        ts_str = data.get("timestamp", datetime.now().isoformat())
        try:
            timestamp = datetime.fromisoformat(ts_str)
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
            period=data.get("period", period),
            model_mode="GEMINI",
            timestamp=timestamp,
            processing_time_ms=float(data.get("processing_time_ms", 0)),
            data_points=int(data.get("data_points", 0)),
            extra=data.get("extra"),
        )
    
    # ============================================================
    # Stats
    # ============================================================
    
    def get_stats(self) -> Dict[str, Any]:
        total = self._stats["total_requests"]
        success_rate = self._stats["successful"] / max(total, 1) * 100
        
        return {
            **self._stats,
            "success_rate": round(success_rate, 2),
            "timestamp": datetime.now().isoformat(),
        }


__all__ = ["PredictCoinGeminiUseCase"]
