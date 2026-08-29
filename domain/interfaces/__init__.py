# domain/interfaces/__init__.py
# ============================================================
# Interfaces - رابط‌های لایه دامنه
# ============================================================

from domain.interfaces.repository import Repository
from domain.interfaces.api_client import APIClient

__all__ = [
    'Repository',
    'APIClient'
]
