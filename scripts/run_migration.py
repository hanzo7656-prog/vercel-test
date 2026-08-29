#!/usr/bin/env python3
# scripts/run_migration.py
# ============================================================
# اجرای مهاجرت دیتابیس - نسخه ۳.۰
# با پشتیبانی از متغیرهای محیطی و Self-Healing
# ============================================================

import os
import sys
import logging
from pathlib import Path
from dotenv import load_dotenv

# ============================================================
# بارگذاری متغیرهای محیطی
# ============================================================

load_dotenv()

# تنظیم مسیر پروژه
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# ============================================================
# تنظیمات لاگ
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================================
# ایمپورت‌های پروژه
# ============================================================

from database import get_primary
from database.database_factory import ensure_databases_connected
from config.version import VERSION


def run_migration(schema_file: str = "database/migrations/models_schema.sql"):
    """
    اجرای اسکریپت SQL روی دیتابیس PostgreSQL
    
    پارامترها:
        schema_file: مسیر فایل SQL
    """
    
    logger.info("=" * 60)
    logger.info(f"🚀 Migration v{VERSION}")
    logger.info("=" * 60)
    
    # 1. بررسی اتصال دیتابیس
    logger.info("📡 Checking database connections...")
    health = ensure_databases_connected()
    
    if not health.get("primary", False):
        logger.error("❌ Primary database not connected!")
        logger.error("   Please check your .env file and database credentials")
        return False
    
    logger.info("✅ Database connections verified")
    
    # 2. خواندن فایل SQL
    sql_file = Path(schema_file)
    
    if not sql_file.exists():
        # جستجوی مسیرهای جایگزین
        alternative_paths = [
            "database/migrations/models_schema.sql",
            "database/models_schema.sql",
            "models_schema.sql"
        ]
        
        for alt in alternative_paths:
            alt_path = PROJECT_ROOT / alt
            if alt_path.exists():
                sql_file = alt_path
                logger.info(f"✅ Schema found at: {alt}")
                break
        else:
            logger.error("❌ Schema file not found!")
            return False
    
    with open(sql_file, 'r', encoding='utf-8') as f:
        sql_content = f.read()
    
    logger.info(f"✅ Schema loaded ({len(sql_content)} chars)")
    
    # 3. اجرای کوئری‌ها
    db = get_primary()
    queries = sql_content.split(';')
    
    success_count = 0
    error_count = 0
    skipped_count = 0
    
    for i, query in enumerate(queries):
        query = query.strip()
        if not query:
            continue
        
        # حذف کامنت‌ها
        clean_lines = []
        for line in query.split('\n'):
            stripped = line.strip()
            if stripped and not stripped.startswith('--'):
                clean_lines.append(line)
        
        query = '\n'.join(clean_lines).strip()
        if not query:
            continue
        
        try:
            db.execute(query)
            success_count += 1
            if i % 10 == 0:
                logger.info(f"✅ Query {i+1} executed")
        except Exception as e:
            error_msg = str(e)
            # نادیده گرفتن خطاهای تکراری
            if 'already exists' in error_msg or 'duplicate' in error_msg:
                skipped_count += 1
                logger.debug(f"ℹ️ Query {i+1} skipped (already exists)")
            else:
                error_count += 1
                logger.warning(f"⚠️ Query {i+1} error: {error_msg[:100]}")
    
    # 4. گزارش نهایی
    logger.info("=" * 50)
    logger.info(f"📊 Migration Report:")
    logger.info(f"   ✅ Successful: {success_count}")
    logger.info(f"   ⚠️ Errors: {error_count}")
    logger.info(f"   ℹ️ Skipped: {skipped_count}")
    logger.info("=" * 50)
    
    # 5. تأیید نهایی
    if success_count > 0:
        logger.info("✅ Migration completed successfully!")
        return True
    else:
        logger.warning("⚠️ No queries were executed")
        return False


def verify_migration():
    """تأیید نهایی مهاجرت"""
    logger.info("\n📋 Verifying migration...")
    
    db = get_primary()
    if not db or not db.is_connected():
        logger.error("❌ Database not connected")
        return False
    
    try:
        # بررسی جدول‌ها
        tables = ['models', 'model_training_history', 'model_errors', 
                  'model_performance', 'model_cache']
        
        all_ok = True
        for table in tables:
            try:
                result = db.execute(f"SELECT COUNT(*) FROM {table}")
                if result:
                    count = result[0].get('count', 0)
                    logger.info(f"   ✅ {table}: {count} records")
                else:
                    logger.info(f"   ✅ {table}: empty")
            except Exception as e:
                logger.error(f"   ❌ {table}: {str(e)}")
                all_ok = False
        
        return all_ok
        
    except Exception as e:
        logger.error(f"❌ Verification error: {e}")
        return False


def main():
    """ورودی اصلی"""
    print("=" * 60)
    print(f"🚀 Database Migration Tool v{VERSION}")
    print("=" * 60)
    
    # بررسی فایل .env
    env_file = PROJECT_ROOT / ".env"
    if not env_file.exists():
        logger.warning("⚠️ .env file not found!")
        logger.warning("   Please create .env from .env.example")
        response = input("   Continue anyway? (y/n): ").strip().lower()
        if response not in ['y', 'yes']:
            print("❌ Migration cancelled")
            return
    
    # اجرای مهاجرت
    logger.info("\n🔄 Running migration...")
    success = run_migration()
    
    if success:
        logger.info("\n🔍 Verifying migration...")
        if verify_migration():
            logger.info("\n✅ Migration completed successfully!")
        else:
            logger.warning("\n⚠️ Migration partially completed - some tables may be missing")
    else:
        logger.error("\n❌ Migration failed!")
        sys.exit(1)


if __name__ == "__main__":
    main()
