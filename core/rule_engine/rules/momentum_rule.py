# core/rule_engine/rules/momentum_rule.py
# ============================================================
# Momentum Rule - قانون مومنتوم (MACD)
# نسخه ۱.۰
# ============================================================
# 
# منطق:
#   اگه MACD Histogram > 0 → pass (مومنتوم صعودی)
#   یا اگه MACD > Signal → pass
# 
# نکته:
#   این قانون از config «macd_positive» استفاده می‌کنه
#   که می‌تونه اختیاری باشه (پیش‌فرض: neutral).
# ============================================================

from typing import Any, Dict

import pandas as pd

from core.rule_engine.rules.base import BaseRule
from core.rule_engine.models import RuleResult


class MomentumRule(BaseRule):
    """
    قانون مومنتوم (MACD)
    
    Config params:
        hist_column: نام ستون MACD Histogram (پیش‌فرض: "MACD_hist")
        macd_column: نام ستون MACD (پیش‌فرض: "MACD")
        signal_column: نام ستون Signal (پیش‌فرض: "MACD_signal")
        macd_positive: آیا باید MACD مثبت باشه؟ (پیش‌فرض: None)
        require_signal_cross: آیا crossover لازمه؟ (پیش‌فرض: False)
    """
    
    name = "momentum"
    
    def __init__(self, config: Dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self.hist_column: str = self.config.get("hist_column", "MACD_hist")
        self.macd_column: str = self.config.get("macd_column", "MACD")
        self.signal_column: str = self.config.get("signal_column", "MACD_signal")
        self.macd_positive = self.config.get("macd_positive")  # None = neutral
        self.require_signal_cross: bool = self.config.get(
            "require_signal_cross", False
        )
    
    def _evaluate(
        self,
        df: pd.DataFrame,
        context: Dict[str, Any],
    ) -> RuleResult:
        """ارزیابی مومنتوم"""
        
        # اول سعی کن histogram رو بگیر
        hist = self._get_last(df, self.hist_column)
        
        # اگه نیست، از MACD و Signal محاسبه کن
        if hist is None:
            macd = self._get_last(df, self.macd_column)
            signal = self._get_last(df, self.signal_column)
            if macd is not None and signal is not None:
                hist = macd - signal
            else:
                # داده نیست
                return self._make_result(
                    passed=False,
                    score=0.0,
                    reason="داده MACD در دسترس نیست",
                    hist=None,
                )
        
        # اگه حالت neutral (macd_positive تنظیم نشده)
        if self.macd_positive is None:
            # فقط اطلاعات می‌دیم، ولی pass نمی‌کنیم
            return self._make_result(
                passed=False,
                score=0.5,  # ← neutral score
                reason=f"ℹ️ MACD_hist={hist:.4f} (حالت neutral)",
                hist=round(hist, 4),
                neutral=True,
            )
        
        # منطق اصلی
        if self.macd_positive:
            passed = hist > 0
            direction = "مثبت"
        else:
            passed = hist < 0
            direction = "منفی"
        
        # چک crossover (اختیاری)
        if self.require_signal_cross and passed:
            passed = self._check_cross(df, self.macd_positive)
        
        if passed:
            reason = f"✅ MACD_hist={hist:.4f} {direction}"
        else:
            reason = f"❌ MACD_hist={hist:.4f} (باید {direction} باشه)"
        
        return self._make_result(
            passed=passed,
            score=1.0 if passed else 0.0,
            reason=reason,
            hist=round(hist, 4),
            require_positive=self.macd_positive,
        )
    
    def _check_cross(self, df: pd.DataFrame, require_positive: bool) -> bool:
        """
        چک کردن crossover در ۲ کندل آخر
        
        Returns:
            True اگه crossover در جهت درست اتفاق افتاده
        """
        if len(df) < 2:
            return False
        
        hist_col = self.hist_column
        if hist_col not in df.columns:
            return False
        
        prev = df[hist_col].iloc[-2]
        curr = df[hist_col].iloc[-1]
        
        if pd.isna(prev) or pd.isna(curr):
            return False
        
        if require_positive:
            # crossover صعودی: از منفی به مثبت
            return prev <= 0 < curr
        else:
            # crossover نزولی
            return prev >= 0 > curr
    
    def update_config(self, new_config: Dict[str, Any]) -> None:
        """آپدیت runtime"""
        super().update_config(new_config)
        if "hist_column" in new_config:
            self.hist_column = new_config["hist_column"]
        if "macd_positive" in new_config:
            self.macd_positive = new_config["macd_positive"]
        if "require_signal_cross" in new_config:
            self.require_signal_cross = bool(new_config["require_signal_cross"])


__all__ = ["MomentumRule"]
