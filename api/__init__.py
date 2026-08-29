# api/__init__.py
# ============================================================
# پکیج API (برای سازگاری با کدهای قدیمی)
# ============================================================

from infrastructure.api.coinstats_client import coinstats_client, CoinStatsClient
from infrastructure.api.cache_manager import cache_manager, CacheManager

__all__ = [
    'coinstats_client',
    'CoinStatsClient',
    'cache_manager',
    'CacheManager'
]
