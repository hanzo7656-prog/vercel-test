# agent/tools/__init__.py
from .debug import (check_health, get_debug_status, get_recent_logs,
                    get_db_health, get_apis_health, get_cache_stats)
from .database import (get_predictions, get_prediction_stats, get_ohlcv,
                       get_db_tables, get_table_data, get_table_sizes)
from .market import (get_price, get_prices, get_fear_greed,
                     get_btc_dominance, get_global_market)
from .prediction import (predict_single, predict_multiple,
                         get_prediction_engines, get_state)
from .crypto import (get_ws_prices, get_ws_price, get_ws_orderbook, get_crypto_stats)
from .system import (get_app_stats, get_metrics, get_metrics_dashboard, get_thread_status)

ALL_TOOLS = [
    # Debug (6)
    check_health, get_debug_status, get_recent_logs,
    get_db_health, get_apis_health, get_cache_stats,
    # Database (6)
    get_predictions, get_prediction_stats, get_ohlcv,
    get_db_tables, get_table_data, get_table_sizes,
    # Market (5)
    get_price, get_prices, get_fear_greed,
    get_btc_dominance, get_global_market,
    # Prediction (4)
    predict_single, predict_multiple,
    get_prediction_engines, get_state,
    # Crypto (4)
    get_ws_prices, get_ws_price, get_ws_orderbook, get_crypto_stats,
    # System (4)
    get_app_stats, get_metrics, get_metrics_dashboard, get_thread_status,
]
