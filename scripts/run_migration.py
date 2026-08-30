# scripts/run_migration.py
# ============================================================
# اجرای مهاجرت دیتابیس
# ============================================================

import os
import sys
import logging
from pathlib import Path

# اضافه کردن مسیر پروژه
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from infrastructure.database import get_primary

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def run_migration():
    """اجرای اسکریپت SQL روی دیتابیس"""
    logger.info("🚀 Starting database migration...")
    
    db = get_primary()
    if not db or not db.is_connected():
        logger.error("❌ Database not connected!")
        return False
    
    # مسیر فایل SQL
    sql_file = Path("infrastructure/database/migrations/models_schema.sql")
    
    if not sql_file.exists():
        logger.error(f"❌ SQL file not found: {sql_file}")
        return False
    
    with open(sql_file, 'r', encoding='utf-8') as f:
        sql_content = f.read()
    
    logger.info(f"✅ SQL file loaded ({len(sql_content)} chars)")
    
    # تقسیم به کوئری‌های جداگانه
    queries = sql_content.split(';')
    success_count = 0
    error_count = 0
    
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
            if i % 5 == 0:
                logger.info(f"✅ Query {i+1} executed")
        except Exception as e:
            error_msg = str(e)
            if 'already exists' in error_msg or 'duplicate' in error_msg:
                logger.debug(f"ℹ️ Query {i+1} skipped (already exists)")
            else:
                error_count += 1
                logger.warning(f"⚠️ Query {i+1} error: {error_msg[:100]}")
    
    logger.info(f"📊 Migration completed: {success_count} success, {error_count} errors")
    return success_count > 0


if __name__ == "__main__":
    run_migration()
