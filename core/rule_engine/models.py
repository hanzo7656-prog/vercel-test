# core/rule_engine/models.py
# ============================================================
# Rule Engine - Models & Data Structures
# نسخه ۱.۰
# ============================================================
# 
# این فایل شامل:
#   - MarketState: enum حالت‌های بازار
#   - Prediction: خروجی استاندارد مدل
#   - RuleResult: نتیجه ارزیابی یک قانون
#   - ScanResult: نتیجه یک اسکن کامل
#   - StateSnapshot: snapshot وضعیت یک symbol
# ============================================================

from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


# ============================================================
# MarketState
# ============================================================

class MarketState(str, Enum):
    """
    حالت‌های بازار برای هر symbol
    
    چرخه:
        IDLE → WATCHING → SETUP → ACTIVE → COOLING → IDLE
    
    توضیح:
        IDLE:     هیچ سیگنالی نیست
        WATCHING: یک شرط جالب فعال شده
        SETUP:    ۲+ شرط تأیید شده — آماده ورود
        ACTIVE:   پوزیشن باز داریم
        COOLING:  بعد از خروج، حداقل N کندل صبر
    """
    
    IDLE = "IDLE"
    WATCHING = "WATCHING"
    SETUP = "SETUP"
    ACTIVE = "ACTIVE"
    COOLING = "COOLING"
    
    @classmethod
    def from_string(cls, value: str) -> "MarketState":
        """ساخت از رشته با fallback به IDLE"""
        try:
            return cls(value.upper())
        except (ValueError, AttributeError):
            return cls.IDLE


# ============================================================
# RuleResult
# ============================================================

@dataclass
class RuleResult:
    """
    نتیجه ارزیابی یک قانون روی یک symbol
    
    Attributes:
        rule_name:    نام قانون (مثلاً "rsi")
        passed:       آیا شرط برقرار بود؟
        score:        امتیاز ۰-۱ (برای weighted scoring)
        weight:       وزن قانون (از config)
        weighted:     score * weight
        reason:       توضیح انسانی چرا pass/fail
        metadata:     اطلاعات اضافی (مقدار اندیکاتور، ...)
    """
    
    rule_name: str
    passed: bool
    score: float
    weight: float
    reason: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def weighted(self) -> float:
        """امتیاز وزن‌دار"""
        return float(self.score * self.weight)
    
    def to_dict(self) -> Dict[str, Any]:
        """تبدیل به دیکشنری"""
        return {
            "rule_name": self.rule_name,
            "passed": self.passed,
            "score": round(self.score, 4),
            "weight": self.weight,
            "weighted": round(self.weighted, 4),
            "reason": self.reason,
            "metadata": self.metadata,
        }


# ============================================================
# Prediction
# ============================================================

@dataclass
class Prediction:
    """
    خروجی استاندارد Rule Engine برای یک symbol
    
    این کلاس interface مشترک همه مدل‌هاست
    (XGBoost سابق، Rule Engine فعلی، GRU آینده).
    
    Attributes:
        symbol:           نماد ارز (BTC/USDT)
        coin_id:          شناسه ارز (bitcoin)
        score:            امتیاز نهایی ۰-۱
        rule_score:       امتیاز خام Rule Layer
        state:            حالت بازار
        reasons:          دلایل (لیست رشته)
        rule_results:     نتیجه تفصیلی هر قانون
        indicators:       مقادیر اندیکاتورها
        rank:             رتبه در اسکن (۱ = بهترین)
        timestamp:        زمان محاسبه
    """
    
    symbol: str
    coin_id: str
    score: float
    rule_score: float
    state: MarketState
    reasons: List[str] = field(default_factory=list)
    rule_results: List[RuleResult] = field(default_factory=list)
    indicators: Dict[str, Any] = field(default_factory=dict)
    rank: Optional[int] = None
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        """تبدیل به دیکشنری (برای JSON)"""
        return {
            "symbol": self.symbol,
            "coin_id": self.coin_id,
            "score": round(self.score, 4),
            "rule_score": round(self.rule_score, 4),
            "state": self.state.value,
            "reasons": self.reasons,
            "rule_results": [r.to_dict() for r in self.rule_results],
            "indicators": self.indicators,
            "rank": self.rank,
            "timestamp": self.timestamp.isoformat(),
        }
    
    def summary(self) -> Dict[str, Any]:
        """نسخه خلاصه (برای لیست اسکن)"""
        return {
            "symbol": self.symbol,
            "coin_id": self.coin_id,
            "score": round(self.score, 4),
            "state": self.state.value,
            "rank": self.rank,
            "reasons": self.reasons,
        }


