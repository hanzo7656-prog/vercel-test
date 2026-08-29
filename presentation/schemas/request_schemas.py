# presentation/schemas/request_schemas.py
# ============================================================
# Request Schemas - Validation برای درخواست‌ها
# ============================================================

from typing import List, Optional
from pydantic import BaseModel, Field, validator


class PredictionRequestSchema(BaseModel):
    """
    Schema درخواست پیش‌بینی
    
    ویژگی‌ها:
        coin: شناسه ارز (پیش‌فرض: bitcoin)
        period: بازه زمانی (پیش‌فرض: 24h)
        coins: لیست ارزها (برای پیش‌بینی چندارز)
    """
    
    coin: str = Field(default='bitcoin', description='شناسه ارز')
    period: str = Field(default='24h', description='بازه زمانی (24h, 1w, 1m, 3m, 6m)')
    coins: Optional[List[str]] = Field(default=None, description='لیست ارزها')
    
    @validator('period')
    def validate_period(cls, v):
        """اعتبارسنجی بازه زمانی"""
        valid_periods = ['24h', '1w', '1m', '3m', '6m']
        if v not in valid_periods:
            raise ValueError(f'period must be one of {valid_periods}')
        return v
    
    @validator('coin')
    def validate_coin(cls, v):
        """اعتبارسنجی شناسه ارز"""
        if not v or v.strip() == '':
            raise ValueError('coin cannot be empty')
        return v.strip().lower()


class TrainRequestSchema(BaseModel):
    """
    Schema درخواست آموزش مدل
    
    ویژگی‌ها:
        period: بازه زمانی (پیش‌فرض: 1m)
        coins: لیست ارزها
        incremental: آموزش افزایشی؟
    """
    
    period: str = Field(default='1m', description='بازه زمانی (1w, 1m, 3m, 6m)')
    coins: List[str] = Field(default=['bitcoin', 'ethereum'], description='لیست ارزها')
    incremental: bool = Field(default=False, description='آموزش افزایشی')
    
    @validator('period')
    def validate_period(cls, v):
        """اعتبارسنجی بازه زمانی"""
        valid_periods = ['1w', '1m', '3m', '6m']
        if v not in valid_periods:
            raise ValueError(f'period must be one of {valid_periods}')
        return v


class BatchRequestSchema(BaseModel):
    """
    Schema درخواست پردازش دسته‌ای
    
    ویژگی‌ها:
        items: لیست آیتم‌ها
        batch_size: اندازه هر Batch
        max_workers: تعداد Threadها
    """
    
    items: List[str] = Field(..., description='لیست آیتم‌ها', min_items=1)
    batch_size: int = Field(default=10, description='اندازه هر Batch', ge=1, le=100)
    max_workers: int = Field(default=5, description='تعداد Threadها', ge=1, le=20)
