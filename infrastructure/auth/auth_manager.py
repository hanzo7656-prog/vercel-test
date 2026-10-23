# infrastructure/auth/auth_manager.py
# ============================================================
# مدیریت احراز هویت - نسخه ۴.۰
# ============================================================
# تغییرات نسخه ۴.۰:
#   - خواندن کاربران از دیتابیس (اولویت اول)
#   - Fallback به Environment Variables (اولویت دوم)
#   - لاگ دقیق منبع کاربران (database / environment)
#   - Retry در login اگر کاربر پیدا نشد (late DB load)
#   - پشتیبانی از AGENT_PASSWORD برای agent_debugger
# ============================================================

import os
import uuid
import logging
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from functools import wraps
from flask import request, jsonify, redirect

logger = logging.getLogger(__name__)


class AuthManager:
    """
    مدیریت احراز هویت با پشتیبانی از Session.

    نسخه ۴.۰:
        - اولویت اول: دیتابیس (جدول users)
        - اولویت دوم: Environment Variables
        - لاگ کامل منبع کاربران
        - Retry در login برای late DB load
        - استفاده از CacheManager (Dual Redis)
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

        # ============================================================
        # منبع کاربران (اولویت: دیتابیس → environment)
        # ============================================================

        self._users: Dict[str, Dict] = {}
        self._users_source: str = "unknown"

        db_users = self._load_users_from_db()
        if db_users:
            self._users = db_users
            self._users_source = "database"
            logger.info(
                f"✅ AuthManager: {len(self._users)} users loaded from DATABASE "
                f"(users={list(self._users.keys())})"
            )
        else:
            self._users = self._load_users_from_env()
            self._users_source = "environment"
            logger.warning(
                f"⚠️ AuthManager: database unavailable or empty → "
                f"using ENVIRONMENT variables "
                f"(users={list(self._users.keys())})"
            )

        # Session storage (in-memory fallback)
        self._sessions: Dict[str, Dict] = {}
        self._session_ttl = 86400  # ۲۴ ساعت

        # Redis (Dual CacheManager)
        self._redis = None
        self._use_redis = False
        self._init_redis()

        logger.info(
            f"✅ AuthManager v4.0 initialized "
            f"(redis={'enabled' if self._use_redis else 'disabled'}, "
            f"users_source={self._users_source}, "
            f"users_count={len(self._users)})"
        )

    # ============================================================
    # Load Users from DB
    # ============================================================

    def _load_users_from_db(self) -> Dict[str, Dict]:
        """
        خواندن کاربران از جدول users در دیتابیس.

        Returns:
            dict: {username: {password, role, name}} یا {} در صورت خطا
        """
        try:
            from infrastructure.database import get_primary

            db = get_primary()
            if db is None:
                logger.debug("⚠️ AuthManager: primary DB not available")
                return {}

            if not db.is_connected():
                logger.debug("⚠️ AuthManager: primary DB not connected")
                return {}

            rows = db.execute(
                """
                SELECT username, password_hash, role, email
                FROM users
                WHERE is_active = TRUE
                """
            )

            if not rows:
                logger.debug("⚠️ AuthManager: users table is empty")
                return {}

            users: Dict[str, Dict] = {}
            for row in rows:
                username = row.get("username")
                if not username:
                    continue
                users[username] = {
                    "password": row.get("password_hash", ""),
                    "role": row.get("role", "user"),
                    "name": row.get("email") or username,
                }

            logger.info(
                f"✅ AuthManager: loaded {len(users)} users from DB "
                f"(users={list(users.keys())})"
            )
            return users

        except ImportError as e:
            logger.debug(f"⚠️ AuthManager: cannot import DB module: {e}")
            return {}
        except Exception as e:
            logger.warning(f"⚠️ AuthManager: DB load error: {e}")
            return {}

    # ============================================================
    # Load Users from Environment
    # ============================================================

    def _load_users_from_env(self) -> Dict[str, Dict]:
        """
        بارگذاری کاربران از Environment Variables.

        Env vars:
            ADMIN_PASSWORD   → رمز admin (پیش‌فرض: Admin@123)
            USER_PASSWORD    → رمز user  (پیش‌فرض: User@123)
            AGENT_PASSWORD   → رمز agent_debugger (بدون پیش‌فرض)
        """
        users: Dict[str, Dict] = {
            "admin": {
                "password": os.getenv("ADMIN_PASSWORD", "Admin@123"),
                "role": "admin",
                "name": "مدیر سیستم",
            },
            "user": {
                "password": os.getenv("USER_PASSWORD", "User@123"),
                "role": "user",
                "name": "کاربر عادی",
            },
        }

        agent_password = os.getenv("AGENT_PASSWORD", "").strip()
        if agent_password:
            users["agent_debugger"] = {
                "password": agent_password,
                "role": "admin",
                "name": "ایجنت دیباگ",
            }
            logger.info(
                "✅ AuthManager: agent_debugger loaded from ENVIRONMENT"
            )
        else:
            logger.debug(
                "⚠️ AuthManager: AGENT_PASSWORD not set → "
                "agent_debugger disabled in environment"
            )

        return users

    # ============================================================
    # Redis Init
    # ============================================================

    def _init_redis(self) -> None:
        """اتصال به CacheManager (Dual Redis)"""
        try:
            from infrastructure.api.cache_manager import cache_manager

            if cache_manager is None:
                logger.warning("⚠️ AuthManager: cache_manager is None")
                return

            if not cache_manager.is_connected():
                logger.warning("⚠️ AuthManager: cache_manager not connected")
                return

            # تست
            cache_manager.set("auth:ping", {"ok": True}, ttl=5)
            val = cache_manager.get("auth:ping")
            cache_manager.delete("auth:ping")

            if not isinstance(val, dict) or val.get("ok") is not True:
                logger.warning(
                    f"⚠️ AuthManager: Redis test failed (got {val!r})"
                )
                return

            self._redis = cache_manager
            self._use_redis = True

            try:
                stats = cache_manager.get_stats()
                active = stats.get("active_redis", "unknown")
                logger.info(
                    f"✅ AuthManager: Session storage via CacheManager "
                    f"(active_redis={active})"
                )
            except Exception:
                logger.info("✅ AuthManager: Session storage enabled")

        except ImportError as e:
            logger.warning(f"⚠️ AuthManager: cannot import cache_manager: {e}")
        except Exception as e:
            logger.warning(f"⚠️ AuthManager: Redis init error: {e}")

    # ============================================================
    # Session Storage Helpers
    # ============================================================

    def _redis_set_session(self, session_id: str, session_data: Dict) -> bool:
        if not self._use_redis or self._redis is None:
            return False
        try:
            self._redis.set(
                f"session:{session_id}", session_data, ttl=self._session_ttl
            )
            return True
        except Exception as e:
            logger.error(f"❌ Redis session save error: {e}")
            return False

    def _redis_get_session(self, session_id: str) -> Optional[Dict]:
        if not self._use_redis or self._redis is None:
            return None
        try:
            key = f"session:{session_id}"
            data = self._redis.get(key)
            if data:
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
        if not self._use_redis or self._redis is None:
            return False
        try:
            self._redis.delete(f"session:{session_id}")
            return True
        except Exception as e:
            logger.error(f"❌ Redis session delete error: {e}")
            return False

    # ============================================================
    # Login / Logout
    # ============================================================

    def login(self, username: str, password: str) -> Dict[str, Any]:
        """
        ورود کاربر.

        ترتیب جستجو:
            ۱. users (که از دیتابیس یا environment پر شده)
            ۲. اگر پیدا نشد → یک بار دیگر DB را چک کن (late load)
            ۳. اگر باز هم پیدا نشد → خطا

        لاگ دقیق منبع.
        """
        logger.info(f"🔐 Login attempt: username={username!r}")

        if not username or not password:
            return {
                "success": False,
                "error": "Username and password are required",
            }

        # ---------- ۱. جستجو در users فعلی ----------
        user = self._users.get(username)
        source_used = self._users_source if user else None

        # ---------- ۲. Late DB load اگر پیدا نشد ----------
        if not user:
            logger.debug(
                f"🔄 User {username!r} not found in '{self._users_source}'. "
                f"Retrying DB lookup..."
            )
            db_users = self._load_users_from_db()
            if db_users:
                # merge به users فعلی (بدون از دست دادن env users)
                for uname, udata in db_users.items():
                    if uname not in self._users:
                        self._users[uname] = udata

                if username in db_users:
                    user = db_users[username]
                    source_used = "database"
                    if self._users_source != "database":
                        logger.info(
                            f"✅ AuthManager: switched users_source → 'database' "
                            f"(late load)"
                        )
                        self._users_source = "database"

        # ---------- ۳. بررسی نهایی ----------
        if not user:
            logger.warning(
                f"⚠️ Login failed: unknown username {username!r} "
                f"(users_source={self._users_source}, "
                f"available_users={list(self._users.keys())})"
            )
            return {"success": False, "error": "Invalid username or password"}

        if user.get("password") != password:
            logger.warning(
                f"⚠️ Login failed: wrong password for {username!r} "
                f"(source={source_used})"
            )
            return {"success": False, "error": "Invalid username or password"}

        # ---------- ۴. موفق ----------
        session_id = self._create_session(username, user)
        logger.info(
            f"✅ Login OK: {username!r} "
            f"(role={user.get('role')}, "
            f"source={source_used}, "
            f"session={session_id[:8]}...)"
        )

        return {
            "success": True,
            "session_id": session_id,
            "username": username,
            "role": user.get("role", "guest"),
            "name": user.get("name", username),
        }

    def logout(self, session_id: str) -> bool:
        if not session_id:
            return False

        session_data = self.get_session(session_id)
        username = session_data.get("username") if session_data else "unknown"

        result = self._remove_session(session_id)

        if result:
            logger.info(
                f"✅ Logout OK: {username!r} (session={session_id[:8]}...)"
            )
        else:
            logger.warning(
                f"⚠️ Logout failed: session={session_id[:8]}..."
            )
        return result

    # ============================================================
    # Session CRUD
    # ============================================================

    def _create_session(self, username: str, user: Dict) -> str:
        session_id = str(uuid.uuid4())
        session_data = {
            "username": username,
            "role": user.get("role", "guest"),
            "name": user.get("name", username),
            "login_time": datetime.now().isoformat(),
            "expires_at": (
                datetime.now() + timedelta(seconds=self._session_ttl)
            ).isoformat(),
        }

        if self._redis_set_session(session_id, session_data):
            return session_id

        self._sessions[session_id] = session_data
        return session_id

    def validate_session(self, session_id: str) -> Optional[Dict]:
        if not session_id:
            return None

        session_data = self._redis_get_session(session_id)
        if session_data is None:
            session_data = self._sessions.get(session_id)

        if session_data:
            expires_at = session_data.get("expires_at")
            if expires_at:
                try:
                    expire_time = datetime.fromisoformat(expires_at)
                    if datetime.now() > expire_time:
                        self._remove_session(session_id)
                        return None
                except Exception:
                    pass
            return session_data

        return None

    def get_session(self, session_id: str) -> Optional[Dict]:
        return self.validate_session(session_id)

    def _remove_session(self, session_id: str) -> bool:
        try:
            self._redis_delete_session(session_id)
            if session_id in self._sessions:
                del self._sessions[session_id]
            return True
        except Exception as e:
            logger.error(f"❌ Session remove error: {e}")
            return False

    def get_user_by_session(self, session_id: str) -> Optional[Dict]:
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
            "login_time": session_data.get("login_time"),
        }

    # ============================================================
    # Cleanup
    # ============================================================

    def clean_expired_sessions(self) -> int:
        count = 0
        now = datetime.now()

        expired_keys = []
        for session_id, data in self._sessions.items():
            expires_at = data.get("expires_at")
            if expires_at:
                try:
                    if now > datetime.fromisoformat(expires_at):
                        expired_keys.append(session_id)
                except Exception:
                    pass

        for key in expired_keys:
            del self._sessions[key]
            count += 1

        if self._use_redis and self._redis is not None:
            try:
                keys = self._redis.scan_keys("session:*", count=100)
                for key in keys:
                    try:
                        ttl = self._redis.ttl(key)
                        if ttl == -1:
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
        """اطلاعات storage برای دیباگ."""
        info: Dict[str, Any] = {
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
            # 🆕 اطلاعات منبع کاربران
            "users_source": self._users_source,
            "users_count": len(self._users),
            "users": list(self._users.keys()),
        }

        try:
            from infrastructure.api.cache_manager import cache_manager
            cache_stats = cache_manager.get_stats()
            info["cache"] = {
                "active_redis": cache_stats.get("active_redis"),
                "failover_count": cache_stats.get("failover_count"),
                "command_usage_percent": cache_stats.get("command_usage_percent"),
                "hits": cache_stats.get("hits"),
                "misses": cache_stats.get("misses"),
            }
        except Exception as e:
            info["cache_error"] = str(e)

        return info

    # ============================================================
    # Reload Users (برای دیباگ)
    # ============================================================

    def reload_users(self) -> Dict[str, Any]:
        """
        بارگذاری مجدد کاربران از دیتابیس.

        استفاده در endpoint دیباگ:
            POST /api/debug/auth/reload-users
        """
        old_source = self._users_source
        old_count = len(self._users)

        db_users = self._load_users_from_db()

        if db_users:
            self._users = db_users
            self._users_source = "database"
            logger.info(
                f"🔄 AuthManager: users reloaded from DATABASE "
                f"({len(db_users)} users)"
            )
        else:
            # اگر DB خالی بود، env را نگه دار
            env_users = self._load_users_from_env()
            if env_users:
                self._users = env_users
                self._users_source = "environment"
                logger.warning(
                    f"🔄 AuthManager: DB empty → keeping ENVIRONMENT "
                    f"({len(env_users)} users)"
                )

        return {
            "success": True,
            "old_source": old_source,
            "old_count": old_count,
            "new_source": self._users_source,
            "new_count": len(self._users),
            "users": list(self._users.keys()),
        }


# ============================================================
# توابع کمکی و دکوراتور
# ============================================================

auth_manager = AuthManager()


def get_auth() -> AuthManager:
    return auth_manager


def require_auth(role: Optional[str] = None):
    """دکوراتور بررسی احراز هویت و نقش."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            session_id = request.cookies.get('session_id')

            is_api_request = (
                request.path.startswith('/api/') or
                'application/json' in (request.headers.get('Accept') or '') or
                'application/json' in (request.headers.get('Content-Type') or '')
            )

            if not session_id:
                logger.debug(
                    f"🔒 require_auth: no session ({request.method} {request.path})"
                )
                if is_api_request:
                    return jsonify({
                        'success': False,
                        'error': 'Authentication required',
                        'redirect': '/login',
                    }), 401
                return redirect('/login')

            auth = get_auth()
            session_data = auth.get_session(session_id)

            if not session_data:
                logger.debug(
                    f"🔒 require_auth: invalid session ({request.method} {request.path})"
                )
                if is_api_request:
                    return jsonify({
                        'success': False,
                        'error': 'Invalid or expired session',
                        'redirect': '/login',
                    }), 401
                return redirect('/login')

            if role:
                user_role = session_data.get('role', 'guest')
                if user_role != role and user_role != 'admin':
                    if is_api_request:
                        return jsonify({
                            'success': False,
                            'error': f'Role {role} required',
                        }), 403
                    return redirect('/403')

            request.user = {
                'username': session_data.get('username'),
                'role': session_data.get('role', 'guest'),
                'session_id': session_id,
            }

            return f(*args, **kwargs)
        return decorated_function
    return decorator
