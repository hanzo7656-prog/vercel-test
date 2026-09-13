#!/usr/bin/env python3
# scripts/manage_databases.py
# ============================================================
# مدیریت دیتابیس‌ها - Migration + Seed + Reset + Status
# نسخه ۴.۰ - ادغام کامل schema قدیم و جدید + Idempotent
# ============================================================

"""
مدیریت کامل دیتابیس‌های سیستم (۵ دیتابیس)

استفاده:
    # اجرای همه کارها (migrate + seed + status)
    python scripts/manage_databases.py --action=all
    
    # فقط migration
    python scripts/manage_databases.py --action=migrate
    
    # فقط seed
    python scripts/manage_databases.py --action=seed
    
    # فقط status
    python scripts/manage_databases.py --action=status
    
    # reset (احتیاط!)
    python scripts/manage_databases.py --action=reset --confirm
    
    # با لاگ دقیق
    python scripts/manage_databases.py --action=all --verbose
"""

import os
import sys
import logging
import argparse
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any

# اضافه کردن مسیر پروژه
sys.path.insert(0, str(Path(__file__).parent.parent))

from infrastructure.database import (
    get_primary,
    get_backup,
    get_analytics,
    get_logs_db,
    get_archive,
    get_cache,
)
from infrastructure.database.quota_manager import quota_manager

logger = logging.getLogger(__name__)


# ============================================================
# Logging Setup
# ============================================================

def setup_logging(verbose: bool = False) -> None:
    """راه‌اندازی logging"""
    level = logging.DEBUG if verbose else logging.INFO
    
    logging.basicConfig(
        level=level,
        format='%(asctime)s | %(levelname)-8s | %(message)s',
        datefmt='%H:%M:%S',
    )


# ============================================================
# Schema Definitions
# ============================================================

