# domain/value_objects/signal.py
# ============================================================
# Value Object: Signal (سیگنال)
# ============================================================

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class SignalType(Enum):
    """نوع سیگنال"""
    BUY = "BUY"
    SELL = "SELL"
    NEUTRAL = "NEUTRAL"


@dataclass(frozen=True)
class Signal:
    """
    Value Object سیگنال
    
    ویژگی‌ها:
        type: نوع سیگنال (BUY/SELL/NEUTRAL)
        confidence: سطح اطمینان (۰-۱۰۰)
        score: امتیاز پیش‌بینی (۰-۱)
    """
    
    type: SignalType
    confidence: int
    score: float
    
    def __post_init__(self) -> None:
        """اعتبارسنجی پس از ایجاد"""
        if not 0 <= self.confidence <= 100:
            raise ValueError("Confidence must be between 0 and 100")
        if not 0 <= self.score <= 1:
            raise ValueError("Score must be between 0 and 1")
    
    def to_dict(self) -> dict:
        """تبدیل به دیکشنری"""
        return {
            'type': self.type.value,
            'confidence': self.confidence,
            'score': self.score
        }
    
    def formatted(self) -> str:
        """نمایش فرمت‌شده سیگنال"""
        emoji = self.get_emoji()
        return f"{emoji} {self.type.value} (اطمینان: {self.confidence}%)"
    
    def get_emoji(self) -> str:
        """دریافت ایموجی متناسب با سیگنال"""
        if self.type == SignalType.BUY:
            return "🟢"
        elif self.type == SignalType.SELL:
            return "🔴"
        else:
            return "🟡"
    
    def get_text(self) -> str:
        """دریافت متن سیگنال"""
        if self.type == SignalType.BUY:
            return "صعودی (الگوی خرید)"
        elif self.type == SignalType.SELL:
            return "نزولی (الگوی فروش)"
        else:
            return "خنثی (بدون الگوی مشخص)"
    
    @classmethod
    def from_score(cls, score: float) -> 'Signal':
        """
        ایجاد سیگنال از امتیاز پیش‌بینی
        
        پارامترها:
            score: امتیاز پیش‌بینی (۰-۱)
        
        خروجی:
            نمونه Signal
        """
        if score >= 0.65:
            signal_type = SignalType.BUY
            confidence = int(((score - 0.5) / 0.5) * 100)
        elif score <= 0.35:
            signal_type = SignalType.SELL
            confidence = int(((0.5 - score) / 0.5) * 100)
        else:
            signal_type = SignalType.NEUTRAL
            confidence = 50
        
        confidence = min(100, max(0, confidence))
        
        return cls(
            type=signal_type,
            confidence=confidence,
            score=score
        )
