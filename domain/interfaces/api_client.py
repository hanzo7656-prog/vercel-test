# domain/interfaces/api_client.py
# ============================================================
# Interface: APIClient
# ============================================================

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Union


class APIClient(ABC):
    """
    Interface کلاینت API
    
    متدهای عمومی برای ارتباط با APIهای خارجی
    """
    
    @abstractmethod
    def get_chart(self, coin_id: str, period: str = "24h", currency: str = "USD") -> Union[List[List], Dict]:
        """
        دریافت داده‌های تاریخی قیمت
        
        پارامترها:
            coin_id: شناسه ارز
            period: بازه زمانی
            currency: واحد پول
        
        خروجی:
            داده‌های قیمت
        """
        pass
    
    @abstractmethod
    def get_coin(self, coin_id: str, currency: str = "USD") -> Optional[Dict]:
        """
        دریافت اطلاعات لحظه‌ای یک ارز
        
        پارامترها:
            coin_id: شناسه ارز
            currency: واحد پول
        
        خروجی:
            اطلاعات ارز
        """
        pass
    
    @abstractmethod
    def get_fear_greed(self, use_cache: bool = True) -> Optional[Dict]:
        """
        دریافت شاخص ترس و طمع
        
        پارامترها:
            use_cache: استفاده از کش
        
        خروجی:
            داده‌های ترس و طمع
        """
        pass
    
    @abstractmethod
    def get_credits(self) -> Optional[Dict]:
        """
        دریافت اعتبار باقیمانده
        
        خروجی:
            اطلاعات اعتبار
        """
        pass
    
    @abstractmethod
    def get_status(self) -> Optional[Dict]:
        """
        بررسی سلامت API
        
        خروجی:
            وضعیت API
        """
        pass
    
    @abstractmethod
    def get_stats(self) -> Dict:
        """
        دریافت آمار کلاینت
        
        خروجی:
            آمار
        """
        pass
