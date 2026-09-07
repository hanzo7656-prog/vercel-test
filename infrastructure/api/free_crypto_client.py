# infrastructure/api/free_crypto_client.py
# ============================================================
# کلاینت REST برای FreeCryptoAPI (جایگزین WebSocket)
# ============================================================

import json
import logging
import time
import threading
from typing import Dict, Any, Optional, List, Callable
from datetime import datetime

import requests

logger = logging.getLogger(__name__)


class FreeCryptoClient:
    """
    کلاینت REST برای FreeCryptoAPI
    دریافت قیمت‌های لحظه‌ای با Polling
    """
    
    def __init__(self, api_key: str, auto_reconnect: bool = True):
        self.api_key: str = api_key
        self.auto_reconnect: bool = auto_reconnect
        self.base_url: str = "https://api.freecryptoapi.com/v1"
        self.is_connected: bool = False
        self.price_cache: Dict[str, Dict[str, Any]] = {}
        self._callbacks: List[Callable] = []
        self._stop_event: threading.Event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock: threading.Lock = threading.Lock()
        self._last_request_time: float = 0
        self._min_interval: float = 0.5
        self._failure_count: int = 0
        self._max_failures: int = 3
        
        # آمار
        self.stats = {
            "messages_received": 0,
            "reconnects": 0,
            "errors": 0,
            "last_update": None,
            "symbols_count": 0,
            "connection_attempts": 0
        }
        
        logger.info("✅ FreeCryptoClient (REST) initialized")
    
    def connect(self) -> None:
        """شروع Polling برای دریافت قیمت‌ها"""
        if self._thread and self._thread.is_alive():
            logger.warning("⚠️ Client already running")
            return
        
        self._stop_event.clear()
        self.is_connected = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        logger.info("🔄 FreeCryptoClient (REST) started")
    
    def _run(self) -> None:
        """حلقه اصلی Polling"""
        while not self._stop_event.is_set():
            try:
                # هر ۱۰ ثانیه یکبار درخواست بزن
                if self._should_poll():
                    self._poll_prices()
                time.sleep(10)
            except Exception as e:
                logger.error(f"❌ Polling error: {e}")
                self.stats["errors"] += 1
                time.sleep(5)
    
    def _should_poll(self) -> bool:
        """بررسی زمان مناسب برای Polling"""
        now = time.time()
        if now - self._last_request_time < 10:
            return False
        return True
    
    def _poll_prices(self) -> None:
        """دریافت قیمت‌های لحظه‌ای"""
        symbols = self._get_watch_symbols()
        if not symbols:
            return
        
        for symbol in symbols:
            try:
                price_data = self._request_price(symbol)
                if price_data:
                    with self._lock:
                        self.price_cache[symbol] = price_data
                        self.stats["last_update"] = datetime.now().isoformat()
                        self.stats["symbols_count"] = len(self.price_cache)
                        self.stats["messages_received"] += 1
                        self.is_connected = True
                        self._failure_count = 0
            except Exception as e:
                logger.error(f"❌ Error fetching {symbol}: {e}")
                self._failure_count += 1
                if self._failure_count >= self._max_failures:
                    self.is_connected = False
                    logger.warning(f"⚠️ FreeCryptoAPI marked as unavailable after {self._max_failures} failures")
    
    def _request_price(self, symbol: str) -> Optional[Dict[str, Any]]:
        """درخواست قیمت یک ارز از REST API"""
        # محدودیت نرخ
        now = time.time()
        if now - self._last_request_time < self._min_interval:
            time.sleep(self._min_interval - (now - self._last_request_time))
        
        url = f"{self.base_url}/getData?symbol={symbol}"
        headers = {"X-API-Key": self.api_key}
        
        try:
            response = requests.get(url, headers=headers, timeout=5)
            self._last_request_time = time.time()
            
            if response.status_code == 200:
                data = response.json()
                if data.get("status") == "success" and data.get("symbols"):
                    item = data["symbols"][0]
                    return {
                        "price": float(item.get("last", 0)),
                        "change_24h": float(item.get("daily_change_percentage", 0)),
                        "high_24h": float(item.get("highest", 0)),
                        "low_24h": float(item.get("lowest", 0)),
                        "timestamp": item.get("date", datetime.now().isoformat()),
                        "source": item.get("source_exchange", "freecryptoapi")
                    }
                else:
                    logger.debug(f"⚠️ API returned error for {symbol}: {data.get('error')}")
                    return None
            else:
                logger.debug(f"⚠️ HTTP {response.status_code} for {symbol}")
                return None
                
        except requests.exceptions.Timeout:
            logger.debug(f"⏳ Timeout for {symbol}")
            return None
        except Exception as e:
            logger.error(f"❌ Request error for {symbol}: {e}")
            return None
    
    def _get_watch_symbols(self) -> List[str]:
        """دریافت لیست ارزهای مورد نظر"""
        # از کش یا پیش‌فرض
        try:
            from infrastructure.database import get_cache
            cache = get_cache()
            coins_list = cache.get("coins_list_50_1_USD_None")
            if coins_list:
                symbols = []
                for coin in coins_list[:20]:
                    symbol = coin.get("symbol", "").upper()
                    if symbol:
                        symbols.append(symbol)
                return symbols or ["BTC", "ETH", "SOL", "ADA", "XRP"]
        except:
            pass
        return ["BTC", "ETH", "SOL", "ADA", "XRP"]
    
    def get_price(self, symbol: str) -> Optional[Dict[str, Any]]:
        """دریافت آخرین قیمت از کش"""
        symbol = symbol.upper()
        with self._lock:
            return self.price_cache.get(symbol)
    
    def get_prices(self, symbols: Optional[List[str]] = None) -> Dict[str, Dict[str, Any]]:
        """دریافت قیمت‌های چند ارز از کش"""
        with self._lock:
            if symbols:
                result = {}
                for s in symbols:
                    s = s.upper()
                    if s in self.price_cache:
                        result[s] = self.price_cache[s]
                return result
            return self.price_cache.copy()
    
    def add_callback(self, callback: Callable) -> None:
        """اضافه کردن callback برای دریافت بروزرسانی‌ها"""
        self._callbacks.append(callback)
    
    def get_stats(self) -> Dict[str, Any]:
        """دریافت آمار کلاینت"""
        return {
            "is_connected": self.is_connected,
            "symbols_count": self.stats["symbols_count"],
            "messages_received": self.stats["messages_received"],
            "reconnects": self.stats["reconnects"],
            "errors": self.stats["errors"],
            "last_update": self.stats["last_update"],
            "cache_size": len(self.price_cache),
            "connection_attempts": self.stats["connection_attempts"]
        }
    
    def stop(self) -> None:
        """متوقف کردن کلاینت"""
        logger.info("⏹️ Stopping FreeCryptoClient...")
        self._stop_event.set()
        self.is_connected = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("✅ FreeCryptoClient stopped")


def create_free_crypto_client(api_key: str) -> FreeCryptoClient:
    """ایجاد نمونه FreeCryptoClient"""
    client = FreeCryptoClient(api_key=api_key)
    client.connect()
    return client
