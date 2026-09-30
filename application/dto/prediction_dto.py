# application/dto/prediction_dto.py
# ============================================================
# DTO: Prediction - نسخه ۳.۰
# Validation + RuleEngine Support
# ============================================================
# 
# تغییرات نسخه ۳.۰:
#   - حذف TrainRequestDTO (XGBoost-specific)
#   - حذف BatchTrainRequestDTO (XGBoost-specific)
#   - اضافه CalibrateRequestDTO (برای WeightCalibrator)
#   - اضافه ScanRequestDTO (برای Screener)
# ============================================================

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any, List

from domain.entities.prediction import Prediction, SignalType


# ============================================================
# Constants
# ============================================================

VALID_PERIODS: List[str] = ["24h", "1w", "1m", "3m", "6m"]
VALID_TRAIN_PERIODS: List[str] = ["1w", "1m", "3m", "6m"]
VALID_SIGNAL_TYPES: List[str] = ["BUY", "SELL", "NEUTRAL", "ERROR", "DEMO"]
VALID_CALIBRATION_PROFILES: List[str] = [
    "fast", "balanced", "accurate", "hill_climb", "random"
]
VALID_TIMEFRAMES: List[str] = ["1m", "5m", "15m", "1h", "4h", "1d"]


# ============================================================
# Prediction Request DTO
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
        """اعتبارسنجی"""
        errors = []
        
        # Period
        if self.period not in VALID_PERIODS:
            errors.append(
                f"period باید یکی از {VALID_PERIODS} باشه"
            )
        
        # Coin
        if not self.coin or not self.coin.strip():
            errors.append("coin نمی‌تونه خالی باشه")
        
        # Coins
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
        """ایجاد از query params"""
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
        """نرمال‌سازی"""
        return PredictionRequestDTO(
            coin=self.coin.strip().lower() if self.coin else "bitcoin",
            period=self.period.strip().lower() if self.period else "24h",
            coins=[c.strip().lower() for c in self.coins] if self.coins else None,
        )


# ============================================================
# Prediction Response DTO
# ============================================================

@dataclass
class PredictionDTO:
    """
    DTO پاسخ پیش‌بینی
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
# Calibrate Request DTO (🆕 - جایگزین TrainRequestDTO)
# ============================================================

@dataclass
class CalibrateRequestDTO:
    """
    DTO درخواست کالیبراسیون وزن‌ها
    
    ویژگی‌ها:
        period: بازه داده تاریخی
        profile_name: نام پروفایل (fast/balanced/accurate/hill_climb/random)
        strategy: استراتژی (override)
        coins: لیست ارزها
        save: ذخیره در DB؟
    """
    
    period: str = "1m"
    profile_name: str = "balanced"
    strategy: Optional[str] = None
    coins: Optional[List[str]] = None
    save: bool = True
    
    # ============================================================
    # Validation
    # ============================================================
    
    def validate(self) -> tuple[bool, List[str]]:
        """اعتبارسنجی"""
        errors = []
        
        # Period
        if self.period not in VALID_TRAIN_PERIODS:
            errors.append(
                f"period باید یکی از {VALID_TRAIN_PERIODS} باشه"
            )
        
        # Profile name
        if self.profile_name:
            if not isinstance(self.profile_name, str):
                errors.append("profile_name باید string باشه")
        
        # Strategy
        if self.strategy is not None:
            valid_strategies = ["grid", "random", "hill_climb"]
            if self.strategy not in valid_strategies:
                errors.append(
                    f"strategy باید یکی از {valid_strategies} باشه"
                )
        
        # Coins
        if self.coins is not None:
            if not isinstance(self.coins, list):
                errors.append("coins باید لیست باشه")
            elif len(self.coins) == 0:
                errors.append("coins نمی‌تونه خالی باشه")
        
        return len(errors) == 0, errors
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CalibrateRequestDTO':
        """ایجاد از دیکشنری"""
        return cls(
            period=data.get("period", "1m"),
            profile_name=data.get("profile_name", "balanced"),
            strategy=data.get("strategy"),
            coins=data.get("coins"),
            save=data.get("save", True),
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """تبدیل به دیکشنری"""
        return {
            "period": self.period,
            "profile_name": self.profile_name,
            "strategy": self.strategy,
            "coins": self.coins,
            "save": self.save,
        }


# ============================================================
# Scan Request DTO (🆕)
# ============================================================

@dataclass
class ScanRequestDTO:
    """
    DTO درخواست اسکن بازار
    
    ویژگی‌ها:
        symbols: لیست نمادها (اگه None، از config)
        top_n: تعداد symbolها
        timeframe: تایم‌فریم
        max_results: حداکثر نتایج
        update_state: آپدیت state؟
        use_cache: استفاده از cache؟
    """
    
    symbols: Optional[List[str]] = None
    top_n: int = 30
    timeframe: Optional[str] = None
    max_results: int = 10
    update_state: bool = True
    use_cache: bool = True
    
    # ============================================================
    # Validation
    # ============================================================
    
    def validate(self) -> tuple[bool, List[str]]:
        """اعتبارسنجی"""
        errors = []
        
        # Symbols
        if self.symbols is not None:
            if not isinstance(self.symbols, list):
                errors.append("symbols باید لیست باشه")
            elif len(self.symbols) == 0:
                errors.append("symbols نمی‌تونه خالی باشه")
        
        # top_n
        if not (1 <= self.top_n <= 500):
            errors.append("top_n باید بین ۱ تا ۵۰۰ باشه")
        
        # max_results
        if not (1 <= self.max_results <= 100):
            errors.append("max_results باید بین ۱ تا ۱۰۰ باشه")
        
        # timeframe
        if self.timeframe is not None:
            if self.timeframe not in VALID_TIMEFRAMES:
                errors.append(
                    f"timeframe باید یکی از {VALID_TIMEFRAMES} باشه"
                )
        
        return len(errors) == 0, errors
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ScanRequestDTO':
        """ایجاد از دیکشنری"""
        return cls(
            symbols=data.get("symbols"),
            top_n=data.get("top_n", 30),
            timeframe=data.get("timeframe"),
            max_results=data.get("max_results", 10),
            update_state=data.get("update_state", True),
            use_cache=data.get("use_cache", True),
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """تبدیل به دیکشنری"""
        return {
            "symbols": self.symbols,
            "top_n": self.top_n,
            "timeframe": self.timeframe,
            "max_results": self.max_results,
            "update_state": self.update_state,
            "use_cache": self.use_cache,
        }
