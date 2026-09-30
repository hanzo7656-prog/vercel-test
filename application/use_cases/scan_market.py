# application/use_cases/scan_market.py
# ============================================================
# Use Case: Scan Market - نسخه ۲.۰
# OHLCV واقعی + لاگ کامل + خطایابی
# ============================================================

import json
import logging
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd

from core.rule_engine import (
    BatchProcessor,
    RuleEngine,
    StateMachine,
    create_engine_from_config,
    load_default_config,
)
from core.rule_engine.models import ScanResult
from infrastructure.repositories.rule_config_repository import (
    rule_config_repository,
)

logger = logging.getLogger(__name__)


# ============================================================
# Constants
# ============================================================

# نگاشت timeframe → interval (برای get_ohlcv_candles)
TIMEFRAME_TO_INTERVAL: Dict[str, str] = {
    "1m":  "1m",
    "5m":  "5m",
    "15m": "15m",
    "1h":  "1h",
    "4h":  "4h",
    "1d":  "1d",
}

# cache TTL برای نتایج اسکن (۱ ساعت)
SCAN_CACHE_TTL = 3600

# حداقل کندل لازم برای اسکن
MIN_CANDLES = 30


# ============================================================
# ScanMarketUseCase v2.0
# ============================================================

class ScanMarketUseCase:
    """
    Use Case اسکن بازار
    
    تغییرات نسخه ۲.۰:
        - OHLCV واقعی از get_ohlcv_candles
        - لاگ کامل هر مرحله
        - Smart interval mapping
        - حذف OHLCV قلابی
    """
    
    def __init__(
        self,
        api_client: Any,
        cache: Any,
        db: Any,
    ) -> None:
        self.api_client = api_client
        self.cache = cache
        self.db = db
        self.config_repo = rule_config_repository
        
        logger.info("✅ ScanMarketUseCase v2.0 initialized")
    
    # ============================================================
    # Main Execute
    # ============================================================
    
    def execute(
        self,
        symbols: Optional[List[str]] = None,
        top_n: int = 30,
        timeframe: Optional[str] = None,
        max_results: int = 10,
        update_state: bool = True,
        use_cache: bool = True,
    ) -> ScanResult:
        """
        اجرای اسکن کامل بازار
        
        لاگ کامل:
            🎯 Scan START
            ✅ Config loaded
            ✅ Symbols fetched
            ✅ Engine built
            ✅ Batch done
            🎉 Scan SUCCESS
        """
        start_time = time.time()
        scan_id = (
            f"scan-{datetime.now().strftime('%Y%m%d-%H%M%S')}-"
            f"{uuid.uuid4().hex[:6]}"
        )
        
        # ============================================================
        # لاگ شروع
        # ============================================================
        
        logger.info("=" * 60)
        logger.info(f"🎯 Scan START: {scan_id}")
        logger.info(
            f"   top_n={top_n}, timeframe={timeframe or 'default'}, "
            f"max_results={max_results}"
        )
        logger.info("=" * 60)
        
        # ============================================================
        # ۱. Config
        # ============================================================
        
        try:
            config = self._load_config()
            logger.info("✅ Scan STEP-1 OK: config loaded")
        except Exception as e:
            logger.error(f"❌ Scan FAILED (STEP-1): config load error: {e}")
            return self._error_result(scan_id, f"Config error: {e}", start_time)
        
        if timeframe:
            config.setdefault("batch", {})["timeframe"] = timeframe
        
        # ============================================================
        # ۲. Symbols
        # ============================================================
        
        try:
            symbol_items = self._get_symbols(
                symbols=symbols,
                top_n=top_n,
                config=config,
            )
        except Exception as e:
            logger.error(f"❌ Scan FAILED (STEP-2): symbol fetch error: {e}")
            return self._error_result(scan_id, f"Symbol error: {e}", start_time)
        
        if not symbol_items:
            logger.error("❌ Scan FAILED (STEP-2): no symbols")
            return self._error_result(
                scan_id, "No symbols to scan", start_time
            )
        
        total_symbols = len(symbol_items)
        logger.info(f"✅ Scan STEP-2 OK: {total_symbols} symbols")
        
        # ============================================================
        # ۳. StateMachine
        # ============================================================
        
        try:
            state_machine = self._create_state_machine(config)
            logger.info("✅ Scan STEP-3 OK: StateMachine created")
        except Exception as e:
            logger.error(f"❌ Scan FAILED (STEP-3): StateMachine error: {e}")
            return self._error_result(
                scan_id, f"StateMachine error: {e}", start_time
            )
        
        # ============================================================
        # ۴. RuleEngine
        # ============================================================
        
        try:
            engine = create_engine_from_config(
                rules_config=config["rules"],
                scoring_config=config.get("scoring", {}),
                state_machine=state_machine,
            )
            logger.info(
                f"✅ Scan STEP-4 OK: RuleEngine built "
                f"({len(engine.rules)} rules)"
            )
        except Exception as e:
            logger.error(f"❌ Scan FAILED (STEP-4): Engine build error: {e}")
            return self._error_result(
                scan_id, f"Engine error: {e}", start_time
            )
        
        # ============================================================
        # ۵. BatchProcessor
        # ============================================================
        
        batch_config = config.get("batch", {})
        try:
            processor = BatchProcessor(
                engine=engine,
                data_fetcher=self._make_data_fetcher(),
                batch_size=batch_config.get("batch_size", 30),
                max_concurrent_fetches=batch_config.get(
                    "max_concurrent_fetches", 10
                ),
                max_workers=batch_config.get("max_workers", 4),
                timeframe=batch_config.get("timeframe", "4h"),
                candle_limit=batch_config.get("candle_limit", 100),
            )
            logger.info(
                f"✅ Scan STEP-5 OK: BatchProcessor "
                f"(batch_size={batch_config.get('batch_size', 30)}, "
                f"timeframe={batch_config.get('timeframe', '4h')})"
            )
        except Exception as e:
            logger.error(f"❌ Scan FAILED (STEP-5): Processor error: {e}")
            return self._error_result(
                scan_id, f"BatchProcessor error: {e}", start_time
            )
        
        # ============================================================
        # ۶. اجرا
        # ============================================================
        
        logger.info(f"🔄 Scan STEP-6: Running batch scan...")
        
        try:
            predictions = processor.process(
                symbols=symbol_items,
                update_state=update_state,
            )
            
            logger.info(
                f"✅ Scan STEP-6 OK: {len(predictions)} passed "
                f"from {total_symbols}"
            )
        except Exception as e:
            logger.error(
                f"❌ Scan FAILED (STEP-6): execution error: {e}",
                exc_info=True,
            )
            return self._error_result(scan_id, f"Scan error: {e}", start_time)
        
        # ============================================================
        # ۷. Filter نهایی
        # ============================================================
        
        predictions = predictions[:max_results]
        
        # ============================================================
        # ۸. ScanResult
        # ============================================================
        
        finished_at = datetime.now()
        duration = time.time() - start_time
        
        result = ScanResult(
            scan_id=scan_id,
            total_scanned=total_symbols,
            passed_count=len(predictions),
            results=predictions,
            config_used=self._sanitize_config(config),
            started_at=datetime.fromtimestamp(start_time),
            finished_at=finished_at,
            duration_seconds=duration,
            errors=[],
        )
        
        # ============================================================
        # ۹. Cache
        # ============================================================
        
        if use_cache:
            self._save_to_cache(result)
            logger.debug(f"💾 Scan result cached: {scan_id}")
        
        # ============================================================
        # ۱۰. History
        # ============================================================
        
        try:
            self._record_scan_history(result)
        except Exception as e:
            logger.warning(f"⚠️ Scan history failed: {e}")
        
        # ============================================================
        # ✅ لاگ موفقیت
        # ============================================================
        
        logger.info("=" * 60)
        logger.info(f"🎉 Scan SUCCESS: {scan_id}")
        logger.info(f"   scanned: {total_symbols}")
        logger.info(f"   passed:  {len(predictions)}")
        logger.info(f"   top:     {[p.symbol for p in predictions[:5]]}")
        logger.info(f"   duration: {duration:.2f}s")
        logger.info("=" * 60)
        
        return result
    
    # ============================================================
    # Execute Single
    # ============================================================
    
    def execute_single(
        self,
        coin_id: str,
        period: str = "24h",
    ) -> Optional[Dict[str, Any]]:
        """اسکن یک symbol واحد"""
        logger.info(f"🎯 Scan SINGLE START: coin_id={coin_id}, period={period}")
        
        try:
            # symbol از coin_id
            symbol = self._coin_to_symbol(coin_id)
            
            config = self._load_config()
            state_machine = self._create_state_machine(config)
            
            engine = create_engine_from_config(
                rules_config=config["rules"],
                scoring_config=config.get("scoring", {}),
                state_machine=state_machine,
            )
            
            # OHLCV
            df = self._fetch_ohlcv_for_symbol(
                symbol=symbol,
                timeframe=config["batch"]["timeframe"],
            )
            
            if df is None or df.empty:
                logger.error(f"❌ Scan SINGLE FAILED: no data for {symbol}")
                return None
            
            prediction = engine.evaluate(
                symbol=symbol,
                coin_id=coin_id,
                df=df,
                update_state=True,
            )
            
            if prediction is None:
                logger.error(f"❌ Scan SINGLE FAILED: prediction None")
                return None
            
            logger.info(
                f"🎉 Scan SINGLE SUCCESS: {symbol} → "
                f"score={prediction.score:.4f}, "
                f"state={prediction.state.value}"
            )
            
            return prediction.to_dict()
        
        except Exception as e:
            logger.error(
                f"❌ Scan SINGLE FAILED for {coin_id}: {e}",
                exc_info=True,
            )
            return None
    
    # ============================================================
    # Config
    # ============================================================
    
    def _load_config(self) -> Dict[str, Any]:
        """بارگذاری config نهایی"""
        default_config = load_default_config()
        
        try:
            effective = self.config_repo.get_effective_config(default_config)
            return effective
        except Exception as e:
            logger.warning(f"⚠️ Override merge failed: {e}")
            return default_config
    
    def reload_config(self) -> Dict[str, Any]:
        """بارگذاری مجدد config"""
        return self._load_config()
    
    # ============================================================
    # Symbols
    # ============================================================
    
    def _get_symbols(
        self,
        symbols: Optional[List[str]],
        top_n: int,
        config: Dict[str, Any],
    ) -> List[Dict[str, str]]:
        """دریافت لیست symbolها"""
        if symbols:
            return [
                {"symbol": s, "coin_id": self._symbol_to_coin(s)}
                for s in symbols
            ]
        
        symbol_config = config.get("symbols", {})
        exclude_stables = symbol_config.get("exclude_stablecoins", True)
        
        try:
            if hasattr(self.api_client, "get_coins_list"):
                coins = self.api_client.get_coins_list(
                    limit=top_n * 2,
                    page=1,
                )
                
                if coins:
                    result = []
                    stables = {
                        "USDT", "USDC", "BUSD", "DAI", "TUSD",
                        "FDUSD", "PYUSD", "USD1",
                    }
                    
                    for coin in coins:
                        sym = coin.get("symbol", "").upper()
                        cid = coin.get("id", "").lower()
                        
                        if not sym or not cid:
                            continue
                        
                        if exclude_stables and sym in stables:
                            continue
                        
                        result.append({
                            "symbol": f"{sym}/USDT",
                            "coin_id": cid,
                        })
                        
                        if len(result) >= top_n:
                            break
                    
                    return result
        except Exception as e:
            logger.warning(f"⚠️ API symbol fetch failed: {e}")
        
        return self._default_symbols(top_n)
    
    def _default_symbols(self, count: int) -> List[Dict[str, str]]:
        """لیست پیش‌فرض"""
        defaults = [
            ("bitcoin", "BTC"),
            ("ethereum", "ETH"),
            ("solana", "SOL"),
            ("binancecoin", "BNB"),
            ("ripple", "XRP"),
            ("cardano", "ADA"),
            ("dogecoin", "DOGE"),
            ("avalanche-2", "AVAX"),
            ("polkadot", "DOT"),
            ("chainlink", "LINK"),
            ("polygon", "MATIC"),
            ("tron", "TRX"),
            ("shiba-inu", "SHIB"),
            ("litecoin", "LTC"),
            ("uniswap", "UNI"),
        ]
        
        return [
            {"symbol": f"{sym}/USDT", "coin_id": cid}
            for cid, sym in defaults[:count]
        ]
    
    @staticmethod
    def _symbol_to_coin(symbol: str) -> str:
        """BTC/USDT → bitcoin"""
        base = symbol.split("/")[0].lower()
        mapping = {
            "btc": "bitcoin",
            "eth": "ethereum",
            "sol": "solana",
            "bnb": "binancecoin",
            "xrp": "ripple",
            "ada": "cardano",
            "doge": "dogecoin",
            "avax": "avalanche-2",
            "dot": "polkadot",
            "link": "chainlink",
        }
        return mapping.get(base, base)
    
    @staticmethod
    def _coin_to_symbol(coin_id: str) -> str:
        """bitcoin → BTC/USDT"""
        mapping = {
            "bitcoin": "BTC/USDT",
            "ethereum": "ETH/USDT",
            "solana": "SOL/USDT",
            "binancecoin": "BNB/USDT",
            "ripple": "XRP/USDT",
            "cardano": "ADA/USDT",
            "dogecoin": "DOGE/USDT",
            "avalanche-2": "AVAX/USDT",
            "polkadot": "DOT/USDT",
            "chainlink": "LINK/USDT",
        }
        cid = coin_id.lower()
        if cid in mapping:
            return mapping[cid]
        return f"{coin_id.upper()}/USDT"
    
    # ============================================================
    # Data Fetcher (OHLCV واقعی)
    # ============================================================
    
    def _make_data_fetcher(self):
        """ساخت تابع fetch داده"""
        def fetch(symbol: str, timeframe: str = "4h") -> Optional[pd.DataFrame]:
            try:
                return self._fetch_ohlcv_for_symbol(symbol, timeframe)
            except Exception as e:
                logger.debug(f"Fetch failed for {symbol}: {e}")
                return None
        
        return fetch
    
    def _fetch_ohlcv_for_symbol(
        self,
        symbol: str,
        timeframe: str = "4h",
    ) -> Optional[pd.DataFrame]:
        """
        دریافت OHLCV واقعی برای یک symbol
        
        Args:
            symbol: "BTC/USDT"
            timeframe: "4h", "1h", ...
        """
        # چک get_ohlcv_candles
        if not hasattr(self.api_client, "get_ohlcv_candles"):
            logger.error("❌ get_ohlcv_candles not available on api_client")
            return None
        
        # interval
        interval = TIMEFRAME_TO_INTERVAL.get(timeframe, "4h")
        
        # range مناسب برای timeframe
        range_map = {
            "1m": "1d",
            "5m": "1w",
            "15m": "1w",
            "1h": "1mo",
            "4h": "3mo",
            "1d": "6mo",
        }
        data_range = range_map.get(timeframe, "3mo")
        
        try:
            result = self.api_client.get_ohlcv_candles(
                exchange="Binance",
                pair=symbol,
                interval=interval,
                range=data_range,
                use_cache=True,
            )
            
            if not result or "candles" not in result:
                return None
            
            # هشدار cap
            if result.get("warning"):
                logger.debug(f"⚠️ {symbol}: {result['warning']}")
            
            candles = result["candles"]
            
            df = self._candles_to_dataframe(candles)
            
            if df is None or len(df) < MIN_CANDLES:
                return None
            
            return df
        
        except Exception as e:
            logger.debug(f"OHLCV fetch error for {symbol}: {e}")
            return None
    
    @staticmethod
    def _candles_to_dataframe(candles: List) -> Optional[pd.DataFrame]:
        """تبدیل candles به DataFrame"""
        if not candles:
            return None
        
        rows = []
        for c in candles:
            if not isinstance(c, (list, tuple)) or len(c) < 6:
                continue
            
            try:
                ts = pd.to_datetime(c[0], unit="ms", errors="coerce")
                if pd.isna(ts):
                    continue
                
                volume = float(c[5]) if c[5] is not None else 0.0
                
                rows.append({
                    "timestamp": ts,
                    "Open": float(c[1]),
                    "High": float(c[2]),
                    "Low": float(c[3]),
                    "Close": float(c[4]),
                    "Volume": volume,
                })
            except (ValueError, TypeError, IndexError):
                continue
        
        if not rows:
            return None
        
        df = pd.DataFrame(rows).set_index("timestamp").sort_index().dropna()
        return df
    
    # ============================================================
    # State Machine
    # ============================================================
    
    def _create_state_machine(self, config: Dict[str, Any]) -> StateMachine:
        """ساخت StateMachine"""
        sm_config = config.get("state_machine", {})
        
        return StateMachine(
            cache=self.cache,
            db=self.db,
            config=sm_config,
        )
    
    # ============================================================
    # Cache
    # ============================================================
    
    def _save_to_cache(self, result: ScanResult) -> None:
        """ذخیره نتیجه در Redis"""
        if not self.cache or not self.cache.is_connected():
            return
        
        try:
            key = f"scan:{result.scan_id}"
            self.cache.set(key, result.to_dict(), ttl=SCAN_CACHE_TTL)
            
            # آخرین اسکن
            self.cache.set(
                "scan:latest",
                result.scan_id,
                ttl=SCAN_CACHE_TTL,
            )
        except Exception as e:
            logger.warning(f"⚠️ Cache save failed: {e}")
    
    def get_cached_scan(self, scan_id: str) -> Optional[Dict[str, Any]]:
        """بازیابی اسکن از cache"""
        if not self.cache or not self.cache.is_connected():
            return None
        
        try:
            if scan_id == "latest":
                scan_id = self.cache.get("scan:latest")
                if not scan_id:
                    return None
            
            return self.cache.get(f"scan:{scan_id}")
        except Exception as e:
            logger.warning(f"⚠️ Cache read failed: {e}")
            return None
    
    # ============================================================
    # DB History
    # ============================================================
    
    def _record_scan_history(self, result: ScanResult) -> None:
        """ثبت اسکن در DB"""
        if not self.db or not self.db.is_connected():
            return
        
        try:
            self.db.execute(
                """
                CREATE TABLE IF NOT EXISTS scan_history (
                    id SERIAL PRIMARY KEY,
                    scan_id VARCHAR(100) NOT NULL UNIQUE,
                    total_scanned INTEGER NOT NULL,
                    passed_count INTEGER NOT NULL,
                    top_symbols TEXT[],
                    duration_seconds REAL,
                    config_used JSONB,
                    created_at TIMESTAMP NOT NULL DEFAULT NOW()
                )
                """
            )
            
            top_symbols = [p.symbol for p in result.results[:10]]
            
            self.db.execute(
                """
                INSERT INTO scan_history (
                    scan_id, total_scanned, passed_count,
                    top_symbols, duration_seconds, config_used, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (scan_id) DO NOTHING
                """,
                (
                    result.scan_id,
                    result.total_scanned,
                    result.passed_count,
                    top_symbols,
                    result.duration_seconds,
                    json.dumps(result.config_used),
                    result.started_at,
                ),
            )
        except Exception as e:
            logger.debug(f"Scan history record failed: {e}")
    
    def get_scan_history(
        self,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """دریافت تاریخچه اسکن‌ها"""
        if not self.db or not self.db.is_connected():
            return []
        
        try:
            result = self.db.execute(
                """
                SELECT scan_id, total_scanned, passed_count,
                       top_symbols, duration_seconds, created_at
                FROM scan_history
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (limit,),
            )
            return result or []
        except Exception as e:
            logger.error(f"❌ Get scan history failed: {e}")
            return []
    
    # ============================================================
    # Helpers
    # ============================================================
    
    @staticmethod
    def _sanitize_config(config: Dict[str, Any]) -> Dict[str, Any]:
        """پاک‌سازی config"""
        import copy
        sanitized = copy.deepcopy(config)
        for key in ["api_key", "secret", "password"]:
            sanitized.pop(key, None)
        return sanitized
    
    def _error_result(
        self,
        scan_id: str,
        error_message: str,
        start_time: float,
    ) -> ScanResult:
        """ساخت ScanResult برای خطا"""
        return ScanResult(
            scan_id=scan_id,
            total_scanned=0,
            passed_count=0,
            results=[],
            started_at=datetime.fromtimestamp(start_time),
            finished_at=datetime.now(),
            duration_seconds=time.time() - start_time,
            errors=[error_message],
        )
    
    # ============================================================
    # Stats
    # ============================================================
    
    def get_stats(self) -> Dict[str, Any]:
        """آمار Use Case"""
        return {
            "cache_connected": (
                self.cache is not None and self.cache.is_connected()
            ),
            "db_connected": (
                self.db is not None and self.db.is_connected()
            ),
            "config_repo": self.config_repo.get_stats(),
            "timeframe_to_interval": TIMEFRAME_TO_INTERVAL,
        }


__all__ = ["ScanMarketUseCase"]