# ============================================================
# StateSnapshot
# ============================================================

@dataclass
class StateSnapshot:
    """
    Snapshot وضعیت یک symbol در یک لحظه
    
    برای ذخیره در Redis و بازیابی:
        - حالت فعلی
        - چه زمانی وارد این حالت شدیم
        - context (اندیکاتورها در لحظه ورود)
        - تعداد سیگنال‌های تکراری در این state
    """
    
    symbol: str
    state: MarketState
    entered_at: datetime
    last_change_at: datetime
    context: Dict[str, Any] = field(default_factory=dict)
    signal_count: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "state": self.state.value,
            "entered_at": self.entered_at.isoformat(),
            "last_change_at": self.last_change_at.isoformat(),
            "context": self.context,
            "signal_count": self.signal_count,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StateSnapshot":
        """بازیابی از دیکشنری (Redis)"""
        return cls(
            symbol=data["symbol"],
            state=MarketState.from_string(data.get("state", "IDLE")),
            entered_at=datetime.fromisoformat(data["entered_at"]),
            last_change_at=datetime.fromisoformat(data["last_change_at"]),
            context=data.get("context", {}),
            signal_count=data.get("signal_count", 0),
        )
    
    @classmethod
    def initial(cls, symbol: str) -> "StateSnapshot":
        """ساخت snapshot اولیه در حالت IDLE"""
        now = datetime.now()
        return cls(
            symbol=symbol,
            state=MarketState.IDLE,
            entered_at=now,
            last_change_at=now,
            context={},
            signal_count=0,
        )


# ============================================================
# ScanResult
# ============================================================

@dataclass
class ScanResult:
    """
    نتیجه کامل یک اسکن بازار
    
    Attributes:
        scan_id:           شناسه یکتای اسکن
        total_scanned:     تعداد symbolهای بررسی‌شده
        passed_count:      تعداد symbolهایی که از فیلتر رد شدن
        results:           لیست Prediction (مرتب‌شده)
        config_used:       config استفاده‌شده
        started_at:        زمان شروع
        finished_at:       زمان پایان
        duration_seconds:  مدت اجرا
        errors:            خطاهای احتمالی
    """
    
    scan_id: str
    total_scanned: int
    passed_count: int
    results: List[Prediction] = field(default_factory=list)
    config_used: Dict[str, Any] = field(default_factory=dict)
    started_at: datetime = field(default_factory=datetime.now)
    finished_at: Optional[datetime] = None
    duration_seconds: float = 0.0
    errors: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """تبدیل کامل به دیکشنری"""
        return {
            "scan_id": self.scan_id,
            "total_scanned": self.total_scanned,
            "passed_count": self.passed_count,
            "results": [r.to_dict() for r in self.results],
            "config_used": self.config_used,
            "started_at": self.started_at.isoformat(),
            "finished_at": (
                self.finished_at.isoformat() if self.finished_at else None
            ),
            "duration_seconds": round(self.duration_seconds, 3),
            "errors": self.errors,
        }
    
    def summary(self) -> Dict[str, Any]:
        """نسخه خلاصه (برای پاسخ API)"""
        return {
            "scan_id": self.scan_id,
            "total_scanned": self.total_scanned,
            "passed_count": self.passed_count,
            "top_results": [r.summary() for r in self.results[:10]],
            "duration_seconds": round(self.duration_seconds, 3),
            "started_at": self.started_at.isoformat(),
        }


# ============================================================
# Export
# ============================================================

__all__ = [
    "MarketState",
    "RuleResult",
    "Prediction",
    "StateSnapshot",
    "ScanResult",
]
