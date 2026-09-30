# infrastructure/repositories/ohlcv_repository.py
# ============================================================
# Repository: OHLCV History - نسخه ۱.۰
# ذخیره و بازیابی OHLCV از DB (fallback برای Redis)
# ============================================================

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import pandas as pd

from domain.interfaces.repository import Repository
from infrastructure.database import get_primary, get_cache

logger = logging.getLogger(__name__)


# ============================================================
# Constants
# ============================================================

TABLE_NAME = "ohlcv_history"

# بازه‌های معتبر
VALID_INTERVALS = ["5m", "15m", "30m", "1h", "4h", "1d", "1w"]

# TTL برای cache
CACHE_TTL = 1800  # ۳۰ دقیقه


# ============================================================
# OHLCVRepository
# ============================================================

class OHLCVRepository(Repository):
    """
    Repository برای OHLCV History
    
    نقش:
        - ذخیره OHLCV در DB (برای backtest)
        - fallback از DB اگه cache خالی بود
        - cleanup رکوردهای قدیمی
        - آمار
    
    نکته:
        - از `INSERT ... ON CONFLICT DO NOTHING` استفاده می‌کنه
        - idempotent هست (چند بار ذخیره بشه، مشکل نیست)
    """
    
    TABLE_NAME = TABLE_NAME
    CACHE_PREFIX = "ohlcv_cache"
    CACHE_TTL = CACHE_TTL
    
    def __init__(self) -> None:
        self._db = None
        self._cache = None
        self._schema_ensured = False
        
        logger.info("✅ OHLCVRepository v1.0 initialized")
    
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
            
            # ایندکس‌ها
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
            logger.info("✅ OHLCVRepository: schema ensured")
        
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
        
        Args:
            symbol: نماد (BTC/USDT)
            interval: بازه (4h)
            candles: لیست candles [[ts, o, h, l, c, v], ...]
            skip_existing: رکوردهای موجود رو رد کن؟
        
        Returns:
            {success, saved, skipped, errors}
        """
        if not self._ensure_db():
            return {"success": False, "error": "Database not connected"}
        
        if interval not in VALID_INTERVALS:
            return {"success": False, "error": f"Invalid interval: {interval}"}
        
        if not candles:
            return {"success": True, "saved": 0, "skipped": 0, "errors": 0}
        
        self._ensure_schema()
        
        try:
            # ساخت rows
            rows = []
            for c in candles:
                if not isinstance(c, (list, tuple)) or len(c) < 6:
                    continue
                
                try:
                    ts_ms = int(c[0])
                    ts = pd.to_datetime(ts_ms, unit="ms", errors="coerce")
                    if pd.isna(ts):
                        continue
                    
                    rows.append((
                        symbol,
                        interval,
                        ts.to_pydatetime(),
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
            
            # Bulk insert با ON CONFLICT
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
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (symbol, interval, timestamp) {on_conflict}
            """
            
            # اجرای bulk
            if hasattr(self.db, "execute_many"):
                saved = self.db.execute_many(query, rows)
            else:
                # fallback: یکی‌یکی
                saved = 0
                for row in rows:
                    try:
                        self.db.execute(query, row)
                        saved += 1
                    except Exception:
                        pass
            
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
            return {"success": False, "error": str(e)}
    
    def save_dataframe(
        self,
        symbol: str,
        interval: str,
        df: pd.DataFrame,
        skip_existing: bool = True,
    ) -> Dict[str, Any]:
        """
        ذخیره DataFrame در DB
        
        Args:
            symbol: نماد
            interval: بازه
            df: DataFrame با index=timestamp و ستون‌های OHLCV
        """
        if df is None or df.empty:
            return {"success": True, "saved": 0, "skipped": 0, "errors": 0}
        
        # تبدیل به candles
        candles = []
        for ts, row in df.iterrows():
            try:
                ts_ms = int(ts.timestamp() * 1000)
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
        """
        بارگذاری candles از DB
        
        Args:
            symbol: نماد
            interval: بازه
            start: از تاریخ
            end: تا تاریخ
            limit: حداکثر تعداد
        
        Returns:
            لیست dict
        """
        if not self._ensure_db():
            return []
        
        self._ensure_schema()
        
        try:
            conditions = ["symbol = %s", "interval = %s"]
            params = [symbol, interval]
            
            if start:
                conditions.append("timestamp >= %s")
                params.append(start)
            
            if end:
                conditions.append("timestamp <= %s")
                params.append(end)
            
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
            
            # معکوس کن (قدیمی → جدید)
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
        """
        بارگذاری DataFrame از DB
        """
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
    # GET OR FETCH (fallback)
    # ============================================================
    
    def get_or_fetch(
        self,
        symbol: str,
        interval: str,
        api_client: Any = None,
        data_range: str = "3mo",
        min_candles: int = 100,
    ) -> Optional[pd.DataFrame]:
        """
        دریافت از DB اگه موجود بود، وگرنه از API
        
        Args:
            symbol: نماد
            interval: بازه
            api_client: برای fetch
            data_range: بازه
            min_candles: حداقل کندل لازم
        
        Returns:
            DataFrame یا None
        """
        # ۱. تلاش از DB
        df = self.load_dataframe(symbol, interval, limit=10000)
        
        if df is not None and len(df) >= min_candles:
            # چک تازگی (اگه آخرین کندل قدیمیه، از API بگیر)
            last_ts = df.index[-1]
            age_hours = (datetime.now() - last_ts.to_pydatetime()).total_seconds() / 3600
            
            # اگه کندل آخر مربوط به بیش از ۲ بازه قبله، refresh کن
            interval_hours = {
                "5m": 5/60, "15m": 0.25, "30m": 0.5,
                "1h": 1, "4h": 4, "1d": 24, "1w": 168,
            }.get(interval, 4)
            
            if age_hours < 2 * interval_hours:
                logger.debug(
                    f"⚡ OHLCV from DB: {symbol} {interval} "
                    f"({len(df)} candles, age={age_hours:.1f}h)"
                )
                return df
        
        # ۲. Fetch از API
        if api_client is None or not hasattr(api_client, "get_ohlcv_candles"):
            return df if df is not None and len(df) >= min_candles else None
        
        try:
            result = api_client.get_ohlcv_candles(
                exchange="Binance",
                pair=symbol,
                interval=interval,
                range=data_range,
                use_cache=True,
            )
            
            if not result or "candles" not in result:
                return df  # fallback به DB اگه داشتیم
            
            # ذخیره در DB
            self.save_candles(symbol, interval, result["candles"])
            
            # ساخت DataFrame
            candles = result["candles"]
            rows = []
            for c in candles:
                try:
                    ts = pd.to_datetime(c[0], unit="ms", errors="coerce")
                    if pd.isna(ts):
                        continue
                    rows.append({
                        "timestamp": ts,
                        "Open": float(c[1]),
                        "High": float(c[2]),
                        "Low": float(c[3]),
                        "Close": float(c[4]),
                        "Volume": float(c[5]) if c[5] else 0.0,
                    })
                except (ValueError, TypeError, IndexError):
                    continue
            
            if not rows:
                return df
            
            new_df = pd.DataFrame(rows).set_index("timestamp").sort_index()
            return new_df
        
        except Exception as e:
            logger.error(f"❌ get_or_fetch error: {e}")
            return df
    
    # ============================================================
    # CLEANUP
    # ============================================================
    
    def cleanup_old(
        self,
        retention_days: int = 90,
        interval: Optional[str] = None,
    ) -> int:
        """
        حذف رکوردهای قدیمی
        
        Args:
            retention_days: مدت نگهداری
            interval: فقط یک interval خاص
        
        Returns:
            تعداد حذف شده
        """
        if not self._ensure_db():
            return 0
        
        try:
            cutoff = datetime.now() - timedelta(days=retention_days)
            
            if interval:
                result = self.db.execute(
                    """
                    DELETE FROM ohlcv_history
                    WHERE interval = %s AND timestamp < %s
                    """,
                    (interval, cutoff),
                )
            else:
                result = self.db.execute(
                    "DELETE FROM ohlcv_history WHERE timestamp < %s",
                    (cutoff,),
                )
            
            # شمارش
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
            # کل رکوردها
            total_result = self.db.execute(
                "SELECT COUNT(*) as count FROM ohlcv_history"
            )
            total = total_result[0]["count"] if total_result else 0
            
            # توسط symbol
            by_symbol = self.db.execute("""
                SELECT symbol, COUNT(*) as count
                FROM ohlcv_history
                GROUP BY symbol
                ORDER BY count DESC
                LIMIT 20
            """)
            
            # توسط interval
            by_interval = self.db.execute("""
                SELECT interval, COUNT(*) as count
                FROM ohlcv_history
                GROUP BY interval
                ORDER BY count DESC
            """)
            
            # حجم تخمینی
            size_result = self.db.execute("""
                SELECT pg_total_relation_size('ohlcv_history') 
                       / 1024.0 / 1024.0 as size_mb
            """)
            size_mb = size_result[0]["size_mb"] if size_result else 0
            
            # محدوده زمانی
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
            params = []
            
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


__all__ = ["OHLCVRepository", "VALID_INTERVALS"]
