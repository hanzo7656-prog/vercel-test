# infrastructure/repositories/init_repository.py
# ============================================================
# RepositoryContainer - نسخه ۳.۰
# Gemini-only (model, rule_config حذف شدند)
# ============================================================

import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class RepositoryContainer:
    """Container برای Repositoryها"""
    
    _instance: Optional['RepositoryContainer'] = None
    
    def __new__(cls) -> 'RepositoryContainer':
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self) -> None:
        if hasattr(self, '_initialized'):
            return
        self._initialized = True
        
        self._prediction_repository = None
        self._settings_repository = None
        self._ohlcv_repository = None
        self._init_count = 0
        
        logger.info("✅ RepositoryContainer v3.0 initialized (Gemini-only)")
    
    # ============================================================
    # Properties
    # ============================================================
    
    @property
    def prediction(self):
        if self._prediction_repository is None:
            from infrastructure.repositories.prediction_repository import PredictionRepository
            self._prediction_repository = PredictionRepository()
            self._init_count += 1
            logger.info("✅ PredictionRepository initialized")
        return self._prediction_repository
    
    @property
    def settings(self):
        if self._settings_repository is None:
            from infrastructure.repositories.settings_repository import SettingsRepository
            self._settings_repository = SettingsRepository()
            self._init_count += 1
            logger.info("✅ SettingsRepository initialized")
        return self._settings_repository
    
    @property
    def ohlcv(self):
        if self._ohlcv_repository is None:
            from infrastructure.repositories.ohlcv_repository import OHLCVRepository
            self._ohlcv_repository = OHLCVRepository()
            self._init_count += 1
            logger.info("✅ OHLCVRepository initialized")
        return self._ohlcv_repository
    
    # ⚠️ model, rule_config حذف شدند
    
    # ============================================================
    # Generic accessors
    # ============================================================
    
    def get(self, name: str):
        if name == "prediction":
            return self.prediction
        elif name == "settings":
            return self.settings
        elif name == "ohlcv":
            return self.ohlcv
        else:
            raise ValueError(f"Unknown repository: {name}")
    
    def has(self, name: str) -> bool:
        return name in ["prediction", "settings", "ohlcv"]
    
    def list_available(self) -> list:
        return ["prediction", "settings", "ohlcv"]
    
    def reset(self) -> None:
        self._prediction_repository = None
        self._settings_repository = None
        self._ohlcv_repository = None
        logger.info("🔄 RepositoryContainer reset")
    
    def get_stats(self) -> Dict[str, Any]:
        return {
            "prediction_initialized": self._prediction_repository is not None,
            "settings_initialized": self._settings_repository is not None,
            "ohlcv_initialized": self._ohlcv_repository is not None,
            "init_count": self._init_count,
            "available": self.list_available(),
        }
    
    def __repr__(self) -> str:
        return (
            f"<RepositoryContainer "
            f"prediction={self._prediction_repository is not None} "
            f"settings={self._settings_repository is not None} "
            f"ohlcv={self._ohlcv_repository is not None}>"
        )


repo_container: RepositoryContainer = RepositoryContainer()


# ============================================================
# Helper functions
# ============================================================

def get_prediction_repository():
    return repo_container.prediction


def get_settings_repository():
    return repo_container.settings


def get_ohlcv_repository():
    return repo_container.ohlcv


# ⚠️ get_model_repository, get_rule_config_repository حذف شدند


def init_all_repositories() -> Dict[str, Any]:
    result = {
        "prediction": False,
        "settings": False,
        "ohlcv": False,
    }
    
    for name in result.keys():
        try:
            getattr(repo_container, name)
            result[name] = True
        except Exception as e:
            logger.error(f"❌ {name} init error: {e}")
    
    logger.info(f"✅ Repositories initialized: {result}")
    return result


def get_repository_stats() -> Dict[str, Any]:
    return repo_container.get_stats()


__all__ = [
    "RepositoryContainer",
    "repo_container",
    "get_prediction_repository",
    "get_settings_repository",
    "get_ohlcv_repository",
    "init_all_repositories",
    "get_repository_stats",
]


logger.info("✅ init_repository module loaded (v3.0 Gemini-only)")
