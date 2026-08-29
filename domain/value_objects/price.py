# domain/value_objects/price.py
# ============================================================
# Value Object: Price (قیمت)
# ============================================================

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Price:
    """
    Value Object قیمت
    
    ویژگی‌ها:
        value: مقدار قیمت
        currency: واحد پول (پیش‌فرض: USD)
        change_24h: تغییر ۲۴ ساعته (درصد)
    """
    
    value: float
    currency: str = "USD"
    change_24h: Optional[float] = None
    
    def __post_init__(self) -> None:
        """اعتبارسنجی پس از ایجاد"""
        if self.value < 0:
            raise ValueError("Price cannot be negative")
    
    def to_dict(self) -> dict:
        """تبدیل به دیکشنری"""
        return {
            'value': self.value,
            'currency': self.currency,
            'change_24h': self.change_24h
        }
    
    def formatted(self) -> str:
        """نمایش فرمت‌شده قیمت"""
        return f"${self.value:,.2f}"
    
    def change_formatted(self) -> str:
        """نمایش فرمت‌شده تغییرات"""
        if self.change_24h is None:
            return "N/A"
        sign = "+" if self.change_24h >= 0 else ""
        return f"{sign}{self.change_24h:.2f}%"
    
    def is_positive_change(self) -> bool:
        """آیا تغییر مثبت است؟"""
        return self.change_24h is not None and self.change_24h > 0
    
    def get_change_emoji(self) -> str:
        """دریافت ایموجی تغییرات"""
        if self.change_24h is None:
            return "➖"
        return "📈" if self.is_positive_change() else "📉"
    
    @classmethod
    def from_dict(cls, data: dict) -> 'Price':
        """ایجاد Price از دیکشنری"""
        return cls(
            value=float(data.get('value', 0)),
            currency=data.get('currency', 'USD'),
            change_24h=data.get('change_24h')
        )
