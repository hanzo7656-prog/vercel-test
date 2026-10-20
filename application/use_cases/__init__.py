# application/use_cases/__init__.py
# ============================================================
# Use Cases - نسخه ۵.۰
# Gemini-only (PredictCoinUseCase, ScanMarketUseCase حذف شدند)
# ============================================================

def __getattr__(name: str):
    # ============================================================
    # Health (مشترک)
    # ============================================================
    
    if name == "GetHealthUseCase":
        from application.use_cases.get_health import GetHealthUseCase
        return GetHealthUseCase
    
    # ============================================================
    # AI (Gemini)
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
    
    if name == "PredictCoinGeminiUseCase":
        from application.use_cases.predict_coin_gemini import PredictCoinGeminiUseCase
        return PredictCoinGeminiUseCase
    
    # ⚠️ PredictCoinUseCase حذف شد (RuleEngine legacy)
    # ⚠️ ScanMarketUseCase حذف شد (RuleEngine legacy)
    
    raise AttributeError(
        f"module {__name__!r} has no attribute {name!r}"
    )


__all__ = [
    # Health
    "GetHealthUseCase",
    # AI (Gemini)
    "AIChatUseCase",
    "AIAnalyzeImageUseCase",
    "AIExplainUseCase",
    "PredictCoinGeminiUseCase",
]
