# config/version.py
# ============================================================
# نسخه‌گذاری یکپارچه سیستم
# ============================================================

VERSION = "8.0.0"
RELEASE_DATE = "2026-08-29"
STATUS = "STABLE"  # STABLE, BETA, DEV

APP_NAME = "Trading Signal System"
APP_DESCRIPTION = "سیستم تشخیص الگوهای بازاری با XGBoost"

def get_version() -> str:
    return f"{APP_NAME} v{VERSION} ({STATUS})"
