# core/rule_engine/rules/volume_rule.py
# ============================================================
# Volume Rule - قانون حجم معاملات
# نسخه ۱.۰
# ============================================================
# 
# منطق:
#   اگه Volume فعلی >= multiplier × Volume_MA باشه → pass
# 
# چرا مهمه؟
#   حجم بالا = تأیید حرکت قیمت
#   حجم پایین = حرکت مشکوک
# ============================================================

from typing import Any, Dict

import pandas as pd

from core.rule_engine.rules.base import BaseRule
from core.rule_engine.models import RuleResult


class VolumeRule(BaseRule):
    """
    قانون حجم
    
    Config params:
        multiplier: چند برابر Volume_MA (پیش‌فرض: 1.2)
        column: نام ستون Volume (پیش‌فرض: "Volume")
        ma_column: نام ستون Volume_MA (پیش‌فرض: "Volume_MA20")
    """
    
    name = "volume"
    
    def __init__(self, config: Dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self.multiplier: float = float(self.config.get("multiplier", 1.2))
        self.column: str = self.config.get("column", "Volume")
        self.ma_column: str = self.config.get("ma_column", "Volume_MA20")
    
    def _evaluate(
        self,
        df: pd.DataFrame,
        context: Dict[str, Any],
    ) -> RuleResult:
        """ارزیابی حجم"""
        
        current_volume = self._get_last(df, self.column)
        ma_volume = self._get_last(df, self.ma_column)
        
        # اگه داده نیست
        if current_volume is None or ma_volume is None or ma_volume == 0:
            # fallback: اگه Volume_Ratio در df هست، ازش استفاده کن
            ratio = self._get_last(df, "Volume_Ratio")
            if ratio is None:
                return self._make_result(
                    passed=False,
                    score=0.0,
                    reason="داده حجم کافی نیست",
                    volume=None,
                    ma=None,
                )
            volume_ratio = ratio
        else:
            volume_ratio = current_volume / ma_volume
        
        passed = volume_ratio >= self.multiplier
        
        if passed:
            reason = f"✅ Volume={volume_ratio:.2f}x MA (بالاتر از {self.multiplier}x)"
        else:
            reason = f"❌ Volume={volume_ratio:.2f}x MA (کمتر از {self.multiplier}x)"
        
        return self._make_result(
            passed=passed,
            score=1.0 if passed else 0.0,
            reason=reason,
            volume_ratio=round(volume_ratio, 3),
            threshold=self.multiplier,
            current_volume=current_volume,
            ma_volume=ma_volume,
        )
    
    def update_config(self, new_config: Dict[str, Any]) -> None:
        """آپدیت runtime"""
        super().update_config(new_config)
        if "multiplier" in new_config:
            self.multiplier = float(new_config["multiplier"])


__all__ = ["VolumeRule"]
