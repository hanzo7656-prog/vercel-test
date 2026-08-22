# auth_manager.py
# ============================================================
# سیستم احراز هویت و مدیریت کاربران
# ============================================================

import os
import json
import hashlib
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
    _config = {}
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not hasattr(self, '_initialized'):
            self._initialized = True
            self._load_users()
    
    def _load_users(self):
        """بارگذاری کاربران از فایل"""
        users_path = Path("config/users.json")
        
        if not users_path.exists():
            logger.warning("⚠️ config/users.json یافت نشد، استفاده از کاربران پیش‌فرض")
            self._create_default_users()
            return
        
        try:
            with open(users_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self._users = data.get("users", {})
                self._config = data.get("settings", {})
            logger.info(f"✅ {len(self._users)} کاربر بارگذاری شد")
        except Exception as e:
            logger.error(f"❌ خطا در بارگذاری کاربران: {e}")
            self._create_default_users()
    
    def _create_default_users(self):
        """ایجاد کاربران پیش‌فرض"""
        self._users = {
            "admin": {
                "username": "admin",
                "password": self._hash_password("hash_8c6976e5b5410415bde908bd4dee15dfb167a9c873fc4bb8a81f6f2ab448a918"),
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
            },
            "guest2": {
                "username": "guest2",
                "password": "",
                "role": "guest",
                "email": "",
                "active": False,
                "recovery_email": ""
            },
            "guest3": {
                "username": "guest3",
                "password": "",
                "role": "guest",
                "email": "",
                "active": False,
                "recovery_email": ""
            }
        }
        self._save_users()
    
    def _hash_password(self, password: str) -> str:
        """هش کردن رمز عبور"""
        if not password:
            return ""
        return hashlib.sha256(password.encode()).hexdigest()
    
    def _save_users(self):
        """ذخیره کاربران در فایل"""
        try:
            users_path = Path("config/users.json")
            users_path.parent.mkdir(parents=True, exist_ok=True)
            
            users_data = {}
            for username, user in self._users.items():
                users_data[username] = user.copy()
                if user.get("password") and not user["password"].startswith("hash_"):
                    users_data[username]["password"] = "hash_" + self._hash_password(user["password"])
            
            data = {
                "users": users_data,
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
        
        stored_password = user.get("password", "")
        if stored_password.startswith("hash_"):
            stored_password = stored_password[5:]
        
        if self._hash_password(password) != stored_password:
            return {"success": False, "error": "نام کاربری یا رمز عبور اشتباه است"}
        
        session_id = secrets.token_hex(16)
        self._sessions[session_id] = {
            "username": username,
            "role": user.get("role", "guest"),
            "created_at": datetime.now().isoformat(),
            "expires_at": (datetime.now() + timedelta(seconds=self._config.get("session_timeout", 86400))).isoformat()
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
        
        return session
    
    def get_user(self, username: str) -> Optional[Dict]:
        """دریافت اطلاعات کاربر"""
        user = self._users.get(username)
        if user:
            user_copy = user.copy()
            user_copy.pop("password", None)
            return user_copy
        return None
    
    def get_all_users(self) -> List[Dict]:
        """دریافت همه کاربران (بدون رمز)"""
        users = []
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
            if key == "password" and value:
                self._users[username]["password"] = "hash_" + self._hash_password(value)
            elif key != "username":
                self._users[username][key] = value
        
        self._save_users()
        return True
    
    def add_user(self, username: str, password: str, role: str = "guest", email: str = "") -> bool:
        """افزودن کاربر جدید"""
        if username in self._users:
            return False
        
        self._users[username] = {
            "username": username,
            "password": "hash_" + self._hash_password(password) if password else "",
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
    
    def get_user_by_email(self, email: str) -> Optional[str]:
        """پیدا کردن کاربر با ایمیل"""
        for username, user in self._users.items():
            if user.get("recovery_email") == email and user.get("active", True):
                return username
        return None
    
    def generate_recovery_code(self, email: str) -> Optional[str]:
        """تولید کد بازیابی"""
        import random
        import string
        
        username = self.get_user_by_email(email)
        if not username:
            return None
        
        code = ''.join(random.choices(string.digits, k=6))
        
        self._sessions[f"recovery_{email}"] = {
            "code": code,
            "username": username,
            "created_at": datetime.now().isoformat(),
            "expires_at": (datetime.now() + timedelta(minutes=5)).isoformat()
        }
        
        return code
    
    def verify_recovery_code(self, email: str, code: str) -> Optional[str]:
        """تایید کد بازیابی"""
        session = self._sessions.get(f"recovery_{email}")
        if not session:
            return None
        
        expires_at = datetime.fromisoformat(session["expires_at"])
        if datetime.now() > expires_at:
            del self._sessions[f"recovery_{email}"]
            return None
        
        if session.get("code") != code:
            return None
        
        del self._sessions[f"recovery_{email}"]
        return session.get("username")


# ============================================================
# نمونه Singleton
# ============================================================

auth = AuthManager()


def get_auth() -> AuthManager:
    """دریافت نمونه AuthManager"""
    return auth


# ============================================================
# دکوراتور محافظت از صفحات
# ============================================================

def require_auth(role: str = None):
    """دکوراتور برای محافظت از صفحات"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            session_id = request.cookies.get('session_id')
            if not session_id:
                return redirect('/login')
            
            auth = get_auth()
            session = auth.verify_session(session_id)
            if not session:
                return redirect('/login')
            
            if role and session.get("role") != role and session.get("role") != "admin":
                return redirect('/403')
            
            return func(*args, **kwargs)
        return wrapper
    return decorator
