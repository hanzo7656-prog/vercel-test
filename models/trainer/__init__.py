# models/trainer/__init__.py
# ============================================================
# پکیج آموزش‌دهنده‌ها - نسخه ۲.۰
# ============================================================

from typing import TYPE_CHECKING

# Lazy import برای جلوگیری از circular dependency
# (چون AutoTrainer به ModelManager وابسته‌ست)


def __getattr__(name):
    """
    Lazy import
    
    این تابع باعث می‌شه import ها فقط وقتی صدا زده بشن، اجرا بشن.
    """
    if name == "AutoTrainer":
        from models.trainer.auto_trainer import AutoTrainer
        return AutoTrainer
    
    if name == "ManualTrainer":
        from models.trainer.manual_trainer import main as manual_main
        # ManualTrainer یه CLI هست، پس فقط main رو export می‌کنیم
        return manual_main
    
    if name == "manual_trainer":
        from models.trainer import manual_trainer as module
        return module
    
    raise AttributeError(
        f"module {__name__!r} has no attribute {name!r}"
    )


__all__ = [
    "AutoTrainer",
    "ManualTrainer",
    "manual_trainer",
]