# ------------------------------------------------------------
# PRIMARY (Neon #1) - دیتابیس اصلی
# ------------------------------------------------------------
SCHEMA_PRIMARY = {
    # --------- جدول مدل‌ها ---------
    "models": """
        CREATE TABLE IF NOT EXISTS models (
            id SERIAL PRIMARY KEY,
            version VARCHAR(50) UNIQUE NOT NULL,
            model_data BYTEA NOT NULL,
            accuracy FLOAT NOT NULL DEFAULT 0,
            training_samples INTEGER DEFAULT 0,
            period VARCHAR(10) DEFAULT '1m',
            coins TEXT[] DEFAULT ARRAY['bitcoin', 'ethereum'],
            features TEXT[] DEFAULT ARRAY[
                'return_1','return_3','return_5','return_10',
                'sma_5','sma_10','sma_20','volatility',
                'fear_greed','trend_5','trend_10','trend_20','r2'
            ],
            is_active BOOLEAN DEFAULT FALSE,
            is_ensemble BOOLEAN DEFAULT FALSE,
            training_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            metadata JSONB DEFAULT '{}'::jsonb
        );
        CREATE INDEX IF NOT EXISTS idx_models_version ON models(version);
        CREATE INDEX IF NOT EXISTS idx_models_active ON models(is_active);
        CREATE INDEX IF NOT EXISTS idx_models_accuracy ON models(accuracy DESC);
        CREATE INDEX IF NOT EXISTS idx_models_training_date ON models(training_date DESC);
    """,
    
    # --------- تاریخچه آموزش ---------
    "model_training_history": """
        CREATE TABLE IF NOT EXISTS model_training_history (
            id SERIAL PRIMARY KEY,
            model_id INTEGER REFERENCES models(id) ON DELETE CASCADE,
            action VARCHAR(50) NOT NULL,
            old_accuracy FLOAT,
            new_accuracy FLOAT,
            improvement_percent FLOAT,
            samples_used INTEGER,
            training_time_seconds FLOAT,
            reason TEXT,
            status VARCHAR(20) DEFAULT 'success',
            error_message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_mth_model_id ON model_training_history(model_id);
        CREATE INDEX IF NOT EXISTS idx_mth_created_at ON model_training_history(created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_mth_status ON model_training_history(status);
    """,
    
    # --------- پیش‌بینی‌ها ---------
    "predictions": """
        CREATE TABLE IF NOT EXISTS predictions (
            id SERIAL PRIMARY KEY,
            coin VARCHAR(50) NOT NULL,
            coin_name VARCHAR(100),
            current_price DECIMAL(20, 8) DEFAULT 0,
            signal_type VARCHAR(20) NOT NULL,
            confidence INTEGER DEFAULT 50,
            prediction_score FLOAT DEFAULT 0.5,
            period VARCHAR(10) DEFAULT '24h',
            model_mode VARCHAR(20) DEFAULT 'DEMO',
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            processing_time_ms FLOAT DEFAULT 0,
            data_points INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_pred_coin ON predictions(coin);
        CREATE INDEX IF NOT EXISTS idx_pred_timestamp ON predictions(timestamp DESC);
        CREATE INDEX IF NOT EXISTS idx_pred_signal ON predictions(signal_type);
        CREATE INDEX IF NOT EXISTS idx_pred_coin_time ON predictions(coin, timestamp DESC);
        CREATE INDEX IF NOT EXISTS idx_pred_confidence ON predictions(confidence DESC);
    """,
    
    # --------- ترس و طمع ---------
    "fear_greed_history": """
        CREATE TABLE IF NOT EXISTS fear_greed_history (
            id SERIAL PRIMARY KEY,
            value INTEGER NOT NULL,
            classification VARCHAR(50),
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_fg_timestamp ON fear_greed_history(timestamp DESC);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_fg_unique_time ON fear_greed_history(timestamp);
    """,
    
    # --------- سلطه بیت‌کوین ---------
    "btc_dominance_history": """
        CREATE TABLE IF NOT EXISTS btc_dominance_history (
            id SERIAL PRIMARY KEY,
            value DECIMAL(5, 2) NOT NULL,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_bd_timestamp ON btc_dominance_history(timestamp DESC);
    """,
    
    # --------- بازار جهانی ---------
    "global_market_history": """
        CREATE TABLE IF NOT EXISTS global_market_history (
            id SERIAL PRIMARY KEY,
            market_cap DECIMAL(30, 2),
            volume DECIMAL(30, 2),
            btc_dominance DECIMAL(5, 2),
            active_cryptocurrencies INTEGER,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_gm_timestamp ON global_market_history(timestamp DESC);
    """,
    
    # --------- کاربران ---------
    "users": """
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username VARCHAR(50) UNIQUE NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            email VARCHAR(100),
            role VARCHAR(20) DEFAULT 'user',
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
        CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);
        CREATE INDEX IF NOT EXISTS idx_users_active ON users(is_active);
    """,
    
    # --------- لاگ دستورات ---------
    "commands_log": """
        CREATE TABLE IF NOT EXISTS commands_log (
            id SERIAL PRIMARY KEY,
            user_id VARCHAR(100),
            command TEXT NOT NULL,
            response TEXT,
            status VARCHAR(20) DEFAULT 'success',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_cl_user_id ON commands_log(user_id);
        CREATE INDEX IF NOT EXISTS idx_cl_created_at ON commands_log(created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_cl_status ON commands_log(status);
    """,
    
    # --------- کش fallback ---------
    "cache": """
        CREATE TABLE IF NOT EXISTS cache (
            key VARCHAR(255) PRIMARY KEY,
            value TEXT,
            expires_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_cache_expires ON cache(expires_at);
    """,
}


