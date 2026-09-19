# infrastructure/auth/auth_manager.py
# ============================================================
# مدیریت احراز هویت - نسخه ۳.۲
# 🆕 استفاده از RedisManager به جای اتصال مستقیم به localhost
# ============================================================

import os
import json
import uuid
import logging
import time
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from functools import wraps
from flask import request, jsonify, redirect, url_for

logger = logging.getLogger(__name__)


class AuthManager:
    """
    مدیریت احراز هویت با پشتیبانی از Session

    نسخه ۳.۲:
        - استفاده از RedisManager (get_cache) به جای اتصال مستقیم
        - لاگ کامل برای تشخیص
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

        # اطلاعات کاربران
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

        # ذخیره session ها (in-memory fallback)
        self._sessions: Dict[str, Dict] = {}
        self._session_ttl = 86400  # ۲۴ ساعت

        # 🆕 اتصال به RedisManager
        self._redis = None
        self._use_redis = False
        self._init_redis()

        logger.info(
            f"✅ AuthManager v3.2 initialized "
            f"(redis={'enabled' if self._use_redis else 'disabled'})"
        )

    # ============================================================
    # Redis Init
    # ============================================================

    def _init_redis(self) -> None:
        """
        🆕 اتصال به Redis از طریق RedisManager

        چرا: قبلاً از redis.Redis(host='localhost') استفاده می‌شد که
        در Render به localhost وصل نمی‌شد. الان از همان RedisManager
        استفاده می‌کنیم که در /api/health سالم است.
        """
        try:
            logger.info("🔗 AuthManager: connecting to Redis via RedisManager...")
            from infrastructure.database import get_cache
            cache = get_cache()

            if cache is None:
                logger.warning("⚠️ AuthManager: get_cache() returned None")
                logger.info("📝 Using in-memory session storage")
                return

            if not cache.is_connected():
                logger.warning("⚠️ AuthManager: RedisManager not connected")
                logger.info("📝 Using in-memory session storage")
                return

            # تست واقعی
            try:
                cache.set("auth:ping", "1", ttl=5)
                val = cache.get("auth:ping")
                cache.delete("auth:ping")
                if val != "1":
                    logger.warning("⚠️ AuthManager: Redis test write/read failed")
                    return
            except Exception as e:
                logger.warning(f"⚠️ AuthManager: Redis test failed: {e}")
                return

            self._redis = cache
            self._use_redis = True
            logger.info("✅ AuthManager: Redis session storage enabled (via RedisManager)")

        except ImportError as e:
            logger.warning(f"⚠️ AuthManager: cannot import get_cache: {e}")
            logger.info("📝 Using in-memory session storage")
        except Exception as e:
            logger.warning(f"⚠️ AuthManager: Redis init error: {e}")
            logger.info("📝 Using in-memory session storage")

    # ============================================================
    # Session Storage Helpers
    # ============================================================

    def _redis_set_session(self, session_id: str, session_data: Dict) -> bool:
        """ذخیره session در Redis"""
        if not self._use_redis or self._redis is None:
            return False
        try:
            key = f"session:{session_id}"
            self._redis.set(key, session_data, ttl=self._session_ttl)
            logger.debug(f"✅ Session stored in Redis: {session_id[:8]}...")
            return True
        except Exception as e:
            logger.error(f"❌ Redis session save error: {e}")
            return False

    def _redis_get_session(self, session_id: str) -> Optional[Dict]:
        """دریافت session از Redis"""
        if not self._use_redis or self._redis is None:
            return None
        try:
            key = f"session:{session_id}"
            data = self._redis.get(key)
            if data:
                # تمدید TTL
                try:
                    self._redis.expire(key, self._session_ttl)
                except Exception:
                    pass
                return data
            return None
        except Exception as e:
            logger.error(f"❌ Redis session get error: {e}")
            return None

    def _redis_delete_session(self, session_id: str) -> bool:
        """حذف session از Redis"""
        if not self._use_redis or self._redis is None:
            return False
        try:
            key = f"session:{session_id}"
            self._redis.delete(key)
            return True
        except Exception as e:
            logger.error(f"❌ Redis session delete error: {e}")
            return False

    # ============================================================
    # Login / Logout
    # ============================================================

    def login(self, username: str, password: str) -> Dict[str, Any]:
        """ورود کاربر و ایجاد session"""
        logger.info(f"🔐 Login attempt: username={username!r}")

        if not username or not password:
            logger.warning("⚠️ Login: empty username or password")
            return {"success": False, "error": "Username and password are required"}

        user = self._users.get(username)
        if not user:
            logger.warning(f"⚠️ Login: unknown username {username!r}")
            return {"success": False, "error": "Invalid username or password"}

        if user.get("password") != password:
            logger.warning(f"⚠️ Login: wrong password for {username!r}")
            return {"success": False, "error": "Invalid username or password"}

        session_id = self._create_session(username, user)
        logger.info(
            f"✅ Login OK: {username!r} "
            f"(role={user.get('role')}, session={session_id[:8]}...)"
        )

        return {
            "success": True,
            "session_id": session_id,
            "username": username,
            "role": user.get("role", "guest"),
            "name": user.get("name", username)
        }

    def logout(self, session_id: str) -> bool:
        """خروج کاربر"""
        if not session_id:
            logger.warning("⚠️ Logout: empty session_id")
            return False

        session_data = self.get_session(session_id)
        username = session_data.get("username") if session_data else "unknown"

        result = self._remove_session(session_id)

        if result:
            logger.info(f"✅ Logout OK: {username!r} (session={session_id[:8]}...)")
        else:
            logger.warning(f"⚠️ Logout failed: session={session_id[:8]}...")

        return result

    # ============================================================
    # Session CRUD
    # ============================================================

    def _create_session(self, username: str, user: Dict) -> str:
        """ایجاد session جدید"""
        session_id = str(uuid.uuid4())
        session_data = {
            "username": username,
            "role": user.get("role", "guest"),
            "name": user.get("name", username),
            "login_time": datetime.now().isoformat(),
            "expires_at": (
                datetime.now() + timedelta(seconds=self._session_ttl)
            ).isoformat()
        }

        # ۱. تلاش Redis
        if self._redis_set_session(session_id, session_data):
            return session_id

        # ۲. Fallback به حافظه
        self._sessions[session_id] = session_data
        logger.debug(f"📝 Session stored in memory: {session_id[:8]}...")
        return session_id

    def validate_session(self, session_id: str) -> Optional[Dict]:
        """بررسی اعتبار session"""
        if not session_id:
            return None

        session_data = None

        # ۱. تلاش Redis
        session_data = self._redis_get_session(session_id)

        # ۲. Fallback به حافظه
        if session_data is None:
            session_data = self._sessions.get(session_id)

        if session_data:
            # چک انقضا (برای امنیت بیشتر)
            expires_at = session_data.get("expires_at")
            if expires_at:
                try:
                    expire_time = datetime.fromisoformat(expires_at)
                    if datetime.now() > expire_time:
                        logger.debug(
                            f"⏰ Session expired: {session_id[:8]}..."
                        )
                        self._remove_session(session_id)
                        return None
                except Exception:
                    pass
            return session_data

        return None

    def get_session(self, session_id: str) -> Optional[Dict]:
        """دریافت اطلاعات session"""
        return self.validate_session(session_id)

    def _remove_session(self, session_id: str) -> bool:
        """حذف session"""
        try:
            # از هر دو حذف کن (برای اطمینان)
            self._redis_delete_session(session_id)
            if session_id in self._sessions:
                del self._sessions[session_id]
            return True
        except Exception as e:
            logger.error(f"❌ Session remove error: {e}")
            return False

    def get_user_by_session(self, session_id: str) -> Optional[Dict]:
        """دریافت اطلاعات کاربر بر اساس session_id"""
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

    # ============================================================
    # Cleanup
    # ============================================================

    def clean_expired_sessions(self) -> int:
        """پاک کردن session های منقضی شده"""
        count = 0
        now = datetime.now()

        # ۱. حافظه
        expired_keys = []
        for session_id, data in self._sessions.items():
            expires_at = data.get("expires_at")
            if expires_at:
                try:
                    expire_time = datetime.fromisoformat(expires_at)
                    if now > expire_time:
                        expired_keys.append(session_id)
                except Exception:
                    pass

        for key in expired_keys:
            del self._sessions[key]
            count += 1

        # ۲. Redis
        if self._use_redis and self._redis is not None:
            try:
                keys = self._redis.scan_keys("session:*", count=100)
                for key in keys:
                    try:
                        ttl = self._redis.ttl(key)
                        if ttl == -1:
                            # بدون TTL → TTL بگذار
                            self._redis.expire(key, self._session_ttl)
                    except Exception:
                        pass
            except Exception as e:
                logger.error(f"❌ Redis cleanup error: {e}")

        if count > 0:
            logger.info(f"🧹 Cleaned {count} expired sessions from memory")

        return count

    # ============================================================
    # Diagnostics
    # ============================================================

    def get_storage_info(self) -> Dict[str, Any]:
        """
        🆕 اطلاعات storage برای دیباگ

        استفاده: /api/auth/storage-info
        """
        return {
            "use_redis": self._use_redis,
            "redis_available": self._redis is not None,
            "redis_connected": (
                self._redis.is_connected()
                if self._redis is not None
                else False
            ),
            "memory_sessions_count": len(self._sessions),
            "session_ttl": self._session_ttl,
            "storage_type": "redis" if self._use_redis else "memory",
        }


# ============================================================
# توابع کمکی و دکوراتور
# ============================================================

auth_manager = AuthManager()


def get_auth() -> AuthManager:
    """دریافت نمونه AuthManager"""
    return auth_manager


def require_auth(role: str = None):
    """
    دکوراتور برای بررسی احراز هویت و نقش کاربر

    پارامترها:
        role: نقش مورد نیاز (admin, user, یا None)
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            session_id = request.cookies.get('session_id')

            if not session_id:
                logger.debug(
                    f"🔒 require_auth: no session_id "
                    f"({request.method} {request.path})"
                )
                if (
                    request.headers.get('Content-Type') == 'application/json'
                    or request.headers.get('Accept') == 'application/json'
                ):
                    return jsonify({
                        'success': False,
                        'error': 'Authentication required',
                        'redirect': '/login'
                    }), 401
                return redirect(url_for('web.login_page'))

            auth = get_auth()
            session_data = auth.get_session(session_id)

            if not session_data:
                logger.debug(
                    f"🔒 require_auth: invalid session "
                    f"({request.method} {request.path})"
                )
                if (
                    request.headers.get('Content-Type') == 'application/json'
                    or request.headers.get('Accept') == 'application/json'
                ):
                    return jsonify({
                        'success': False,
                        'error': 'Invalid or expired session',
                        'redirect': '/login'
                    }), 401
                return redirect(url_for('web.login_page'))

            if role:
                user_role = session_data.get('role', 'guest')
                if user_role != role and user_role != 'admin':
                    logger.debug(
                        f"🔒 require_auth: role mismatch "
                        f"(need={role}, have={user_role}) "
                        f"({request.method} {request.path})"
                    )
                    if (
                        request.headers.get('Content-Type') == 'application/json'
                        or request.headers.get('Accept') == 'application/json'
                    ):
                        return jsonify({
                            'success': False,
                            'error': f'Role {role} required'
                        }), 403
                    return redirect(url_for('web.page_403'))

            request.user = {
                'username': session_data.get('username'),
                'role': session_data.get('role', 'guest'),
                'session_id': session_id
            }

            return f(*args, **kwargs)
        return decorated_function
    return decorator
