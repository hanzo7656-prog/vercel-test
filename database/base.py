# database/base.py
# ============================================================
# کلاس پایه برای همه دیتابیس‌ها
# ============================================================

from abc import ABC, abstractmethod
from typing import Any, Optional, Dict
import logging

logger = logging.getLogger(__name__)


class DatabaseBase(ABC):
    """کلاس پایه برای همه اتصالات دیتابیس"""
    
    def __init__(self, name: str, config: Dict[str, Any]):
        self.name = name
        self.config = config
        self._connected = False
        self._client = None
    
    @abstractmethod
    def connect(self) -> bool:
        """برقراری اتصال به دیتابیس"""
        pass
    
    @abstractmethod
    def disconnect(self) -> bool:
        """قطع اتصال از دیتابیس"""
        pass
    
    @abstractmethod
    def get(self, key: str) -> Optional[Any]:
        """دریافت مقدار"""
        pass
    
    @abstractmethod
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """ذخیره مقدار"""
        pass
    
    @abstractmethod
    def delete(self, key: str) -> bool:
        """حذف مقدار"""
        pass
    
    @abstractmethod
    def exists(self, key: str) -> bool:
        """بررسی وجود کلید"""
        pass
    
    @abstractmethod
    def flush(self) -> bool:
        """پاک کردن همه داده‌ها (احتیاط!)"""
        pass
    
    def is_connected(self) -> bool:
        """بررسی وضعیت اتصال با تست واقعی"""
        if not self._connected or not self._client:
            return False
        # تست واقعی با ping
        return self.ping()
        
    def get_client(self):
        """دریافت کلاینت اصلی (برای دسترسی مستقیم)"""
        return self._client
    
    def ping(self) -> bool:
        """بررسی سلامت اتصال"""
        try:
            if hasattr(self._client, 'ping'):
                return self._client.ping()
            return self.is_connected()
        except:
            return False
    
    def health_check(self) -> Dict[str, Any]:
        """بررسی سلامت کامل"""
        return {
            "name": self.name,
            "type": self.config.get("type", "unknown"),
            "connected": self.is_connected(),
            "ping": self.ping(),
            "enabled": self.config.get("enabled", True)
        }
