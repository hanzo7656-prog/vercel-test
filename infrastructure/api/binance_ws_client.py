# infrastructure/api/binance_ws_client.py
# ============================================================
# Binance WebSocket Client - نسخه ۴.۰
# Thread مستقل + لاگ کامل در تمام حالت‌ها
# ============================================================

import asyncio
import json
import logging
import threading
import time
import traceback
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
        - Background thread مستقل (بدون ThreadingManager)
        - Auto-reconnect با exponential backoff
        - Cache در Redis
        - Multiple symbols
        - REST snapshot + WS updates
        - Thread-safe
        - is_running مستقل (heartbeat داخلی)
        - لاگ کامل در تمام حالت‌ها
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

        # 🆕 لاگ شروع
        print(f"[BinanceWS] INIT: symbols={self.symbols}", flush=True)
        logger.info(f"[BinanceWS] INIT: symbols={self.symbols}")

        # Cache (با try/except چون ممکن است Redis آماده نباشد)
        self.cache = None
        try:
            self.cache = get_cache()
            print(f"[BinanceWS] Cache: {self.cache}", flush=True)
            logger.info(f"[BinanceWS] Cache: {self.cache}")
        except Exception as e:
            print(f"[BinanceWS] ⚠️ Cache init error: {e}", flush=True)
            logger.warning(f"[BinanceWS] ⚠️ Cache init error: {e}")

        # State
        self._orderbooks: Dict[str, Dict[str, Any]] = {}
        self._prices: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

        # فلگ صریح
        self._running: bool = False

        # وضعیت اتصال per-symbol
        self._connected_symbols: Set[str] = set()

        # Stats
        self.stats: Dict[str, Any] = {
            "connected": False,
            "started_at": None,
            "last_message_at": None,
            "heartbeat": None,
            "total_messages": 0,
            "total_errors": 0,
            "reconnect_count": 0,
            "active_symbols": [],
            "current_symbol": None,
        }

        print(f"[BinanceWS] ✅ initialized (auto_start={auto_start})", flush=True)
        logger.info(f"[BinanceWS] ✅ initialized (auto_start={auto_start})")

        if auto_start:
            self.start()

    # ============================================================
    # Start / Stop / IsRunning
    # ============================================================

    def start(self) -> bool:
        """شروع کلاینت در background thread مستقل"""
        print("[BinanceWS] start() called", flush=True)
        logger.info("[BinanceWS] start() called")

        # اگر thread قبلی زنده است، اول بکشش
        if self._thread and self._thread.is_alive():
            print("[BinanceWS] ⚠️ Old thread still alive, stopping first", flush=True)
            logger.warning("[BinanceWS] ⚠️ Old thread still alive, stopping first")
            self._stop_event.set()
            self._thread.join(timeout=10)
            if self._thread.is_alive():
                print("[BinanceWS] ❌ Old thread did not stop in 10s", flush=True)
                logger.error("[BinanceWS] ❌ Old thread did not stop in 10s")
                return False

        # ریست کامل
        self._stop_event.clear()
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

        # ساخت thread
        try:
            self._thread = threading.Thread(
                target=self._run_loop,
                name="BinanceWSClient",
                daemon=True,
            )
            self._thread.start()
            print(
                f"[BinanceWS] 🚀 thread started: "
                f"name={self._thread.name}, alive={self._thread.is_alive()}",
                flush=True,
            )
            logger.info(
                f"[BinanceWS] 🚀 thread started: "
                f"name={self._thread.name}, alive={self._thread.is_alive()}"
            )
            return True
        except Exception as e:
            print(f"[BinanceWS] ❌ thread start failed: {e}", flush=True)
            logger.error(f"[BinanceWS] ❌ thread start failed: {e}")
            logger.error(traceback.format_exc())
            self._running = False
            return False

    def stop(self, timeout: float = 5.0) -> bool:
        """توقف کلاینت"""
        print("[BinanceWS] stop() called", flush=True)
        logger.info("[BinanceWS] stop() called")

        if not self._thread or not self._thread.is_alive():
            self._running = False
            return False

        self._stop_event.set()
        self._thread.join(timeout=timeout)
        self._running = False

        with self._lock:
            self._connected_symbols.clear()
        self.stats["connected"] = False

        print("[BinanceWS] ⏹️ stopped", flush=True)
        logger.info("[BinanceWS] ⏹️ stopped")
        return True

    def is_running(self) -> bool:
        """آیا کلاینت در حال اجراست؟ (مستقل، بر اساس heartbeat)"""
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
        print(
            f"[BinanceWS] _run_loop STARTED in thread={threading.current_thread().name}",
            flush=True,
        )
        logger.info(
            f"[BinanceWS] _run_loop STARTED in thread={threading.current_thread().name}"
        )

        self._running = True
        self.stats["heartbeat"] = datetime.now().isoformat()

        # heartbeat thread مستقل
        def heartbeat_loop():
            print("[BinanceWS] heartbeat_loop started", flush=True)
            logger.info("[BinanceWS] heartbeat_loop started")
            while not self._stop_event.is_set():
                self.stats["heartbeat"] = datetime.now().isoformat()
                self._stop_event.wait(self.HEARTBEAT_INTERVAL)
            print("[BinanceWS] heartbeat_loop stopped", flush=True)
            logger.info("[BinanceWS] heartbeat_loop stopped")

        hb_thread = threading.Thread(
            target=heartbeat_loop,
            daemon=True,
            name="BinanceWS-Heartbeat",
        )
        hb_thread.start()

        iteration = 0
        try:
            while not self._stop_event.is_set():
                iteration += 1
                print(
                    f"[BinanceWS] _run_loop iteration={iteration} "
                    f"stop_event={self._stop_event.is_set()}",
                    flush=True,
                )
                logger.info(
                    f"[BinanceWS] _run_loop iteration={iteration} "
                    f"stop_event={self._stop_event.is_set()}"
                )

                try:
                    print("[BinanceWS] calling asyncio.run(_run_all_symbols)...", flush=True)
                    logger.info("[BinanceWS] calling asyncio.run(_run_all_symbols)...")
                    asyncio.run(self._run_all_symbols())
                    print("[BinanceWS] asyncio.run() returned normally", flush=True)
                    logger.info("[BinanceWS] asyncio.run() returned normally")
                except Exception as e:
                    print(f"[BinanceWS] ❌ asyncio.run() error: {e}", flush=True)
                    logger.error(f"[BinanceWS] ❌ asyncio.run() error: {e}")
                    logger.error(traceback.format_exc())

                if not self._stop_event.is_set():
                    print(
                        f"[BinanceWS] 🔄 Reconnecting in 5s... (iteration {iteration} done)",
                        flush=True,
                    )
                    logger.info(
                        f"[BinanceWS] 🔄 Reconnecting in 5s... (iteration {iteration} done)"
                    )
                    self._stop_event.wait(5)

        except BaseException as e:
            print(f"[BinanceWS] ❌❌ _run_loop BASE EXCEPTION: {e}", flush=True)
            logger.error(f"[BinanceWS] ❌❌ _run_loop BASE EXCEPTION: {e}")
            logger.error(traceback.format_exc())

        finally:
            print("[BinanceWS] _run_loop FINALLY block", flush=True)
            logger.info("[BinanceWS] _run_loop FINALLY block")
            self._running = False
            with self._lock:
                self._connected_symbols.clear()
            self.stats["connected"] = False
            self.stats["heartbeat"] = None
            print("[BinanceWS] _run_loop FINISHED", flush=True)
            logger.info("[BinanceWS] _run_loop FINISHED")

    async def _run_all_symbols(self) -> None:
        """شروع task برای همه symbol ها"""
        print(
            f"[BinanceWS] _run_all_symbols: creating {len(self.symbols)} tasks",
            flush=True,
        )
        logger.info(
            f"[BinanceWS] _run_all_symbols: creating {len(self.symbols)} tasks"
        )

        tasks = []
        for symbol in self.symbols:
            if self._stop_event.is_set():
                print("[BinanceWS] stop_event set, breaking task creation", flush=True)
                logger.info("[BinanceWS] stop_event set, breaking task creation")
                break
            task = asyncio.create_task(self._ws_task(symbol), name=f"ws-{symbol}")
            tasks.append(task)
            print(f"[BinanceWS] task created for {symbol}", flush=True)
            logger.info(f"[BinanceWS] task created for {symbol}")

        if tasks:
            print(f"[BinanceWS] gathering {len(tasks)} tasks...", flush=True)
            logger.info(f"[BinanceWS] gathering {len(tasks)} tasks...")
            results = await asyncio.gather(*tasks, return_exceptions=True)
            print(f"[BinanceWS] gather done, results={results}", flush=True)
            logger.info(f"[BinanceWS] gather done, results={results}")
            for i, r in enumerate(results):
                if isinstance(r, Exception):
                    print(
                        f"[BinanceWS] ❌ task[{i}] exception: {type(r).__name__}: {r}",
                        flush=True,
                    )
                    logger.error(
                        f"[BinanceWS] ❌ task[{i}] exception: {type(r).__name__}: {r}"
                    )

    # ============================================================
    # WebSocket Task for one symbol
    # ============================================================

    async def _ws_task(self, symbol: str) -> None:
        """Task برای یک symbol"""
        print(f"[BinanceWS][{symbol}] _ws_task started", flush=True)
        logger.info(f"[BinanceWS][{symbol}] _ws_task started")

        reconnect_delay = self.RECONNECT_INITIAL
        url = (
            f"{self.BINANCE_WS_BASE}/{symbol}"
            f"@depth{self.DEPTH_LEVELS}@{self.UPDATE_SPEED}"
        )
        print(f"[BinanceWS][{symbol}] URL: {url}", flush=True)
        logger.info(f"[BinanceWS][{symbol}] URL: {url}")

        iteration = 0
        while not self._stop_event.is_set():
            iteration += 1
            try:
                self.stats["current_symbol"] = symbol

                # ۱. REST snapshot
                print(f"[BinanceWS][{symbol}] fetching snapshot... (iter {iteration})", flush=True)
                logger.info(f"[BinanceWS][{symbol}] fetching snapshot... (iter {iteration})")
                snapshot = await self._fetch_snapshot(symbol)

                if snapshot:
                    with self._lock:
                        self._orderbooks[symbol] = snapshot
                    self._cache_orderbook(symbol, snapshot)
                    print(f"[BinanceWS][{symbol}] ✅ snapshot fetched", flush=True)
                    logger.info(f"[BinanceWS][{symbol}] ✅ snapshot fetched")
                else:
                    print(f"[BinanceWS][{symbol}] ⚠️ snapshot is None", flush=True)
                    logger.warning(f"[BinanceWS][{symbol}] ⚠️ snapshot is None")

                # ۲. WebSocket connect
                print(f"[BinanceWS][{symbol}] 🔗 connecting to WS...", flush=True)
                logger.info(f"[BinanceWS][{symbol}] 🔗 connecting to WS...")

                async with websockets.connect(
                    url,
                    ping_interval=20,
                    ping_timeout=10,
                    close_timeout=5,
                ) as ws:
                    print(f"[BinanceWS][{symbol}] ✅ WS connected", flush=True)
                    logger.info(f"[BinanceWS][{symbol}] ✅ WS connected")

                    with self._lock:
                        self._connected_symbols.add(symbol)
                    self._update_connected_flag()

                    reconnect_delay = self.RECONNECT_INITIAL

                    async for message in ws:
                        if self._stop_event.is_set():
                            print(f"[BinanceWS][{symbol}] stop_event set, breaking", flush=True)
                            logger.info(f"[BinanceWS][{symbol}] stop_event set, breaking")
                            break

                        try:
                            data = json.loads(message)
                            self._process_orderbook_update(symbol, data)

                            self.stats["total_messages"] += 1
                            self.stats["last_message_at"] = datetime.now().isoformat()

                            # هر ۱۰۰ پیام لاگ کن
                            if self.stats["total_messages"] % 100 == 0:
                                print(
                                    f"[BinanceWS][{symbol}] 📨 total_messages={self.stats['total_messages']}",
                                    flush=True,
                                )
                                logger.info(
                                    f"[BinanceWS][{symbol}] 📨 total_messages={self.stats['total_messages']}"
                                )

                        except json.JSONDecodeError as e:
                            print(f"[BinanceWS][{symbol}] ⚠️ Invalid JSON: {e}", flush=True)
                            logger.warning(f"[BinanceWS][{symbol}] ⚠️ Invalid JSON: {e}")
                        except Exception as e:
                            print(f"[BinanceWS][{symbol}] ❌ process error: {e}", flush=True)
                            logger.error(f"[BinanceWS][{symbol}] ❌ process error: {e}")
                            logger.error(traceback.format_exc())

                    print(f"[BinanceWS][{symbol}] WS loop ended", flush=True)
                    logger.info(f"[BinanceWS][{symbol}] WS loop ended")

            except asyncio.CancelledError:
                print(f"[BinanceWS][{symbol}] 🛑 task cancelled", flush=True)
                logger.info(f"[BinanceWS][{symbol}] 🛑 task cancelled")
                break
            except ConnectionClosed as e:
                print(f"[BinanceWS][{symbol}] 🔌 WS closed: {e}", flush=True)
                logger.warning(f"[BinanceWS][{symbol}] 🔌 WS closed: {e}")
                self.stats["reconnect_count"] += 1
            except Exception as e:
                print(
                    f"[BinanceWS][{symbol}] ❌ WS error: {type(e).__name__}: {e}",
                    flush=True,
                )
                logger.error(
                    f"[BinanceWS][{symbol}] ❌ WS error: {type(e).__name__}: {e}"
                )
                logger.error(traceback.format_exc())
                self.stats["reconnect_count"] += 1
                self.stats["total_errors"] += 1
            finally:
                with self._lock:
                    self._connected_symbols.discard(symbol)
                self._update_connected_flag()
                print(
                    f"[BinanceWS][{symbol}] finally: connected_symbols={len(self._connected_symbols)}",
                    flush=True,
                )
                logger.info(
                    f"[BinanceWS][{symbol}] finally: connected_symbols={len(self._connected_symbols)}"
                )

            if not self._stop_event.is_set():
                print(
                    f"[BinanceWS][{symbol}] ⏳ reconnect in {reconnect_delay}s",
                    flush=True,
                )
                logger.info(
                    f"[BinanceWS][{symbol}] ⏳ reconnect in {reconnect_delay}s"
                )
                await asyncio.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 2, self.RECONNECT_MAX)

        print(f"[BinanceWS][{symbol}] _ws_task FINISHED", flush=True)
        logger.info(f"[BinanceWS][{symbol}] _ws_task FINISHED")

    def _update_connected_flag(self) -> None:
        """به‌روزرسانی فلگ connected"""
        with self._lock:
            self.stats["connected"] = len(self._connected_symbols) > 0

    # ============================================================
    # REST Snapshot
    # ============================================================

    async def _fetch_snapshot(self, symbol: str) -> Optional[Dict[str, Any]]:
        """دریافت snapshot اولیه از REST API"""
        try:
            url = f"{self.BINANCE_REST_BASE}/api/v3/depth"
            params = {"symbol": symbol.upper(), "limit": self.DEPTH_LEVELS}

            print(f"[BinanceWS][{symbol}] GET {url} params={params}", flush=True)
            logger.info(f"[BinanceWS][{symbol}] GET {url} params={params}")

            response = await asyncio.to_thread(
                requests.get,
                url,
                params=params,
                timeout=10,
            )

            print(
                f"[BinanceWS][{symbol}] snapshot HTTP {response.status_code}",
                flush=True,
            )
            logger.info(
                f"[BinanceWS][{symbol}] snapshot HTTP {response.status_code}"
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

            print(
                f"[BinanceWS][{symbol}] ⚠️ snapshot HTTP {response.status_code}",
                flush=True,
            )
            logger.warning(
                f"[BinanceWS][{symbol}] ⚠️ snapshot HTTP {response.status_code}"
            )
            return None

        except Exception as e:
            print(
                f"[BinanceWS][{symbol}] ❌ snapshot error: {type(e).__name__}: {e}",
                flush=True,
            )
            logger.error(
                f"[BinanceWS][{symbol}] ❌ snapshot error: {type(e).__name__}: {e}"
            )
            logger.error(traceback.format_exc())
            return None

    # ============================================================
    # Process Updates
    # ============================================================

    def _process_orderbook_update(self, symbol: str, data: Dict[str, Any]) -> None:
        """پردازش update از WebSocket"""
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
            print(f"[BinanceWS][{symbol}] ❌ process error: {e}", flush=True)
            logger.error(f"[BinanceWS][{symbol}] ❌ process error: {e}")

    @staticmethod
    def _to_float(value: Any) -> float:
        """تبدیل ایمن string به float"""
        try:
            return float(Decimal(str(value)))
        except (InvalidOperation, ValueError, TypeError):
            return 0.0

    # ============================================================
    # Cache
    # ============================================================

    def _cache_orderbook(self, symbol: str, orderbook: Dict[str, Any]) -> None:
        """ذخیره order book در Redis"""
        if not self.cache:
            return
        try:
            if hasattr(self.cache, 'is_connected') and not self.cache.is_connected():
                return
            self.cache.set(f"ws:orderbook:{symbol}", orderbook, ttl=self.CACHE_TTL_ORDERBOOK)
        except Exception as e:
            print(f"[BinanceWS][{symbol}] ⚠️ cache orderbook error: {e}", flush=True)
            logger.debug(f"[BinanceWS][{symbol}] ⚠️ cache orderbook error: {e}")

    def _cache_price(self, symbol: str, price: float, best_bid: float, best_ask: float) -> None:
        """ذخیره قیمت در Redis"""
        if not self.cache:
            return
        try:
            if hasattr(self.cache, 'is_connected') and not self.cache.is_connected():
                return
            self.cache.set(f"ws:price:{symbol}", {
                "price": price,
                "best_bid": best_bid,
                "best_ask": best_ask,
                "timestamp": datetime.now().isoformat(),
            }, ttl=self.CACHE_TTL_PRICE)
        except Exception as e:
            print(f"[BinanceWS][{symbol}] ⚠️ cache price error: {e}", flush=True)
            logger.debug(f"[BinanceWS][{symbol}] ⚠️ cache price error: {e}")

    # ============================================================
    # Public API
    # ============================================================

    def _is_stale(self, item: Dict[str, Any]) -> bool:
        """بررسی کهنگی داده"""
        ts = item.get("timestamp")
        if not ts:
            return True
        try:
            age = (datetime.now() - datetime.fromisoformat(ts)).total_seconds()
            return age > self.MAX_STALE_SECONDS
        except Exception:
            return True

    def get_orderbook(self, symbol: str) -> Optional[Dict[str, Any]]:
        """دریافت order book یک symbol"""
        symbol = symbol.lower()
        with self._lock:
            if symbol in self._orderbooks:
                ob = self._orderbooks[symbol].copy()
                if not self._is_stale(ob):
                    return ob
        return None

    def get_price(self, symbol: str) -> Optional[Dict[str, Any]]:
        """دریافت قیمت یک symbol"""
        symbol = symbol.lower()
        with self._lock:
            if symbol in self._prices:
                p = self._prices[symbol].copy()
                if not self._is_stale(p):
                    return p
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
            active_symbols = [s for s in self.symbols if s in self._orderbooks]
            connected_count = len(self._connected_symbols)

        thread_alive = self._thread is not None and self._thread.is_alive()

        return {
            **self.stats,
            "is_running": self.is_running(),
            "thread_alive": thread_alive,
            "thread_name": self._thread.name if self._thread else None,
            "symbols": self.symbols,
            "active_symbols": active_symbols,
            "cached_symbols_count": len(active_symbols),
            "total_symbols": len(self.symbols),
            "cache_connected": (
                self.cache is not None
                and hasattr(self.cache, 'is_connected')
                and self.cache.is_connected()
            ),
            "connected_symbols_count": connected_count,
        }

    def subscribe(self, symbol: str) -> bool:
        """اضافه کردن symbol جدید (runtime)"""
        symbol = symbol.lower()
        if symbol in self.symbols:
            return False
        self.symbols.append(symbol)
        print(f"[BinanceWS] ✅ symbol added: {symbol}", flush=True)
        logger.info(f"[BinanceWS] ✅ symbol added: {symbol}")
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
        print(f"[BinanceWS] ✅ symbol removed: {symbol}", flush=True)
        logger.info(f"[BinanceWS] ✅ symbol removed: {symbol}")
        return True


# ============================================================
# Singleton
# ============================================================

binance_ws_client = BinanceWSClient(auto_start=False)
print("[BinanceWS] Singleton created", flush=True)
