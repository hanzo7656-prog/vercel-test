# application/dto/prediction_dto.py
# ============================================================
# DTO: Prediction (پیش‌بینی)
# ============================================================

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any, List

from domain.entities.prediction import Prediction, SignalType


@dataclass
class PredictionRequestDTO:
    """
    DTO درخواست پیش‌بینی
    
    ویژگی‌ها:
        coin: شناسه ارز (پیش‌فرض: bitcoin)
        period: بازه زمانی (پیش‌فرض: 24h)
        coins: لیست ارزها (برای پیش‌بینی چندارز)
    """
    
    coin: str = "bitcoin"
    period: str = "24h"
    coins: Optional[List[str]] = None
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PredictionRequestDTO':
        """ایجاد از دیکشنری"""
        return cls(
            coin=data.get('coin', 'bitcoin'),
            period=data.get('period', '24h'),
            coins=data.get('coins')
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """تبدیل به دیکشنری"""
        return {
            'coin': self.coin,
            'period': self.period,
            'coins': self.coins
        }
    
    def is_multiple(self) -> bool:
        """آیا درخواست چندارز است؟"""
        return self.coins is not None and len(self.coins) > 0


@dataclass
class PredictionDTO:
    """
    DTO پاسخ پیش‌بینی
    
    ویژگی‌ها:
        success: موفقیت عملیات
        data: داده‌های پیش‌بینی
        error: پیام خطا
        count: تعداد نتایج
        timestamp: زمان پاسخ
    """
    
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    count: int = 0
    timestamp: datetime = field(default_factory=datetime.now)
    
    @classmethod
    def from_prediction(cls, prediction: Prediction) -> 'PredictionDTO':
        """
        ایجاد از Entity Prediction
        
        پارامترها:
            prediction: Entity پیش‌بینی
        
        خروجی:
            DTO پیش‌بینی
        """
        return cls(
            success=True,
            data=prediction.to_dict(),
            count=1
        )
    
    @classmethod
    def from_predictions(cls, predictions: List[Prediction]) -> 'PredictionDTO':
        """
        ایجاد از لیست Predictions
        
        پارامترها:
            predictions: لیست Entities پیش‌بینی
        
        خروجی:
            DTO پیش‌بینی
        """
        return cls(
            success=True,
            data={'results': [p.to_dict() for p in predictions]},
            count=len(predictions)
        )
    
    @classmethod
    def from_error(cls, error: str) -> 'PredictionDTO':
        """
        ایجاد DTO خطا
        
        پارامترها:
            error: پیام خطا
        
        خروجی:
            DTO خطا
        """
        return cls(
            success=False,
            error=error,
            count=0
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """تبدیل به دیکشنری"""
        return {
            'success': self.success,
            'data': self.data,
            'error': self.error,
            'count': self.count,
            'timestamp': self.timestamp.isoformat()
        }
