# agent/tools/market.py
from .base import call_flask

def get_price(coin: str = "bitcoin") -> dict:
    """دریافت قیمت لحظه‌ای یک ارز (bitcoin/ethereum/solana/...)."""
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

def get_global_market() -> dict:
    """دریافت وضعیت کلی بازار (Market Cap, Volume, BTC Dominance)."""
    return call_flask("GET", "/api/coinstats/global-market")
