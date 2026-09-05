# ============================================================
# free_crypto_client.py - کلاینت WebSocket FreeCryptoAPI
# ============================================================

import json
import logging
import threading
import time
from typing import Dict, Any, Optional, List, Callable
from datetime import datetime

import websocket

logger = logging.getLogger(__name__)


class FreeCryptoClient:
    """
    کلاینت WebSocket برای FreeCryptoAPI
    دریافت قیمت‌های لحظه‌ای ارزها
    """
    
    def __init__(self, api_key: str, auto_reconnect: bool = True):
        self.api_key: str = api_key
        self.auto_reconnect: bool = auto_reconnect
        self.ws: Optional[websocket.WebSocketApp] = None
        self.is_connected: bool = False
        self.price_cache: Dict[str, Dict[str, Any]] = {}
        self._callbacks: List[Callable] = []
        self._reconnect_delay: int = 1
        self._max_reconnect_delay: int = 60
        self._stop_event: threading.Event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock: threading.Lock = threading.Lock()
        self._last_heartbeat: Optional[datetime] = None
        self._subscribed_symbols: set = set()
        
        # آمار
        self.stats = {
            "messages_received": 0,
            "reconnects": 0,
            "errors": 0,
            "last_update": None,
            "symbols_count": 0
        }
        
        logger.info("✅ FreeCryptoClient initialized")
    
    def connect(self) -> None:
        """اتصال به WebSocket"""
        if self._thread and self._thread.is_alive():
            logger.warning("⚠️ WebSocket already running")
            return
        
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        logger.info("🔄 WebSocket connection thread started")
    
    def _run(self) -> None:
        """اجرای WebSocket در thread جداگانه"""
        while not self._stop_event.is_set():
            try:
                self._connect_ws()
                if not self.auto_reconnect:
                    break
                
                # در صورت قطع، با backoff reconnect
                self._reconnect_delay = min(self._reconnect_delay * 2, self._max_reconnect_delay)
                time.sleep(self._reconnect_delay)
                
            except Exception as e:
                logger.error(f"❌ WebSocket error: {e}")
                self.stats["errors"] += 1
                time.sleep(self._reconnect_delay)
    
    def _connect_ws(self) -> None:
        """اتصال به WebSocket و نگهداری اتصال"""
        ws_url = "wss://freecryptoapi.com/ws"
        
        self.ws = websocket.WebSocketApp(
            ws_url,
            on_open=self._on_open,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close
        )
        
        self.ws.run_forever(
            ping_interval=30,
            ping_timeout=10,
            reconnect=5
        )
    
    def _on_open(self, ws) -> None:
        """وقتی اتصال برقرار شد"""
        logger.info("✅ WebSocket connected to FreeCryptoAPI")
        self.is_connected = True
        self._reconnect_delay = 1
        
        # ارسال احراز هویت
        auth_msg = json.dumps({
            "action": "auth",
            "apiKey": self.api_key
        })
        ws.send(auth_msg)
        logger.info("🔑 Authentication sent")
        
        # اشتراک مجدد نمادهای قبلی
        if self._subscribed_symbols:
            symbols = list(self._subscribed_symbols)
            self.subscribe_symbols(ws, symbols)
    
    def _on_message(self, ws, message: str) -> None:
        """دریافت پیام از WebSocket"""
        try:
            data = json.loads(message)
            self.stats["messages_received"] += 1
            
            # بررسی نوع پیام
            if "type" in data:
                if data["type"] == "auth":
                    if data.get("status") == "success":
                        logger.info("✅ Authentication successful")
                    else:
                        logger.error(f"❌ Authentication failed: {data}")
                
                elif data["type"] == "price":
                    self._handle_price_update(data.get("data", {}))
                
                elif data["type"] == "ping":
                    # پاسخ به پینگ
                    ws.send(json.dumps({"type": "pong"}))
                    self._last_heartbeat = datetime.now()
            
            # فراخوانی callbackها
            for cb in self._callbacks:
                try:
                    cb(data)
                except Exception as e:
                    logger.error(f"Callback error: {e}")
                    
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {e}")
        except Exception as e:
            logger.error(f"Message handling error: {e}")
    
    def _handle_price_update(self, data: Dict) -> None:
        """پردازش بروزرسانی قیمت"""
        if not data:
            return
        
        symbol = data.get("symbol", "").upper()
        if not symbol:
            return
        
        with self._lock:
            # ذخیره در کش
            self.price_cache[symbol] = {
                "price": data.get("price", 0),
                "change_24h": data.get("change24h", 0),
                "high_24h": data.get("high24h", 0),
                "low_24h": data.get("low24h", 0),
                "volume": data.get("volume", 0),
                "timestamp": datetime.now().isoformat()
            }
            self.stats["last_update"] = datetime.now().isoformat()
            self.stats["symbols_count"] = len(self.price_cache)
    
    def _on_error(self, ws, error) -> None:
        """وقتی خطایی رخ می‌دهد"""
        logger.error(f"❌ WebSocket error: {error}")
        self.is_connected = False
        self.stats["errors"] += 1
    
    def _on_close(self, ws, close_status_code, close_msg) -> None:
        """وقتی اتصال بسته می‌شود"""
        logger.warning(f"⚠️ WebSocket closed: {close_status_code} - {close_msg}")
        self.is_connected = False
        self.stats["reconnects"] += 1
    
    def subscribe_symbols(self, ws, symbols: List[str]) -> None:
        """اشتراک در قیمت یک یا چند ارز"""
        if not symbols:
            return
        
        # حداکثر ۵۰ تا در هر درخواست
        batch_size = 50
        for i in range(0, len(symbols), batch_size):
            batch = symbols[i:i+batch_size]
            msg = json.dumps({
                "action": "subscribe",
                "symbols": batch
            })
            ws.send(msg)
            self._subscribed_symbols.update(batch)
            logger.info(f"📡 Subscribed to {len(batch)} symbols")
    
    def unsubscribe_symbols(self, ws, symbols: List[str]) -> None:
        """لغو اشتراک قیمت ارزها"""
        if not symbols:
            return
        
        msg = json.dumps({
            "action": "unsubscribe",
            "symbols": symbols
        })
        ws.send(msg)
        for s in symbols:
            self._subscribed_symbols.discard(s)
        logger.info(f"📡 Unsubscribed from {len(symbols)} symbols")
    
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
            "cache_size": len(self.price_cache)
        }
    
    def stop(self) -> None:
        """متوقف کردن WebSocket"""
        logger.info("⏹️ Stopping WebSocket...")
        self._stop_event.set()
        if self.ws:
            self.ws.close()
        if self._thread:
            self._thread.join(timeout=5)
        self.is_connected = False
        logger.info("✅ WebSocket stopped")


# ============================================================
# نمونه Singleton (برای استفاده در Container)
# ============================================================

def create_free_crypto_client(api_key: str) -> FreeCryptoClient:
    """ایجاد نمونه FreeCryptoClient"""
    client = FreeCryptoClient(api_key=api_key)
    client.connect()
    return client
