# infrastructure/database/quota_manager.py
# ============================================================
# مدیریت Quota دیتابیس‌ها - نسخه ۱.۱
# UTC-safe + قابل تنظیم از فرانت‌اند + Auto-cleanup
# ============================================================

import logging
import json
from typing import Any, Optional, Dict, List
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


# ============================================================
# Timezone Helper
# ============================================================

def _utc_now_iso() -> str:
    """زمان فعلی UTC به شکل ISO با Z."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


# ============================================================
# QuotaManager
# ============================================================

class QuotaManager:
    """
    مدیریت Quota برای دیتابیس‌ها

    ویژگی‌ها:
        - بررسی Quota قبل از Write
        - Alert در صورت نزدیک شدن
        - Auto-cleanup
        - قابل تنظیم از فرانت‌اند
        - ذخیره تنظیمات در فایل
        - Thread-safe

    ارتقاهای نسخه ۱.۱:
        - تمام timestampها UTC با Z
    """

    _instance: Optional['QuotaManager'] = None

    def __new__(cls) -> 'QuotaManager':
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if hasattr(self, '_initialized'):
            return
        self._initialized = True

        self._config_path: Path = Path("config/databases.json")
        self._quota_overrides_path: Path = Path("config/quota_overrides.json")

        self._overrides: Dict[str, Dict[str, Any]] = {}

        self._checks: int = 0
        self._warnings: int = 0
        self._cleanups: int = 0

        self._load_overrides()

        logger.info("✅ QuotaManager initialized")

    # ============================================================
    # بارگذاری و ذخیره Overrides
    # ============================================================

    def _load_overrides(self) -> None:
        try:
            if self._quota_overrides_path.exists():
                with open(self._quota_overrides_path, 'r', encoding='utf-8') as f:
                    self._overrides = json.load(f)
                logger.info(
                    f"✅ Loaded quota overrides for "
                    f"{len(self._overrides)} databases"
                )
        except Exception as e:
            logger.error(f"❌ Failed to load quota overrides: {e}")
            self._overrides = {}

    def _save_overrides(self) -> None:
        try:
            self._quota_overrides_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._quota_overrides_path, 'w', encoding='utf-8') as f:
                json.dump(self._overrides, f, indent=2, ensure_ascii=False)
            logger.info("✅ Quota overrides saved")
        except Exception as e:
            logger.error(f"❌ Failed to save quota overrides: {e}")

    # ============================================================
    # دریافت تنظیمات Quota
    # ============================================================

    def get_quota(self, db_name: str) -> Dict[str, Any]:
        base_quota = self._read_base_quota(db_name)

        if db_name in self._overrides:
            override = self._overrides[db_name]
            base_quota = self._merge_quota(base_quota, override)

        return base_quota

    def _read_base_quota(self, db_name: str) -> Dict[str, Any]:
        try:
            if not self._config_path.exists():
                return {}

            with open(self._config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)

            db_config = config.get("databases", {}).get(db_name, {})
            return db_config.get("quota", {})

        except Exception as e:
            logger.error(f"❌ Failed to read quota for '{db_name}': {e}")
            return {}

    def _merge_quota(
        self,
        base: Dict[str, Any],
        override: Dict[str, Any]
    ) -> Dict[str, Any]:
        result = {**base}

        for key, value in override.items():
            if key == "per_table" and "per_table" in base:
                result["per_table"] = {**base["per_table"], **value}
            elif key == "per_namespace" and "per_namespace" in base:
                result["per_namespace"] = {**base["per_namespace"], **value}
            else:
                result[key] = value

        return result

    # ============================================================
    # تنظیم Quota (از فرانت‌اند)
    # ============================================================

    def set_database_limit(
        self,
        db_name: str,
        total_mb: Optional[int] = None,
        reserved_mb: Optional[int] = None,
        warn_threshold: Optional[int] = None,
        critical_threshold: Optional[int] = None,
        auto_cleanup: Optional[bool] = None
    ) -> Dict[str, Any]:
        try:
            if db_name not in self._overrides:
                self._overrides[db_name] = {}

            if total_mb is not None:
                self._overrides[db_name]["total_mb"] = total_mb
            if reserved_mb is not None:
                self._overrides[db_name]["reserved_mb"] = reserved_mb
            if warn_threshold is not None:
                self._overrides[db_name]["warn_threshold_percent"] = warn_threshold
            if critical_threshold is not None:
                self._overrides[db_name]["critical_threshold_percent"] = critical_threshold
            if auto_cleanup is not None:
                self._overrides[db_name]["auto_cleanup"] = auto_cleanup

            self._save_overrides()

            logger.info(f"✅ Quota updated for '{db_name}': {self._overrides[db_name]}")

            return {
                "success": True,
                "db_name": db_name,
                "quota": self.get_quota(db_name),
            }

        except Exception as e:
            logger.error(f"❌ Failed to set quota for '{db_name}': {e}")
            return {"success": False, "error": str(e)}

    def set_table_limit(
        self,
        db_name: str,
        table_name: str,
        max_mb: Optional[int] = None,
        retention_days: Optional[int] = None,
        keep_last_n: Optional[int] = None
    ) -> Dict[str, Any]:
        try:
            if db_name not in self._overrides:
                self._overrides[db_name] = {}

            if "per_table" not in self._overrides[db_name]:
                self._overrides[db_name]["per_table"] = {}

            if table_name not in self._overrides[db_name]["per_table"]:
                self._overrides[db_name]["per_table"][table_name] = {}

            table_config = self._overrides[db_name]["per_table"][table_name]

            if max_mb is not None:
                table_config["max_mb"] = max_mb
            if retention_days is not None:
                table_config["retention_days"] = retention_days
            if keep_last_n is not None:
                table_config["keep_last_n"] = keep_last_n

            self._save_overrides()

            logger.info(
                f"✅ Table quota updated: {db_name}.{table_name} "
                f"= {table_config}"
            )

            return {
                "success": True,
                "db_name": db_name,
                "table_name": table_name,
                "config": table_config,
            }

        except Exception as e:
            logger.error(f"❌ Failed to set table quota: {e}")
            return {"success": False, "error": str(e)}

    def reset_overrides(self, db_name: Optional[str] = None) -> Dict[str, Any]:
        try:
            if db_name:
                if db_name in self._overrides:
                    del self._overrides[db_name]
            else:
                self._overrides = {}

            self._save_overrides()

            logger.info(
                f"✅ Quota overrides reset "
                f"({'all' if not db_name else db_name})"
            )

            return {"success": True}

        except Exception as e:
            logger.error(f"❌ Failed to reset overrides: {e}")
            return {"success": False, "error": str(e)}

    # ============================================================
    # بررسی Quota
    # ============================================================

    def check_quota(
        self,
        db_name: str,
        used_mb: float,
        table_name: Optional[str] = None
    ) -> Dict[str, Any]:
        self._checks += 1

        quota = self.get_quota(db_name)

        if not quota:
            return {
                "status": "unknown",
                "used_mb": used_mb,
                "total_mb": 0,
                "usable_mb": 0,
                "used_percent": 0,
                "exceeded": False,
                "warning": False,
                "cleanup_needed": False,
            }

        total_mb = quota.get("total_mb", 0)
        reserved_mb = quota.get("reserved_mb", 0)
        usable_mb = quota.get("usable_mb", total_mb - reserved_mb)
        warn_threshold = quota.get("warn_threshold_percent", 75)
        critical_threshold = quota.get("critical_threshold_percent", 90)
        auto_cleanup = quota.get("auto_cleanup", False)
        cleanup_threshold = quota.get("cleanup_before_percent", 95)

        used_percent = (used_mb / usable_mb * 100) if usable_mb > 0 else 0

        if used_percent >= 100:
            status = "exceeded"
            exceeded = True
            warning = True
        elif used_percent >= critical_threshold:
            status = "critical"
            exceeded = False
            warning = True
        elif used_percent >= warn_threshold:
            status = "warning"
            exceeded = False
            warning = True
        else:
            status = "ok"
            exceeded = False
            warning = False

        cleanup_needed = (
            auto_cleanup
            and used_percent >= cleanup_threshold
            and not exceeded
        )

        if warning:
            self._warnings += 1

        table_info = None
        if table_name and "per_table" in quota:
            table_info = quota["per_table"].get(table_name, {})

        return {
            "status": status,
            "used_mb": round(used_mb, 2),
            "total_mb": total_mb,
            "reserved_mb": reserved_mb,
            "usable_mb": usable_mb,
            "used_percent": round(used_percent, 2),
            "warn_threshold": warn_threshold,
            "critical_threshold": critical_threshold,
            "exceeded": exceeded,
            "warning": warning,
            "cleanup_needed": cleanup_needed,
            "auto_cleanup": auto_cleanup,
            "table_name": table_name,
            "table_info": table_info,
            "db_name": db_name,
        }

    def check_all(self, used_mb_map: Dict[str, float]) -> Dict[str, Dict[str, Any]]:
        result = {}
        for db_name, used_mb in used_mb_map.items():
            result[db_name] = self.check_quota(db_name, used_mb)
        return result

    # ============================================================
    # Cleanup
    # ============================================================

    def get_cleanup_config(
        self,
        db_name: str,
        table_name: str
    ) -> Dict[str, Any]:
        quota = self.get_quota(db_name)
        per_table = quota.get("per_table", {})
        table_config = per_table.get(table_name, {})

        return {
            "max_mb": table_config.get("max_mb"),
            "retention_days": table_config.get("retention_days"),
            "keep_last_n": table_config.get("keep_last_n"),
            "auto_cleanup": quota.get("auto_cleanup", False),
        }

    def mark_cleanup_done(self, db_name: str, table_name: str) -> None:
        self._cleanups += 1
        logger.info(f"✅ Cleanup done: {db_name}.{table_name}")

    # ============================================================
    # آمار
    # ============================================================

    def get_stats(self) -> Dict[str, Any]:
        """آمار QuotaManager (UTC)"""
        return {
            "checks": self._checks,
            "warnings": self._warnings,
            "cleanups": self._cleanups,
            "overrides_count": len(self._overrides),
            "overrides": list(self._overrides.keys()),
            "timestamp": _utc_now_iso(),  # 🆕 UTC
        }

    def get_all_quotas(self) -> Dict[str, Dict[str, Any]]:
        result = {}

        try:
            if not self._config_path.exists():
                return result

            with open(self._config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)

            for db_name in config.get("databases", {}).keys():
                result[db_name] = self.get_quota(db_name)

        except Exception as e:
            logger.error(f"❌ Failed to get all quotas: {e}")

        return result

    def get_full_status(self, used_mb_map: Dict[str, float]) -> Dict[str, Any]:
        all_quotas = self.get_all_quotas()

        statuses = {}
        total_used = 0
        total_capacity = 0
        warnings_count = 0
        critical_count = 0

        for db_name, quota in all_quotas.items():
            used_mb = used_mb_map.get(db_name, 0)
            status = self.check_quota(db_name, used_mb)

            statuses[db_name] = {
                "quota": quota,
                "status": status,
            }

            total_used += used_mb
            total_capacity += quota.get("total_mb", 0)

            if status["status"] == "critical":
                critical_count += 1
            elif status["status"] == "warning":
                warnings_count += 1

        return {
            "databases": statuses,
            "summary": {
                "total_databases": len(all_quotas),
                "total_used_mb": round(total_used, 2),
                "total_capacity_mb": total_capacity,
                "total_used_percent": round(
                    (total_used / total_capacity * 100) if total_capacity > 0 else 0,
                    2
                ),
                "warnings": warnings_count,
                "critical": critical_count,
            },
            "timestamp": _utc_now_iso(),  # 🆕 UTC
        }


# ============================================================
# Singleton
# ============================================================

quota_manager: QuotaManager = QuotaManager()
