# run_migration.py
# ============================================================
# اجرای اسکریپت دیتابیس با پایتون (بدون نیاز به psql)
# ============================================================

import os
import sys
import logging
from pathlib import Path

# تنظیم لاگ
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# اضافه کردن مسیر پروژه به sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import get_primary


def run_migration():
    """اجرای اسکریپت SQL روی دیتابیس PostgreSQL"""
    
    logger.info("🚀 شروع اجرای مهاجرت دیتابیس...")
    
    # ۱. اتصال به دیتابیس
    db = get_primary()
    if not db or not db.is_connected():
        logger.error("❌ اتصال به دیتابیس برقرار نشد!")
        return False
    
    logger.info("✅ اتصال به PostgreSQL برقرار شد")
    
    # ۲. خواندن فایل SQL
    sql_file = Path("database/models_schema.sql")
    
    if not sql_file.exists():
        logger.error(f"❌ فایل {sql_file} یافت نشد!")
        return False
    
    with open(sql_file, 'r', encoding='utf-8') as f:
        sql_content = f.read()
    
    logger.info(f"✅ فایل SQL خوانده شد ({len(sql_content)} کاراکتر)")
    
    # ۳. تقسیم به کوئری‌های جداگانه
    queries = sql_content.split(';')
    success_count = 0
    error_count = 0
    
    for i, query in enumerate(queries):
        query = query.strip()
        if not query:
            continue
        
        # حذف کامنت‌های یک خطی
        query_lines = query.split('\n')
        clean_lines = []
        for line in query_lines:
            if not line.strip().startswith('--'):
                clean_lines.append(line)
        query = '\n'.join(clean_lines).strip()
        
        if not query:
            continue
        
        try:
            db.execute(query)
            success_count += 1
            logger.info(f"✅ کوئری {i+1} اجرا شد")
        except Exception as e:
            error_count += 1
            logger.warning(f"⚠️ خطا در کوئری {i+1}: {e}")
            # ادامه میدیم (بعضی کوئری‌ها ممکنه تکراری باشن)
    
    # ۴. گزارش نهایی
    logger.info("=" * 50)
    logger.info(f"📊 گزارش نهایی:")
    logger.info(f"   ✅ کوئری‌های موفق: {success_count}")
    logger.info(f"   ⚠️ کوئری‌های ناموفق: {error_count}")
    logger.info("=" * 50)
    
    # ۵. تست اتصال نهایی
    try:
        test_result = db.execute("SELECT COUNT(*) FROM models")
        if test_result:
            logger.info("✅ جدول models با موفقیت ایجاد شد!")
            return True
    except:
        logger.warning("⚠️ جدول models هنوز ایجاد نشده یا خالی است")
    
    return success_count > 0


def test_connection():
    """تست ساده اتصال به دیتابیس"""
    db = get_primary()
    if not db or not db.is_connected():
        print("❌ اتصال به دیتابیس برقرار نشد!")
        return False
    
    try:
        result = db.execute("SELECT version()")
        if result:
            print(f"✅ PostgreSQL ورژن: {result[0].get('version', 'unknown')}")
            return True
    except Exception as e:
        print(f"❌ خطا در تست: {e}")
        return False


if __name__ == "__main__":
    print("=" * 50)
    print("🚀 اجرای مهاجرت دیتابیس سیستم تحلیلگر")
    print("=" * 50)
    
    # تست اتصال اولیه
    print("\n📡 تست اتصال به دیتابیس...")
    if not test_connection():
        print("❌ لطفاً ابتدا اتصال به دیتابیس را بررسی کنید!")
        sys.exit(1)
    
    # اجرای مهاجرت
    print("\n📦 اجرای مهاجرت...")
    success = run_migration()
    
    if success:
        print("\n✅ مهاجرت با موفقیت انجام شد!")
    else:
        print("\n⚠️ مهاجرت با خطا مواجه شد، لطفاً لاگ‌ها را بررسی کنید.")
        sys.exit(1)
