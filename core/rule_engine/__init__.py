# core/rule_engine/__init__.py
# ============================================================
# Rule Engine Package - نسخه ۱.۰
# ============================================================
# 
# این پکیج جایگزین XGBoost می‌شه و شامل:
#   - RuleEngine: موتور اصلی
#   - StateMachine: مدیریت وضعیت
#   - BatchProcessor: پردازش موازی
#   - Rules: قوانین (RSI, Volume, Trend, Momentum)
# ============================================================

from typing import TYPE_CHECKING

# ============================================================
# Direct Imports (بدون circular)
# ============================================================

from core.rule_engine.models import (
    MarketState,
    Prediction,
    RuleResult,
    ScanResult,
    StateSnapshot,
)

from core.rule_engine.rules import (
    BaseRule,
    RSIRule,
    VolumeRule,
    TrendRule,
    MomentumRule,
    RULE_REGISTRY,
    create_rule,
    create_rules_from_config,
    get_rule_class,
    list_available_rules,
)

from core.rule_engine.state_machine import StateMachine
from core.rule_engine.engine import RuleEngine
from core.rule_engine.batch_processor import BatchProcessor

from core.rule_engine.indicators import (
    compute_indicators,
    compute_rsi,
    compute_macd,
    compute_atr,
    get_indicator_columns,
    validate_indicators,
)


# ============================================================
# Factory Helpers
# ============================================================

def create_engine_from_config(
    rules_config: dict,
    scoring_config: dict | None = None,
    state_machine: StateMachine | None = None,
) -> RuleEngine:
    """
    ساخت RuleEngine از config
    
    Args:
        rules_config: دیکشنری قوانین
        scoring_config: تنظیمات scoring
        state_machine: StateMachine (اختیاری)
    
    Returns:
        RuleEngine instance
    """
    return RuleEngine(
        rules_config=rules_config,
        scoring_config=scoring_config or {},
        state_machine=state_machine,
    )


def load_default_config() -> dict:
    """
    بارگذاری config پیش‌فرض از JSON
    
    Returns:
        دیکشنری config کامل
    """
    import json
    from pathlib import Path
    
    config_path = Path(__file__).parent / "config" / "default_rules.json"
    
    if not config_path.exists():
        raise FileNotFoundError(f"Config not found: {config_path}")
    
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def create_default_engine() -> RuleEngine:
    """
    ساخت RuleEngine با config پیش‌فرض
    
    استفاده سریع برای تست
    """
    config = load_default_config()
    
    return RuleEngine(
        rules_config=config["rules"],
        scoring_config=config.get("scoring", {}),
        config=config,
    )


# ============================================================
# Export
# ============================================================

__all__ = [
    # Models
    "MarketState",
    "Prediction",
    "RuleResult",
    "ScanResult",
    "StateSnapshot",
    
    # Rules
    "BaseRule",
    "RSIRule",
    "VolumeRule",
    "TrendRule",
    "MomentumRule",
    "RULE_REGISTRY",
    "create_rule",
    "create_rules_from_config",
    "get_rule_class",
    "list_available_rules",
    
    # Core
    "StateMachine",
    "RuleEngine",
    "BatchProcessor",
    
    # Indicators
    "compute_indicators",
    "compute_rsi",
    "compute_macd",
    "compute_atr",
    "get_indicator_columns",
    "validate_indicators",
    
    # Factory
    "create_engine_from_config",
    "load_default_config",
    "create_default_engine",
]
