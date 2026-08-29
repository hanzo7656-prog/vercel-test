# domain/services/__init__.py
# ============================================================
# Domain Services - سرویس‌های لایه دامنه
# ============================================================

# ✅ استفاده از Lazy Loading برای جلوگیری از Circular Import
# from domain.services.numeric_analyzer import NumericAnalyzer

def get_numeric_analyzer():
    """Lazy Loading برای NumericAnalyzer (جلوگیری از Circular Import)"""
    from domain.services.numeric_analyzer import NumericAnalyzer
    return NumericAnalyzer

__all__ = [
    'get_numeric_analyzer',
    # 'NumericAnalyzer'  # ❌ حذف شده برای جلوگیری از Import در زمان بارگذاری
]