# ------------------------------------------------------------
# BACKUP (Neon #2) - نسخه پشتیبان
# ------------------------------------------------------------
SCHEMA_BACKUP = {
    "models_backup": """
        CREATE TABLE IF NOT EXISTS models_backup (
            id SERIAL PRIMARY KEY,
            original_id INTEGER,
            version VARCHAR(50) NOT NULL,
            model_data BYTEA,
            accuracy FLOAT,
            period VARCHAR(10),
            coins TEXT[],
            backup_reason VARCHAR(100),
            backup_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_mb_version ON models_backup(version);
        CREATE INDEX IF NOT EXISTS idx_mb_backup_at ON models_backup(backup_at DESC);
        CREATE INDEX IF NOT EXISTS idx_mb_original_id ON models_backup(original_id);
    """,
    
    "predictions_backup": """
        CREATE TABLE IF NOT EXISTS predictions_backup (
            id SERIAL PRIMARY KEY,
            original_id INTEGER,
            coin VARCHAR(50) NOT NULL,
            signal_type VARCHAR(20),
            confidence INTEGER,
            prediction_score FLOAT,
            period VARCHAR(10),
            timestamp TIMESTAMP,
            backup_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_pb_coin ON predictions_backup(coin);
        CREATE INDEX IF NOT EXISTS idx_pb_backup_at ON predictions_backup(backup_at DESC);
        CREATE INDEX IF NOT EXISTS idx_pb_original_id ON predictions_backup(original_id);
    """,
    
    "system_state": """
        CREATE TABLE IF NOT EXISTS system_state (
            id SERIAL PRIMARY KEY,
            key VARCHAR(100) UNIQUE NOT NULL,
            value TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_ss_key ON system_state(key);
    """,
    
    "backup_metadata": """
        CREATE TABLE IF NOT EXISTS backup_metadata (
            id SERIAL PRIMARY KEY,
            backup_type VARCHAR(50) NOT NULL,
            source_table VARCHAR(100),
            row_count INTEGER,
            size_mb FLOAT,
            status VARCHAR(20) DEFAULT 'success',
            error_message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_bm_type ON backup_metadata(backup_type);
        CREATE INDEX IF NOT EXISTS idx_bm_created_at ON backup_metadata(created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_bm_status ON backup_metadata(status);
    """,
    
    "cache": """
        CREATE TABLE IF NOT EXISTS cache (
            key VARCHAR(255) PRIMARY KEY,
            value TEXT,
            expires_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_cache_expires ON cache(expires_at);
    """,
}


# ------------------------------------------------------------
# ANALYTICS (Neon #3) - تحلیل و آمار
# ------------------------------------------------------------
SCHEMA_ANALYTICS = {
    "predictions_analytics": """
        CREATE TABLE IF NOT EXISTS predictions_analytics (
            id SERIAL PRIMARY KEY,
            date DATE NOT NULL,
            coin VARCHAR(50),
            total_predictions INTEGER DEFAULT 0,
            buy_count INTEGER DEFAULT 0,
            sell_count INTEGER DEFAULT 0,
            neutral_count INTEGER DEFAULT 0,
            avg_confidence FLOAT DEFAULT 0,
            avg_score FLOAT DEFAULT 0.5,
            correct_predictions INTEGER DEFAULT 0,
            accuracy FLOAT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(date, coin)
        );
        CREATE INDEX IF NOT EXISTS idx_pa_date ON predictions_analytics(date DESC);
        CREATE INDEX IF NOT EXISTS idx_pa_coin ON predictions_analytics(coin);
    """,
    
    "model_performance": """
        CREATE TABLE IF NOT EXISTS model_performance (
            id SERIAL PRIMARY KEY,
            model_version VARCHAR(50),
            date DATE NOT NULL,
            predictions_made INTEGER DEFAULT 0,
            correct_predictions INTEGER DEFAULT 0,
            accuracy FLOAT,
            precision_score FLOAT,
            recall_score FLOAT,
            f1_score FLOAT,
            avg_confidence FLOAT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(model_version, date)
        );
        CREATE INDEX IF NOT EXISTS idx_mp_version ON model_performance(model_version);
        CREATE INDEX IF NOT EXISTS idx_mp_date ON model_performance(date DESC);
    """,
    
    "market_analytics": """
        CREATE TABLE IF NOT EXISTS market_analytics (
            id SERIAL PRIMARY KEY,
            date DATE NOT NULL,
            btc_price DECIMAL(20, 2),
            eth_price DECIMAL(20, 2),
            total_market_cap DECIMAL(30, 2),
            volume_24h DECIMAL(30, 2),
            fear_greed INTEGER,
            btc_dominance DECIMAL(5, 2),
            volatility FLOAT,
            trend VARCHAR(20),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(date)
        );
        CREATE INDEX IF NOT EXISTS idx_ma_date ON market_analytics(date DESC);
        CREATE INDEX IF NOT EXISTS idx_ma_trend ON market_analytics(trend);
    """,
    
    "signal_statistics": """
        CREATE TABLE IF NOT EXISTS signal_statistics (
            id SERIAL PRIMARY KEY,
            coin VARCHAR(50) NOT NULL,
            period VARCHAR(10) NOT NULL,
            signal_type VARCHAR(20) NOT NULL,
            count INTEGER DEFAULT 0,
            avg_confidence FLOAT DEFAULT 0,
            win_rate FLOAT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(coin, period, signal_type)
        );
        CREATE INDEX IF NOT EXISTS idx_ss_coin ON signal_statistics(coin);
        CREATE INDEX IF NOT EXISTS idx_ss_signal ON signal_statistics(signal_type);
    """,
    
    "daily_summary": """
        CREATE TABLE IF NOT EXISTS daily_summary (
            id SERIAL PRIMARY KEY,
            date DATE UNIQUE NOT NULL,
            total_predictions INTEGER DEFAULT 0,
            unique_coins INTEGER DEFAULT 0,
            model_version VARCHAR(50),
            model_accuracy FLOAT,
            market_sentiment VARCHAR(50),
            top_signal VARCHAR(20),
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_ds_date ON daily_summary(date DESC);
    """,
    
    "cache": """
        CREATE TABLE IF NOT EXISTS cache (
            key VARCHAR(255) PRIMARY KEY,
            value TEXT,
            expires_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_cache_expires ON cache(expires_at);
    """,
}


