# infrastructure/api/__init__.py
# ============================================================
# API Clients - کلاینت‌های ارتباط با سرویس‌های خارجی
# ============================================================

from infrastructure.api.coinstats_client import coinstats_client, CoinStatsClient
from infrastructure.api.cache_manager import cache_manager, CacheManager
from infrastructure.api.free_crypto_client import FreeCryptoClient, create_free_crypto_client

__all__ = [
    # CoinStats
    'coinstats_client',
    'CoinStatsClient',
    
    # Cache
    'cache_manager',
    'CacheManager',
    
    # WebSocket (FreeCryptoAPI)
    'FreeCryptoClient',
    'create_free_crypto_client',
]
