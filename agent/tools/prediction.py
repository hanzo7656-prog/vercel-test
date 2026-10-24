# agent/tools/prediction.py
from .base import call_flask

def predict_single(coin: str = "bitcoin", period: str = "24h") -> dict:
    """پیش‌بینی یک ارز برای بازه مشخص (period: 24h/1w/1m/3m/6m)."""
    return call_flask("GET", "/api/predict/single",
                      params={"coin": coin, "period": period})

def predict_multiple(coins: list, period: str = "24h") -> dict:
    """پیش‌بینی چند ارز همزمان."""
    return call_flask("POST", "/api/predict/multiple",
                      json_body={"coins": coins, "period": period})

def get_prediction_engines() -> dict:
    """لیست موتورهای پیش‌بینی موجود و وضعیت دسترسی آن‌ها."""
    return call_flask("GET", "/api/predict/engines")

def get_state(symbol: str) -> dict:
    """دریافت وضعیت State Machine یک نماد (مثلاً BTCUSDT)."""
    return call_flask("GET", f"/api/state/{symbol}")