# ------------------------------------------------------------
# LOGS (Neon #4) - لاگ‌ها
# ------------------------------------------------------------
SCHEMA_LOGS = {
    "system_logs": """
        CREATE TABLE IF NOT EXISTS system_logs (
            id SERIAL PRIMARY KEY,
            level VARCHAR(20) NOT NULL,
            source VARCHAR(100),
            message TEXT,
            metadata JSONB,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_sl_level ON system_logs(level);
        CREATE INDEX IF NOT EXISTS idx_sl_created_at ON system_logs(created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_sl_source ON system_logs(source);
    """,
    
    "error_logs": """
        CREATE TABLE IF NOT EXISTS error_logs (
            id SERIAL PRIMARY KEY,
            error_type VARCHAR(100),
            error_message TEXT,
            stack_trace TEXT,
            endpoint VARCHAR(255),
            user_id VARCHAR(100),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_el_type ON error_logs(error_type);
        CREATE INDEX IF NOT EXISTS idx_el_created_at ON error_logs(created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_el_endpoint ON error_logs(endpoint);
    """,
    
    "api_logs": """
        CREATE TABLE IF NOT EXISTS api_logs (
            id SERIAL PRIMARY KEY,
            endpoint VARCHAR(255),
            method VARCHAR(10),
            status_code INTEGER,
            response_time_ms FLOAT,
            user_id VARCHAR(100),
            ip_address VARCHAR(45),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_al_endpoint ON api_logs(endpoint);
        CREATE INDEX IF NOT EXISTS idx_al_created_at ON api_logs(created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_al_status ON api_logs(status_code);
        CREATE INDEX IF NOT EXISTS idx_al_user ON api_logs(user_id);
    """,
    
    "audit_logs": """
        CREATE TABLE IF NOT EXISTS audit_logs (
            id SERIAL PRIMARY KEY,
            user_id VARCHAR(100),
            action VARCHAR(100) NOT NULL,
            resource_type VARCHAR(50),
            resource_id VARCHAR(100),
            old_value TEXT,
            new_value TEXT,
            ip_address VARCHAR(45),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_aul_user_id ON audit_logs(user_id);
        CREATE INDEX IF NOT EXISTS idx_aul_action ON audit_logs(action);
        CREATE INDEX IF NOT EXISTS idx_aul_created_at ON audit_logs(created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_aul_resource ON audit_logs(resource_type, resource_id);
    """,
}


# ------------------------------------------------------------
# ARCHIVE (Layerbase SQLite) - آرشیو
# ------------------------------------------------------------
SCHEMA_ARCHIVE = {
    "predictions_archive": """
        CREATE TABLE IF NOT EXISTS predictions_archive (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            original_id INTEGER,
            coin VARCHAR(50) NOT NULL,
            coin_name VARCHAR(100),
            current_price REAL DEFAULT 0,
            signal_type VARCHAR(20),
            confidence INTEGER,
            prediction_score REAL,
            period VARCHAR(10),
            model_mode VARCHAR(20),
            timestamp TEXT,
            archived_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_par_coin ON predictions_archive(coin);
        CREATE INDEX IF NOT EXISTS idx_par_timestamp ON predictions_archive(timestamp DESC);
        CREATE INDEX IF NOT EXISTS idx_par_original_id ON predictions_archive(original_id);
    """,
    
    "models_archive": """
        CREATE TABLE IF NOT EXISTS models_archive (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            original_id INTEGER,
            version VARCHAR(50) NOT NULL,
            accuracy REAL,
            period VARCHAR(10),
            coins TEXT,
            archived_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_mar_version ON models_archive(version);
        CREATE INDEX IF NOT EXISTS idx_mar_original_id ON models_archive(original_id);
    """,
    
    "logs_archive": """
        CREATE TABLE IF NOT EXISTS logs_archive (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            original_id INTEGER,
            level VARCHAR(20),
            source VARCHAR(100),
            message TEXT,
            created_at TEXT,
            archived_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_lar_level ON logs_archive(level);
        CREATE INDEX IF NOT EXISTS idx_lar_original_id ON logs_archive(original_id);
    """,
    
    "backup_snapshots": """
        CREATE TABLE IF NOT EXISTS backup_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_type VARCHAR(50),
            source_table VARCHAR(100),
            row_count INTEGER,
            size_mb REAL,
            data TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_bs_type ON backup_snapshots(snapshot_type);
        CREATE INDEX IF NOT EXISTS idx_bs_created_at ON backup_snapshots(created_at DESC);
    """,
}


