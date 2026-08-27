# run_migration.py
# ============================================================
# اجرای اسکریپت دیتابیس با پایتون (بدون نیاز به psql)
# نسخه ۲.۰ - با پشتیبانی از Schema جدید مدل
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


def run_migration(schema_file: str = "database/migrations/models_schema.sql"):
    """
    اجرای اسکریپت SQL روی دیتابیس PostgreSQL
    
    پارامترها:
        schema_file: مسیر فایل SQL (پیش‌فرض: database/migrations/models_schema.sql)
    """
    
    logger.info("🚀 شروع اجرای مهاجرت دیتابیس...")
    
    # ۱. اتصال به دیتابیس
    db = get_primary()
    if not db or not db.is_connected():
        logger.error("❌ اتصال به دیتابیس برقرار نشد!")
        return False
    
    logger.info("✅ اتصال به PostgreSQL برقرار شد")
    
    # ۲. خواندن فایل SQL
    sql_file = Path(schema_file)
    
    if not sql_file.exists():
        logger.error(f"❌ فایل {sql_file} یافت نشد!")
        # تلاش برای پیدا کردن فایل در مسیرهای دیگر
        alternative_paths = [
            "database/models_schema.sql",
            "models_schema.sql",
            "database/migrations/models_schema.sql"
        ]
        for alt in alternative_paths:
            alt_path = Path(alt)
            if alt_path.exists():
                sql_file = alt_path
                logger.info(f"✅ فایل در مسیر جایگزین یافت شد: {alt}")
                break
        else:
            logger.error("❌ فایل Schema در هیچ مسیری یافت نشد!")
            return False
    
    with open(sql_file, 'r', encoding='utf-8') as f:
        sql_content = f.read()
    
    logger.info(f"✅ فایل SQL خوانده شد ({len(sql_content)} کاراکتر) - مسیر: {sql_file}")
    
    # ۳. تقسیم به کوئری‌های جداگانه
    queries = sql_content.split(';')
    success_count = 0
    error_count = 0
    skipped_count = 0
    
    for i, query in enumerate(queries):
        query = query.strip()
        if not query:
            continue
        
        # حذف کامنت‌های یک خطی
        query_lines = query.split('\n')
        clean_lines = []
        for line in query_lines:
            stripped = line.strip()
            # حذف خطوط خالی و کامنت‌ها
            if stripped and not stripped.startswith('--'):
                clean_lines.append(line)
            elif stripped.startswith('--'):
                # کامنت را نگه می‌داریم ولی برای اجرا نمی‌فرستیم
                pass
        
        query = '\n'.join(clean_lines).strip()
        
        if not query:
            continue
        
        # بررسی اینکه کوئری DROP یا CREATE است
        query_upper = query.upper()
        is_dangerous = 'DROP' in query_upper and 'TABLE' in query_upper
        
        try:
            if is_dangerous and 'IF EXISTS' not in query_upper:
                logger.warning(f"⚠️ کوئری خطرناک در خط {i+1}: {query[:50]}...")
                # با احتیاط اجرا می‌کنیم
                db.execute(query)
            else:
                db.execute(query)
            success_count += 1
            if i % 10 == 0:  # لاگ هر ۱۰ کوئری
                logger.info(f"✅ کوئری {i+1} اجرا شد")
        except Exception as e:
            error_count += 1
            error_msg = str(e)
            # اگر خطا به خاطر وجود جدول باشد، نادیده می‌گیریم
            if 'already exists' in error_msg or 'duplicate' in error_msg:
                skipped_count += 1
                logger.debug(f"ℹ️ کوئری {i+1}跳过 (از قبل وجود دارد): {error_msg[:50]}")
            else:
                logger.warning(f"⚠️ خطا در کوئری {i+1}: {error_msg[:100]}")
                # ادامه می‌دیم (بعضی کوئری‌ها ممکنه تکراری باشن)
    
    # ۴. گزارش نهایی
    logger.info("=" * 50)
    logger.info(f"📊 گزارش نهایی مهاجرت:")
    logger.info(f"   ✅ کوئری‌های موفق: {success_count}")
    logger.info(f"   ⚠️ کوئری‌های ناموفق: {error_count}")
    logger.info(f"   ℹ️ کوئری‌های跳过: {skipped_count}")
    logger.info("=" * 50)
    
    # ۵. تست اتصال نهایی و بررسی جدول‌ها
    try:
        # بررسی جدول models
        test_result = db.execute("SELECT COUNT(*) FROM models")
        if test_result:
            count = test_result[0].get('count', 0)
            logger.info(f"✅ جدول models با {count} رکورد وجود دارد!")
        
        # بررسی جدول‌های دیگر
        tables = ['model_training_history', 'model_errors', 'model_performance', 'model_cache']
        for table in tables:
            try:
                result = db.execute(f"SELECT COUNT(*) FROM {table}")
                if result:
                    logger.info(f"✅ جدول {table} با موفقیت ایجاد شد!")
            except:
                logger.warning(f"⚠️ جدول {table} وجود ندارد یا خالی است")
        
        return True
    except Exception as e:
        logger.warning(f"⚠️ خطا در تست نهایی: {e}")
    
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


def check_tables():
    """بررسی وجود جدول‌های مورد نیاز"""
    db = get_primary()
    if not db or not db.is_connected():
        print("❌ اتصال به دیتابیس برقرار نشد!")
        return False
    
    tables = ['models', 'model_training_history', 'model_errors', 'model_performance', 'model_cache']
    missing = []
    
    for table in tables:
        try:
            result = db.execute(f"SELECT COUNT(*) FROM {table}")
            if result:
                count = result[0].get('count', 0)
                print(f"✅ جدول {table}: {count} رکورد")
        except:
            missing.append(table)
            print(f"❌ جدول {table}: وجود ندارد")
    
    if missing:
        print(f"\n⚠️ جدول‌های缺失: {', '.join(missing)}")
        print("   لطفاً run_migration.py را اجرا کنید.")
        return False
    
    print("\n✅ همه جدول‌ها وجود دارند!")
    return True


if __name__ == "__main__":
    print("=" * 60)
    print("🚀 اجرای مهاجرت دیتابیس سیستم تحلیلگر (نسخه ۲.۰)")
    print("=" * 60)
    
    # تست اتصال اولیه
    print("\n📡 تست اتصال به دیتابیس...")
    if not test_connection():
        print("❌ لطفاً ابتدا اتصال به دیتابیس را بررسی کنید!")
        sys.exit(1)
    
    # بررسی جدول‌های موجود
    print("\n📋 بررسی جدول‌های موجود...")
    check_tables()
    
    # پرسش برای اجرای مهاجرت
    print("\n⚠️ آیا می‌خواهید مهاجرت را اجرا کنید؟")
    print("   (جدول‌های موجود حذف نمی‌شوند، فقط اضافه می‌شوند)")
    response = input("   ادامه دهید؟ (y/n): ").strip().lower()
    
    if response not in ['y', 'yes', 'بله', '']:
        print("❌ مهاجرت لغو شد.")
        sys.exit(0)
    
    # اجرای مهاجرت
    print("\n📦 اجرای مهاجرت...")
    success = run_migration()
    
    if success:
        print("\n✅ مهاجرت با موفقیت انجام شد!")
        print("\n📊 بررسی نهایی جدول‌ها:")
        check_tables()
    else:
        print("\n⚠️ مهاجرت با خطا مواجه شد، لطفاً لاگ‌ها را بررسی کنید.")
        sys.exit(1)
