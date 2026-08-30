# infrastructure/__init__.py
# ============================================================
# لایه زیرساخت (Infrastructure Layer)
# شامل API، Database، Repositories، Auth و External
# ============================================================

from infrastructure.api.coinstats_client import coinstats_client, CoinStatsClient
from infrastructure.api.cache_manager import cache_manager, CacheManager

from infrastructure.database import (
    get_primary,
    get_cache,
    get_backup,
    health_check,
    db_factory,
    ensure_databases_connected,
    registry,
    router,
    get_db,
    get_db_for,
    get_all_databases,
    get_database_status
)

from infrastructure.repositories.model_repository import ModelRepository
from infrastructure.repositories.prediction_repository import PredictionRepository

from infrastructure.auth.auth_manager import auth_manager, AuthManager

# ✅ اضافه کردن External
from infrastructure.external.alerter import alerter, Alerter

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
    'registry',
    'router',
    'get_db',
    'get_db_for',
    'get_all_databases',
    'get_database_status',
    
    # Repositories
    'ModelRepository',
    'PredictionRepository',
    
    # Auth
    'auth_manager',
    'AuthManager',
    
    # External
    'alerter',
    'Alerter'
]