# ============================================================
# Migration Functions
# ============================================================

def execute_schema(
    db,
    schema: Dict[str, str],
    db_name: str,
) -> Dict[str, Any]:
    """
    اجرای schema روی یک دیتابیس
    
    پارامترها:
        db: نمونه دیتابیس
        schema: دیکشنری {table_name: CREATE statement}
        db_name: نام دیتابیس (برای لاگ)
    
    خروجی:
        دیکشنری نتیجه شامل:
            - success: bool
            - tables: لیست جداول ساخته شده
            - errors: لیست خطاها
            - skipped: لیست جداول رد شده
    """
    if db is None:
        logger.warning(f"⚠️ Database '{db_name}' not available")
        return {
            "success": False,
            "error": "not available",
            "tables": [],
            "errors": [],
            "skipped": [],
        }
    
    if not db.is_connected():
        logger.error(f"❌ Database '{db_name}' not connected")
        return {
            "success": False,
            "error": "not connected",
            "tables": [],
            "errors": [],
            "skipped": [],
        }
    
    results = {
        "success": True,
        "tables": [],
        "errors": [],
        "skipped": [],
    }
    
    logger.info(f"🔄 Creating {len(schema)} tables in '{db_name}'...")
    
    for table_name, create_sql in schema.items():
        try:
            # اجرای CREATE TABLE IF NOT EXISTS
            db.execute(create_sql)
            results["tables"].append(table_name)
            logger.debug(f"  ✅ {table_name}")
        except Exception as e:
            error_msg = str(e)
            
            # اگه جدول از قبل وجود داشت، skip کن
            if "already exists" in error_msg.lower():
                results["skipped"].append(table_name)
                logger.debug(f"  ⏭️ {table_name} (already exists)")
            else:
                error_log = f"{table_name}: {error_msg}"
                results["errors"].append(error_log)
                results["success"] = False
                logger.error(f"  ❌ {error_log[:200]}")
    
    logger.info(
        f"✅ '{db_name}': "
        f"{len(results['tables'])} created, "
        f"{len(results['skipped'])} skipped, "
        f"{len(results['errors'])} errors"
    )
    
    return results


def run_migrations() -> Dict[str, Any]:
    """
    اجرای همه migrations روی ۵ دیتابیس
    
    خروجی:
        دیکشنری نتیجه شامل نتایج هر دیتابیس
    """
    logger.info("=" * 70)
    logger.info("🚀 Starting Database Migration")
    logger.info(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 70)
    
    results = {
        "primary": None,
        "backup": None,
        "analytics": None,
        "logs": None,
        "archive": None,
    }
    
    # ---------- ۱. Primary ----------
    logger.info("\n📦 [1/5] Primary Database (Neon #1)")
    results["primary"] = execute_schema(
        get_primary(),
        SCHEMA_PRIMARY,
        "primary",
    )
    
    # ---------- ۲. Backup ----------
    logger.info("\n📦 [2/5] Backup Database (Neon #2)")
    results["backup"] = execute_schema(
        get_backup(),
        SCHEMA_BACKUP,
        "backup",
    )
    
    # ---------- ۳. Analytics ----------
    logger.info("\n📦 [3/5] Analytics Database (Neon #3)")
    results["analytics"] = execute_schema(
        get_analytics(),
        SCHEMA_ANALYTICS,
        "analytics",
    )
    
    # ---------- ۴. Logs ----------
    logger.info("\n📦 [4/5] Logs Database (Neon #4)")
    results["logs"] = execute_schema(
        get_logs_db(),
        SCHEMA_LOGS,
        "logs",
    )
    
    # ---------- ۵. Archive ----------
    logger.info("\n📦 [5/5] Archive Database (Layerbase SQLite)")
    results["archive"] = execute_schema(
        get_archive(),
        SCHEMA_ARCHIVE,
        "archive",
    )
    
    # ---------- خلاصه ----------
    total_created = sum(
        len(r["tables"]) for r in results.values() if r
    )
    total_skipped = sum(
        len(r["skipped"]) for r in results.values() if r
    )
    total_errors = sum(
        len(r["errors"]) for r in results.values() if r
    )
    
    logger.info("\n" + "=" * 70)
    logger.info("📊 Migration Summary")
    logger.info("=" * 70)
    logger.info(f"  ✅ Created: {total_created} tables")
    logger.info(f"  ⏭️  Skipped: {total_skipped} tables (already existed)")
    logger.info(f"  ❌ Errors:  {total_errors}")
    logger.info("=" * 70)
    
    return results


