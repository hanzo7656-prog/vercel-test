# infrastructure/auth/__init__.py
# ============================================================
# Authentication - احراز هویت
# ============================================================

from infrastructure.auth.auth_manager import auth_manager, AuthManager, get_auth

__all__ = [
    'auth_manager',
    'AuthManager',
    'get_auth'
]
