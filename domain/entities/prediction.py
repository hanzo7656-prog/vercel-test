# domain/entities/prediction.py
# ============================================================
# Entity: Prediction (پیش‌بینی)
# ============================================================

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any


class SignalType(Enum):
    """نوع سیگنال پیش‌بینی"""
    BUY = "BUY"
    SELL = "SELL"
    NEUTRAL = "NEUTRAL"
    ERROR = "ERROR"
    DEMO = "DEMO"


@dataclass
class Prediction:
    """
    Entity پیش‌بینی
    
    ویژگی‌ها:
        coin: شناسه ارز
        coin_name: نام ارز
        current_price: قیمت لحظه‌ای
        signal: سیگنال (BUY/SELL/NEUTRAL)
        signal_type: نوع سیگنال به صورت Enum
        confidence: سطح اطمینان (درصد)
        confidence_score: امتیاز اطمینان (۰-۱۰۰)
        prediction_score: امتیاز پیش‌بینی (۰-۱)
        period: بازه زمانی
        model_mode: حالت مدل (PRODUCTION/DEMO)
        timestamp: زمان پیش‌بینی
        processing_time_ms: زمان پردازش (میلی‌ثانیه)
        data_points: تعداد نقاط داده استفاده شده
        extra: داده‌های اضافی
    """
    
    coin: str
    coin_name: str
    current_price: float
    signal: str
    signal_type: SignalType
    confidence: int
    confidence_score: int
    prediction_score: float
    period: str
    model_mode: str
    timestamp: datetime
    processing_time_ms: float
    data_points: int
    extra: Optional[Dict[str, Any]] = None
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Prediction':
        """
        ایجاد Prediction از دیکشنری
        
        پارامترها:
            data: دیکشنری داده‌ها
        
        خروجی:
            نمونه Prediction
        """
        return cls(
            coin=data.get('coin', ''),
            coin_name=data.get('coin_name', ''),
            current_price=float(data.get('current_price', 0)),
            signal=data.get('signal', ''),
            signal_type=SignalType(data.get('signal_type', 'NEUTRAL')),
            confidence=int(data.get('confidence', 50)),
            confidence_score=int(data.get('confidence_score', 50)),
            prediction_score=float(data.get('prediction_score', 0.5)),
            period=data.get('period', '24h'),
            model_mode=data.get('model_mode', 'DEMO'),
            timestamp=datetime.fromisoformat(data.get('timestamp', datetime.now().isoformat())),
            processing_time_ms=float(data.get('processing_time_ms', 0)),
            data_points=int(data.get('data_points', 0)),
            extra=data.get('extra')
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """
        تبدیل به دیکشنری
        
        خروجی:
            دیکشنری داده‌ها
        """
        return {
            'coin': self.coin,
            'coin_name': self.coin_name,
            'current_price': self.current_price,
            'signal': self.signal,
            'signal_type': self.signal_type.value,
            'confidence': f"{self.confidence}%",
            'confidence_score': self.confidence_score,
            'prediction_score': self.prediction_score,
            'period': self.period,
            'model_mode': self.model_mode,
            'timestamp': self.timestamp.isoformat(),
            'processing_time_ms': self.processing_time_ms,
            'data_points': self.data_points,
            'extra': self.extra
        }
    
    def is_buy(self) -> bool:
        """آیا سیگنال خرید است؟"""
        return self.signal_type == SignalType.BUY
    
    def is_sell(self) -> bool:
        """آیا سیگنال فروش است؟"""
        return self.signal_type == SignalType.SELL
    
    def is_neutral(self) -> bool:
        """آیا سیگنال خنثی است؟"""
        return self.signal_type == SignalType.NEUTRAL
    
    def get_emoji(self) -> str:
        """دریافت ایموجی متناسب با سیگنال"""
        if self.is_buy():
            return "🟢"
        elif self.is_sell():
            return "🔴"
        else:
            return "🟡"
    
    def get_summary(self) -> str:
        """
        دریافت خلاصه پیش‌بینی به صورت متن
        
        خروجی:
            متن خلاصه
        """
        emoji = self.get_emoji()
        return f"{emoji} {self.coin_name}: {self.signal} (اطمینان: {self.confidence}%)"
