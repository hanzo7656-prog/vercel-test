# infrastructure/api/binance_ws_client.py

import asyncio
import json
import logging
import threading
import time
from typing import Dict, Any, Optional, List, Set
from datetime import datetime
from pathlib import Path

import requests  # برای REST snapshot
import websockets  # برای WebSocket
from websockets.exceptions import ConnectionClosed

from infrastructure.database import get_cache



logger = logging.getLogger(__name__)


class BinanceWSClient:
    """
    Binance WebSocket Client
    
    ویژگی‌ها:
        - Background thread
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
    UPDATE_SPEED = "100ms"
    
    RECONNECT_INITIAL = 1
    RECONNECT_MAX = 30
    
    CACHE_TTL_ORDERBOOK = 30   # 30s
    CACHE_TTL_PRICE = 300      # 5min
    CACHE_TTL_STATS = 60       # 1min
    
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
    # Start / Stop
    # ============================================================
    
    def start(self) -> bool:
        """شروع کلاینت در background thread"""
        if self._thread and self._thread.is_alive():
            logger.warning("⚠️ Client already running")
            return False
        
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop,
            name="BinanceWSClient",
            daemon=True,
        )
        self._thread.start()
        
        self.stats["started_at"] = datetime.now().isoformat()
        logger.info("🚀 BinanceWSClient started")
        return True
    
    def stop(self, timeout: float = 5.0) -> bool:
        """توقف کلاینت"""
        if not self._thread or not self._thread.is_alive():
            return False
        
        self._stop_event.set()
        
        if self._thread:
            self._thread.join(timeout=timeout)
        
        logger.info("⏹️ BinanceWSClient stopped")
        return True
    
    def is_running(self) -> bool:
        """آیا کلاینت در حال اجراست؟"""
        return self._thread is not None and self._thread.is_alive()
    
    # ============================================================
    # Thread Main
    # ============================================================
    
    def _run_loop(self) -> None:
        """حلقه اصلی (در thread)"""
        logger.info("🔄 BinanceWSClient thread started")
        
        while not self._stop_event.is_set():
            try:
                # برای هر symbol یه task جدا
                # ولی همه در یه event loop
                asyncio.run(self._run_all_symbols())
            except Exception as e:
                logger.error(f"❌ Run loop error: {e}", exc_info=True)
            
            if not self._stop_event.is_set():
                logger.info("🔄 Reconnecting in 5s...")
                self._stop_event.wait(5)
        
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
                    
                    self.stats["connected"] = True
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
            
            if not self._stop_event.is_set():
                logger.info(f"⏳ Reconnect in {reconnect_delay}s ({symbol})")
                await asyncio.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 2, self.RECONNECT_MAX)
        
        self.stats["connected"] = False
    
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
            
            # در thread جدا (چون requests blocking هست)
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
        
        ساختار data:
            {
                "lastUpdateId": 123,
                "bids": [["price", "quantity"], ...],
                "asks": [["price", "quantity"], ...],
            }
        """
        try:
            # ساخت order book جدید
            bids = data.get("bids", [])
            asks = data.get("asks", [])
            
            # بهترین bid و ask
            best_bid = float(bids[0][0]) if bids else 0
            best_ask = float(asks[0][0]) if asks else 0
            mid_price = (best_bid + best_ask) / 2 if (best_bid and best_ask) else 0
            
            # ذخیره در حافظه
            orderbook = {
                "symbol": symbol,
                "lastUpdateId": data.get("lastUpdateId"),
                "bids": bids,
                "asks": asks,
                "best_bid": best_bid,
                "best_ask": best_ask,
                "mid_price": mid_price,
                "spread": best_ask - best_bid if (best_bid and best_ask) else 0,
                "timestamp": datetime.now().isoformat(),
                "source": "websocket",
            }
            
            with self._lock:
                self._orderbooks[symbol] = orderbook
                
                self._prices[symbol] = {
                    "symbol": symbol,
                    "price": mid_price,
                    "best_bid": best_bid,
                    "best_ask": best_ask,
                    "timestamp": datetime.now().isoformat(),
                }
            
            # Cache در Redis
            self._cache_orderbook(symbol, orderbook)
            self._cache_price(symbol, mid_price, best_bid, best_ask)
            
        except Exception as e:
            logger.error(f"❌ Process update error for {symbol}: {e}")
    
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
    
    def get_orderbook(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        دریافت order book یک symbol
        
        اول از حافظه، اگه نبود از Redis
        """
        symbol = symbol.lower()
        
        # ۱. از حافظه
        with self._lock:
            if symbol in self._orderbooks:
                return self._orderbooks[symbol].copy()
        
        # ۲. از Redis
        if self.cache and self.cache.is_connected():
            try:
                cached = self.cache.get(f"ws:orderbook:{symbol}")
                if cached:
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
                return self._prices[symbol].copy()
        
        # ۲. از Redis
        if self.cache and self.cache.is_connected():
            try:
                cached = self.cache.get(f"ws:price:{symbol}")
                if cached:
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
                    result[symbol] = self._prices[symbol].copy()
        
        return result
    
    def get_stats(self) -> Dict[str, Any]:
        """دریافت آمار کامل"""
        with self._lock:
            active_symbols = list(self._orderbooks.keys())
        
        return {
            **self.stats,
            "is_running": self.is_running(),
            "symbols": self.symbols,
            "active_symbols": active_symbols,
            "cached_symbols_count": len(active_symbols),
            "total_symbols": len(self.symbols),
            "cache_connected": self.cache is not None and self.cache.is_connected(),
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
            self.stop()
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
        
        logger.info(f"✅ Symbol removed: {symbol}")
        return True


# ============================================================
# Singleton
# ============================================================

binance_ws_client = BinanceWSClient(auto_start=False)
