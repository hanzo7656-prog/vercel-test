# presentation/schemas/response_schemas.py
# ============================================================
# Response Schemas - Validation برای پاسخ‌ها
# ============================================================

from typing import Optional, Any, Dict, List
from pydantic import BaseModel, Field
from datetime import datetime


class PredictionResponseSchema(BaseModel):
    """
    Schema پاسخ پیش‌بینی
    
    ویژگی‌ها:
        success: موفقیت عملیات
        data: داده‌های پیش‌بینی
        error: پیام خطا
        timestamp: زمان پاسخ
    """
    
    success: bool = Field(..., description='موفقیت عملیات')
    data: Optional[Dict[str, Any]] = Field(default=None, description='داده‌های پیش‌بینی')
    error: Optional[str] = Field(default=None, description='پیام خطا')
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat(), description='زمان پاسخ')


class HealthResponseSchema(BaseModel):
    """
    Schema پاسخ سلامت
    
    ویژگی‌ها:
        status: وضعیت کلی (ok/degraded/error)
        components: وضعیت اجزا
        timestamp: زمان پاسخ
    """
    
    status: str = Field(..., description='وضع
