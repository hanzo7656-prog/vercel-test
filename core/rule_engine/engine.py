# core/rule_engine/engine.py
# ============================================================
# Rule Engine - کلاس اصلی
# نسخه ۱.۰
# ============================================================
# 
# نقش:
#   ۱. دریافت OHLCV برای چند symbol
#   ۲. محاسبه اندیکاتورها
#   ۳. اعمال قوانین
#   ۴. محاسبه امتیاز نهایی
#   ۵. آپدیت State
#   ۶. برگرداندن Prediction‌های مرتب‌شده
# 
# این کلاس از batch_processor برای parallel استفاده می‌کنه
# ولی خودش منطق اصلی رو داره.
# ============================================================

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from core.rule_engine.models import (
    MarketState,
    Prediction,
    RuleResult,
)
from core.rule_engine.rules import (
    BaseRule,
    create_rules_from_config,
)
from core.rule_engine.state_machine import StateMachine

logger = logging.getLogger(__name__)


# ============================================================
# RuleEngine
# ============================================================

class RuleEngine:
    """
    موتور اصلی Rule-Based Screener
    
    Attributes:
        rules: لیست قوانین فعال
        state_machine: مدیریت وضعیت
        config: تنظیمات کامل
        indicators_calculator: تابع محاسبه اندیکاتورها
        data_fetcher: تابع دریافت OHLCV
    """
    
    # آستانه‌های پیش‌فرض
    DEFAULT_MIN_PASS_SCORE = 0.55
    DEFAULT_MIN_CANDLES = 50
    
    def __init__(
        self,
        rules_config: Dict[str, Dict[str, Any]],
        state_machine: Optional[StateMachine] = None,
        indicators_calculator: Optional[Any] = None,
        data_fetcher: Optional[Any] = None,
        scoring_config: Optional[Dict[str, Any]] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Args:
            rules_config: تنظیمات قوانین
            state_machine: StateMachine (اگه None، از default استفاده کن)
            indicators_calculator: تابع محاسبه اندیکاتورها
            data_fetcher: تابع fetch OHLCV
            scoring_config: تنظیمات scoring
            config: تنظیمات عمومی
        """
        # قوانین
        self.rules: List[BaseRule] = create_rules_from_config(rules_config)
        self.rules_config = rules_config
        
        # state machine
        self.state_machine = state_machine or StateMachine()
        
        # indicator calculator و data fetcher
        # (اگه داده نشه، از core.indicators استفاده می‌کنیم)
        self.indicators_calculator = (
            indicators_calculator or self._default_indicators
        )
        self.data_fetcher = data_fetcher
        
        # scoring config
        scoring_config = scoring_config or {}
        self.min_pass_score: float = float(
            scoring_config.get("min_pass_score", self.DEFAULT_MIN_PASS_SCORE)
        )
        self.min_candles: int = int(
            scoring_config.get("min_candles", self.DEFAULT_MIN_CANDLES)
        )
        self.aggregation: str = scoring_config.get("aggregation", "weighted_sum")
        
        # config کلی
        self.config = config or {}
        
        logger.info(
            f"✅ RuleEngine initialized "
            f"({len(self.rules)} rules, "
            f"min_pass_score={self.min_pass_score})"
        )
    
    # ============================================================
    # Main Public API
    # ============================================================
    
    def evaluate(
        self,
        symbol: str,
        coin_id: str,
        df: pd.DataFrame,
        update_state: bool = True,
    ) -> Optional[Prediction]:
        """
        ارزیابی یک symbol
        
        Args:
            symbol: نماد (BTC/USDT)
            coin_id: شناسه (bitcoin)
            df: DataFrame با OHLCV + اندیکاتورها
            update_state: آیا state رو آپدیت کنه؟
        
        Returns:
            Prediction یا None اگه داده کافی نبود
        """
        # چک داده کافی
        if df is None or len(df) < self.min_candles:
            return None
        
        # اگه اندیکاتورها محاسبه نشدن، محاسبه کن
        if "RSI" not in df.columns:
            try:
                df = self.indicators_calculator(df)
            except Exception as e:
                logger.error(f"❌ Indicator calculation failed for {symbol}: {e}")
                return None
        
        # اعمال همه قوانین
        rule_results: List[RuleResult] = []
        for rule in self.rules:
            result = rule.evaluate(df, context={"symbol": symbol, "coin_id": coin_id})
            rule_results.append(result)
        
        # محاسبه امتیاز نهایی
        final_score = self._aggregate_scores(rule_results)
        
        # استخراج دلایل (فقط passها + failها)
        reasons = [r.reason for r in rule_results]
        
        # استخراج اندیکاتورهای کلیدی
        indicators = self._extract_indicators(df)
        
        # آپدیت state
        if update_state:
            snapshot = self.state_machine.update_state(
                symbol=symbol,
                score=final_score,
                context=indicators,
            )
            state = snapshot.state
        else:
            snapshot = self.state_machine.get_state(symbol)
            state = snapshot.state
        
        # ساخت Prediction
        prediction = Prediction(
            symbol=symbol,
            coin_id=coin_id,
            score=final_score,
            rule_score=final_score,
            state=state,
            reasons=reasons,
            rule_results=rule_results,
            indicators=indicators,
            timestamp=datetime.now(),
        )
        
        return prediction
    
    def evaluate_batch(
        self,
        symbols: List[Dict[str, str]],
        data_map: Dict[str, pd.DataFrame],
        update_state: bool = True,
    ) -> List[Prediction]:
        """
        ارزیابی گروهی چند symbol
        
        Args:
            symbols: لیست {symbol, coin_id}
            data_map: دیکشنری {symbol: df}
            update_state: آپدیت state؟
        
        Returns:
            لیست Prediction (فقط اونهایی که score >= min_pass)
        """
        results: List[Prediction] = []
        
        for item in symbols:
            symbol = item.get("symbol")
            coin_id = item.get("coin_id", symbol)
            
            df = data_map.get(symbol)
            if df is None:
                continue
            
            try:
                prediction = self.evaluate(
                    symbol=symbol,
                    coin_id=coin_id,
                    df=df,
                    update_state=update_state,
                )
                
                if prediction and prediction.score >= self.min_pass_score:
                    results.append(prediction)
            except Exception as e:
                logger.error(f"❌ Evaluate failed for {symbol}: {e}")
                continue
        
        # مرتب‌سازی نزولی بر اساس score
        results.sort(key=lambda p: p.score, reverse=True)
        
        # اضافه کردن rank
        for i, pred in enumerate(results, 1):
            pred.rank = i
        
        return results
    
    def evaluate_single(
        self,
        symbol: str,
        coin_id: str,
        df: pd.DataFrame,
    ) -> Optional[Prediction]:
        """
        ارزیابی سریع یک symbol (بدون آپدیت state)
        برای debug و تست
        """
        return self.evaluate(
            symbol=symbol,
            coin_id=coin_id,
            df=df,
            update_state=False,
        )
    
    # ============================================================
    # Scoring
    # ============================================================
    
    def _aggregate_scores(self, results: List[RuleResult]) -> float:
        """
        جمع‌آوری امتیازهای قوانین به یک عدد نهایی
        
        روش‌ها:
            weighted_sum: Σ(score_i × weight_i) / Σ(weight_i)
            max:          بیشترین score
            voting:       (تعداد pass) / (تعداد کل)
        """
        if not results:
            return 0.0
        
        if self.aggregation == "weighted_sum":
            total_weight = sum(r.weight for r in results)
            if total_weight == 0:
                return 0.0
            weighted = sum(r.score * r.weight for r in results)
            return float(np.clip(weighted / total_weight, 0.0, 1.0))
        
        elif self.aggregation == "max":
            return float(max(r.score for r in results))
        
        elif self.aggregation == "voting":
            passes = sum(1 for r in results if r.passed)
            return passes / len(results)
        
        # fallback → weighted_sum
        total_weight = sum(r.weight for r in results) or 1.0
        weighted = sum(r.score * r.weight for r in results)
        return float(np.clip(weighted / total_weight, 0.0, 1.0))
    
    # ============================================================
    # Indicator Helpers
    # ============================================================
    
    def _default_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        محاسبه اندیکاتورهای استاندارد
        
        این تابع اگه indicators_calculator داده نشه استفاده می‌شه.
        """
        from core.rule_engine.indicators import compute_indicators
        return compute_indicators(df)
    
    def _extract_indicators(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        استخراج اندیکاتورهای کلیدی از df برای context
        
        Returns:
            دیکشنری اندیکاتورها
        """
        indicators: Dict[str, Any] = {}
        
        last = df.iloc[-1] if len(df) > 0 else None
        if last is None:
            return indicators
        
        # ستون‌های استاندارد
        columns_to_extract = [
            ("Close", "price"),
            ("RSI", "rsi"),
            ("Volume", "volume"),
            ("Volume_MA20", "volume_ma"),
            ("Volume_Ratio", "volume_ratio"),
            ("MA50", "ma50"),
            ("MA200", "ma200"),
            ("MACD", "macd"),
            ("MACD_signal", "macd_signal"),
            ("MACD_hist", "macd_hist"),
            ("ATR", "atr"),
        ]
        
        for col, key in columns_to_extract:
            if col in df.columns:
                value = last[col]
                if pd.notna(value):
                    indicators[key] = float(value)
        
        return indicators
    
    # ============================================================
    # Config Management
    # ============================================================
    
    def update_rules_config(
        self,
        rules_config: Dict[str, Dict[str, Any]],
    ) -> None:
        """
        آپدیت runtime تنظیمات قوانین
        (برای Weight Tuner)
        """
        for rule in self.rules:
            if rule.name in rules_config:
                rule.update_config(rules_config[rule.name])
        
        self.rules_config = rules_config
        logger.info(f"🔄 Rules config updated ({len(self.rules)} rules)")
    
    def get_rules_config(self) -> Dict[str, Any]:
        """خروجی config قوانین فعلی"""
        return {rule.name: rule.to_dict() for rule in self.rules}
    
    # ============================================================
    # Stats
    # ============================================================
    
    def get_stats(self) -> Dict[str, Any]:
        """آمار Rule Engine"""
        return {
            "rule_count": len(self.rules),
            "rules": [rule.name for rule in self.rules],
            "aggregation": self.aggregation,
            "min_pass_score": self.min_pass_score,
            "min_candles": self.min_candles,
            "state_machine": self.state_machine.get_stats(),
        }


__all__ = ["RuleEngine"]
