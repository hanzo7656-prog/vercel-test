# config/version.py
# ============================================================
# نسخه‌گذاری یکپارچه سیستم - نسخه ۹.۰
# ============================================================

VERSION = "9.0.0"
RELEASE_DATE = "2026-08-29"
STATUS = "STABLE"  # STABLE, BETA, DEV

APP_NAME = "Trading Signal System"
APP_DESCRIPTION = "سیستم تشخیص الگوهای بازاری با معماری لایه‌بندی شده"

# معماری
ARCHITECTURE = {
    "layers": ["Domain", "Application", "Infrastructure", "Presentation"],
    "pattern": "Clean Architecture",
    "di": "Container-based Dependency Injection"
}

def get_version() -> str:
    """دریافت نسخه کامل"""
    return f"{APP_NAME} v{VERSION} ({STATUS})"

def get_info() -> dict:
    """دریافت اطلاعات کامل"""
    return {
        "name": APP_NAME,
        "version": VERSION,
        "release_date": RELEASE_DATE,
        "status": STATUS,
        "architecture": ARCHITECTURE
    }
