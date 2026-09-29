# core/rule_engine/state_machine.py
# ============================================================
# State Machine - مدیریت وضعیت هر symbol
# نسخه ۱.۰
# ============================================================
# 
# چرخه:
#   IDLE → WATCHING → SETUP → ACTIVE → COOLING → IDLE
# 
# قوانین transition:
#   IDLE → WATCHING:  score >= watching_threshold (0.35)
#   WATCHING → SETUP: score >= setup_threshold (0.65)
#   SETUP → ACTIVE:   entry signal (از پورتفولیو یا سیستم)
#   ACTIVE → COOLING: exit signal
#   COOLING → IDLE:   بعد از N کندل صبر
# 
# storage:
#   Redis: state:market:{symbol} با TTL = 8 ساعت
#   DB:    فقط تغییرات state ذخیره می‌شن (جدول state_transitions)
# ============================================================

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from core.rule_engine.models import MarketState, StateSnapshot

logger = logging.getLogger(__name__)


# ============================================================
# StateMachine
# ============================================================

class StateMachine:
    """
    مدیریت وضعیت بازار برای هر symbol
    
    ویژگی‌ها:
        - ذخیره در Redis (سریع)
        - تاریخچه تغییرات در DB
        - transition های قابل تنظیم
        - نرخ fallback امن
    """
    
    # TTL برای snapshot در Redis (۸ ساعت = ۲ کندل 4h)
    SNAPSHOT_TTL = 8 * 3600
    
    # تعداد کندل صبر در COOLING
    COOLING_CANDLES = 3
    
    # آستانه‌های پیش‌فرض
    DEFAULT_WATCHING_THRESHOLD = 0.35
    DEFAULT_SETUP_THRESHOLD = 0.65
    
    def __init__(
        self,
        cache: Any = None,
        db: Any = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Args:
            cache: Redis client (get_cache())
            db: PostgreSQL client (get_primary())
            config: تنظیمات سفارشی
        """
        self.cache = cache
        self.db = db
        
        config = config or {}
        self.watching_threshold: float = float(
            config.get("watching_threshold", self.DEFAULT_WATCHING_THRESHOLD)
        )
        self.setup_threshold: float = float(
            config.get("setup_threshold", self.DEFAULT_SETUP_THRESHOLD)
        )
        self.cooling_candles: int = int(
            config.get("cooling_candles", self.COOLING_CANDLES)
        )
        self.snapshot_ttl: int = int(
            config.get("snapshot_ttl", self.SNAPSHOT_TTL)
        )
        self.enable_db_history: bool = config.get("enable_db_history", True)
        
        logger.info(
            f"✅ StateMachine initialized "
            f"(watching={self.watching_threshold}, "
            f"setup={self.setup_threshold})"
        )
    
    # ============================================================
    # Public API
    # ============================================================
    
    def get_state(self, symbol: str) -> StateSnapshot:
        """
        دریافت snapshot فعلی یک symbol
        
        اگه در cache نبود → initial IDLE
        
        Args:
            symbol: مثل "BTC/USDT"
        
        Returns:
            StateSnapshot
        """
        # تلاش از cache
        if self.cache and self.cache.is_connected():
            try:
                key = self._cache_key(symbol)
                cached = self.cache.get(key)
                if cached and isinstance(cached, dict):
                    return StateSnapshot.from_dict(cached)
            except Exception as e:
                logger.warning(f"⚠️ Cache read failed for {symbol}: {e}")
        
        # fallback: IDLE اولیه
        return StateSnapshot.initial(symbol)
    
    def update_state(
        self,
        symbol: str,
        score: float,
        context: Optional[Dict[str, Any]] = None,
        force_state: Optional[MarketState] = None,
    ) -> StateSnapshot:
        """
        آپدیت وضعیت یک symbol بر اساس score جدید
        
        Args:
            symbol: نماد
            score: امتیاز Rule Engine (۰-۱)
            context: اطلاعات اضافی (اندیکاتورها)
            force_state: اگه داده شده، transition رو override کن
        
        Returns:
            StateSnapshot جدید
        """
        current = self.get_state(symbol)
        old_state = current.state
        
        # اگه force_state داریم
        if force_state is not None:
            new_state = force_state
        else:
            new_state = self._compute_next_state(current, score)
        
        # اگه تغییر نکرد → فقط signal_count++
        if new_state == old_state:
            current.signal_count += 1
            current.context = context or current.context
            self._save_snapshot(current)
            return current
        
        # تغییر state → snapshot جدید
        now = datetime.now()
        new_snapshot = StateSnapshot(
            symbol=symbol,
            state=new_state,
            entered_at=now,
            last_change_at=now,
            context=context or {},
            signal_count=1,
        )
        
        # ذخیره
        self._save_snapshot(new_snapshot)
        
        # ذخیره در history
        if self.enable_db_history:
            self._record_transition(
                symbol=symbol,
                from_state=old_state,
                to_state=new_state,
                score=score,
                context=context or {},
            )
        
        logger.debug(
            f"🔄 {symbol}: {old_state.value} → {new_state.value} "
            f"(score={score:.3f})"
        )
        
        return new_snapshot
    
    def set_active(self, symbol: str, context: Optional[Dict[str, Any]] = None) -> StateSnapshot:
        """
        علامت‌گذاری symbol به‌عنوان ACTIVE (پوزیشن باز شد)
        
        Args:
            symbol: نماد
            context: اطلاعات پوزیشن (entry_price, ...)
        """
        return self.update_state(
            symbol=symbol,
            score=1.0,
            context=context or {},
            force_state=MarketState.ACTIVE,
        )
    
    def set_cooling(self, symbol: str, context: Optional[Dict[str, Any]] = None) -> StateSnapshot:
        """
        علامت‌گذاری symbol به‌عنوان COOLING (پوزیشن بسته شد)
        """
        return self.update_state(
            symbol=symbol,
            score=0.0,
            context=context or {},
            force_state=MarketState.COOLING,
        )
    
    def reset(self, symbol: str) -> StateSnapshot:
        """ریست کامل یک symbol به IDLE"""
        snapshot = StateSnapshot.initial(symbol)
        self._save_snapshot(snapshot)
        return snapshot
    
    def get_transitions(
        self,
        symbol: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        دریافت تاریخچه تغییرات state
        
        Args:
            symbol: فیلتر (اختیاری)
            limit: حداکثر تعداد
        """
        if not self.db or not self.db.is_connected():
            return []
        
        try:
            if symbol:
                result = self.db.execute(
                    """
                    SELECT symbol, from_state, to_state, score,
                           context, changed_at
                    FROM state_transitions
                    WHERE symbol = %s
                    ORDER BY changed_at DESC
                    LIMIT %s
                    """,
                    (symbol, limit),
                )
            else:
                result = self.db.execute(
                    """
                    SELECT symbol, from_state, to_state, score,
                           context, changed_at
                    FROM state_transitions
                    ORDER BY changed_at DESC
                    LIMIT %s
                    """,
                    (limit,),
                )
            
            return result or []
        except Exception as e:
            logger.error(f"❌ Failed to get transitions: {e}")
            return []
    
    def bulk_update(
        self,
        updates: List[Dict[str, Any]],
    ) -> Dict[str, StateSnapshot]:
        """
        آپدیت گروهی چند symbol
        
        Args:
            updates: لیست دیکشنری {symbol, score, context}
        
        Returns:
            دیکشنری {symbol: StateSnapshot}
        """
        results: Dict[str, StateSnapshot] = {}
        
        for update in updates:
            try:
                symbol = update["symbol"]
                score = float(update.get("score", 0.0))
                context = update.get("context", {})
                
                snapshot = self.update_state(
                    symbol=symbol,
                    score=score,
                    context=context,
                )
                results[symbol] = snapshot
            except Exception as e:
                logger.error(f"❌ Bulk update failed for {update}: {e}")
        
        return results
    
    def get_states_by_state(
        self,
        state: MarketState,
        symbols: List[str],
    ) -> List[str]:
        """
        دریافت symbolهایی که در state خاصی هستن
        
        Args:
            state: state مورد نظر
            symbols: لیست symbolهای بررسی‌شده
        
        Returns:
            لیست symbolهایی که state اونها مطابق state داده‌شده هست
        """
        matching = []
        for symbol in symbols:
            snapshot = self.get_state(symbol)
            if snapshot.state == state:
                matching.append(symbol)
        return matching
    
    # ============================================================
    # Internal - Transition Logic
    # ============================================================
    
    def _compute_next_state(
        self,
        current: StateSnapshot,
        score: float,
    ) -> MarketState:
        """
        محاسبه state بعدی بر اساس state فعلی و score جدید
        
        قوانین:
            IDLE → WATCHING:   score >= watching_threshold
            WATCHING → SETUP:  score >= setup_threshold
            WATCHING → IDLE:   score < watching_threshold
            SETUP → WATCHING:  score < setup_threshold
            SETUP → ACTIVE:    فقط با force_state
            ACTIVE → COOLING:  فقط با force_state
            COOLING → IDLE:    بعد از N کندل
        """
        state = current.state
        
        # IDLE: فقط WATCHING اگر score کافی
        if state == MarketState.IDLE:
            if score >= self.setup_threshold:
                # جهش مستقیم به SETUP
                return MarketState.SETUP
            elif score >= self.watching_threshold:
                return MarketState.WATCHING
            return MarketState.IDLE
        
        # WATCHING: بسته به score
        if state == MarketState.WATCHING:
            if score >= self.setup_threshold:
                return MarketState.SETUP
            elif score < self.watching_threshold:
                # score افت کرد → برگرد IDLE
                return MarketState.IDLE
            return MarketState.WATCHING
        
        # SETUP: بسته به score
        if state == MarketState.SETUP:
            if score < self.watching_threshold:
                # score افت شدید → IDLE
                return MarketState.IDLE
            elif score < self.setup_threshold:
                # score کم شد → WATCHING
                return MarketState.WATCHING
            return MarketState.SETUP
        
        # ACTIVE: فقط با force_state عوض می‌شه
        if state == MarketState.ACTIVE:
            return MarketState.ACTIVE
        
        # COOLING: بعد از N کندل → IDLE
        if state == MarketState.COOLING:
            return self._check_cooling_exit(current)
        
        return MarketState.IDLE
    
    def _check_cooling_exit(self, snapshot: StateSnapshot) -> MarketState:
        """
        چک کنه آیا از COOLING خارج بشیم
        
        بر اساس مدت زمانی که در COOLING بودیم
        (فرض: هر کندل 4h)
        """
        now = datetime.now()
        # هر کندل ۴ ساعت (قابل تنظیم در آینده)
        candle_seconds = 4 * 3600
        cooling_duration = (now - snapshot.entered_at).total_seconds()
        candles_passed = cooling_duration / candle_seconds
        
        if candles_passed >= self.cooling_candles:
            return MarketState.IDLE
        return MarketState.COOLING
    
    # ============================================================
    # Internal - Storage
    # ============================================================
    
    def _cache_key(self, symbol: str) -> str:
        """ساخت کلید cache برای یک symbol"""
        return f"state:market:{symbol}"
    
    def _save_snapshot(self, snapshot: StateSnapshot) -> None:
        """ذخیره snapshot در Redis"""
        if not self.cache or not self.cache.is_connected():
            return
        
        try:
            self.cache.set(
                self._cache_key(snapshot.symbol),
                snapshot.to_dict(),
                ttl=self.snapshot_ttl,
            )
        except Exception as e:
            logger.warning(f"⚠️ Cache write failed for {snapshot.symbol}: {e}")
    
    def _record_transition(
        self,
        symbol: str,
        from_state: MarketState,
        to_state: MarketState,
        score: float,
        context: Dict[str, Any],
    ) -> None:
        """
        ثبت تغییر state در DB
        
        جدول: state_transitions
        (self._ensure_table() مسئول ساختش)
        """
        if not self.db or not self.db.is_connected():
            return
        
        try:
            self._ensure_table()
            
            self.db.execute(
                """
                INSERT INTO state_transitions (
                    symbol, from_state, to_state, score,
                    context, changed_at
                ) VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    symbol,
                    from_state.value,
                    to_state.value,
                    float(score),
                    json.dumps(context),
                    datetime.now(),
                ),
            )
        except Exception as e:
            logger.warning(f"⚠️ Failed to record transition: {e}")
    
    def _ensure_table(self) -> None:
        """ساخت جدول state_transitions اگه نبود"""
        if not self.db or not self.db.is_connected():
            return
        
        try:
            self.db.execute(
                """
                CREATE TABLE IF NOT EXISTS state_transitions (
                    id SERIAL PRIMARY KEY,
                    symbol VARCHAR(50) NOT NULL,
                    from_state VARCHAR(20) NOT NULL,
                    to_state VARCHAR(20) NOT NULL,
                    score REAL NOT NULL,
                    context JSONB,
                    changed_at TIMESTAMP NOT NULL DEFAULT NOW()
                )
                """
            )
            # ایندکس برای سرعت
            self.db.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_state_transitions_symbol_time
                ON state_transitions (symbol, changed_at DESC)
                """
            )
        except Exception as e:
            logger.warning(f"⚠️ Failed to ensure table: {e}")
    
    # ============================================================
    # Stats
    # ============================================================
    
    def get_stats(self) -> Dict[str, Any]:
        """آمار State Machine"""
        return {
            "watching_threshold": self.watching_threshold,
            "setup_threshold": self.setup_threshold,
            "cooling_candles": self.cooling_candles,
            "snapshot_ttl_seconds": self.snapshot_ttl,
            "enable_db_history": self.enable_db_history,
            "cache_connected": (
                self.cache is not None and self.cache.is_connected()
            ),
            "db_connected": (
                self.db is not None and self.db.is_connected()
            ),
        }


__all__ = ["StateMachine"]
