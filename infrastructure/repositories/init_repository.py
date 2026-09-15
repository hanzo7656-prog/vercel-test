# infrastructure/repositories/init_repository.py
# ============================================================
# راه‌انداز Repositoryها - نسخه ۲.۰
# با SettingsRepository
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
        
        self._model_repository = None
        self._prediction_repository = None
        self._settings_repository = None      # 🆕
        self._init_count = 0
        
        logger.info("✅ RepositoryContainer v2.0 initialized")
    
    @property
    def model(self):
        """ModelRepository"""
        if self._model_repository is None:
            from infrastructure.repositories.model_repository import ModelRepository
            self._model_repository = ModelRepository()
            self._init_count += 1
            logger.info("✅ ModelRepository initialized")
        return self._model_repository
    
    @property
    def prediction(self):
        """PredictionRepository"""
        if self._prediction_repository is None:
            from infrastructure.repositories.prediction_repository import PredictionRepository
            self._prediction_repository = PredictionRepository()
            self._init_count += 1
            logger.info("✅ PredictionRepository initialized")
        return self._prediction_repository
    
    @property
    def settings(self):
        """SettingsRepository (🆕)"""
        if self._settings_repository is None:
            from infrastructure.repositories.settings_repository import SettingsRepository
            self._settings_repository = SettingsRepository()
            self._init_count += 1
            logger.info("✅ SettingsRepository initialized")
        return self._settings_repository
    
    def get(self, name: str):
        """دریافت Repository با نام"""
        if name == "model":
            return self.model
        elif name == "prediction":
            return self.prediction
        elif name == "settings":
            return self.settings
        else:
            raise ValueError(f"Unknown repository: {name}")
    
    def has(self, name: str) -> bool:
        """بررسی وجود Repository"""
        return name in ["model", "prediction", "settings"]
    
    def list_available(self) -> list:
        """لیست Repositoryهای موجود"""
        return ["model", "prediction", "settings"]
    
    def reset(self) -> None:
        """ریست"""
        self._model_repository = None
        self._prediction_repository = None
        self._settings_repository = None
        logger.info("🔄 RepositoryContainer reset")
    
    def get_stats(self) -> Dict[str, Any]:
        """آمار"""
        return {
            "model_initialized": self._model_repository is not None,
            "prediction_initialized": self._prediction_repository is not None,
            "settings_initialized": self._settings_repository is not None,
            "init_count": self._init_count,
            "available": self.list_available(),
        }
    
    def __repr__(self) -> str:
        return (
            f"<RepositoryContainer "
            f"model={self._model_repository is not None} "
            f"prediction={self._prediction_repository is not None} "
            f"settings={self._settings_repository is not None}>"
        )


# ============================================================
# Singleton
# ============================================================

repo_container: RepositoryContainer = RepositoryContainer()


def get_model_repository():
    """ModelRepository"""
    return repo_container.model


def get_prediction_repository():
    """PredictionRepository"""
    return repo_container.prediction


def get_settings_repository():
    """SettingsRepository (🆕)"""
    return repo_container.settings


def init_all_repositories() -> Dict[str, Any]:
    """راه‌اندازی همه Repositoryها"""
    result = {"model": False, "prediction": False, "settings": False}
    
    try:
        repo_container.model
        result["model"] = True
    except Exception as e:
        logger.error(f"❌ ModelRepository init error: {e}")
    
    try:
        repo_container.prediction
        result["prediction"] = True
    except Exception as e:
        logger.error(f"❌ PredictionRepository init error: {e}")
    
    try:
        repo_container.settings
        result["settings"] = True
    except Exception as e:
        logger.error(f"❌ SettingsRepository init error: {e}")
    
    logger.info(f"✅ Repositories initialized: {result}")
    return result


def get_repository_stats() -> Dict[str, Any]:
    """آمار Repositoryها"""
    return repo_container.get_stats()


__all__ = [
    "RepositoryContainer",
    "repo_container",
    "get_model_repository",
    "get_prediction_repository",
    "get_settings_repository",
    "init_all_repositories",
    "get_repository_stats",
]


logger.info("✅ init_repository module loaded (v2.0 with Settings)")
