# domain/entities/alert.py
# ============================================================
# Entity: Alert (هشدار)
# ============================================================

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any


class AlertLevel(Enum):
    """سطح هشدار"""
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


@dataclass
class Alert:
    """
    Entity هشدار
    
    ویژگی‌ها:
        id: شناسه یکتا
        level: سطح هشدار (INFO/WARNING/CRITICAL)
        message: پیام هشدار
        source: منبع هشدار (cpu, ram, api, model, database)
        data: داده‌های مرتبط
        timestamp: زمان ایجاد
        resolved: آیا رفع شده؟
        resolved_at: زمان رفع
    """
    
    id: int
    level: AlertLevel
    message: str
    source: str
    data: Dict[str, Any]
    timestamp: datetime
    resolved: bool = False
    resolved_at: Optional[datetime] = None
    
    @classmethod
    def create(
        cls,
        level: str,
        message: str,
        source: str,
        data: Optional[Dict[str, Any]] = None
    ) -> 'Alert':
        """
        ایجاد یک هشدار جدید
        
        پارامترها:
            level: سطح هشدار
            message: پیام
            source: منبع
            data: داده‌های اضافی
        
        خروجی:
            نمونه Alert
        """
        return cls(
            id=0,  # در زمان ذخیره تنظیم می‌شود
            level=AlertLevel(level),
            message=message,
            source=source,
            data=data or {},
            timestamp=datetime.now()
        )
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Alert':
        """ایجاد Alert از دیکشنری"""
        return cls(
            id=data.get('id', 0),
            level=AlertLevel(data.get('level', 'INFO')),
            message=data.get('message', ''),
            source=data.get('source', ''),
            data=data.get('data', {}),
            timestamp=datetime.fromisoformat(data.get('timestamp', datetime.now().isoformat())),
            resolved=data.get('resolved', False),
            resolved_at=datetime.fromisoformat(data['resolved_at']) if data.get('resolved_at') else None
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """تبدیل به دیکشنری"""
        return {
            'id': self.id,
            'level': self.level.value,
            'message': self.message,
            'source': self.source,
            'data': self.data,
            'timestamp': self.timestamp.isoformat(),
            'resolved': self.resolved,
            'resolved_at': self.resolved_at.isoformat() if self.resolved_at else None
        }
    
    def resolve(self) -> None:
        """علامت‌گذاری هشدار به عنوان رفع‌شده"""
        self.resolved = True
        self.resolved_at = datetime.now()
    
    def is_critical(self) -> bool:
        """آیا هشدار بحرانی است؟"""
        return self.level == AlertLevel.CRITICAL
    
    def get_emoji(self) -> str:
        """دریافت ایموجی متناسب با سطح"""
        if self.is_critical():
            return "🚨"
        elif self.level == AlertLevel.WARNING:
            return "⚠️"
        else:
            return "ℹ️"
