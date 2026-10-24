# agent/tools/__init__.py
from .debug import (
    check_health, get_debug_status, get_recent_logs,
    get_db_health, get_apis_health, get_cache_stats,
)
from .database import (
    get_predictions, get_prediction_stats, get_ohlcv,
    get_db_tables, get_table_data,
)
from .market import (
    get_price, get_prices, get_fear_greed,
    get_btc_dominance, get_ws_prices,
)

# ابزارهای فقط‌خواندنی (بدون نیاز به تأیید)
ALL_TOOLS = [
    # Debug
    check_health, get_debug_status, get_recent_logs,
    get_db_health, get_apis_health, get_cache_stats,
    # Database
    get_predictions, get_prediction_stats, get_ohlcv,
    get_db_tables, get_table_data,
    # Market
    get_price, get_prices, get_fear_greed,
    get_btc_dominance, get_ws_prices,
]
