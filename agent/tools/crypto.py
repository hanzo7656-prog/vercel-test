# agent/tools/crypto.py
from .base import call_flask

def get_ws_prices() -> dict:
    """دریافت قیمت‌های real-time از WebSocket بایننس (همه symbolها)."""
    return call_flask("GET", "/api/crypto/ws-prices")

def get_ws_price(symbol: str = "btcusdt") -> dict:
    """دریافت قیمت real-time یک symbol از WebSocket (مثلاً btcusdt)."""
    return call_flask("GET", f"/api/crypto/ws-price/{symbol}")

def get_ws_orderbook(symbol: str = "btcusdt", levels: int = 10) -> dict:
    """دریافت Order Book یک symbol از WebSocket."""
    return call_flask("GET", f"/api/crypto/ws-orderbook/{symbol}",
                      params={"levels": levels})

def get_crypto_stats() -> dict:
    """دریافت آمار WebSocket (connected, messages, errors)."""
    return call_flask("GET", "/api/crypto/stats")
