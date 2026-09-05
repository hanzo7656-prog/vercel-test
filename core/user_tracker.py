# ============================================================
# user_tracker.py - پیگیری کاربران آنلاین
# ============================================================

import time
import threading
import logging
from typing import Dict, Set
from datetime import datetime

from infrastructure.database import get_cache

logger = logging.getLogger(__name__)


class UserTracker:
    """
    پیگیری تعداد کاربران آنلاین
    برای توقف بروزرسانی‌ها در صورت آفلاین بودن همه کاربران
    """
    
    def __init__(self, timeout: int = 30):
        self.timeout = timeout  # ثانیه
        self._users: Dict[str, float] = {}  # session_id -> last_heartbeat
        self._lock = threading.Lock()
        self.cache = get_cache()
        logger.info("✅ UserTracker initialized")
    
    def heartbeat(self, session_id: str) -> None:
        """ثبت ضربان قلب کاربر"""
        with self._lock:
            self._users[session_id] = time.time()
            # ذخیره در Redis برای دسترسی بین چند instance
            self.cache.set(f"user_heartbeat_{session_id}", time.time(), self.timeout + 10)
    
    def remove_user(self, session_id: str) -> None:
        """حذف کاربر از لیست آنلاین"""
        with self._lock:
            if session_id in self._users:
                del self._users[session_id]
            self.cache.delete(f"user_heartbeat_{session_id}")
    
    def get_online_count(self) -> int:
        """دریافت تعداد کاربران آنلاین"""
        self._cleanup()
        with self._lock:
            return len(self._users)
    
    def get_online_users(self) -> Set[str]:
        """دریافت لیست کاربران آنلاین"""
        self._cleanup()
        with self._lock:
            return set(self._users.keys())
    
    def _cleanup(self) -> None:
        """پاکسازی کاربران منقضی شده"""
        now = time.time()
        with self._lock:
            expired = [
                sid for sid, last_heartbeat in self._users.items()
                if (now - last_heartbeat) > self.timeout
            ]
            for sid in expired:
                del self._users[sid]
                self.cache.delete(f"user_heartbeat_{sid}")
            
            if expired:
                logger.debug(f"🧹 Cleaned up {len(expired)} expired users")
    
    def get_stats(self) -> Dict[str, Any]:
        """دریافت آمار"""
        return {
            "online_count": self.get_online_count(),
            "total_users": len(self._users),
            "timeout_seconds": self.timeout
        }