# ============================================================
# Seed Data
# ============================================================

def seed_data() -> Dict[str, Any]:
    """
    داده اولیه
    
    خروجی:
        دیکشنری نتیجه
    """
    logger.info("\n🌱 Seeding initial data...")
    
    results = {
        "users": 0,
        "cache": 0,
        "system_state": 0,
        "errors": [],
    }
    
    db = get_primary()
    if db is None or not db.is_connected():
        logger.error("❌ Primary database not available for seeding")
        results["errors"].append("primary: not connected")
        return results
    
    # ---------- ۱. کاربران پیش‌فرض ----------
    try:
        existing = db.execute("SELECT COUNT(*) as count FROM users")
        
        if existing and existing[0]["count"] == 0:
            db.execute(
                """
                INSERT INTO users (username, password_hash, role, email)
                VALUES 
                    (%s, %s, %s, %s),
                    (%s, %s, %s, %s)
                """,
                (
                    "admin", "Admin@123", "admin", "admin@example.com",
                    "user", "User@123", "user", "user@example.com",
                ),
            )
            results["users"] = 2
            logger.info("  ✅ Created 2 default users (admin, user)")
        else:
            logger.info(
                f"  ⏭️  Users already exist "
                f"({existing[0]['count']} found)"
            )
    except Exception as e:
        results["errors"].append(f"users: {e}")
        logger.error(f"  ❌ users: {e}")
    
    # ---------- ۲. Cache seed ----------
    try:
        db.execute(
            """
            INSERT INTO cache (key, value)
            VALUES (%s, %s)
            ON CONFLICT (key) DO NOTHING
            """,
            ("system_initialized", datetime.now().isoformat()),
        )
        results["cache"] = 1
        logger.info("  ✅ Initialized system cache")
    except Exception as e:
        results["errors"].append(f"cache: {e}")
        logger.error(f"  ❌ cache: {e}")
    
    # ---------- ۳. System State (Backup) ----------
    try:
        backup_db = get_backup()
        if backup_db and backup_db.is_connected():
            backup_db.execute(
                """
                INSERT INTO system_state (key, value)
                VALUES (%s, %s)
                ON CONFLICT (key) DO NOTHING
                """,
                ("initialized_at", datetime.now().isoformat()),
            )
            results["system_state"] = 1
            logger.info("  ✅ Initialized system_state (backup)")
    except Exception as e:
        results["errors"].append(f"system_state: {e}")
        logger.error(f"  ❌ system_state: {e}")
    
    logger.info(
        f"✅ Seeding complete: "
        f"{results['users']} users, "
        f"{results['cache']} cache, "
        f"{results['system_state']} state"
    )
    
    return results


# ============================================================
# Reset (حذف همه جداول)
# ============================================================

