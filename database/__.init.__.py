# database/__init__.py
# ============================================================
# پکیج دیتابیس - استفاده آسان
# ============================================================

from database.database_factory import (
    DatabaseFactory,
    get_db,
    get_redis,
    health_check,
    db_factory
)
from database.base import DatabaseBase
from database.redis_manager import RedisManager

__all__ = [
    'DatabaseFactory',
    'get_db',
    'get_redis',
    'health_check',
    'db_factory',
    'DatabaseBase',
    'RedisManager'
]
