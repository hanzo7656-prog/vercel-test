# infrastructure/auth/auth_manager.py
# ============================================================
# مدیریت احراز هویت - نسخه ۳.۰ (با get_session)
# ============================================================

import os
import json
import uuid
import logging
import time
from typing import Dict, Any, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class AuthManager:
    """
    مدیریت احراز هویت با پشتیبانی از Session
    
    ویژگی‌ها:
        - ایجاد session با UUID
        - ذخیره session در Redis یا حافظه داخلی
        - بررسی اعتبار session
        - حذف session (خروج)
        - دریافت اطلاعات session با get_session
    """
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if hasattr(self, '_initialized'):
            return
        self._initialized = True
        
        # اطلاعات کاربران (در محیط واقعی از دیتابیس بگیرید)
        self._users = {
            "admin": {
                "password": "Admin@123",
                "role": "admin",
                "name": "مدیر سیستم"
            },
            "user": {
                "password": "User@123",
                "role": "user",
                "name": "کاربر عادی"
            }
        }
        
        # ذخیره session ها در حافظه (در محیط واقعی از Redis استفاده کنید)
        self._sessions: Dict[str, Dict] = {}
        self._session_ttl = 86400  # ۲۴ ساعت
        
        # تلاش برای اتصال به Redis
        self._redis = None
        self._use_redis = False
        try:
            import redis
            self._redis = redis.Redis(
                host=os.getenv('REDIS_HOST', 'localhost'),
                port=int(os.getenv('REDIS_PORT', 6379)),
                password=os.getenv('REDIS_PASSWORD', None),
                db=int(os.getenv('REDIS_SESSION_DB', 1)),
                decode_responses=True,
                socket_connect_timeout=3
            )
            self._redis.ping()
            self._use_redis = True
            logger.info("✅ Redis session storage enabled")
        except Exception as e:
            logger.warning(f"⚠️ Redis session storage not available: {e}")
            logger.info("📝 Using in-memory session storage")
        
        logger.info("✅ AuthManager v3.0 initialized")
    
    def login(self, username: str, password: str) -> Dict[str, Any]:
        """
        ورود کاربر و ایجاد session
        
        پارامترها:
            username: نام کاربری
            password: رمز عبور
        
        خروجی:
            دیکشنری شامل success, session_id, username, role
        """
        # اعتبارسنجی ورودی
        if not username or not password:
            return {
                "success": False,
                "error": "Username and password are required"
            }
        
        # بررسی کاربر
        user = self._users.get(username)
        if not user:
            logger.warning(f"⚠️ Login attempt with unknown username: {username}")
            return {
                "success": False,
                "error": "Invalid username or password"
            }
        
        # بررسی رمز عبور
        if user.get("password") != password:
            logger.warning(f"⚠️ Login attempt with wrong password for: {username}")
            return {
                "success": False,
                "error": "Invalid username or password"
            }
        
        # ایجاد session
        session_id = self._create_session(username, user)
        
        logger.info(f"✅ User logged in: {username} (role: {user.get('role')})")
        
        return {
            "success": True,
            "session_id": session_id,
            "username": username,
            "role": user.get("role", "guest"),
            "name": user.get("name", username)
        }
    
    def _create_session(self, username: str, user: Dict) -> str:
        """ایجاد session جدید"""
        session_id = str(uuid.uuid4())
        session_data = {
            "username": username,
            "role": user.get("role", "guest"),
            "name": user.get("name", username),
            "login_time": datetime.now().isoformat(),
            "expires_at": (datetime.now() + timedelta(seconds=self._session_ttl)).isoformat()
        }
        
        # ذخیره در Redis یا حافظه
        if self._use_redis and self._redis:
            try:
                key = f"session:{session_id}"
                self._redis.setex(
                    key,
                    self._session_ttl,
                    json.dumps(session_data)
                )
                logger.debug(f"✅ Session stored in Redis: {session_id[:8]}...")
            except Exception as e:
                logger.error(f"❌ Redis session save error: {e}")
                self._sessions[session_id] = session_data
        else:
            self._sessions[session_id] = session_data
            logger.debug(f"✅ Session stored in memory: {session_id[:8]}...")
        
        return session_id
    
    def validate_session(self, session_id: str) -> Optional[Dict]:
        """
        بررسی اعتبار session
        
        پارامترها:
            session_id: شناسه session
        
        خروجی:
            اطلاعات session در صورت معتبر بودن، یا None
        """
        if not session_id:
            return None
        
        session_data = None
        
        # دریافت از Redis یا حافظه
        if self._use_redis and self._redis:
            try:
                key = f"session:{session_id}"
                data = self._redis.get(key)
                if data:
                    session_data = json.loads(data)
                    # تمدید زمان انقضا
                    self._redis.expire(key, self._session_ttl)
            except Exception as e:
                logger.error(f"❌ Redis session get error: {e}")
        
        # اگر Redis کار نکرد، از حافظه بگیر
        if session_data is None:
            session_data = self._sessions.get(session_id)
        
        # بررسی اعتبار
        if session_data:
            # چک کردن انقضا
            expires_at = session_data.get("expires_at")
            if expires_at:
                try:
                    expire_time = datetime.fromisoformat(expires_at)
                    if datetime.now() > expire_time:
                        self._remove_session(session_id)
                        return None
                except:
                    pass
            return session_data
        
        return None
    
    def get_session(self, session_id: str) -> Optional[Dict]:
        """
        دریافت اطلاعات session بر اساس session_id
        
        پارامترها:
            session_id: شناسه session
        
        خروجی:
            دیکشنری اطلاعات session یا None
        """
        return self.validate_session(session_id)
    
    def _remove_session(self, session_id: str) -> bool:
        """حذف session"""
        try:
            if self._use_redis and self._redis:
                self._redis.delete(f"session:{session_id}")
            if session_id in self._sessions:
                del self._sessions[session_id]
            return True
        except Exception as e:
            logger.error(f"❌ Session remove error: {e}")
            return False
    
    def logout(self, session_id: str) -> bool:
        """
        خروج کاربر و حذف session
        
        پارامترها:
            session_id: شناسه session
        
        خروجی:
            موفقیت عملیات
        """
        if not session_id:
            return False
        
        # دریافت اطلاعات برای لاگ
        session_data = self.get_session(session_id)
        username = session_data.get("username") if session_data else "unknown"
        
        result = self._remove_session(session_id)
        
        if result:
            logger.info(f"✅ User logged out: {username}")
        else:
            logger.warning(f"⚠️ Logout failed for session: {session_id[:8]}...")
        
        return result
    
    def get_user_by_session(self, session_id: str) -> Optional[Dict]:
        """
        دریافت اطلاعات کاربر بر اساس session_id
        
        پارامترها:
            session_id: شناسه session
        
        خروجی:
            دیکشنری اطلاعات کاربر یا None
        """
        session_data = self.get_session(session_id)
        if not session_data:
            return None
        
        username = session_data.get("username")
        if not username:
            return None
        
        user = self._users.get(username)
        if not user:
            return None
        
        return {
            "username": username,
            "role": user.get("role", "guest"),
            "name": user.get("name", username),
            "login_time": session_data.get("login_time")
        }
    
    def get_current_user(self, session_id: str) -> Optional[Dict]:
        """دریافت اطلاعات کاربر فعلی (alias برای get_user_by_session)"""
        return self.get_user_by_session(session_id)
    
    def is_admin(self, session_id: str) -> bool:
        """بررسی ادمین بودن کاربر"""
        user = self.get_user_by_session(session_id)
        if user:
            return user.get("role") == "admin"
        return False
    
    def is_authenticated(self, session_id: str) -> bool:
        """بررسی احراز هویت کاربر"""
        return self.get_session(session_id) is not None
    
    def clean_expired_sessions(self) -> int:
        """پاک کردن session های منقضی شده"""
        count = 0
        now = datetime.now()
        
        # پاک کردن از حافظه
        expired_keys = []
        for session_id, data in self._sessions.items():
            expires_at = data.get("expires_at")
            if expires_at:
                try:
                    expire_time = datetime.fromisoformat(expires_at)
                    if now > expire_time:
                        expired_keys.append(session_id)
                except:
                    pass
        
        for key in expired_keys:
            del self._sessions[key]
            count += 1
        
        # پاک کردن از Redis (با اسکن)
        if self._use_redis and self._redis:
            try:
                cursor = 0
                while True:
                    cursor, keys = self._redis.scan(cursor, match="session:*", count=100)
                    for key in keys:
                        ttl = self._redis.ttl(key)
                        if ttl == -2:  # کلید وجود ندارد
                            continue
                        if ttl == -1:  # بدون تاریخ انقضا
                            self._redis.expire(key, self._session_ttl)
                    if cursor == 0:
                        break
            except Exception as e:
                logger.error(f"❌ Redis cleanup error: {e}")
        
        if count > 0:
            logger.info(f"🧹 Cleaned {count} expired sessions")
        
        return count


# ایجاد نمونه Singleton
auth_manager = AuthManager()


def get_auth() -> AuthManager:
    """دریافت نمونه AuthManager"""
    return auth_manager
