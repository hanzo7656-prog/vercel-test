# core/rule_engine/rules/base.py
# ============================================================
# Base Rule - Abstract Class برای همه قوانین
# نسخه ۱.۰
# ============================================================
# 
# هر قانون باید:
#   1. نام یگانه داشته باشه (name)
#   2. بتونه از روی DataFrame اندیکاتور، RuleResult بسازه
#   3. weight رو از config بگیره
#   4. reason انسانی برگردونه
# ============================================================

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

import pandas as pd

from core.rule_engine.models import RuleResult


class BaseRule(ABC):
    """
    کلاس پایه برای همه قوانین
    
    هر قانون concrete باید:
        - name رو تعریف کنه
        - _evaluate رو پیاده کنه
    
    مثال استفاده:
        rule = RSIRule(config={"min": 25, "max": 60, "weight": 0.30})
        result = rule.evaluate(df, context={"symbol": "BTC/USDT"})
    """
    
    # هر زیرکلاس باید name رو override کنه
    name: str = "base"
    
    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        """
        Args:
            config: تنظیمات قانون
                - enabled: فعال/غیرفعال
                - weight: وزن (۰-۱)
                - + پارامترهای خاص هر قانون
        """
        self.config: Dict[str, Any] = config or {}
        self.enabled: bool = self.config.get("enabled", True)
        self.weight: float = float(self.config.get("weight", 0.25))
    
    # ============================================================
    # Public API
    # ============================================================
    
    def evaluate(
        self,
        df: pd.DataFrame,
        context: Optional[Dict[str, Any]] = None,
    ) -> RuleResult:
        """
        ارزیابی قانون روی یک DataFrame
        
        Args:
            df: DataFrame با اندیکاتورهای محاسبه‌شده
                (حداقل شامل: Close, RSI, Volume, ...)
            context: اطلاعات اضافی (symbol, timeframe, ...)
        
        Returns:
            RuleResult با score, passed, reason, metadata
        """
        # اگه غیرفعاله → score = 0
        if not self.enabled:
            return RuleResult(
                rule_name=self.name,
                passed=False,
                score=0.0,
                weight=self.weight,
                reason="قانون غیرفعال است",
                metadata={"disabled": True},
            )
        
        # اگه داده کافی نیست
        if df is None or df.empty:
            return RuleResult(
                rule_name=self.name,
                passed=False,
                score=0.0,
                weight=self.weight,
                reason="داده کافی نیست",
                metadata={"error": "no_data"},
            )
        
        try:
            return self._evaluate(df, context or {})
        except Exception as e:
            # هر خطایی → fail امن
            return RuleResult(
                rule_name=self.name,
                passed=False,
                score=0.0,
                weight=self.weight,
                reason=f"خطا در ارزیابی: {str(e)[:80]}",
                metadata={"error": str(e)},
            )
    
    # ============================================================
    # Abstract Method
    # ============================================================
    
    @abstractmethod
    def _evaluate(
        self,
        df: pd.DataFrame,
        context: Dict[str, Any],
    ) -> RuleResult:
        """
        پیاده‌سازی منطق قانون
        
        باید:
            - RuleResult برگردونه
            - reason انسانی داشته باشه
            - metadata شامل مقادیر مهم باشه
        
        Args:
            df: DataFrame با ستون‌های اندیکاتور
            context: اطلاعات اضافی
        
        Returns:
            RuleResult
        """
        raise NotImplementedError
    
    # ============================================================
    # Helpers
    # ============================================================
    
    def _make_result(
        self,
        passed: bool,
        score: float,
        reason: str,
        **metadata: Any,
    ) -> RuleResult:
        """
        Helper برای ساخت RuleResult تمیز
        
        Args:
            passed: آیا شرط برقرار بود؟
            score: امتیاز ۰-۱ (معمولاً 1.0 برای pass، 0.0 برای fail)
            reason: توضیح انسانی
            **metadata: داده‌های اضافی
        """
        return RuleResult(
            rule_name=self.name,
            passed=passed,
            score=float(score),
            weight=self.weight,
            reason=reason,
            metadata=metadata,
        )
    
    def _get_last(self, df: pd.DataFrame, column: str) -> Optional[float]:
        """
        آخرین مقدار یک ستون (ایمن در برابر NaN)
        
        Returns:
            مقدار float یا None اگه NaN بود
        """
        if column not in df.columns:
            return None
        value = df[column].iloc[-1]
        if pd.isna(value):
            return None
        return float(value)
    
    def update_config(self, new_config: Dict[str, Any]) -> None:
        """
        آپدیت runtime تنظیمات (برای Weight Tuner)
        """
        self.config.update(new_config)
        self.enabled = self.config.get("enabled", True)
        self.weight = float(self.config.get("weight", self.weight))
    
    def to_dict(self) -> Dict[str, Any]:
        """خروجی config فعلی (برای API)"""
        return {
            "name": self.name,
            "enabled": self.enabled,
            "weight": self.weight,
            "config": self.config,
        }


__all__ = ["BaseRule"]
