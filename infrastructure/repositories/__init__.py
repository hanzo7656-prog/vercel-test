# infrastructure/repositories/__init__.py
# ============================================================
# Repositories - نسخه ۴.۰
# Gemini-only (ModelRepository, RuleConfigRepository حذف شدند)
# ============================================================

import logging
from typing import Optional, Any, Dict, List

logger = logging.getLogger(__name__)


# ============================================================
# Lazy Imports
# ============================================================

def _get_prediction_repository_class():
    from infrastructure.repositories.prediction_repository import PredictionRepository
    return PredictionRepository


def _get_settings_repository_class():
    from infrastructure.repositories.settings_repository import SettingsRepository
    return SettingsRepository


def _get_ohlcv_repository_class():
    from infrastructure.repositories.ohlcv_repository import OHLCVRepository
    return OHLCVRepository


# ⚠️ _get_model_repository_class حذف شد (RuleEngine legacy)
# ⚠️ _get_rule_config_repository_class حذف شد (RuleEngine legacy)


def _get_container():
    from infrastructure.repositories.init_repository import repo_container
    return repo_container


# ============================================================
# Direct Access
# ============================================================

def get_prediction_repository():
    return _get_prediction_repository_class()()


def get_settings_repository():
    return _get_settings_repository_class()()


def get_ohlcv_repository():
    return _get_ohlcv_repository_class()()


# ⚠️ get_model_repository حذف شد
# ⚠️ get_rule_config_repository حذف شد


# ============================================================
# Container Access
# ============================================================

def get_container():
    return _get_container()


def get_repository(name: str):
    return _get_container().get(name)


def init_all_repositories() -> Dict[str, bool]:
    from infrastructure.repositories.init_repository import (
        init_all_repositories as _init
    )
    return _init()


def get_repository_stats() -> Dict[str, Any]:
    from infrastructure.repositories.init_repository import (
        get_repository_stats as _stats
    )
    return _stats()


# ============================================================
# Singleton Access
# ============================================================

class Repositories:
    """دسترسی سریع به Repositoryها"""
    
    @property
    def prediction(self):
        return _get_container().prediction
    
    @property
    def settings(self):
        return _get_container().settings
    
    @property
    def ohlcv(self):
        return _get_container().ohlcv
    
    # ⚠️ model, rule_config حذف شدند
    
    def get(self, name: str):
        return _get_container().get(name)
    
    def list_available(self) -> List[str]:
        return _get_container().list_available()
    
    def get_stats(self) -> Dict[str, Any]:
        return _get_container().get_stats()
    
    def reset(self) -> None:
        _get_container().reset()


repos = Repositories()


# ============================================================
# Export
# ============================================================

__all__ = [
    "PredictionRepository",
    "SettingsRepository",
    "OHLCVRepository",
    "RepositoryContainer",
    
    "get_prediction_repository",
    "get_settings_repository",
    "get_ohlcv_repository",
    
    "get_container",
    "get_repository",
    "init_all_repositories",
    "get_repository_stats",
    
    "repos",
]


# ============================================================
# Lazy Class Access
# ============================================================

def __getattr__(name: str):
    if name == "PredictionRepository":
        return _get_prediction_repository_class()
    elif name == "SettingsRepository":
        return _get_settings_repository_class()
    elif name == "OHLCVRepository":
        return _get_ohlcv_repository_class()
    elif name == "RepositoryContainer":
        from infrastructure.repositories.init_repository import RepositoryContainer
        return RepositoryContainer
    
    # ⚠️ ModelRepository, RuleConfigRepository حذف شدند
    
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


logger.info("✅ infrastructure.repositories package loaded (v4.0 Gemini-only)")
