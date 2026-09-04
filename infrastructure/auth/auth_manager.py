# infrastructure/auth/auth_manager.py
# ============================================================
# مدیریت احراز هویت - نسخه ۳.۱ (با require_auth)
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
        
        # ذخیره session ها
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
        
        logger.info("✅ AuthManager v3.1 initialized")
    
    def login(self, username: str, password: str) -> Dict[str, Any]:
        """ورود کاربر و ایجاد session"""
        if not username or not password:
            return {"success": False, "error": "Username and password are required"}
        
        user = self._users.get(username)
        if not user:
            logger.warning(f"⚠️ Login attempt with unknown username: {username}")
            return {"success": False, "error": "Invalid username or password"}
        
        if user.get("password") != password:
            logger.warning(f"⚠️ Login attempt with wrong password for: {username}")
            return {"success": False, "error": "Invalid username or password"}
        
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
        
        if self._use_redis and self._redis:
            try:
                key = f"session:{session_id}"
                self._redis.setex(key, self._session_ttl, json.dumps(session_data))
                logger.debug(f"✅ Session stored in Redis: {session_id[:8]}...")
            except Exception as e:
                logger.error(f"❌ Redis session save error: {e}")
                self._sessions[session_id] = session_data
        else:
            self._sessions[session_id] = session_data
            logger.debug(f"✅ Session stored in memory: {session_id[:8]}...")
        
        return session_id
    
    def validate_session(self, session_id: str) -> Optional[Dict]:
        """بررسی اعتبار session"""
        if not session_id:
            return None
        
        session_data = None
        
        if self._use_redis and self._redis:
            try:
                key = f"session:{session_id}"
                data = self._redis.get(key)
                if data:
                    session_data = json.loads(data)
                    self._redis.expire(key, self._session_ttl)
            except Exception as e:
                logger.error(f"❌ Redis session get error: {e}")
        
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
                except:
                    pass
            return session_data
        
        return None
    
    def get_session(self, session_id: str) -> Optional[Dict]:
        """دریافت اطلاعات session"""
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
        """خروج کاربر"""
        if not session_id:
            return False
        
        session_data = self.get_session(session_id)
        username = session_data.get("username") if session_data else "unknown"
        result = self._remove_session(session_id)
        
        if result:
            logger.info(f"✅ User logged out: {username}")
        else:
            logger.warning(f"⚠️ Logout failed for session: {session_id[:8]}...")
        
        return result
    
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
    
    def clean_expired_sessions(self) -> int:
        """پاک کردن session های منقضی شده"""
        count = 0
        now = datetime.now()
        
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
        
        if self._use_redis and self._redis:
            try:
                cursor = 0
                while True:
                    cursor, keys = self._redis.scan(cursor, match="session:*", count=100)
                    for key in keys:
                        ttl = self._redis.ttl(key)
                        if ttl == -2:
                            continue
                        if ttl == -1:
                            self._redis.expire(key, self._session_ttl)
                    if cursor == 0:
                        break
            except Exception as e:
                logger.error(f"❌ Redis cleanup error: {e}")
        
        if count > 0:
            logger.info(f"🧹 Cleaned {count} expired sessions")
        
        return count


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
        role: نقش مورد نیاز (admin, user, یا None برای هر کاربر احراز هویت شده)
    
    کاربرد:
        @require_auth()
        def protected_endpoint():
            return jsonify({"message": "Authenticated"})
        
        @require_auth('admin')
        def admin_endpoint():
            return jsonify({"message": "Admin only"})
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            session_id = request.cookies.get('session_id')
            
            if not session_id:
                if request.headers.get('Content-Type') == 'application/json' or request.headers.get('Accept') == 'application/json':
                    return jsonify({
                        'success': False,
                        'error': 'Authentication required',
                        'redirect': '/login'
                    }), 401
                return redirect(url_for('web.login_page'))
            
            auth = get_auth()
            session_data = auth.get_session(session_id)
            
            if not session_data:
                if request.headers.get('Content-Type') == 'application/json' or request.headers.get('Accept') == 'application/json':
                    return jsonify({
                        'success': False,
                        'error': 'Invalid or expired session',
                        'redirect': '/login'
                    }), 401
                return redirect(url_for('web.login_page'))
            
            if role:
                user_role = session_data.get('role', 'guest')
                if user_role != role and user_role != 'admin':
                    if request.headers.get('Content-Type') == 'application/json' or request.headers.get('Accept') == 'application/json':
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