def reset_databases(confirm: bool = False) -> None:
    """
    حذف همه جداول (احتیاط!)
    
    پارامترها:
        confirm: تأیید صریح
    """
    if not confirm:
        logger.error("❌ Reset requires --confirm flag")
        logger.error("   Usage: python manage_databases.py --action=reset --confirm")
        return
    
    logger.warning("=" * 70)
    logger.warning("⚠️  RESETTING ALL DATABASES!")
    logger.warning("=" * 70)
    
    schemas = {
        "primary": (get_primary(), SCHEMA_PRIMARY),
        "backup": (get_backup(), SCHEMA_BACKUP),
        "analytics": (get_analytics(), SCHEMA_ANALYTICS),
        "logs": (get_logs_db(), SCHEMA_LOGS),
        "archive": (get_archive(), SCHEMA_ARCHIVE),
    }
    
    total_dropped = 0
    total_errors = 0
    
    for db_name, (db, schema) in schemas.items():
        if db is None or not db.is_connected():
            logger.warning(f"⏭️  '{db_name}' not connected, skipping")
            continue
        
        logger.info(f"🗑️  Dropping tables from '{db_name}'...")
        
        # ترتیب معکوس (FK constraints)
        tables = list(schema.keys())
        
        for table_name in reversed(tables):
            try:
                db.execute(f"DROP TABLE IF EXISTS {table_name} CASCADE")
                total_dropped += 1
                logger.debug(f"  ✅ Dropped {table_name}")
            except Exception as e:
                total_errors += 1
                logger.error(f"  ❌ {table_name}: {e}")
    
    logger.warning("=" * 70)
    logger.warning(
        f"✅ Reset complete: "
        f"{total_dropped} tables dropped, "
        f"{total_errors} errors"
    )
    logger.warning("=" * 70)


# ============================================================
# Status
# ============================================================

