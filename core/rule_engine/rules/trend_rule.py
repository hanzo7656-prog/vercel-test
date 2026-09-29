# core/rule_engine/rules/trend_rule.py
# ============================================================
# Trend Rule - قانون روند (Price vs MA)
# نسخه ۱.۰
# ============================================================
# 
# منطق:
#   اگه Price > MA → pass (روند صعودی)
#   یا اگه Price < MA → pass (روند نزولی)
#   بسته به تنظیمات vs_ma
# 
# نکته مهم:
#   اگه MA محاسبه نشده باشه (مثلاً MA200 با ۱۰۰ کندل)،
#   قانون به صورت «neutral pass» با score=0.5 رد می‌شه.
# ============================================================

from typing import Any, Dict

import pandas as pd

from core.rule_engine.rules.base import BaseRule
from core.rule_engine.models import RuleResult


class TrendRule(BaseRule):
    """
    قانون روند
    
    Config params:
        ma_column: نام ستون MA (پیش‌فرض: "MA50")
        vs_ma: "above" | "below" | "any" (پیش‌فرض: "above")
        tolerance: تلورانس درصدی (پیش‌فرض: 0.0)
    """
    
    name = "trend"
    
    def __init__(self, config: Dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self.ma_column: str = self.config.get("ma_column", "MA50")
        self.vs_ma: str = self.config.get("vs_ma", "above").lower()
        self.tolerance: float = float(self.config.get("tolerance", 0.0))
    
    def _evaluate(
        self,
        df: pd.DataFrame,
        context: Dict[str, Any],
    ) -> RuleResult:
        """ارزیابی روند"""
        
        price = self._get_last(df, "Close")
        ma_value = self._get_last(df, self.ma_column)
        
        # اگه MA نیست (مثلاً MA200 با داده کم)
        if ma_value is None or ma_value == 0:
            # Neutral: نه pass نه fail کامل — امتیاز متوسط
            return self._make_result(
                passed=False,
                score=0.5,  # ← نکته: score بالاتر از صفر چون خطا نیست
                reason=f"⚠️ {self.ma_column} در دسترس نیست (داده کم؟)",
                price=price,
                ma=None,
                neutral=True,
            )
        
        # اگه price نیست
        if price is None:
            return self._make_result(
                passed=False,
                score=0.0,
                reason="قیمت در دسترس نیست",
                price=None,
                ma=ma_value,
            )
        
        # محاسبه نسبت
        ratio = (price - ma_value) / ma_value  # نسبی، نه درصدی
        
        # منطق
        if self.vs_ma == "above":
            # price باید بالاتر از MA باشه (با تلورانس)
            passed = ratio >= self.tolerance
            if passed:
                reason = (
                    f"✅ Price={price:.2f} بالاتر از {self.ma_column}={ma_value:.2f} "
                    f"({ratio*100:+.2f}%)"
                )
            else:
                reason = (
                    f"❌ Price={price:.2f} زیر {self.ma_column}={ma_value:.2f} "
                    f"({ratio*100:+.2f}%)"
                )
        elif self.vs_ma == "below":
            # price باید پایین‌تر از MA باشه
            passed = ratio <= -self.tolerance
            if passed:
                reason = (
                    f"✅ Price={price:.2f} زیر {self.ma_column}={ma_value:.2f} "
                    f"({ratio*100:+.2f}%)"
                )
            else:
                reason = (
                    f"❌ Price={price:.2f} بالاتر از {self.ma_column}={ma_value:.2f} "
                    f"({ratio*100:+.2f}%)"
                )
        else:
            # "any" → همیشه pass اگه MA محاسبه شده
            passed = True
            reason = f"✅ Price={price:.2f}, {self.ma_column}={ma_value:.2f}"
        
        return self._make_result(
            passed=passed,
            score=1.0 if passed else 0.0,
            reason=reason,
            price=price,
            ma=ma_value,
            ratio=round(ratio, 4),
            vs_ma=self.vs_ma,
        )
    
    def update_config(self, new_config: Dict[str, Any]) -> None:
        """آپدیت runtime"""
        super().update_config(new_config)
        if "ma_column" in new_config:
            self.ma_column = new_config["ma_column"]
        if "vs_ma" in new_config:
            self.vs_ma = new_config["vs_ma"].lower()
        if "tolerance" in new_config:
            self.tolerance = float(new_config["tolerance"])


__all__ = ["TrendRule"]
