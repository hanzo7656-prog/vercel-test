# infrastructure/auth/auth_manager.py
# ============================================================
# سیستم احراز هویت و مدیریت کاربران - نسخه ۳.۰ (انتقال به Infrastructure)
# ============================================================

import os
import json
import secrets
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from pathlib import Path
from functools import wraps
from flask import request, redirect

logger = logging.getLogger(__name__)


class AuthManager:
    """مدیریت احراز هویت و کاربران"""
    
    _instance = None
    _users: Dict[str, Any] = {}
    _sessions: Dict[str, Dict] = {}
    _config: Dict[str, Any] = {}
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self) -> None:
        if not hasattr(self, '_initialized'):
            self._initialized = True
            self._load_users()
    
    def _load_users(self) -> None:
        """بارگذاری کاربران از فایل"""
        users_path: Path = Path("config/users.json")
        
        if not users_path.exists():
            logger.warning("⚠️ config/users.json یافت نشد، استفاده از کاربران پیش‌فرض")
            self._create_default_users()
            return
        
        try:
            with open(users_path, 'r', encoding='utf-8') as f:
                data: Dict[str, Any] = json.load(f)
                self._users = data.get("users", {})
                self._config = data.get("settings", {})
            logger.info(f"✅ {len(self._users)} کاربر بارگذاری شد")
        except Exception as e:
            logger.error(f"❌ خطا در بارگذاری کاربران: {e}")
            self._create_default_users()
    
    def _create_default_users(self) -> None:
        """ایجاد کاربران پیش‌فرض"""
        self._users = {
            "admin": {
                "username": "admin",
                "password": "Admin@123",
                "role": "admin",
                "email": "admin@example.com",
                "active": True,
                "recovery_email": "admin@example.com"
            },
            "guest1": {
                "username": "guest1",
                "password": "",
                "role": "guest",
                "email": "",
                "active": False,
                "recovery_email": ""
            }
        }
        self._save_users()
    
    def _save_users(self) -> None:
        """ذخیره کاربران در فایل"""
        try:
            users_path: Path = Path("config/users.json")
            users_path.parent.mkdir(parents=True, exist_ok=True)
            
            data: Dict[str, Any] = {
                "users": self._users,
                "settings": self._config
            }
            
            with open(users_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            logger.info("✅ کاربران ذخیره شدند")
        except Exception as e:
            logger.error(f"❌ خطا در ذخیره کاربران: {e}")
    
    def login(self, username: str, password: str) -> Dict[str, Any]:
        """ورود کاربر"""
        user = self._users.get(username)
        
        if not user:
            return {"success": False, "error": "نام کاربری یا رمز عبور اشتباه است"}
        
        if not user.get("active", True):
            return {"success": False, "error": "حساب کاربری غیرفعال است"}
        
        if user.get("password", "") != password:
            return {"success": False, "error": "نام کاربری یا رمز عبور اشتباه است"}
        
        session_id: str = secrets.token_hex(16)
        timeout: int = self._config.get("session_timeout", 86400)
        
        self._sessions[session_id] = {
            "username": username,
            "role": user.get("role", "guest"),
            "created_at": datetime.now().isoformat(),
            "expires_at": (datetime.now() + timedelta(seconds=timeout)).isoformat()
        }
        
        return {
            "success": True,
            "session_id": session_id,
            "username": username,
            "role": user.get("role", "guest"),
            "message": "✅ ورود موفق"
        }
    
    def logout(self, session_id: str) -> bool:
        """خروج از حساب"""
        if session_id in self._sessions:
            del self._sessions[session_id]
            return True
        return False
    
    def verify_session(self, session_id: str) -> Optional[Dict]:
        """بررسی اعتبار نشست"""
        session = self._sessions.get(session_id)
        if not session:
            return None
        
        expires_at = datetime.fromisoformat(session["expires_at"])
        if datetime.now() > expires_at:
            del self._sessions[session_id]
            return None
        
        if "role" not in session:
            user = self._users.get(session["username"])
            if user:
                session["role"] = user.get("role", "guest")
        
        return session
    
    def get_user(self, username: str) -> Optional[Dict]:
        """دریافت اطلاعات کاربر"""
        user = self._users.get(username)
        if user:
            return user.copy()
        return None
    
    def get_all_users(self) -> List[Dict]:
        """دریافت همه کاربران (بدون رمز)"""
        users: List[Dict] = []
        for username, user in self._users.items():
            user_copy = user.copy()
            user_copy.pop("password", None)
            user_copy["username"] = username
            users.append(user_copy)
        return users
    
    def update_user(self, username: str, data: Dict) -> bool:
        """به‌روزرسانی کاربر"""
        if username not in self._users:
            return False
        
        for key, value in data.items():
            if key != "username":
                self._users[username][key] = value
        
        self._save_users()
        return True
    
    def add_user(self, username: str, password: str, role: str = "guest", email: str = "") -> bool:
        """افزودن کاربر جدید"""
        if username in self._users:
            return False
        
        self._users[username] = {
            "username": username,
            "password": password,
            "role": role,
            "email": email,
            "active": True,
            "recovery_email": email
        }
        self._save_users()
        return True
    
    def delete_user(self, username: str) -> bool:
        """حذف کاربر (به جز ادمین)"""
        if username == "admin":
            return False
        if username in self._users:
            del self._users[username]
            self._save_users()
            return True
        return False


# نمونه Singleton
auth_manager: AuthManager = AuthManager()


def get_auth() -> AuthManager:
    """دریافت نمونه AuthManager"""
    return auth_manager


def require_auth(role: str = None):
    """دکوراتور برای محافظت از صفحات"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            session_id = request.cookies.get('session_id')
            if not session_id:
                return redirect('/login')
            
            auth_manager_instance = get_auth()
            session = auth_manager_instance.verify_session(session_id)
            if not session:
                return redirect('/login')
            
            if role and session.get("role") != role and session.get("role") != "admin":
                return redirect('/403')
            
            return func(*args, **kwargs)
        return wrapper
    return decorator


def get_current_user_from_request():
    """دریافت کاربر فعلی از درخواست"""
    session_id = request.cookies.get('session_id')
    if not session_id:
        return None
    return get_auth().get_current_user(session_id)
