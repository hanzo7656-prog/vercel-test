# application/use_cases/__init__.py
# ============================================================
# Use Cases - نسخه ۳.۰
# ============================================================

def __getattr__(name: str):
    if name == "PredictCoinUseCase":
        from application.use_cases.predict_coin import PredictCoinUseCase
        return PredictCoinUseCase
    
    if name == "GetHealthUseCase":
        from application.use_cases.get_health import GetHealthUseCase
        return GetHealthUseCase
    
    if name == "ScanMarketUseCase":
        from application.use_cases.scan_market import ScanMarketUseCase
        return ScanMarketUseCase
    
    raise AttributeError(
        f"module {__name__!r} has no attribute {name!r}"
    )


__all__ = [
    "PredictCoinUseCase",
    "GetHealthUseCase",
    "ScanMarketUseCase",
]
