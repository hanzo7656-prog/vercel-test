# infrastructure/api/binance_ws_client.py

import asyncio
import json
import logging
import threading
import time
from typing import Dict, Any, Optional, List, Set
from datetime import datetime
from decimal import Decimal, InvalidOperation

import requests  # برای REST snapshot
import websockets  # برای WebSocket
from websockets.exceptions import ConnectionClosed

from infrastructure.database import get_cache


logger = logging.getLogger(__name__)


class BinanceWSClient:
    """
    Binance WebSocket Client

    ویژگی‌ها:
        - Background thread از طریق ThreadingManager
        - Auto-reconnect با exponential backoff
        - Cache در Redis
        - Multiple symbols
        - REST snapshot + WS updates
        - Thread-safe

    استفاده:
        client = BinanceWSClient()
        client.start()

        # در هر جای دیگه
        orderbook = client.get_orderbook('btcusdt')
        price = client.get_price('btcusdt')
    """

    # Constants
    BINANCE_WS_BASE = "wss://data-stream.binance.vision/ws"
    BINANCE_REST_BASE = "https://api.binance.com"

    DEFAULT_SYMBOLS = ["btcusdt", "ethusdt", "solusdt", "adausdt", "xrpusdt"]

    DEPTH_LEVELS = 20
    UPDATE_SPEED = "1000ms"   # 🆕 برای Render free tier (قبلاً 100ms)

    RECONNECT_INITIAL = 1
    RECONNECT_MAX = 30

    CACHE_TTL_ORDERBOOK = 30   # 30s
    CACHE_TTL_PRICE = 300      # 5min
    CACHE_TTL_STATS = 60       # 1min

    # 🆕 حداکثر کهنگی مجاز داده (ثانیه)
    MAX_STALE_SECONDS = 10

    # 🆕 نام thread در ThreadingManager
    THREAD_NAME = "binance_ws_client"

    # ============================================================
    # Init
    # ============================================================

    def __init__(
        self,
        symbols: Optional[List[str]] = None,
        auto_start: bool = False,
    ):
        self.symbols: List[str] = [
            s.lower() for s in (symbols or self.DEFAULT_SYMBOLS)
        ]

        # Cache
        self.cache = get_cache()

        # State
        self._orderbooks: Dict[str, Dict[str, Any]] = {}
        self._prices: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

        # 🆕 فلگ صریح (مثل is_connected در FreeCryptoClient)
        self._running: bool = False

        # 🆕 وضعیت اتصال per-symbol
        self._connected_symbols: Set[str] = set()

        # Stats
        self.stats: Dict[str, Any] = {
            "connected": False,
            "started_at": None,
            "last_message_at": None,
            "total_messages": 0,
            "total_errors": 0,
            "reconnect_count": 0,
            "active_symbols": [],
            "current_symbol": None,
        }

        logger.info(f"✅ BinanceWSClient initialized (symbols: {self.symbols})")

        if auto_start:
            self.start()

    # ============================================================
    # Start / Stop / IsRunning — از طریق ThreadingManager
    # ============================================================

    def start(self) -> bool:
        """شروع کلاینت از طریق ThreadingManager"""
        from core.threading_manager import threading_manager

        # اگر قبلاً ثبت شده و زنده است
        status = threading_manager.get_status(self.THREAD_NAME)
        if status and status.get("alive"):
            logger.warning("⚠️ BinanceWSClient already running")
            return False

        # ریست کامل state
        self._stop_event.clear()
        with self._lock:
            self._connected_symbols.clear()
        self.stats["connected"] = False
        self._running = True

        # ثبت در ThreadingManager — target همان _run_loop است، نه start
        threading_manager.register(
            name=self.THREAD_NAME,
            target=self._run_loop,
            daemon=True,
            auto_restart=True,
            max_restarts=10,
            restart_delay=30,       # 🆕 فاصله‌ی restart برای جلوگیری از حلقه‌ی سریع
            start_now=True,
        )

        self.stats["started_at"] = datetime.now().isoformat()
        logger.info("🚀 BinanceWSClient started via ThreadingManager")
        return True

    def stop(self, timeout: float = 5.0) -> bool:
        """توقف کلاینت از طریق ThreadingManager"""
        from core.threading_manager import threading_manager

        self._stop_event.set()
        self._running = False

        # توقف از طریق ThreadingManager
        threading_manager.stop(self.THREAD_NAME)

        with self._lock:
            self._connected_symbols.clear()
        self.stats["connected"] = False

        logger.info("⏹️ BinanceWSClient stopped")
        return True

    def is_running(self) -> bool:
        """آیا کلاینت در حال اجراست؟"""
        from core.threading_manager import threading_manager

        status = threading_manager.get_status(self.THREAD_NAME)
        if status:
            return bool(status.get("alive", False)) and self._running
        return False

    # ============================================================
    # Thread Main
    # ============================================================

    def _run_loop(self) -> None:
        """
        حلقه اصلی (به‌عنوان target به ThreadingManager داده می‌شود)

        ⚠️ نکته: ManagedThread._run_wrapper این تابع را در یک حلقه صدا می‌زند.
        پس این تابع باید یا تا ابد بچرخد (while not stop)، یا سریع برگردد.
        اینجا while داخلی داریم، پس عملاً یک بار صدا زده می‌شود و تا stop ادامه می‌دهد.
        """
        logger.info("🔄 BinanceWSClient thread started")
        self._running = True

        try:
            while not self._stop_event.is_set():
                try:
                    asyncio.run(self._run_all_symbols())
                except Exception as e:
                    logger.error(f"❌ Run loop error: {e}", exc_info=True)

                if not self._stop_event.is_set():
                    logger.info("🔄 Reconnecting in 5s...")
                    self._stop_event.wait(5)

        finally:
            # 🆕 حتی اگر thread به‌خاطر exception بمیرد، این اجرا می‌شود
            self._running = False
            with self._lock:
                self._connected_symbols.clear()
            self.stats["connected"] = False
            logger.info("🔄 BinanceWSClient thread stopped")

    async def _run_all_symbols(self) -> None:
        """شروع task برای همه symbol ها"""
        tasks = []

        for symbol in self.symbols:
            if self._stop_event.is_set():
                break
            task = asyncio.create_task(self._ws_task(symbol))
            tasks.append(task)

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    # ============================================================
    # WebSocket Task for one symbol
    # ============================================================

    async def _ws_task(self, symbol: str) -> None:
        """
        Task برای یک symbol

        مراحل:
            1. REST snapshot (order book اولیه)
            2. WS connect
            3. دریافت updates
            4. Cache در Redis
        """
        reconnect_delay = self.RECONNECT_INITIAL
        url = f"{self.BINANCE_WS_BASE}/{symbol}@depth{self.DEPTH_LEVELS}@{self.UPDATE_SPEED}"

        while not self._stop_event.is_set():
            try:
                self.stats["current_symbol"] = symbol

                # ۱. REST snapshot
                snapshot = await self._fetch_snapshot(symbol)

                if snapshot:
                    with self._lock:
                        self._orderbooks[symbol] = snapshot

                    self._cache_orderbook(symbol, snapshot)
                    logger.info(f"✅ Snapshot fetched: {symbol}")

                # ۲. WebSocket connect
                logger.info(f"🔗 Connecting to Binance WS: {symbol}")

                async with websockets.connect(
                    url,
                    ping_interval=20,
                    ping_timeout=10,
                    close_timeout=5,
                ) as ws:
                    logger.info(f"✅ WS connected: {symbol}")

                    # 🆕 ثبت اتصال per-symbol
                    with self._lock:
                        self._connected_symbols.add(symbol)
                    self._update_connected_flag()

                    reconnect_delay = self.RECONNECT_INITIAL

                    async for message in ws:
                        if self._stop_event.is_set():
                            break

                        try:
                            data = json.loads(message)
                            self._process_orderbook_update(symbol, data)

                            self.stats["total_messages"] += 1
                            self.stats["last_message_at"] = datetime.now().isoformat()

                        except json.JSONDecodeError as e:
                            logger.warning(f"⚠️ Invalid JSON for {symbol}: {e}")
                        except Exception as e:
                            logger.error(f"❌ Process error for {symbol}: {e}")

            except asyncio.CancelledError:
                logger.info(f"🛑 Task cancelled: {symbol}")
                break
            except ConnectionClosed as e:
                logger.warning(f"🔌 WS closed: {symbol} | {e}")
                self.stats["reconnect_count"] += 1
            except Exception as e:
                logger.error(f"❌ WS error: {symbol} | {e}")
                self.stats["reconnect_count"] += 1
                self.stats["total_errors"] += 1
            finally:
                # 🆕 حذف اتصال per-symbol در هر خروج
                with self._lock:
                    self._connected_symbols.discard(symbol)
                self._update_connected_flag()

            if not self._stop_event.is_set():
                logger.info(f"⏳ Reconnect in {reconnect_delay}s ({symbol})")
                await asyncio.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 2, self.RECONNECT_MAX)

    def _update_connected_flag(self) -> None:
        """🆕 به‌روزرسانی فلگ connected بر اساس اتصال‌های واقعی"""
        with self._lock:
            self.stats["connected"] = len(self._connected_symbols) > 0

    # ============================================================
    # REST Snapshot
    # ============================================================

    async def _fetch_snapshot(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        دریافت snapshot اولیه از REST API

        این لازمه چون Binance depth stream فقط updates می‌ده
        """
        try:
            url = f"{self.BINANCE_REST_BASE}/api/v3/depth"
            params = {
                "symbol": symbol.upper(),
                "limit": self.DEPTH_LEVELS,
            }

            response = await asyncio.to_thread(
                requests.get,
                url,
                params=params,
                timeout=10,
            )

            if response.status_code == 200:
                data = response.json()
                return {
                    "symbol": symbol,
                    "lastUpdateId": data.get("lastUpdateId"),
                    "bids": data.get("bids", []),
                    "asks": data.get("asks", []),
                    "timestamp": datetime.now().isoformat(),
                    "source": "rest_snapshot",
                }

            logger.warning(f"⚠️ Snapshot failed for {symbol}: HTTP {response.status_code}")
            return None

        except Exception as e:
            logger.error(f"❌ Snapshot error for {symbol}: {e}")
            return None

    # ============================================================
    # Process Updates
    # ============================================================

    def _process_orderbook_update(
        self,
        symbol: str,
        data: Dict[str, Any],
    ) -> None:
        """
        پردازش update از WebSocket
        """
        try:
            bids = data.get("bids", [])
            asks = data.get("asks", [])

            # 🆕 محاسبه با Decimal برای جلوگیری از نویز float
            best_bid = self._to_float(bids[0][0]) if bids else 0.0
            best_ask = self._to_float(asks[0][0]) if asks else 0.0

            if best_bid and best_ask:
                mid_price = (best_bid + best_ask) / 2
                spread = float(Decimal(str(best_ask)) - Decimal(str(best_bid)))
            else:
                mid_price = 0.0
                spread = 0.0

            now_iso = datetime.now().isoformat()

            orderbook = {
                "symbol": symbol,
                "lastUpdateId": data.get("lastUpdateId"),
                "bids": bids,
                "asks": asks,
                "best_bid": best_bid,
                "best_ask": best_ask,
                "mid_price": mid_price,
                "spread": spread,
                "timestamp": now_iso,
                "source": "websocket",
            }

            with self._lock:
                self._orderbooks[symbol] = orderbook

                self._prices[symbol] = {
                    "symbol": symbol,
                    "price": mid_price,
                    "best_bid": best_bid,
                    "best_ask": best_ask,
                    "timestamp": now_iso,
                }

            self._cache_orderbook(symbol, orderbook)
            self._cache_price(symbol, mid_price, best_bid, best_ask)

        except Exception as e:
            logger.error(f"❌ Process update error for {symbol}: {e}")

    @staticmethod
    def _to_float(value: Any) -> float:
        """🆕 تبدیل ایمن string به float"""
        try:
            return float(Decimal(str(value)))
        except (InvalidOperation, ValueError, TypeError):
            return 0.0

    # ============================================================
    # Cache
    # ============================================================

    def _cache_orderbook(
        self,
        symbol: str,
        orderbook: Dict[str, Any],
    ) -> None:
        """ذخیره order book در Redis"""
        if not self.cache or not self.cache.is_connected():
            return

        try:
            key = f"ws:orderbook:{symbol}"
            self.cache.set(key, orderbook, ttl=self.CACHE_TTL_ORDERBOOK)
        except Exception as e:
            logger.debug(f"⚠️ Cache orderbook error: {e}")

    def _cache_price(
        self,
        symbol: str,
        price: float,
        best_bid: float,
        best_ask: float,
    ) -> None:
        """ذخیره قیمت در Redis"""
        if not self.cache or not self.cache.is_connected():
            return

        try:
            key = f"ws:price:{symbol}"
            self.cache.set(key, {
                "price": price,
                "best_bid": best_bid,
                "best_ask": best_ask,
                "timestamp": datetime.now().isoformat(),
            }, ttl=self.CACHE_TTL_PRICE)
        except Exception as e:
            logger.debug(f"⚠️ Cache price error: {e}")

    def _cache_stats(self) -> None:
        """ذخیره آمار در Redis"""
        if not self.cache or not self.cache.is_connected():
            return

        try:
            self.cache.set(
                "ws:stats",
                self.get_stats(),
                ttl=self.CACHE_TTL_STATS,
            )
        except Exception as e:
            logger.debug(f"⚠️ Cache stats error: {e}")

    # ============================================================
    # Public API
    # ============================================================

    def _is_stale(self, item: Dict[str, Any]) -> bool:
        """🆕 بررسی کهنگی داده"""
        ts = item.get("timestamp")
        if not ts:
            return True
        try:
            age = (datetime.now() - datetime.fromisoformat(ts)).total_seconds()
            return age > self.MAX_STALE_SECONDS
        except Exception:
            return True

    def get_orderbook(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        دریافت order book یک symbol

        اول از حافظه، اگه نبود از Redis
        """
        symbol = symbol.lower()

        # ۱. از حافظه
        with self._lock:
            if symbol in self._orderbooks:
                ob = self._orderbooks[symbol].copy()
                if not self._is_stale(ob):
                    return ob

        # ۲. از Redis
        if self.cache and self.cache.is_connected():
            try:
                cached = self.cache.get(f"ws:orderbook:{symbol}")
                if cached and not self._is_stale(cached):
                    return cached
            except Exception:
                pass

        return None

    def get_price(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        دریافت قیمت یک symbol

        اول از حافظه، اگه نبود از Redis
        """
        symbol = symbol.lower()

        # ۱. از حافظه
        with self._lock:
            if symbol in self._prices:
                p = self._prices[symbol].copy()
                if not self._is_stale(p):
                    return p

        # ۲. از Redis
        if self.cache and self.cache.is_connected():
            try:
                cached = self.cache.get(f"ws:price:{symbol}")
                if cached and not self._is_stale(cached):
                    return cached
            except Exception:
                pass

        return None

    def get_all_prices(self) -> Dict[str, Dict[str, Any]]:
        """دریافت همه قیمت‌ها"""
        result = {}

        with self._lock:
            for symbol in self.symbols:
                if symbol in self._prices:
                    p = self._prices[symbol].copy()
                    if not self._is_stale(p):
                        result[symbol] = p

        return result

    def get_stats(self) -> Dict[str, Any]:
        """دریافت آمار کامل"""
        with self._lock:
            active_symbols = [
                s for s in self.symbols if s in self._orderbooks
            ]
            connected_count = len(self._connected_symbols)

        return {
            **self.stats,
            "is_running": self.is_running(),
            "symbols": self.symbols,
            "active_symbols": active_symbols,
            "cached_symbols_count": len(active_symbols),
            "total_symbols": len(self.symbols),
            "cache_connected": self.cache is not None and self.cache.is_connected(),
            "connected_symbols_count": connected_count,
        }

    def subscribe(self, symbol: str) -> bool:
        """اضافه کردن symbol جدید (runtime)"""
        symbol = symbol.lower()

        if symbol in self.symbols:
            return False

        self.symbols.append(symbol)
        logger.info(f"✅ Symbol added: {symbol}")

        # نیاز به restart thread
        if self.is_running():
            self.stop(timeout=10)
            time.sleep(1)
            self.start()

        return True

    def unsubscribe(self, symbol: str) -> bool:
        """حذف symbol (runtime)"""
        symbol = symbol.lower()

        if symbol not in self.symbols:
            return False

        self.symbols.remove(symbol)

        with self._lock:
            self._orderbooks.pop(symbol, None)
            self._prices.pop(symbol, None)
            self._connected_symbols.discard(symbol)

        self._update_connected_flag()
        logger.info(f"✅ Symbol removed: {symbol}")
        return True


# ============================================================
# Singleton
# ============================================================

binance_ws_client = BinanceWSClient(auto_start=False)
