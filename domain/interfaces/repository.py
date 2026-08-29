# domain/interfaces/repository.py
# ============================================================
# Interface: Repository
# ============================================================

from abc import ABC, abstractmethod
from typing import Generic, TypeVar, Optional, List, Dict, Any

T = TypeVar('T')


class Repository(ABC, Generic[T]):
    """
    Interface اصلی Repository Pattern
    
    متدهای عمومی برای ذخیره، بازیابی و حذف داده‌ها
    """
    
    @abstractmethod
    def save(self, entity: T) -> T:
        """
        ذخیره یک Entity
        
        پارامترها:
            entity: Entity برای ذخیره
        
        خروجی:
            Entity ذخیره شده (با ID به‌روزرسانی شده)
        """
        pass
    
    @abstractmethod
    def find_by_id(self, entity_id: int) -> Optional[T]:
        """
        پیدا کردن Entity با ID
        
        پارامترها:
            entity_id: شناسه
        
        خروجی:
            Entity یا None
        """
        pass
    
    @abstractmethod
    def find_all(self, limit: int = 100, offset: int = 0) -> List[T]:
        """
        دریافت لیست همه Entities
        
        پارامترها:
            limit: تعداد
            offset: offset
        
        خروجی:
            لیست Entities
        """
        pass
    
    @abstractmethod
    def delete(self, entity_id: int) -> bool:
        """
        حذف Entity با ID
        
        پارامترها:
            entity_id: شناسه
        
        خروجی:
            موفقیت عملیات
        """
        pass
    
    @abstractmethod
    def count(self) -> int:
        """
        تعداد کل Entities
        
        خروجی:
            تعداد
        """
        pass
    
    @abstractmethod
    def find_by_criteria(self, criteria: Dict[str, Any]) -> List[T]:
        """
        جستجو با معیارهای مشخص
        
        پارامترها:
            criteria: دیکشنری معیارها
        
        خروجی:
            لیست Entities
        """
        pass
