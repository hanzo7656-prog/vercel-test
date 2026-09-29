# infrastructure/repositories/rule_config_repository.py
# ============================================================
# Repository: Rule Config - ذخیره overrideهای کاربر
# نسخه ۱.۰
# ============================================================
# 
# نقش:
#   - ذخیره overrideهای config در PostgreSQL
#   - ترکیب با default config (merge)
#   - تاریخچه تغییرات config
# 
# چرا override جدا؟
#   default_rules.json  → در git، ثابت
#   rule_config_overrides → در DB، قابل تغییر runtime
# ============================================================

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from infrastructure.database import get_primary

logger = logging.getLogger(__name__)


# ============================================================
# RuleConfigRepository
# ============================================================

class RuleConfigRepository:
    """
    Repository برای ذخیره overrideهای config
    
    جدول: rule_config_overrides
    ساختار:
        - id: SERIAL
        - name: TEXT UNIQUE (rule name یا section)
        - config: JSONB
        - updated_at: TIMESTAMP
        - updated_by: VARCHAR (اختیاری)
    """
    
    TABLE_NAME = "rule_config_overrides"
    
    def __init__(self) -> None:
        self._db = None
        logger.info("✅ RuleConfigRepository initialized")
    
    # ============================================================
    # DB Helper
    # ============================================================
    
    @property
    def db(self):
        """دیتابیس primary"""
        if self._db is None or not self._db.is_connected():
            self._db = get_primary()
        return self._db
    
    def _ensure_db(self) -> bool:
        """اطمینان از اتصال"""
        if self._db is None or not self._db.is_connected():
            self._db = get_primary()
        return self._db is not None and self._db.is_connected()
    
    def _ensure_table(self) -> None:
        """ساخت جدول اگه نبود"""
        if not self._ensure_db():
            return
        
        try:
            self.db.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {self.TABLE_NAME} (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(100) NOT NULL UNIQUE,
                    config JSONB NOT NULL,
                    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    updated_by VARCHAR(100)
                )
                """
            )
            self.db.execute(
                f"""
                CREATE INDEX IF NOT EXISTS idx_{self.TABLE_NAME}_name
                ON {self.TABLE_NAME} (name)
                """
            )
        except Exception as e:
            logger.warning(f"⚠️ Failed to ensure table: {e}")
    
    # ============================================================
    # Save
    # ============================================================
    
    def save_override(
        self,
        name: str,
        config: Dict[str, Any],
        updated_by: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        ذخیره یا آپدیت override
        
        Args:
            name: نام (مثلاً "rules" یا "rules.rsi")
            config: config جدید
            updated_by: کاربر
        
        Returns:
            {success, name, updated_at}
        """
        if not self._ensure_db():
            return {"success": False, "error": "Database not connected"}
        
        try:
            self._ensure_table()
            
            result = self.db.execute(
                f"""
                INSERT INTO {self.TABLE_NAME} (name, config, updated_at, updated_by)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (name) DO UPDATE
                SET config = EXCLUDED.config,
                    updated_at = EXCLUDED.updated_at,
                    updated_by = EXCLUDED.updated_by
                RETURNING name, updated_at
                """,
                (
                    name,
                    json.dumps(config),
                    datetime.now(),
                    updated_by,
                ),
            )
            
            logger.info(f"✅ Override saved: {name}")
            
            return {
                "success": True,
                "name": name,
                "updated_at": (
                    result[0]["updated_at"].isoformat() if result else None
                ),
            }
        except Exception as e:
            logger.error(f"❌ Save override failed: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
    
    def save_rules_override(
        self,
        rules_config: Dict[str, Dict[str, Any]],
        updated_by: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        ذخیره override کامل rules
        
        Args:
            rules_config: {rule_name: rule_config}
        """
        return self.save_override(
            name="rules",
            config=rules_config,
            updated_by=updated_by,
        )
    
    def save_scoring_override(
        self,
        scoring_config: Dict[str, Any],
        updated_by: Optional[str] = None,
    ) -> Dict[str, Any]:
        """ذخیره override scoring"""
        return self.save_override(
            name="scoring",
            config=scoring_config,
            updated_by=updated_by,
        )
    
    # ============================================================
    # Load
    # ============================================================
    
    def get_override(self, name: str) -> Optional[Dict[str, Any]]:
        """
        دریافت یک override
        
        Args:
            name: نام
        
        Returns:
            config یا None
        """
        if not self._ensure_db():
            return None
        
        try:
            self._ensure_table()
            
            result = self.db.execute(
                f"""
                SELECT config, updated_at, updated_by
                FROM {self.TABLE_NAME}
                WHERE name = %s
                """,
                (name,),
            )
            
            if not result:
                return None
            
            row = result[0]
            config = row["config"]
            
            # اگه به‌عنوان JSON string ذخیره شده
            if isinstance(config, str):
                config = json.loads(config)
            
            return config
        except Exception as e:
            logger.error(f"❌ Get override failed: {e}")
            return None
    
    def get_all_overrides(self) -> Dict[str, Any]:
        """
        دریافت همه overrideها
        
        Returns:
            {name: config}
        """
        if not self._ensure_db():
            return {}
        
        try:
            self._ensure_table()
            
            result = self.db.execute(
                f"""
                SELECT name, config, updated_at, updated_by
                FROM {self.TABLE_NAME}
                ORDER BY name
                """
            )
            
            overrides: Dict[str, Any] = {}
            for row in result or []:
                config = row["config"]
                if isinstance(config, str):
                    config = json.loads(config)
                overrides[row["name"]] = config
            
            return overrides
        except Exception as e:
            logger.error(f"❌ Get all overrides failed: {e}")
            return {}
    
    # ============================================================
    # Merge
    # ============================================================
    
    def get_effective_config(
        self,
        default_config: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        ترکیب default config با overrideهای DB
        
        منطق merge:
            - برای هر کلید در override، جایگزین default می‌شه
            - برای rules، merge در سطح rule انجام می‌شه
              (مثلاً override فقط weight رو عوض کنه)
        
        Args:
            default_config: config پیش‌فرض از JSON
        
        Returns:
            config نهایی
        """
        overrides = self.get_all_overrides()
        
        if not overrides:
            return default_config.copy()
        
        # کپی عمیق
        import copy
        effective = copy.deepcopy(default_config)
        
        for section, override_value in overrides.items():
            # ============================================================
            # حالت ویژه: rules
            # merge در سطح هر rule
            # ============================================================
            if section == "rules" and "rules" in effective:
                if isinstance(override_value, dict):
                    for rule_name, rule_override in override_value.items():
                        if rule_name in effective["rules"]:
                            # merge در سطح rule
                            effective["rules"][rule_name].update(
                                rule_override
                            )
                        else:
                            # rule جدید
                            effective["rules"][rule_name] = rule_override
            
            # ============================================================
            # حالت ویژه: scoring
            # ============================================================
            elif section == "scoring" and "scoring" in effective:
                if isinstance(override_value, dict):
                    effective["scoring"].update(override_value)
            
            # ============================================================
            # بقیه: override کامل
            # ============================================================
            else:
                effective[section] = override_value
        
        return effective
    
    # ============================================================
    # Delete
    # ============================================================
    
    def delete_override(self, name: str) -> Dict[str, Any]:
        """حذف یک override"""
        if not self._ensure_db():
            return {"success": False, "error": "Database not connected"}
        
        try:
            self._ensure_table()
            
            self.db.execute(
                f"DELETE FROM {self.TABLE_NAME} WHERE name = %s",
                (name,),
            )
            
            logger.info(f"✅ Override deleted: {name}")
            return {"success": True, "name": name}
        except Exception as e:
            logger.error(f"❌ Delete override failed: {e}")
            return {"success": False, "error": str(e)}
    
    def reset_all(self) -> Dict[str, Any]:
        """حذف همه overrideها (بازگشت به default)"""
        if not self._ensure_db():
            return {"success": False, "error": "Database not connected"}
        
        try:
            self._ensure_table()
            
            self.db.execute(f"DELETE FROM {self.TABLE_NAME}")
            
            logger.info("✅ All overrides reset")
            return {"success": True}
        except Exception as e:
            logger.error(f"❌ Reset all failed: {e}")
            return {"success": False, "error": str(e)}
    
    # ============================================================
    # Stats
    # ============================================================
    
    def get_stats(self) -> Dict[str, Any]:
        """آمار Repository"""
        if not self._ensure_db():
            return {"connected": False}
        
        try:
            self._ensure_table()
            
            result = self.db.execute(
                f"SELECT COUNT(*) as count FROM {self.TABLE_NAME}"
            )
            count = result[0]["count"] if result else 0
            
            return {
                "connected": True,
                "override_count": count,
                "table": self.TABLE_NAME,
            }
        except Exception as e:
            return {"connected": False, "error": str(e)}


# ============================================================
# Singleton
# ============================================================

rule_config_repository = RuleConfigRepository()


__all__ = [
    "RuleConfigRepository",
    "rule_config_repository",
]
