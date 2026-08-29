# database/__init__.py
# ============================================================
# پکیج Database (برای سازگاری با کدهای قدیمی)
# ============================================================

from infrastructure.database import (
    get_primary,
    get_cache,
    get_backup,
    health_check,
    db_factory,
    ensure_databases_connected,
    registry,
    router
)

__all__ = [
    'get_primary',
    'get_cache',
    'get_backup',
    'health_check',
    'db_factory',
    'ensure_databases_connected',
    'registry',
    'router'
]