def show_status() -> None:
    """نمایش وضعیت دیتابیس‌ها"""
    logger.info("=" * 70)
    logger.info("📊 Database Status")
    logger.info(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 70)
    
    databases = {
        "primary": (get_primary(), SCHEMA_PRIMARY, "postgresql"),
        "backup": (get_backup(), SCHEMA_BACKUP, "postgresql"),
        "analytics": (get_analytics(), SCHEMA_ANALYTICS, "postgresql"),
        "logs": (get_logs_db(), SCHEMA_LOGS, "postgresql"),
        "archive": (get_archive(), SCHEMA_ARCHIVE, "sqlite"),
    }
    
    for db_name, (db, schema, db_type) in databases.items():
        if db is None:
            logger.info(f"❌ {db_name:10s} | NOT AVAILABLE")
            continue
        
        if not db.is_connected():
            logger.info(f"❌ {db_name:10s} | NOT CONNECTED")
            continue
        
        try:
            # شمارش جداول
            if db_type == "sqlite":
                result = db.execute(
                    "SELECT COUNT(*) as count FROM sqlite_master "
                    "WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                )
            else:
                result = db.execute(
                    "SELECT COUNT(*) as count FROM information_schema.tables "
                    "WHERE table_schema = 'public'"
                )
            
            table_count = result[0]["count"] if result else 0
            expected = len(schema)
            
            # وضعیت
            if table_count >= expected:
                emoji = "✅"
                status = "OK"
            elif table_count > 0:
                emoji = "⚠️"
                status = "PARTIAL"
            else:
                emoji = "❌"
                status = "EMPTY"
            
            logger.info(
                f"{emoji} {db_name:10s} | "
                f"{table_count:2d}/{expected:2d} tables | "
                f"{status}"
            )
            
        except Exception as e:
            logger.info(f"⚠️  {db_name:10s} | ERROR: {str(e)[:60]}")
    
    logger.info("=" * 70)


# ============================================================
# Info (جداول دقیق)
# ============================================================

def show_tables_info() -> None:
    """نمایش اطلاعات دقیق جداول"""
    logger.info("\n" + "=" * 70)
    logger.info("📋 Tables Info")
    logger.info("=" * 70)
    
    databases = {
        "primary": (get_primary(), SCHEMA_PRIMARY),
        "backup": (get_backup(), SCHEMA_BACKUP),
        "analytics": (get_analytics(), SCHEMA_ANALYTICS),
        "logs": (get_logs_db(), SCHEMA_LOGS),
        "archive": (get_archive(), SCHEMA_ARCHIVE),
    }
    
    for db_name, (db, schema) in databases.items():
        if db is None or not db.is_connected():
            continue
        
        logger.info(f"\n📦 {db_name.upper()} ({len(schema)} tables)")
        logger.info("-" * 70)
        
        for table_name in schema.keys():
            try:
                # شمارش رکوردها
                count_result = db.execute(
                    f"SELECT COUNT(*) as count FROM {table_name}"
                )
                count = count_result[0]["count"] if count_result else 0
                
                logger.info(f"  • {table_name:30s} | {count:>10,} rows")
            except Exception as e:
                logger.info(f"  • {table_name:30s} | ❌ {str(e)[:30]}")
    
    logger.info("\n" + "=" * 70)


# ============================================================
# Verify
# ============================================================

def verify_schemas() -> Dict[str, Any]:
    """
    بررسی کامل همه جداول
    
    خروجی:
        دیکشنری نتیجه
    """
    logger.info("\n🔍 Verifying schemas...")
    
    databases = {
        "primary": (get_primary(), SCHEMA_PRIMARY),
        "backup": (get_backup(), SCHEMA_BACKUP),
        "analytics": (get_analytics(), SCHEMA_ANALYTICS),
        "logs": (get_logs_db(), SCHEMA_LOGS),
        "archive": (get_archive(), SCHEMA_ARCHIVE),
    }
    
    results = {
        "total_expected": 0,
        "total_found": 0,
        "missing_tables": [],
        "extra_tables": [],
    }
    
    for db_name, (db, schema) in databases.items():
        if db is None or not db.is_connected():
            continue
        
        expected_tables = set(schema.keys())
        results["total_expected"] += len(expected_tables)
        
        try:
            # دریافت جداول موجود
            if db_name == "archive":
                result = db.execute(
                    "SELECT name FROM sqlite_master "
                    "WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                )
            else:
                result = db.execute(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'public'"
                )
            
            existing_tables = {
                row.get("name") or row.get("table_name")
                for row in result
            }
            
            found = expected_tables & existing_tables
            missing = expected_tables - existing_tables
            extra = existing_tables - expected_tables
            
            results["total_found"] += len(found)
            
            for table in missing:
                results["missing_tables"].append(f"{db_name}.{table}")
            
            for table in extra:
                results["extra_tables"].append(f"{db_name}.{table}")
            
            if missing:
                logger.warning(
                    f"  ⚠️  {db_name}: missing {len(missing)} tables"
                )
            else:
                logger.info(f"  ✅ {db_name}: all {len(expected_tables)} tables present")
            
        except Exception as e:
            logger.error(f"  ❌ {db_name}: {e}")
    
    logger.info(
        f"\n📊 Verification: "
        f"{results['total_found']}/{results['total_expected']} tables found"
    )
    
    if results["missing_tables"]:
        logger.warning(f"⚠️  Missing: {results['missing_tables']}")
    
    if results["extra_tables"]:
        logger.info(f"ℹ️  Extra: {results['extra_tables']}")
    
    return results


# ============================================================
# Main
# ============================================================

def main():
    """ورودی اصلی"""
    parser = argparse.ArgumentParser(
        description="Database initialization and management",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python manage_databases.py --action=migrate
  python manage_databases.py --action=seed
  python manage_databases.py --action=status
  python manage_databases.py --action=tables
  python manage_databases.py --action=verify
  python manage_databases.py --action=all
  python manage_databases.py --action=reset --confirm
        """,
    )
    
    parser.add_argument(
        "--action",
        choices=[
            "migrate",
            "seed",
            "reset",
            "status",
            "tables",
            "verify",
            "all",
        ],
        default="migrate",
        help="Action to perform (default: migrate)",
    )
    
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Confirm destructive actions (required for reset)",
    )
    
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose (DEBUG) logging",
    )
    
    args = parser.parse_args()
    
    setup_logging(args.verbose)
    
    # ---------- Dispatch ----------
    if args.action == "status":
        show_status()
    
    elif args.action == "tables":
        show_tables_info()
    
    elif args.action == "verify":
        verify_schemas()
    
    elif args.action == "migrate":
        run_migrations()
        show_status()
    
    elif args.action == "seed":
        seed_data()
    
    elif args.action == "reset":
        reset_databases(confirm=args.confirm)
    
    elif args.action == "all":
        logger.info("🚀 Running full initialization...")
        logger.info("")
        
        # ۱. Migration
        run_migrations()
        
        # ۲. Seed
        seed_data()
        
        # ۳. Verify
        verify_schemas()
        
        # ۴. Status
        show_status()
        
        logger.info("\n" + "=" * 70)
        logger.info("✅ Full initialization complete!")
        logger.info("=" * 70)


if __name__ == "__main__":
    main()
