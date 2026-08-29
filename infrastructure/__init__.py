# infrastructure/__init__.py
# ============================================================
# لایه زیرساخت (Infrastructure Layer)
# شامل API Client، Database، Repositories و Auth
# ============================================================

from infrastructure.api.coinstats_client import coinstats_client, CoinStatsClient
from infrastructure.api.cache_manager import cache_manager, CacheManager
from infrastructure.database import (
    get_primary,
    get_cache,
    get_backup,
    health_check,
    db_factory,
    ensure_databases_connected
)
from infrastructure.repositories.model_repository import ModelRepository
from infrastructure.repositories.prediction_repository import PredictionRepository
from infrastructure.auth.auth_manager import auth_manager, AuthManager

__all__ = [
    # API
    'coinstats_client',
    'CoinStatsClient',
    'cache_manager',
    'CacheManager',
    # Database
    'get_primary',
    'get_cache',
    'get_backup',
    'health_check',
    'db_factory',
    'ensure_databases_connected',
    # Repositories
    'ModelRepository',
    'PredictionRepository',
    # Auth
    'auth_manager',
    'AuthManager'
]
