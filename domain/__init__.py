# domain/__init__.py
# ============================================================
# لایه دامنه (Domain Layer)
# شامل Entity‌ها، Value Objects، Interfaces و Services
# ============================================================

from domain.entities.prediction import Prediction, SignalType
from domain.entities.alert import Alert, AlertLevel
from domain.value_objects.price import Price
from domain.value_objects.signal import Signal
from domain.interfaces.repository import Repository
from domain.interfaces.api_client import APIClient

# ✅ Lazy Loading برای NumericAnalyzer (جلوگیری از Circular Import)
# from domain.services.numeric_analyzer import NumericAnalyzer

def get_numeric_analyzer():
    """Lazy Loading برای NumericAnalyzer"""
    from domain.services.numeric_analyzer import NumericAnalyzer
    return NumericAnalyzer

__all__ = [
    # Entities
    'Prediction',
    'SignalType',
    'Alert',
    'AlertLevel',
    # Value Objects
    'Price',
    'Signal',
    # Interfaces
    'Repository',
    'APIClient',
    # Services (با Lazy Loading)
    # 'NumericAnalyzer',  # ❌ حذف
    'get_numeric_analyzer'
]
