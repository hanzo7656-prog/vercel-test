# infrastructure/repositories/ohlcv_repository.py
# ============================================================
# Repository: OHLCV History - نسخه ۲.۰
# Two-Phase Loading (DB → API → Merge) + Timezone-safe + Logging
# ============================================================

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from domain.interfaces.repository import Repository
from infrastructure.database import get_primary, get_cache

logger = logging.getLogger(__name__)


# ============================================================
# Constants
# ============================================================

TABLE_NAME = "ohlcv_history"

VALID_INTERVALS = ["5m", "15m", "30m", "1h", "4h", "1d", "1w"]

# TTL برای cache
CACHE_TTL = 1800  # ۳۰ دقیقه

# حداکثر کندل برای ذخیره در DB (جلوگیری از انفجار داده)
MAX_CANDLES_TO_SAVE = 2000

# حداکثر کندل در یک درخواست از API
MAX_CANDLES_FROM_API = 1500

# حداقل کندل برای استفاده از DB (اگه کمتر بود، از API گرفته می‌شود)
DEFAULT_MIN_CANDLES = 100


# ============================================================
# Staleness Tolerance per interval
# ============================================================
# اگه آخرین کندل DB از این مقدار قدیمی‌تر بود → refresh از API
# قاعده: ۲ تا ۳ برابر interval (با کمی ارفاق)
STALENESS_TOLERANCE_SECONDS: Dict[str, int] = {
    "5m":  15 * 60,          # ۱۵ دقیقه
    "15m": 45 * 60,          # ۴۵ دقیقه
    "30m": 90 * 60,          # ۱.۵ ساعت
    "1h":  3 * 3600,         # ۳ ساعت
    "4h":  12 * 3600,        # ۱۲ ساعت
    "1d":  3 * 86400,        # ۳ روز
    "1w":  14 * 86400,       # ۲ هفته
}


# ============================================================
# OHLCVRepository
# ============================================================

