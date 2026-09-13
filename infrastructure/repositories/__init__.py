# infrastructure/repositories/__init__.py
# ============================================================
# Repositories - مخازن داده - نسخه ۲.۰
# Export کامل + RepositoryContainer
# ============================================================

import logging
from typing import Optional, Any, Dict, List

logger = logging.getLogger(__name__)


# ============================================================
# Lazy Imports (جلوگیری از Circular Import)
# ============================================================

def _get_model_repository_class():
    """Lazy import ModelRepository"""
    from infrastructure.repositories.model_repository import ModelRepository
    return ModelRepository


def _get_prediction_repository_class():
    """Lazy import PredictionRepository"""
    from infrastructure.repositories.prediction_repository import PredictionRepository
    return PredictionRepository


def _get_container():
    """Lazy import RepositoryContainer"""
    from infrastructure.repositories.init_repository import repo_container
    return repo_container


# ============================================================
# Direct Access (ساخت نمونه جدید)
# ============================================================

def get_model_repository():
    """
    دریافت ModelRepository (نمونه جدید)
    
    خروجی:
        ModelRepository instance
    
    توجه:
        برای استفاده از singleton، از repo_container استفاده کن
    """
    ModelRepository = _get_model_repository_class()
    return ModelRepository()


def get_prediction_repository():
    """
    دریافت PredictionRepository (نمونه جدید)
    
    خروجی:
        PredictionRepository instance
    
    توجه:
        برای استفاده از singleton، از repo_container استفاده کن
    """
    PredictionRepository = _get_prediction_repository_class()
    return PredictionRepository()


# ============================================================
# Container Access (Singleton)
# ============================================================

def get_container():
    """
    دریافت RepositoryContainer
    
    خروجی:
        RepositoryContainer instance (singleton)
    """
    return _get_container()


def get_repository(name: str):
    """
    دریافت Repository با نام از Container
    
    پارامترها:
        name: نام Repository (model, prediction)
    
    خروجی:
        Repository instance
    """
    return _get_container().get(name)


def init_all_repositories() -> Dict[str, bool]:
    """
    راه‌اندازی همه Repositoryها
    
    خروجی:
        دیکشنری وضعیت
    """
    from infrastructure.repositories.init_repository import (
        init_all_repositories as _init
    )
    return _init()


def get_repository_stats() -> Dict[str, Any]:
    """
    دریافت آمار Repositoryها
    
    خروجی:
        دیکشنری آمار
    """
    from infrastructure.repositories.init_repository import (
        get_repository_stats as _stats
    )
    return _stats()


# ============================================================
# Properties (Singleton Access)
# ============================================================

class Repositories:
    """
    دسترسی سریع به Repositoryها (Singleton)
    
    استفاده:
        from infrastructure.repositories import repos
        
        repos.model.save_model(...)
        repos.prediction.save(...)
    """
    
    @property
    def model(self):
        """ModelRepository (singleton)"""
        return _get_container().model
    
    @property
    def prediction(self):
        """PredictionRepository (singleton)"""
        return _get_container().prediction
    
    def get(self, name: str):
        """دریافت Repository با نام"""
        return _get_container().get(name)
    
    def list_available(self) -> List[str]:
        """لیست Repositoryهای موجود"""
        return _get_container().list_available()
    
    def get_stats(self) -> Dict[str, Any]:
        """آمار Container"""
        return _get_container().get_stats()
    
    def reset(self) -> None:
        """ریست Container"""
        _get_container().reset()


# Singleton instance
repos = Repositories()


# ============================================================
# Export
# ============================================================

__all__ = [
    # Classes
    "ModelRepository",
    "PredictionRepository",
    "RepositoryContainer",
    
    # Direct access
    "get_model_repository",
    "get_prediction_repository",
    
    # Container
    "get_container",
    "get_repository",
    "init_all_repositories",
    "get_repository_stats",
    
    # Singleton
    "repos",
]


# ============================================================
# Lazy Class Access (برای Import مستقیم)
# ============================================================

def __getattr__(name: str):
    """
    Lazy loading برای کلاس‌ها
    
    این تابع باعث می‌شود که:
        from infrastructure.repositories import ModelRepository
    کار کند، ولی فقط وقتی که واقعاً استفاده شود، import انجام شود.
    """
    if name == "ModelRepository":
        return _get_model_repository_class()
    elif name == "PredictionRepository":
        return _get_prediction_repository_class()
    elif name == "RepositoryContainer":
        from infrastructure.repositories.init_repository import (
            RepositoryContainer
        )
        return RepositoryContainer
    
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


logger.info("✅ infrastructure.repositories package loaded")
