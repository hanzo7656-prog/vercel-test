# infrastructure/repositories/settings_repository.py
# ============================================================
# Repository: Settings - تنظیمات کاربر
# ============================================================

import json
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime

from infrastructure.database import get_primary

logger = logging.getLogger(__name__)


class SettingsRepository:
    """
    Repository برای تنظیمات کاربر
    
    ذخیره در جدول app_settings (PostgreSQL)
    """
    
    DEFAULT_SETTINGS: Dict[str, Dict[str, Any]] = {
        "scheduler": {
            "metrics": {"enabled": True, "interval": 10000},
            "appStats": {"enabled": True, "interval": 3000},
            "alerts": {"enabled": True, "interval": 30000},
            "dbHealth": {"enabled": True, "interval": 60000},
            "modelStatus": {"enabled": False, "interval": 15000},
            "quotas": {"enabled": False, "interval": 120000},
        },
        "theme": {
            "mode": "dark",
            "accent": "cyan",
            "fontSize": 16,
            "font": "Vazir",
        },
        "cache": {
            "coinsList": 86400,
            "prices": 60,
            "fearGreed": 300,
            "btcDominance": 300,
            "modelStatus": 10,
            "chart": 3600,
        },
        "notifications": {
            "enabled": True,
            "sound": True,
            "criticalOnly": False,
            "doNotDisturb": False,
            "dndStart": "22:00",
            "dndEnd": "08:00",
        },
        "dashboard": {
            "showMetrics": True,
            "showPrices": True,
            "showAlerts": True,
            "showModel": True,
            "defaultTab": "dashboard",
        },
    }
    
    def __init__(self) -> None:
        self.db = get_primary()
        logger.info("✅ SettingsRepository initialized")
    
    def _ensure_db(self) -> bool:
        if not self.db or not self.db.is_connected():
            self.db = get_primary()
        return self.db is not None and self.db.is_connected()
    
    # ============================================================
    # Schema
    # ============================================================
    
    @classmethod
    def get_schema_sql(cls) -> str:
        """SQL برای ساخت جدول"""
        return """
            CREATE TABLE IF NOT EXISTS app_settings (
                id SERIAL PRIMARY KEY,
                user_id INTEGER,
                category VARCHAR(50) NOT NULL,
                value JSONB NOT NULL DEFAULT '{}'::jsonb,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            
            CREATE INDEX IF NOT EXISTS idx_settings_user_category 
                ON app_settings(user_id, category);
            
            CREATE INDEX IF NOT EXISTS idx_settings_user 
                ON app_settings(user_id);
        """
    
    # ============================================================
    # Get
    # ============================================================
    
    def get_category(
        self,
        category: str,
        user_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        دریافت تنظیمات یک دسته
        
        اگه در DB نباشه، default برمی‌گردونه
        """
        if not self._ensure_db():
            return self.DEFAULT_SETTINGS.get(category, {})
        
        try:
            result = self.db.execute(
                """
                SELECT value FROM app_settings
                WHERE category = %s
                  AND (user_id = %s OR (user_id IS NULL AND %s IS NULL))
                ORDER BY id DESC LIMIT 1
                """,
                (category, user_id, user_id),
            )
            
            if result and result[0].get("value"):
                value = result[0]["value"]
                if isinstance(value, str):
                    value = json.loads(value)
                return value
            
            # Fallback به default
            return self.DEFAULT_SETTINGS.get(category, {}).copy()
            
        except Exception as e:
            logger.error(f"❌ Get category error: {e}")
            return self.DEFAULT_SETTINGS.get(category, {}).copy()
    
    def get_all(self, user_id: Optional[int] = None) -> Dict[str, Any]:
        """دریافت همه تنظیمات"""
        if not self._ensure_db():
            return self._get_defaults()
        
        try:
            result = self.db.execute(
                """
                SELECT category, value FROM app_settings
                WHERE user_id = %s OR (user_id IS NULL AND %s IS NULL)
                ORDER BY category, id DESC
                """,
                (user_id, user_id),
            )
            
            settings = self._get_defaults()
            
            for row in result:
                category = row["category"]
                value = row["value"]
                
                if isinstance(value, str):
                    value = json.loads(value)
                
                settings[category] = value
            
            return settings
            
        except Exception as e:
            logger.error(f"❌ Get all settings error: {e}")
            return self._get_defaults()
    
    def _get_defaults(self) -> Dict[str, Any]:
        """کپی از default settings"""
        return json.loads(json.dumps(self.DEFAULT_SETTINGS))
    
    # ============================================================
    # Save
    # ============================================================
    
    def save_category(
        self,
        category: str,
        value: Dict[str, Any],
        user_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """ذخیره تنظیمات یک دسته"""
        if not self._ensure_db():
            return {"success": False, "error": "Database not connected"}
        
        try:
            value_json = json.dumps(value)
            
            result = self.db.execute(
                """
                INSERT INTO app_settings (user_id, category, value, updated_at)
                VALUES (%s, %s, %s, NOW())
                ON CONFLICT (user_id, category) 
                DO UPDATE SET 
                    value = EXCLUDED.value,
                    updated_at = NOW()
                RETURNING id, category
                """,
                (user_id, category, value_json),
            )
            
            logger.info(f"✅ Settings saved: {category} (user: {user_id})")
            
            return {
                "success": True,
                "category": category,
                "value": value,
                "id": result[0]["id"] if result else None,
            }
            
        except Exception as e:
            logger.error(f"❌ Save category error: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
    
    def save_all(
        self,
        settings: Dict[str, Any],
        user_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """ذخیره همه تنظیمات"""
        results = {}
        
        for category, value in settings.items():
            results[category] = self.save_category(category, value, user_id)
        
        success = all(r.get("success") for r in results.values())
        
        return {
            "success": success,
            "results": results,
        }
    
    # ============================================================
    # Reset
    # ============================================================
    
    def reset_category(
        self,
        category: str,
        user_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """ریست یک دسته"""
        if not self._ensure_db():
            return {"success": False, "error": "Database not connected"}
        
        try:
            self.db.execute(
                """
                DELETE FROM app_settings
                WHERE category = %s
                  AND (user_id = %s OR (user_id IS NULL AND %s IS NULL))
                """,
                (category, user_id, user_id),
            )
            
            default_value = self.DEFAULT_SETTINGS.get(category, {})
            
            logger.info(f"✅ Settings reset: {category}")
            
            return {
                "success": True,
                "category": category,
                "value": default_value,
            }
            
        except Exception as e:
            logger.error(f"❌ Reset error: {e}")
            return {"success": False, "error": str(e)}
    
    def reset_all(self, user_id: Optional[int] = None) -> Dict[str, Any]:
        """ریست همه"""
        if not self._ensure_db():
            return {"success": False, "error": "Database not connected"}
        
        try:
            self.db.execute(
                """
                DELETE FROM app_settings
                WHERE user_id = %s OR (user_id IS NULL AND %s IS NULL)
                """,
                (user_id, user_id),
            )
            
            logger.info(f"✅ All settings reset")
            
            return {
                "success": True,
                "settings": self._get_defaults(),
            }
            
        except Exception as e:
            logger.error(f"❌ Reset all error: {e}")
            return {"success": False, "error": str(e)}
    
    # ============================================================
    # Categories
    # ============================================================
    
    def get_categories(self) -> List[str]:
        """لیست دسته‌ها"""
        return list(self.DEFAULT_SETTINGS.keys())