class OHLCVRepository(Repository):
    """
    Repository برای OHLCV History — نسخه ۲.۰

    رویکرد دو زمانه:
        ۱. تلاش از DB (اگه تازه و کافی بود) → source=DB
        ۲. اگه نه: API → merge با DB → source=HYBRID یا source=API
        ۳. اگه API خطا داد ولی DB داشت → source=DB_FALLBACK
        ۴. اگه هیچ‌کدام نبود → None (خطا در endpoint)

    نکات:
        - تمام timestampها UTC هستند (naive در DB برای سازگاری با schema موجود)
        - ذخیره با execute_values (نه execute_many) برای پشتیبانی ON CONFLICT
        - لاگ واضح برای تشخیص منبع داده
    """

    TABLE_NAME = TABLE_NAME
    CACHE_PREFIX = "ohlcv_cache"
    CACHE_TTL = CACHE_TTL

    def __init__(self) -> None:
        self._db = None
        self._cache = None
        self._schema_ensured = False

        logger.info("✅ OHLCVRepository v2.0 initialized")

    # ============================================================
    # Lazy properties
    # ============================================================

    @property
    def db(self):
        """DB primary"""
        if self._db is None or not self._db.is_connected():
            self._db = get_primary()
        return self._db

    @property
    def cache(self):
        """Cache"""
        if self._cache is None or not self._cache.is_connected():
            self._cache = get_cache()
        return self._cache

    def _ensure_db(self) -> bool:
        """اطمینان از اتصال"""
        if self._db is None or not self._db.is_connected():
            self._db = get_primary()
        return self._db is not None and self._db.is_connected()

    # ============================================================
    # Timezone Helpers
    # ============================================================

    @staticmethod
    def _utc_now_naive() -> datetime:
        """
        زمان فعلی UTC به شکل naive
        (چون schema از TIMESTAMP WITHOUT TIME ZONE استفاده می‌کند)
        """
        return datetime.now(timezone.utc).replace(tzinfo=None)

    @staticmethod
    def _to_utc_naive(dt: Any) -> Optional[datetime]:
        """تبدیل هر ورودی به UTC naive"""
        if dt is None:
            return None

        try:
            # اگه pandas Timestamp بود
            if hasattr(dt, "to_pydatetime"):
                dt = dt.to_pydatetime()

            if not isinstance(dt, datetime):
                return None

            # اگه timezone داشت → به UTC تبدیل کن، بعد tz حذف کن
            if dt.tzinfo is not None:
                return dt.astimezone(timezone.utc).replace(tzinfo=None)

            # naive → فرض کن UTC است
            return dt

        except Exception:
            return None

    # ============================================================
    # Schema Ensure
    # ============================================================

    def _ensure_schema(self) -> None:
        """ساخت جدول اگه نبود"""
        if self._schema_ensured:
            return

        if not self._ensure_db():
            return

        try:
            self.db.execute("""
                CREATE TABLE IF NOT EXISTS ohlcv_history (
                    id BIGSERIAL PRIMARY KEY,
                    symbol VARCHAR(50) NOT NULL,
                    interval VARCHAR(10) NOT NULL,
                    timestamp TIMESTAMP NOT NULL,
                    open DECIMAL(20, 8) NOT NULL,
                    high DECIMAL(20, 8) NOT NULL,
                    low DECIMAL(20, 8) NOT NULL,
                    close DECIMAL(20, 8) NOT NULL,
                    volume DECIMAL(30, 8) DEFAULT 0,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)

            self.db.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_ohlcv_unique
                ON ohlcv_history (symbol, interval, timestamp)
            """)

            self.db.execute("""
                CREATE INDEX IF NOT EXISTS idx_ohlcv_symbol_interval
                ON ohlcv_history (symbol, interval, timestamp DESC)
            """)

            self.db.execute("""
                CREATE INDEX IF NOT EXISTS idx_ohlcv_created
                ON ohlcv_history (created_at DESC)
            """)

            self._schema_ensured = True
            logger.debug("✅ OHLCVRepository: schema ensured")

        except Exception as e:
            logger.warning(f"⚠️ OHLCV schema ensure failed: {e}")

    # ============================================================
    # SAVE
    # ============================================================

    def save_candles(
        self,
        symbol: str,
        interval: str,
        candles: List[List],
        skip_existing: bool = True,
    ) -> Dict[str, Any]:
        """
        ذخیره candles در DB

        از execute_values استفاده می‌کند (نه execute_many)
        چون ON CONFLICT با executemany در psycopg2 درست کار نمی‌کند.
        """
        if not self._ensure_db():
            return {"success": False, "error": "Database not connected", "saved": 0}

        if interval not in VALID_INTERVALS:
            return {"success": False, "error": f"Invalid interval: {interval}", "saved": 0}

        if not candles:
            return {"success": True, "saved": 0, "skipped": 0, "errors": 0}

        self._ensure_schema()

        # محدودیت تعداد
        if len(candles) > MAX_CANDLES_TO_SAVE:
            candles = candles[-MAX_CANDLES_TO_SAVE:]

        try:
            rows: List[Tuple] = []
            for c in candles:
                if not isinstance(c, (list, tuple)) or len(c) < 6:
                    continue
                try:
                    ts_ms = int(c[0])
                    ts = pd.to_datetime(ts_ms, unit="ms", utc=True, errors="coerce")
                    if pd.isna(ts):
                        continue
                    ts_naive_utc = ts.tz_localize(None).to_pydatetime()

                    rows.append((
                        symbol,
                        interval,
                        ts_naive_utc,
                        float(c[1]),
                        float(c[2]),
                        float(c[3]),
                        float(c[4]),
                        float(c[5]) if c[5] is not None else 0.0,
                    ))
                except (ValueError, TypeError, IndexError):
                    continue

            if not rows:
                return {"success": True, "saved": 0, "skipped": 0, "errors": 0}

            # ✅ استفاده از execute_values با ON CONFLICT
            on_conflict = "DO NOTHING" if skip_existing else """
                DO UPDATE SET
                    open = EXCLUDED.open,
                    high = EXCLUDED.high,
                    low = EXCLUDED.low,
                    close = EXCLUDED.close,
                    volume = EXCLUDED.volume
            """

            query = f"""
                INSERT INTO ohlcv_history (
                    symbol, interval, timestamp,
                    open, high, low, close, volume
                ) VALUES %s
                ON CONFLICT (symbol, interval, timestamp) {on_conflict}
            """

            saved = 0
            if hasattr(self.db, "execute_values"):
                saved = self.db.execute_values(query, rows, page_size=500)
            elif hasattr(self.db, "execute_many"):
                # fallback: یکی‌یکی با execute (کندتر ولی امن)
                fallback_query = query.replace("VALUES %s", "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)")
                for row in rows:
                    try:
                        self.db.execute(fallback_query, row)
                        saved += 1
                    except Exception:
                        pass
            else:
                logger.error("❌ No bulk insert method available")
                return {"success": False, "error": "No bulk insert method", "saved": 0}

            logger.info(
                f"✅ OHLCV saved: {symbol} {interval} "
                f"({saved} candles, {len(rows) - saved} skipped)"
            )

            return {
                "success": True,
                "saved": saved,
                "skipped": len(rows) - saved,
                "errors": 0,
            }

        except Exception as e:
            logger.error(f"❌ Save candles error: {e}", exc_info=True)
            return {"success": False, "error": str(e), "saved": 0}

    def save_dataframe(
        self,
        symbol: str,
        interval: str,
        df: pd.DataFrame,
        skip_existing: bool = True,
    ) -> Dict[str, Any]:
        """ذخیره DataFrame در DB"""
        if df is None or df.empty:
            return {"success": True, "saved": 0, "skipped": 0, "errors": 0}

        candles = []
        for ts, row in df.iterrows():
            try:
                # ts ممکنه timezone داشته باشه یا نه
                if hasattr(ts, "timestamp"):
                    ts_ms = int(ts.timestamp() * 1000)
                else:
                    ts_ms = int(pd.Timestamp(ts).timestamp() * 1000)

                candles.append([
                    ts_ms,
                    float(row.get("Open", 0)),
                    float(row.get("High", 0)),
                    float(row.get("Low", 0)),
                    float(row.get("Close", 0)),
                    float(row.get("Volume", 0)),
                ])
            except (ValueError, TypeError, AttributeError):
                continue

        return self.save_candles(symbol, interval, candles, skip_existing)

    # ============================================================
    # LOAD
    # ============================================================

    def load_candles(
        self,
        symbol: str,
        interval: str,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        limit: int = 1000,
    ) -> List[Dict[str, Any]]:
        """بارگذاری candles از DB"""
        if not self._ensure_db():
            return []

        self._ensure_schema()

        try:
            conditions = ["symbol = %s", "interval = %s"]
            params: List[Any] = [symbol, interval]

            if start:
                start_naive = self._to_utc_naive(start)
                if start_naive:
                    conditions.append("timestamp >= %s")
                    params.append(start_naive)

            if end:
                end_naive = self._to_utc_naive(end)
                if end_naive:
                    conditions.append("timestamp <= %s")
                    params.append(end_naive)

            where_clause = " AND ".join(conditions)
            params.append(limit)

            query = f"""
                SELECT symbol, interval, timestamp,
                       open, high, low, close, volume
                FROM ohlcv_history
                WHERE {where_clause}
                ORDER BY timestamp DESC
                LIMIT %s
            """

            result = self.db.execute(query, tuple(params))
            return list(reversed(result or []))

        except Exception as e:
            logger.error(f"❌ Load candles error: {e}")
            return []

    def load_dataframe(
        self,
        symbol: str,
        interval: str,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        limit: int = 1000,
    ) -> Optional[pd.DataFrame]:
        """بارگذاری DataFrame از DB"""
        rows = self.load_candles(symbol, interval, start, end, limit)

        if not rows:
            return None

        try:
            df = pd.DataFrame(rows)
            df = df.rename(columns={
                "timestamp": "timestamp",
                "open": "Open",
                "high": "High",
                "low": "Low",
                "close": "Close",
                "volume": "Volume",
            })

            df["timestamp"] = pd.to_datetime(df["timestamp"])
            df = df.set_index("timestamp").sort_index()
            df = df[["Open", "High", "Low", "Close", "Volume"]].astype(float)

            return df

        except Exception as e:
            logger.error(f"❌ Load dataframe error: {e}")
            return None

    # ============================================================
    # GET OR FETCH (Two-Phase)
    # ============================================================

    def get_or_fetch(
        self,
        symbol: str,
        interval: str,
        api_client: Any = None,
        data_range: str = "3mo",
        min_candles: int = DEFAULT_MIN_CANDLES,
    ) -> Optional[pd.DataFrame]:
        """
        دریافت OHLCV با رویکرد دو زمانه.

        Returns:
            DataFrame با attrs['source'] در یکی از این مقادیر:
                - 'DB'          : از DB تازه و کافی
                - 'API'         : از API، DB خالی یا ناکافی
                - 'HYBRID'      : merge DB + API
                - 'DB_FALLBACK' : API خطا داد، DB قدیمی/ناقص برگردانده شد
            یا None در صورت نبود هیچ داده‌ای.
        """
        db_df: Optional[pd.DataFrame] = None
        db_count = 0
        db_age_hours: Optional[float] = None
        db_fresh = False
        db_sufficient = False

        # ------------------------------------------------------------
        # فاز ۱ — تلاش از DB
        # ------------------------------------------------------------
        try:
            db_df = self.load_dataframe(symbol, interval, limit=10000)
            if db_df is not None and not db_df.empty:
                db_count = len(db_df)
                db_sufficient = db_count >= min_candles

                last_ts = db_df.index[-1]
                last_ts_naive = self._to_utc_naive(last_ts)

                if last_ts_naive is not None:
                    now_utc = self._utc_now_naive()
                    age_seconds = (now_utc - last_ts_naive).total_seconds()
                    db_age_hours = age_seconds / 3600

                    tolerance = STALENESS_TOLERANCE_SECONDS.get(interval, 12 * 3600)
                    db_fresh = age_seconds <= tolerance

                    # ✅ DB تازه و کافی → برگردان
                    if db_sufficient and db_fresh:
                        db_df.attrs["source"] = "DB"
                        db_df.attrs["db_count"] = db_count
                        db_df.attrs["api_count"] = 0
                        db_df.attrs["merged_count"] = db_count
                        db_df.attrs["age_hours"] = round(db_age_hours, 2)

                        logger.debug(
                            f"OHLCV[source=DB] {symbol} {interval} — "
                            f"count={db_count}, age={db_age_hours:.1f}h"
                        )
                        return db_df
        except Exception as e:
            logger.warning(f"⚠️ DB load failed for {symbol} {interval}: {e}")

        # ------------------------------------------------------------
        # فاز ۲ — API
        # ------------------------------------------------------------
        api_df: Optional[pd.DataFrame] = None
        api_count = 0
        api_error: Optional[str] = None

        if api_client is not None and hasattr(api_client, "get_ohlcv_candles"):
            try:
                result = api_client.get_ohlcv_candles(
                    exchange="Binance",
                    pair=symbol,
                    interval=interval,
                    range=data_range,
                    use_cache=True,
                )

                if not result or "candles" not in result:
                    api_error = "no candles in API response"
                else:
                    candles = result["candles"][-MAX_CANDLES_FROM_API:]
                    if candles:
                        rows = []
                        for c in candles:
                            try:
                                ts = pd.to_datetime(
                                    c[0], unit="ms", utc=True, errors="coerce"
                                )
                                if pd.isna(ts):
                                    continue
                                rows.append({
                                    "timestamp": ts.tz_localize(None),
                                    "Open": float(c[1]),
                                    "High": float(c[2]),
                                    "Low": float(c[3]),
                                    "Close": float(c[4]),
                                    "Volume": float(c[5]) if c[5] else 0.0,
                                })
                            except (ValueError, TypeError, IndexError):
                                continue

                        if rows:
                            api_df = (
                                pd.DataFrame(rows)
                                .set_index("timestamp")
                                .sort_index()
                            )
                            api_count = len(api_df)

                            # ذخیره در DB
                            self.save_dataframe(
                                symbol, interval, api_df, skip_existing=True
                            )
                        else:
                            api_error = "no valid candles parsed"

            except Exception as e:
                api_error = str(e)
                logger.warning(
                    f"⚠️ API fetch failed for {symbol} {interval}: {e}"
                )

        # ------------------------------------------------------------
        # فاز ۳ — تصمیم نهایی
        # ------------------------------------------------------------

        # حالت ۱: API موفق
        if api_df is not None and not api_df.empty:
            if db_df is not None and not db_df.empty:
                # merge
                merged = self._merge_dataframes(db_df, api_df)
                merged.attrs["source"] = "HYBRID"
                merged.attrs["db_count"] = db_count
                merged.attrs["api_count"] = api_count
                merged.attrs["merged_count"] = len(merged)

                logger.info(
                    f"OHLCV[source=HYBRID] {symbol} {interval} — "
                    f"count={len(merged)}, db={db_count}, api={api_count}"
                )
                return merged
            else:
                api_df.attrs["source"] = "API"
                api_df.attrs["db_count"] = 0
                api_df.attrs["api_count"] = api_count
                api_df.attrs["merged_count"] = api_count

                logger.info(
                    f"OHLCV[source=API] {symbol} {interval} — "
                    f"count={api_count}, reason=db_missing"
                )
                return api_df

        # حالت ۲: API خطا داد ولی DB داشتیم
        if db_df is not None and not db_df.empty:
            db_df.attrs["source"] = "DB_FALLBACK"
            db_df.attrs["db_count"] = db_count
            db_df.attrs["api_count"] = 0
            db_df.attrs["merged_count"] = db_count
            db_df.attrs["age_hours"] = (
                round(db_age_hours, 2) if db_age_hours is not None else None
            )
            db_df.attrs["api_error"] = api_error or "unknown"

            logger.warning(
                f"OHLCV[source=DB_FALLBACK] {symbol} {interval} — "
                f"count={db_count}, age={db_age_hours}, "
                f"api_error={api_error}"
            )
            return db_df

        # حالت ۳: هیچ داده‌ای نبود
        logger.error(
            f"❌ OHLCV[no-data] {symbol} {interval} — "
            f"db_count={db_count}, api_error={api_error}"
        )
        return None

    @staticmethod
    def _merge_dataframes(
        db_df: pd.DataFrame,
        api_df: pd.DataFrame,
    ) -> pd.DataFrame:
        """
        Merge DB و API بر اساس timestamp.
        داده‌های API اولویت دارند (چون تازه‌ترند).
        """
        # concat: DB اول، API دوم → API روی DB رو override می‌کند
        merged = pd.concat([db_df, api_df])
        # حذف تکراری‌ها بر اساس index، نگه‌داشتن آخری (API)
        merged = merged[~merged.index.duplicated(keep="last")]
        merged = merged.sort_index()
        return merged

    # ============================================================
    # CLEANUP
    # ============================================================

    def cleanup_old(
        self,
        retention_days: int = 90,
        interval: Optional[str] = None,
    ) -> int:
        """حذف رکوردهای قدیمی"""
        if not self._ensure_db():
            return 0

        try:
            cutoff = self._utc_now_naive() - timedelta(days=retention_days)

            if interval:
                self.db.execute(
                    """
                    DELETE FROM ohlcv_history
                    WHERE interval = %s AND timestamp < %s
                    """,
                    (interval, cutoff),
                )
            else:
                self.db.execute(
                    "DELETE FROM ohlcv_history WHERE timestamp < %s",
                    (cutoff,),
                )

            count_result = self.db.execute(
                "SELECT COUNT(*) as count FROM ohlcv_history"
            )
            remaining = count_result[0]["count"] if count_result else 0

            logger.info(
                f"✅ OHLCV cleanup: retention={retention_days}d, "
                f"interval={interval or 'all'}, remaining={remaining}"
            )

            return remaining

        except Exception as e:
            logger.error(f"❌ Cleanup error: {e}")
            return 0

    # ============================================================
    # STATS
    # ============================================================

    def get_stats(self) -> Dict[str, Any]:
        """آمار Repository"""
        if not self._ensure_db():
            return {"connected": False}

        self._ensure_schema()

        try:
            total_result = self.db.execute(
                "SELECT COUNT(*) as count FROM ohlcv_history"
            )
            total = total_result[0]["count"] if total_result else 0

            by_symbol = self.db.execute("""
                SELECT symbol, COUNT(*) as count
                FROM ohlcv_history
                GROUP BY symbol
                ORDER BY count DESC
                LIMIT 20
            """)

            by_interval = self.db.execute("""
                SELECT interval, COUNT(*) as count
                FROM ohlcv_history
                GROUP BY interval
                ORDER BY count DESC
            """)

            size_result = self.db.execute("""
                SELECT pg_total_relation_size('ohlcv_history')
                       / 1024.0 / 1024.0 as size_mb
            """)
            size_mb = size_result[0]["size_mb"] if size_result else 0

            time_range = self.db.execute("""
                SELECT
                    MIN(timestamp) as oldest,
                    MAX(timestamp) as newest
                FROM ohlcv_history
            """)

            return {
                "connected": True,
                "total_records": total,
                "size_mb": round(size_mb or 0, 2),
                "by_symbol": by_symbol or [],
                "by_interval": by_interval or [],
                "oldest": (
                    time_range[0]["oldest"].isoformat()
                    if time_range and time_range[0].get("oldest") else None
                ),
                "newest": (
                    time_range[0]["newest"].isoformat()
                    if time_range and time_range[0].get("newest") else None
                ),
            }

        except Exception as e:
            logger.error(f"❌ Get stats error: {e}")
            return {"connected": True, "error": str(e)}

    def count(
        self,
        symbol: Optional[str] = None,
        interval: Optional[str] = None,
    ) -> int:
        """تعداد رکوردها"""
        if not self._ensure_db():
            return 0

        try:
            conditions = []
            params: List[Any] = []

            if symbol:
                conditions.append("symbol = %s")
                params.append(symbol)

            if interval:
                conditions.append("interval = %s")
                params.append(interval)

            where_clause = " AND ".join(conditions) if conditions else "1=1"

            result = self.db.execute(
                f"SELECT COUNT(*) as count FROM ohlcv_history WHERE {where_clause}",
                tuple(params),
            )

            return result[0]["count"] if result else 0

        except Exception as e:
            logger.error(f"❌ Count error: {e}")
            return 0

    # ============================================================
    # Repository Interface
    # ============================================================

    def save(self, entity: Any) -> Any:
        """ذخیره Entity (الزامی)"""
        raise NotImplementedError(
            "Use save_candles or save_dataframe instead"
        )


    # ============================================================
    # Repository Interface (stubs)
    # ============================================================
    # این متدها برای مطابقت با interface الزامی‌اند، ولی OHLCV
    # از الگوی repository معمولی استفاده نمی‌کند.

    def find_by_id(self, entity_id: Any) -> Optional[Dict[str, Any]]:
        """دریافت یک رکورد با ID"""
        if not self._ensure_db():
            return None
        try:
            result = self.db.execute(
                "SELECT * FROM ohlcv_history WHERE id = %s",
                (entity_id,),
            )
            return result[0] if result else None
        except Exception as e:
            logger.error(f"❌ find_by_id error: {e}")
            return None

    def find_all(self, limit: int = 1000) -> List[Dict[str, Any]]:
        """دریافت همه رکوردها"""
        if not self._ensure_db():
            return []
        try:
            return self.db.execute(
                "SELECT * FROM ohlcv_history ORDER BY timestamp DESC LIMIT %s",
                (limit,),
            ) or []
        except Exception as e:
            logger.error(f"❌ find_all error: {e}")
            return []

    def find_by_criteria(
        self,
        criteria: Optional[Dict[str, Any]] = None,
        limit: int = 1000,
    ) -> List[Dict[str, Any]]:
        """جستجو بر اساس معیارها"""
        if not self._ensure_db():
            return []

        criteria = criteria or {}
        conditions = []
        params: List[Any] = []

        for key, val in criteria.items():
            if key in ("symbol", "interval"):
                conditions.append(f"{key} = %s")
                params.append(val)

        where_clause = " AND ".join(conditions) if conditions else "1=1"
        params.append(limit)

        try:
            return self.db.execute(
                f"SELECT * FROM ohlcv_history WHERE {where_clause} "
                f"ORDER BY timestamp DESC LIMIT %s",
                tuple(params),
            ) or []
        except Exception as e:
            logger.error(f"❌ find_by_criteria error: {e}")
            return []

    def delete(self, entity_id: Any) -> bool:
        """حذف یک رکورد با ID"""
        if not self._ensure_db():
            return False
        try:
            self.db.execute(
                "DELETE FROM ohlcv_history WHERE id = %s",
                (entity_id,),
            )
            return True
        except Exception as e:
            logger.error(f"❌ delete error: {e}")
            return False

__all__ = ["OHLCVRepository", "VALID_INTERVALS"]
