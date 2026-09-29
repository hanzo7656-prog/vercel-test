# models/trainer/__init__.py
# ============================================================
# پکیج آموزش‌دهنده‌ها - نسخه ۳.۰
# ============================================================

def __getattr__(name):
    """Lazy import"""
    if name == "AutoTrainer":
        from models.trainer.auto_trainer import AutoTrainer
        return AutoTrainer
    
    if name == "CALIBRATION_PROFILES":
        from models.trainer.auto_trainer import CALIBRATION_PROFILES
        return CALIBRATION_PROFILES
    
    raise AttributeError(
        f"module {__name__!r} has no attribute {name!r}"
    )


__all__ = [
    "AutoTrainer",
    "CALIBRATION_PROFILES",
]
