# agent/tools/market.py
from .base import call_flask

def get_price(coin: str = "bitcoin") -> dict:
    """دریافت قیمت لحظه‌ای یک ارز (مثلا bitcoin یا ethereum)."""
    return call_flask("GET", f"/api/coinstats/price/{coin}")

def get_prices() -> dict:
    """دریافت قیمت همزمان BTC و ETH."""
    return call_flask("GET", "/api/coinstats/prices")

def get_fear_greed() -> dict:
    """دریافت شاخص ترس و طمع (Fear & Greed Index)."""
    return call_flask("GET", "/api/coinstats/fear-greed")

def get_btc_dominance() -> dict:
    """دریافت درصد سلطه بیت‌کوین."""
    return call_flask("GET", "/api/coinstats/btc-dominance")

def get_ws_prices() -> dict:
    """دریافت قیمت‌های real-time از WebSocket بایننس."""
    return call_flask("GET", "/api/crypto/ws-prices")
