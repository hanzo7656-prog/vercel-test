# core/rule_engine/rules/__init__.py
# ============================================================
# Rules Package - رجیستری قوانین
# نسخه ۱.۰
# ============================================================
# 
# این پکیج همه قوانین Rule Engine رو export می‌کنه
# و یه registry مرکزی برای ساخت قوانین از config فراهم می‌کنه.
# ============================================================

from typing import Any, Dict, List, Type

from core.rule_engine.rules.base import BaseRule
from core.rule_engine.rules.rsi_rule import RSIRule
from core.rule_engine.rules.volume_rule import VolumeRule
from core.rule_engine.rules.trend_rule import TrendRule
from core.rule_engine.rules.momentum_rule import MomentumRule


# ============================================================
# Rule Registry
# ============================================================

RULE_REGISTRY: Dict[str, Type[BaseRule]] = {
    "rsi": RSIRule,
    "volume": VolumeRule,
    "trend": TrendRule,
    "momentum": MomentumRule,
}


def get_rule_class(name: str) -> Type[BaseRule]:
    """
    دریافت کلاس یک قانون با نام
    
    Args:
        name: نام قانون (rsi, volume, trend, momentum)
    
    Raises:
        ValueError: اگه قانون ناشناخته باشه
    """
    if name not in RULE_REGISTRY:
        available = ", ".join(RULE_REGISTRY.keys())
        raise ValueError(
            f"قانون ناشناخته: '{name}'. "
            f"قوانین موجود: {available}"
        )
    return RULE_REGISTRY[name]


def create_rule(name: str, config: Dict[str, Any]) -> BaseRule:
    """
    ساخت نمونه قانون از config
    
    Args:
        name: نام قانون
        config: تنظیمات قانون
    
    Returns:
        نمونه BaseRule
    """
    rule_class = get_rule_class(name)
    return rule_class(config=config)


def create_rules_from_config(
    rules_config: Dict[str, Dict[str, Any]],
) -> List[BaseRule]:
    """
    ساخت لیست قوانین از config کامل
    
    Args:
        rules_config: دیکشنری {rule_name: rule_config}
    
    Returns:
        لیست قوانین ساخته‌شده (به ترتیب config)
    
    مثال:
        config = {
            "rsi": {"enabled": True, "weight": 0.30, "min": 25, "max": 60},
            "volume": {"enabled": True, "weight": 0.20, "multiplier": 1.2},
        }
        rules = create_rules_from_config(config)
    """
    rules: List[BaseRule] = []
    for name, rule_config in rules_config.items():
        try:
            rule = create_rule(name, rule_config)
            rules.append(rule)
        except ValueError as e:
            # log و رد شو از قانون ناشناخته
            import logging
            logging.getLogger(__name__).warning(
                f"قانون ناشناخته در config: {name} — {e}"
            )
    return rules


def list_available_rules() -> List[str]:
    """لیست نام همه قوانین موجود"""
    return list(RULE_REGISTRY.keys())


# ============================================================
# Export
# ============================================================

__all__ = [
    "BaseRule",
    "RSIRule",
    "VolumeRule",
    "TrendRule",
    "MomentumRule",
    "RULE_REGISTRY",
    "get_rule_class",
    "create_rule",
    "create_rules_from_config",
    "list_available_rules",
]
