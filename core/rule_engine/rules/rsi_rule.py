# core/rule_engine/rules/rsi_rule.py
# ============================================================
# RSI Rule - قانون شاخص قدرت نسبی
# نسخه ۱.۰
# ============================================================
# 
# منطق:
#   اگه RSI در بازه [min, max] باشه → pass
# 
# چرا این بازه؟
#   RSI < 30 = oversold (فرصت خرید)
#   RSI > 70 = overbought (هشدار)
#   بازه پیش‌فرض (25, 60) = «نه خیلی اشباع، نه خیلی ضعیف»
# ============================================================

from typing import Any, Dict

import pandas as pd

from core.rule_engine.rules.base import BaseRule
from core.rule_engine.models import RuleResult


class RSIRule(BaseRule):
    """
    قانون RSI
    
    Config params:
        min: حد پایین بازه (پیش‌فرض: 25)
        max: حد بالای بازه (پیش‌فرض: 60)
        column: نام ستون RSI در df (پیش‌فرض: "RSI")
    """
    
    name = "rsi"
    
    def __init__(self, config: Dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self.min_value: float = float(self.config.get("min", 25))
        self.max_value: float = float(self.config.get("max", 60))
        self.column: str = self.config.get("column", "RSI")
    
    def _evaluate(
        self,
        df: pd.DataFrame,
        context: Dict[str, Any],
    ) -> RuleResult:
        """ارزیابی RSI"""
        
        rsi_value = self._get_last(df, self.column)
        
        # اگه RSI محاسبه نشده
        if rsi_value is None:
            return self._make_result(
                passed=False,
                score=0.0,
                reason=f"{self.column} در دسترس نیست",
                rsi=None,
                min=self.min_value,
                max=self.max_value,
            )
        
        # چک بازه
        passed = self.min_value <= rsi_value <= self.max_value
        
        if passed:
            reason = (
                f"✅ RSI={rsi_value:.1f} در بازه "
                f"[{self.min_value:.0f}, {self.max_value:.0f}]"
            )
        elif rsi_value < self.min_value:
            reason = (
                f"❌ RSI={rsi_value:.1f} کمتر از "
                f"{self.min_value:.0f} (oversold شدید)"
            )
        else:
            reason = (
                f"❌ RSI={rsi_value:.1f} بیشتر از "
                f"{self.max_value:.0f} (overbought)"
            )
        
        return self._make_result(
            passed=passed,
            score=1.0 if passed else 0.0,
            reason=reason,
            rsi=round(rsi_value, 2),
            min=self.min_value,
            max=self.max_value,
        )
    
    def update_config(self, new_config: Dict[str, Any]) -> None:
        """آپدیت runtime"""
        super().update_config(new_config)
        if "min" in new_config:
            self.min_value = float(new_config["min"])
        if "max" in new_config:
            self.max_value = float(new_config["max"])
        if "column" in new_config:
            self.column = new_config["column"]


__all__ = ["RSIRule"]
