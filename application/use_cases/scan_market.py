# application/use_cases/scan_market.py
# ============================================================
# Use Case: Scan Market
# نسخه ۱.۰
# ============================================================
# 
# نقش:
#   - Orchestrate کل فرآیند اسکن بازار
#   - اتصال RuleEngine + BatchProcessor + StateMachine
#   - ذخیره نتایج در Redis (کش) و DB (تاریخچه)
# 
# این Use Case جایگزین PredictCoinUseCase قدیمی می‌شه
# (البته PredictCoinUseCase برای تک‌ارز باقی می‌مونه)
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
# ScanMarketUseCase
# ============================================================

class ScanMarketUseCase:
    """
    Use Case اسکن بازار
    
    مسئولیت‌ها:
        ۱. بارگذاری config (default + override)
        ۲. ساخت RuleEngine
        ۳. ساخت BatchProcessor
        ۴. دریافت symbolها
        ۵. اجرای اسکن
        ۶. ذخیره نتایج
        ۷. برگرداندن ScanResult
    """
    
    # Cache TTL برای نتایج اسکن (۱ ساعت)
    SCAN_CACHE_TTL = 3600
    
    def __init__(
        self,
        api_client: Any,
        cache: Any,
        db: Any,
    ) -> None:
        """
        Args:
            api_client: coinstats_client یا مشابه
            cache: Redis client (get_cache())
            db: PostgreSQL client (get_primary())
        """
        self.api_client = api_client
        self.cache = cache
        self.db = db
        self.config_repo = rule_config_repository
        
        logger.info("✅ ScanMarketUseCase initialized")
    
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
        اجرای اسکن کامل
        
        Args:
            symbols: لیست symbolها (اگه None، از config می‌گیریم)
            top_n: تعداد symbolها (وقتی symbols داده نشه)
            timeframe: تایم‌فریم (اگه None، از config)
            max_results: حداکثر نتیجه نهایی
            update_state: آپدیت State Machine؟
            use_cache: استفاده از cache برای نتایج؟
        
        Returns:
            ScanResult
        """
        start_time = time.time()
        scan_id = f"scan-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
        
        logger.info(f"🔍 Scan started: {scan_id}")
        
        # ============================================================
        # ۱. بارگذاری config
        # ============================================================
        
        try:
            config = self._load_config()
        except Exception as e:
            logger.error(f"❌ Config load failed: {e}")
            return self._error_result(scan_id, f"Config error: {e}", start_time)
        
        # اعمال overrideها
        if timeframe:
            config.setdefault("batch", {})["timeframe"] = timeframe
        
        # ============================================================
        # ۲. دریافت symbolها
        # ============================================================
        
        try:
            symbol_items = self._get_symbols(
                symbols=symbols,
                top_n=top_n,
                config=config,
            )
        except Exception as e:
            logger.error(f"❌ Symbol fetch failed: {e}")
            return self._error_result(scan_id, f"Symbol error: {e}", start_time)
        
        if not symbol_items:
            return self._error_result(
                scan_id, "No symbols to scan", start_time
            )
        
        total_symbols = len(symbol_items)
        logger.info(f"📊 Scanning {total_symbols} symbols")
        
        # ============================================================
        # ۳. ساخت StateMachine
        # ============================================================
        
        try:
            state_machine = self._create_state_machine(config)
        except Exception as e:
            logger.error(f"❌ StateMachine failed: {e}")
            return self._error_result(scan_id, f"StateMachine error: {e}", start_time)
        
        # ============================================================
        # ۴. ساخت RuleEngine
        # ============================================================
        
        try:
            engine = create_engine_from_config(
                rules_config=config["rules"],
                scoring_config=config.get("scoring", {}),
                state_machine=state_machine,
            )
        except Exception as e:
            logger.error(f"❌ RuleEngine build failed: {e}")
            return self._error_result(scan_id, f"Engine error: {e}", start_time)
        
        # ============================================================
        # ۵. ساخت BatchProcessor
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
        except Exception as e:
            logger.error(f"❌ BatchProcessor build failed: {e}")
            return self._error_result(
                scan_id, f"BatchProcessor error: {e}", start_time
            )
        
        # ============================================================
        # ۶. اجرای اسکن
        # ============================================================
        
        try:
            predictions = processor.process(
                symbols=symbol_items,
                update_state=update_state,
            )
        except Exception as e:
            logger.error(f"❌ Scan execution failed: {e}", exc_info=True)
            return self._error_result(scan_id, f"Scan error: {e}", start_time)
        
        # ============================================================
        # ۷. فیلتر نهایی
        # ============================================================
        
        # فقط top max_results
        predictions = predictions[:max_results]
        
        # ============================================================
        # ۸. ساخت ScanResult
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
        # ۹. ذخیره در cache
        # ============================================================
        
        if use_cache:
            self._save_to_cache(result)
        
        # ============================================================
        # ۱۰. ثبت در DB (اختیاری)
        # ============================================================
        
        try:
            self._record_scan_history(result)
        except Exception as e:
            logger.warning(f"⚠️ Scan history record failed: {e}")
        
        logger.info(
            f"✅ Scan completed: {scan_id} — "
            f"{len(predictions)} passed from {total_symbols} "
            f"({duration:.2f}s)"
        )
        
        return result
    
    # ============================================================
    # Execute Single (برای PredictCoinUseCase)
    # ============================================================
    
    def execute_single(
        self,
        coin_id: str,
        period: str = "24h",
    ) -> Optional[Dict[str, Any]]:
        """
        اسکن یک symbol واحد
        
        برای سازگاری با PredictCoinUseCase قدیمی
        
        Args:
            coin_id: مثل "bitcoin"
            period: بازه داده
        
        Returns:
            دیکشنری با prediction
        """
        try:
            # symbol از coin_id
            symbol = self._coin_to_symbol(coin_id)
            
            # config
            config = self._load_config()
            
            # state machine
            state_machine = self._create_state_machine(config)
            
            # engine
            engine = create_engine_from_config(
                rules_config=config["rules"],
                scoring_config=config.get("scoring", {}),
                state_machine=state_machine,
            )
            
            # fetch داده
            fetch = self._make_data_fetcher()
            df = fetch(symbol=symbol, timeframe=config["batch"]["timeframe"])
            
            if df is None or df.empty:
                return None
            
            # ارزیابی
            prediction = engine.evaluate(
                symbol=symbol,
                coin_id=coin_id,
                df=df,
                update_state=True,
            )
            
            if prediction is None:
                return None
            
            return prediction.to_dict()
        except Exception as e:
            logger.error(f"❌ Single scan failed for {coin_id}: {e}", exc_info=True)
            return None
    
    # ============================================================
    # Config
    # ============================================================
    
    def _load_config(self) -> Dict[str, Any]:
        """
        بارگذاری config نهایی (default + override)
        """
        default_config = load_default_config()
        
        try:
            effective = self.config_repo.get_effective_config(default_config)
            return effective
        except Exception as e:
            logger.warning(f"⚠️ Override merge failed, using default: {e}")
            return default_config
    
    def reload_config(self) -> Dict[str, Any]:
        """
        بارگذاری مجدد config (برای API)
        """
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
        """
        دریافت لیست symbolها
        
        اگه symbols داده شده → مستقیم
        وگرنه → از API top n
        """
        if symbols:
            return [
                {"symbol": s, "coin_id": self._symbol_to_coin(s)}
                for s in symbols
            ]
        
        # از config
        symbol_config = config.get("symbols", {})
        exclude_stables = symbol_config.get("exclude_stablecoins", True)
        
        # از API top volume
        try:
            if hasattr(self.api_client, "get_coins_list"):
                coins = self.api_client.get_coins_list(
                    limit=top_n * 2,  # کمی بیشتر برای فیلتر
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
        
        # Fallback: پیش‌فرض
        return self._default_symbols(top_n)
    
    def _default_symbols(self, count: int) -> List[Dict[str, str]]:
        """لیست پیش‌فرض symbolها (fallback)"""
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
        """BTC/USDT → bitcoin (تقریبی)"""
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
        """bitcoin → BTC/USDT (تقریبی)"""
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
        # fallback: از خود coin_id بساز
        return f"{coin_id.upper()}/USDT"
    
    # ============================================================
    # Data Fetcher
    # ============================================================
    
    def _make_data_fetcher(self):
        """
        ساخت تابع fetch داده برای BatchProcessor
        
        Returns:
            callable(symbol, timeframe) → DataFrame
        """
        def fetch(symbol: str, timeframe: str = "4h") -> Optional[pd.DataFrame]:
            try:
                return self._fetch_ohlcv(symbol, timeframe)
            except Exception as e:
                logger.debug(f"Fetch failed for {symbol}: {e}")
                return None
        
        return fetch
    
    def _fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str = "4h",
    ) -> Optional[pd.DataFrame]:
        """
        دریافت OHLCV از API
        
        چالش: CoinStats API از symbol پشتیبانی نمی‌کنه
        راه‌حل: از coin_id استفاده کن
        """
        # استخراج coin_id از symbol
        coin_id = self._symbol_to_coin(symbol)
        
        # نگاشت timeframe به period مورد قبول API
        period_map = {
            "1h": "24h",
            "4h": "1w",
            "1d": "1m",
            "1w": "3m",
        }
        period = period_map.get(timeframe, "1m")
        
        try:
            # تلاش از coinstats_client
            if hasattr(self.api_client, "get_chart"):
                data = self.api_client.get_chart(coin_id, period)
                
                if not data or not isinstance(data, list):
                    return None
                
                # تبدیل به DataFrame
                df = self._list_to_dataframe(data)
                return df
        except Exception as e:
            logger.debug(f"API fetch failed for {coin_id}: {e}")
        
        return None
    
    @staticmethod
    def _list_to_dataframe(data: List) -> pd.DataFrame:
        """
        تبدیل خروجی API به DataFrame OHLCV
        
        ساختار API: [[timestamp, price], ...]
        ولی ما OHLCV نیاز داریم. از price برای همه استفاده می‌کنیم.
        """
        if not data:
            return pd.DataFrame()
        
        rows = []
        for point in data:
            if isinstance(point, (list, tuple)) and len(point) >= 2:
                ts = point[0]
                price = float(point[1])
                
                # حجم و OHLC رو نداریم → تقریب
                rows.append({
                    "timestamp": pd.to_datetime(ts, unit="ms", errors="coerce"),
                    "Open": price,
                    "High": price,
                    "Low": price,
                    "Close": price,
                    "Volume": 1.0,  # placeholder
                })
        
        if not rows:
            return pd.DataFrame()
        
        df = pd.DataFrame(rows)
        df = df.set_index("timestamp").sort_index()
        df = df.dropna()
        
        # فیلتر: حداقل ۳۰ ردیف
        if len(df) < 30:
            return pd.DataFrame()
        
        return df
    
    # ============================================================
    # State Machine
    # ============================================================
    
    def _create_state_machine(self, config: Dict[str, Any]) -> StateMachine:
        """ساخت StateMachine از config"""
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
            self.cache.set(
                key,
                result.to_dict(),
                ttl=self.SCAN_CACHE_TTL,
            )
            
            # آخرین اسکن
            self.cache.set(
                "scan:latest",
                result.scan_id,
                ttl=self.SCAN_CACHE_TTL,
            )
        except Exception as e:
            logger.warning(f"⚠️ Cache save failed: {e}")
    
    def get_cached_scan(self, scan_id: str) -> Optional[Dict[str, Any]]:
        """
        بازیابی اسکن از cache
        
        Args:
            scan_id: شناسه اسکن ("latest" برای آخرین)
        """
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
        """
        ثبت اسکن در DB
        
        جدول: scan_history
        (خودکار ساخته می‌شه)
        """
        if not self.db or not self.db.is_connected():
            return
        
        try:
            # ساخت جدول
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
            
            # ثبت
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
        """پاک‌سازی config برای ذخیره (حذف داده‌های حساس)"""
        import copy
        sanitized = copy.deepcopy(config)
        # حذف کلیدهای حساس اگه هستن
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
        }


__all__ = ["ScanMarketUseCase"]
