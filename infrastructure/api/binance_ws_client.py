# infrastructure/api/binance_ws_client.py

import asyncio
import json
import logging
import threading
import time
from typing import Dict, Any, Optional, List, Set
from datetime import datetime
from decimal import Decimal, InvalidOperation

import requests
import websockets
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
        - is_running مستقل (heartbeat داخلی)
    """

    # Constants
    BINANCE_WS_BASE = "wss://data-stream.binance.vision/ws"
    BINANCE_REST_BASE = "https://api.binance.com"

    DEFAULT_SYMBOLS = ["btcusdt", "ethusdt", "solusdt", "adausdt", "xrpusdt"]

    DEPTH_LEVELS = 20
    UPDATE_SPEED = "1000ms"

    RECONNECT_INITIAL = 1
    RECONNECT_MAX = 30

    CACHE_TTL_ORDERBOOK = 30
    CACHE_TTL_PRICE = 300
    CACHE_TTL_STATS = 60

    MAX_STALE_SECONDS = 10
    HEARTBEAT_INTERVAL = 5
    HEARTBEAT_MAX_AGE = 15

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

        self.cache = get_cache()

        self._orderbooks: Dict[str, Dict[str, Any]] = {}
        self._prices: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

        # 🆕 فلگ صریح
        self._running: bool = False

        # 🆕 وضعیت اتصال per-symbol
        self._connected_symbols: Set[str] = set()

        # Stats
        self.stats: Dict[str, Any] = {
            "connected": False,
            "started_at": None,
            "last_message_at": None,
            "heartbeat": None,          # 🆕
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
    # Start / Stop / IsRunning
    # ============================================================

    def start(self) -> bool:
        from core.threading_manager import threading_manager
    
        # 🆕 اگر thread قبلی در ThreadingManager هست، اول بکشش
        status = threading_manager.get_status(self.THREAD_NAME)
        if status and status.get("alive"):
            logger.warning("⚠️ Stopping old thread before starting new one")
            threading_manager.stop(self.THREAD_NAME)
            time.sleep(2)   # صبر کن تا کامل بمیرد
    
        # ریست کامل
        self._stop_event.clear()
        self._running = False
        with self._lock:
            self._connected_symbols.clear()
        self.stats["connected"] = False
        self.stats["heartbeat"] = None
        self.stats["total_messages"] = 0
        self.stats["total_errors"] = 0
        self.stats["reconnect_count"] = 0
        self.stats["last_message_at"] = None
        self.stats["started_at"] = datetime.now().isoformat()
    
        self._running = True
    
        threading_manager.register(
            name=self.THREAD_NAME,
            target=self._run_loop,
            daemon=True,
            auto_restart=True,
            max_restarts=10,
            restart_delay=30,
            start_now=True,
        )
    
        logger.info("🚀 BinanceWSClient started via ThreadingManager")
        return True

    def stop(self, timeout: float = 5.0) -> bool:
        """توقف کلاینت"""
        from core.threading_manager import threading_manager

        self._stop_event.set()
        self._running = False

        threading_manager.stop(self.THREAD_NAME)

        with self._lock:
            self._connected_symbols.clear()
        self.stats["connected"] = False

        logger.info("⏹️ BinanceWSClient stopped")
        return True

    def is_running(self) -> bool:
        """
        🆕 مستقل از ThreadingManager — بر اساس heartbeat داخلی

        چرا: ThreadingManager per-worker است و درخواست ممکن است به
        worker دیگری برسد که ThreadingManager خالی دارد.
        """
        if not self._running:
            return False

        hb = self.stats.get("heartbeat")
        if not hb:
            return False

        try:
            age = (datetime.now() - datetime.fromisoformat(hb)).total_seconds()
            return age <= self.HEARTBEAT_MAX_AGE
        except Exception:
            return False

    # ============================================================
    # Thread Main
    # ============================================================

    def _run_loop(self) -> None:
        """حلقه اصلی + heartbeat داخلی"""
        logger.info("🔄 BinanceWSClient thread started")
        self._running = True
        self.stats["heartbeat"] = datetime.now().isoformat()

        # 🆕 heartbeat thread مستقل
        def heartbeat_loop():
            while not self._stop_event.is_set():
                self.stats["heartbeat"] = datetime.now().isoformat()
                self._stop_event.wait(self.HEARTBEAT_INTERVAL)

        hb_thread = threading.Thread(
            target=heartbeat_loop,
            daemon=True,
            name="BinanceWS-Heartbeat",
        )
        hb_thread.start()

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
            self._running = False
            with self._lock:
                self._connected_symbols.clear()
            self.stats["connected"] = False
            self.stats["heartbeat"] = None
            logger.info("🔄 BinanceWSClient thread stopped")

    async def _run_all_symbols(self) -> None:
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
        reconnect_delay = self.RECONNECT_INITIAL
        url = f"{self.BINANCE_WS_BASE}/{symbol}@depth{self.DEPTH_LEVELS}@{self.UPDATE_SPEED}"

        while not self._stop_event.is_set():
            try:
                self.stats["current_symbol"] = symbol

                snapshot = await self._fetch_snapshot(symbol)
                if snapshot:
                    with self._lock:
                        self._orderbooks[symbol] = snapshot
                    self._cache_orderbook(symbol, snapshot)
                    logger.info(f"✅ Snapshot fetched: {symbol}")

                logger.info(f"🔗 Connecting to Binance WS: {symbol}")

                async with websockets.connect(
                    url,
                    ping_interval=20,
                    ping_timeout=10,
                    close_timeout=5,
                ) as ws:
                    logger.info(f"✅ WS connected: {symbol}")

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
                with self._lock:
                    self._connected_symbols.discard(symbol)
                self._update_connected_flag()

            if not self._stop_event.is_set():
                logger.info(f"⏳ Reconnect in {reconnect_delay}s ({symbol})")
                await asyncio.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 2, self.RECONNECT_MAX)

    def _update_connected_flag(self) -> None:
        with self._lock:
            self.stats["connected"] = len(self._connected_symbols) > 0

    # ============================================================
    # REST Snapshot
    # ============================================================

    async def _fetch_snapshot(self, symbol: str) -> Optional[Dict[str, Any]]:
        try:
            url = f"{self.BINANCE_REST_BASE}/api/v3/depth"
            params = {"symbol": symbol.upper(), "limit": self.DEPTH_LEVELS}

            response = await asyncio.to_thread(
                requests.get, url, params=params, timeout=10,
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

    def _process_orderbook_update(self, symbol: str, data: Dict[str, Any]) -> None:
        try:
            bids = data.get("bids", [])
            asks = data.get("asks", [])

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
        try:
            return float(Decimal(str(value)))
        except (InvalidOperation, ValueError, TypeError):
            return 0.0

    # ============================================================
    # Cache
    # ============================================================

    def _cache_orderbook(self, symbol: str, orderbook: Dict[str, Any]) -> None:
        if not self.cache or not self.cache.is_connected():
            return
        try:
            self.cache.set(f"ws:orderbook:{symbol}", orderbook, ttl=self.CACHE_TTL_ORDERBOOK)
        except Exception as e:
            logger.debug(f"⚠️ Cache orderbook error: {e}")

    def _cache_price(self, symbol: str, price: float, best_bid: float, best_ask: float) -> None:
        if not self.cache or not self.cache.is_connected():
            return
        try:
            self.cache.set(f"ws:price:{symbol}", {
                "price": price,
                "best_bid": best_bid,
                "best_ask": best_ask,
                "timestamp": datetime.now().isoformat(),
            }, ttl=self.CACHE_TTL_PRICE)
        except Exception as e:
            logger.debug(f"⚠️ Cache price error: {e}")

    def _cache_stats(self) -> None:
        if not self.cache or not self.cache.is_connected():
            return
        try:
            self.cache.set("ws:stats", self.get_stats(), ttl=self.CACHE_TTL_STATS)
        except Exception as e:
            logger.debug(f"⚠️ Cache stats error: {e}")

    # ============================================================
    # Public API
    # ============================================================

    def _is_stale(self, item: Dict[str, Any]) -> bool:
        ts = item.get("timestamp")
        if not ts:
            return True
        try:
            age = (datetime.now() - datetime.fromisoformat(ts)).total_seconds()
            return age > self.MAX_STALE_SECONDS
        except Exception:
            return True

    def get_orderbook(self, symbol: str) -> Optional[Dict[str, Any]]:
        symbol = symbol.lower()
        with self._lock:
            if symbol in self._orderbooks:
                ob = self._orderbooks[symbol].copy()
                if not self._is_stale(ob):
                    return ob
        return None

    def get_price(self, symbol: str) -> Optional[Dict[str, Any]]:
        symbol = symbol.lower()
        with self._lock:
            if symbol in self._prices:
                p = self._prices[symbol].copy()
                if not self._is_stale(p):
                    return p
        return None

    def get_all_prices(self) -> Dict[str, Dict[str, Any]]:
        result = {}
        with self._lock:
            for symbol in self.symbols:
                if symbol in self._prices:
                    p = self._prices[symbol].copy()
                    if not self._is_stale(p):
                        result[symbol] = p
        return result

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            active_symbols = [s for s in self.symbols if s in self._orderbooks]
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
        symbol = symbol.lower()
        if symbol in self.symbols:
            return False
        self.symbols.append(symbol)
        logger.info(f"✅ Symbol added: {symbol}")
        if self.is_running():
            self.stop(timeout=10)
            time.sleep(1)
            self.start()
        return True

    def unsubscribe(self, symbol: str) -> bool:
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
