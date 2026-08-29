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
from domain.services.numeric_analyzer import NumericAnalyzer

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
    # Services
    'NumericAnalyzer'
]
