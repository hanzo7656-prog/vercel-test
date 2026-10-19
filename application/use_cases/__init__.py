# application/use_cases/__init__.py
# ============================================================
# Use Cases - نسخه ۴.۰
# + AI (Gemini) Use Cases
# ============================================================

def __getattr__(name: str):
    # ============================================================
    # Existing (RuleEngine)
    # ============================================================
    
    if name == "PredictCoinUseCase":
        from application.use_cases.predict_coin import PredictCoinUseCase
        return PredictCoinUseCase
    
    if name == "GetHealthUseCase":
        from application.use_cases.get_health import GetHealthUseCase
        return GetHealthUseCase
    
    if name == "ScanMarketUseCase":
        from application.use_cases.scan_market import ScanMarketUseCase
        return ScanMarketUseCase
    
    # ============================================================
    # AI (Gemini) — 🆕
    # ============================================================
    
    if name == "AIChatUseCase":
        from application.use_cases.ai_chat import AIChatUseCase
        return AIChatUseCase
    
    if name == "AIAnalyzeImageUseCase":
        from application.use_cases.ai_analyze_image import AIAnalyzeImageUseCase
        return AIAnalyzeImageUseCase
    
    if name == "AIExplainUseCase":
        from application.use_cases.ai_explain import AIExplainUseCase
        return AIExplainUseCase
    
    raise AttributeError(
        f"module {__name__!r} has no attribute {name!r}"
    )


__all__ = [
    # Existing
    "PredictCoinUseCase",
    "GetHealthUseCase",
    "ScanMarketUseCase",
    # AI (Gemini)
    "AIChatUseCase",
    "AIAnalyzeImageUseCase",
    "AIExplainUseCase",
]
