# application/dto/prediction_dto.py
# ============================================================
# DTO: Prediction - نسخه ۲.۰
# Validation + Profile support
# ============================================================

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional, Dict, Any, List, ClassVar

from domain.entities.prediction import Prediction, SignalType


# ============================================================
# Constants
# ============================================================

VALID_PERIODS: List[str] = ["24h", "1w", "1m", "3m", "6m"]
VALID_SIGNAL_TYPES: List[str] = ["BUY", "SELL", "NEUTRAL", "ERROR", "DEMO"]


# ============================================================
# Request DTO
# ============================================================

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
    
    # ============================================================
    # Validation
    # ============================================================
    
    def validate(self) -> tuple[bool, List[str]]:
        """
        اعتبارسنجی
        
        خروجی:
            (valid: bool, errors: List[str])
        """
        errors = []
        
        # Period
        if self.period not in VALID_PERIODS:
            errors.append(
                f"period باید یکی از {VALID_PERIODS} باشه"
            )
        
        # Coin
        if not self.coin or not self.coin.strip():
            errors.append("coin نمی‌تونه خالی باشه")
        
        # Coins (اگه هست)
        if self.coins is not None:
            if not isinstance(self.coins, list):
                errors.append("coins باید لیست باشه")
            elif len(self.coins) == 0:
                errors.append("coins نمی‌تونه خالی باشه")
        
        return len(errors) == 0, errors
    
    # ============================================================
    # Factory Methods
    # ============================================================
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PredictionRequestDTO':
        """ایجاد از دیکشنری"""
        return cls(
            coin=data.get("coin", "bitcoin"),
            period=data.get("period", "24h"),
            coins=data.get("coins"),
        )
    
    @classmethod
    def from_query(cls, args: Any) -> 'PredictionRequestDTO':
        """ایجاد از query params (Flask request.args)"""
        coins_param = args.get("coins", "")
        coins = None
        
        if coins_param:
            coins = [c.strip() for c in coins_param.split(",") if c.strip()]
        
        return cls(
            coin=args.get("coin", "bitcoin"),
            period=args.get("period", "24h"),
            coins=coins,
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """تبدیل به دیکشنری"""
        return {
            "coin": self.coin,
            "period": self.period,
            "coins": self.coins,
        }
    
    def is_multiple(self) -> bool:
        """آیا درخواست چندارز است؟"""
        return self.coins is not None and len(self.coins) > 0
    
    def normalized(self) -> 'PredictionRequestDTO':
        """نرمال‌سازی (lowercase, strip)"""
        return PredictionRequestDTO(
            coin=self.coin.strip().lower() if self.coin else "bitcoin",
            period=self.period.strip().lower() if self.period else "24h",
            coins=[c.strip().lower() for c in self.coins] if self.coins else None,
        )


# ============================================================
# Response DTO
# ============================================================

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
    
    # ============================================================
    # Factory Methods
    # ============================================================
    
    @classmethod
    def from_prediction(cls, prediction: Prediction) -> 'PredictionDTO':
        """ایجاد از Entity Prediction"""
        return cls(
            success=True,
            data=prediction.to_dict(),
            count=1,
        )
    
    @classmethod
    def from_predictions(cls, predictions: List[Prediction]) -> 'PredictionDTO':
        """ایجاد از لیست Predictionها"""
        return cls(
            success=True,
            data={"results": [p.to_dict() for p in predictions]},
            count=len(predictions),
        )
    
    @classmethod
    def from_error(cls, error: str, count: int = 0) -> 'PredictionDTO':
        """ایجاد DTO خطا"""
        return cls(
            success=False,
            error=error,
            count=count,
        )
    
    # ============================================================
    # Serialization
    # ============================================================
    
    def to_dict(self) -> Dict[str, Any]:
        """تبدیل به دیکشنری"""
        return {
            "success": self.success,
            "data": self.data,
            "error": self.error,
            "count": self.count,
            "timestamp": self.timestamp.isoformat(),
        }


# ============================================================
# Trainer DTO (🆕)
# ============================================================

@dataclass
class TrainRequestDTO:
    """
    DTO درخواست آموزش (🆕)
    
    ویژگی‌ها:
        period: بازه داده
        coins: لیست ارزها
        profile_name: نام پروفایل
        profile: پروفایل مستقیم
        strategy: استراتژی آموزش
        save: ذخیره بشه؟
    """
    
    period: str = "1m"
    coins: Optional[List[str]] = None
    profile_name: Optional[str] = None
    profile: Optional[Dict[str, Any]] = None
    strategy: Optional[str] = None
    save: bool = True
    
    # ============================================================
    # Validation
    # ============================================================
    
    def validate(self) -> tuple[bool, List[str]]:
        """اعتبارسنجی"""
        errors = []
        
        valid_train_periods = ["1w", "1m", "3m", "6m"]
        
        if self.period not in valid_train_periods:
            errors.append(
                f"period باید یکی از {valid_train_periods} باشه"
            )
        
        if self.profile_name is not None and not isinstance(self.profile_name, str):
            errors.append("profile_name باید string باشه")
        
        valid_strategies = ["full", "incremental", "transfer", "fine_tune", "ensemble"]
        if self.strategy is not None and self.strategy not in valid_strategies:
            errors.append(f"strategy باید یکی از {valid_strategies} باشه")
        
        if self.coins is not None:
            if not isinstance(self.coins, list):
                errors.append("coins باید لیست باشه")
            elif len(self.coins) == 0:
                errors.append("coins نمی‌تونه خالی باشه")
        
        return len(errors) == 0, errors
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TrainRequestDTO':
        """ایجاد از دیکشنری"""
        return cls(
            period=data.get("period", "1m"),
            coins=data.get("coins"),
            profile_name=data.get("profile_name"),
            profile=data.get("profile"),
            strategy=data.get("strategy"),
            save=data.get("save", True),
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """تبدیل به دیکشنری"""
        return {
            "period": self.period,
            "coins": self.coins,
            "profile_name": self.profile_name,
            "profile": self.profile,
            "strategy": self.strategy,
            "save": self.save,
        }


# ============================================================
# Batch DTO (🆕)
# ============================================================

@dataclass
class BatchTrainRequestDTO:
    """
    DTO برای A/B Testing (🆕)
    
    ویژگی‌ها:
        profiles: لیست نام پروفایل‌ها
        period: بازه
        coins: ارزها
    """
    
    profiles: List[str] = field(default_factory=list)
    period: str = "1m"
    coins: Optional[List[str]] = None
    
    def validate(self) -> tuple[bool, List[str]]:
        """اعتبارسنجی"""
        errors = []
        
        if not self.profiles or len(self.profiles) < 2:
            errors.append("برای A/B Testing حداقل ۲ پروفایل لازمه")
        
        valid_periods = ["1w", "1m", "3m", "6m"]
        if self.period not in valid_periods:
            errors.append(f"period باید یکی از {valid_periods} باشه")
        
        return len(errors) == 0, errors
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'BatchTrainRequestDTO':
        """ایجاد از دیکشنری"""
        return cls(
            profiles=data.get("profiles", []),
            period=data.get("period", "1m"),
            coins=data.get("coins"),
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """تبدیل به دیکشنری"""
        return {
            "profiles": self.profiles,
            "period": self.period,
            "coins": self.coins,
        }
