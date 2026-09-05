# core/price_manager.py
# ============================================================
# مدیریت قیمت‌های لحظه‌ای با Redis Cache و مدیریت خطا
# ============================================================

import logging
import time
import threading
from typing import Dict, Any, Optional, List
from datetime import datetime

from infrastructure.api.free_crypto_client import FreeCryptoClient
from infrastructure.api.coinstats_client import coinstats_client
from infrastructure.database import get_cache
from core.user_tracker import UserTracker

logger = logging.getLogger(__name__)


class PriceManager:
    """
    مدیریت قیمت‌های لحظه‌ای
    - اولویت اول: WebSocket (FreeCryptoAPI)
    - Fallback: CoinStats REST API
    - کش در Redis برای دسترسی سریع
    - فقط زمانی که کاربر آنلاین است بروزرسانی می‌شود
    """
    
    def __init__(
        self,
        free_client: FreeCryptoClient,
        user_tracker: UserTracker,
        cache=None,
        update_interval: int = 10,
        fallback_interval: int = 60,
        redis_ttl: int = 300  # ۵ دقیقه
    ):
        self.free_client = free_client
        self.user_tracker = user_tracker
        self.cache = cache or get_cache()
        self.update_interval = update_interval
        self.fallback_interval = fallback_interval
        self.redis_ttl = redis_ttl
        self.is_running = False
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._last_update = None
        self._last_fallback = None
        self._fallback_count = 0
        self._error_count = 0
        self._success_count = 0
        
        # لیست ارزهایی که باید بروزرسانی شوند
        self._watch_symbols = set()
        
        logger.info("✅ PriceManager initialized with Redis TTL: %ds", redis_ttl)
    
    def start(self) -> None:
        """شروع بروزرسانی قیمت‌ها"""
        if self.is_running:
            logger.warning("⚠️ PriceManager already running")
            return
        
        self.is_running = True
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        logger.info("🔄 PriceManager started")
    
    def stop(self) -> None:
        """توقف بروزرسانی قیمت‌ها"""
        self.is_running = False
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("⏹️ PriceManager stopped")
    
    def _run(self) -> None:
        """حلقه اصلی بروزرسانی"""
        consecutive_errors = 0
        max_consecutive_errors = 5
        
        while not self._stop_event.is_set():
            try:
                online_users = self.user_tracker.get_online_count()
                
                if online_users > 0:
                    # بروزرسانی از WebSocket
                    ws_success = self._update_from_websocket()
                    
                    # بروزرسانی از CoinStats (Fallback)
                    self._update_from_coinstats()
                    
                    if ws_success:
                        consecutive_errors = 0
                    else:
                        consecutive_errors += 1
                        if consecutive_errors >= max_consecutive_errors:
                            logger.warning(f"⚠️ {consecutive_errors} consecutive WebSocket errors, trying reconnect...")
                            self._try_reconnect_websocket()
                            consecutive_errors = 0
                    
                    time.sleep(self.update_interval)
                else:
                    # اگر کاربری آنلاین نیست، کمتر چک کن
                    logger.debug("💤 No online users, waiting...")
                    time.sleep(30)
                    
            except Exception as e:
                logger.error(f"❌ PriceManager error: {e}")
                self._error_count += 1
                time.sleep(5)
    
    def _update_from_websocket(self) -> bool:
        """بروزرسانی قیمت‌ها از WebSocket"""
        if not self.free_client.is_connected:
            logger.warning("⚠️ WebSocket not connected")
            return False
        
        try:
            symbols = self._get_watch_symbols()
            if not symbols:
                return True
            
            prices = self.free_client.get_prices(symbols)
            
            if prices:
                # ذخیره در Redis
                for symbol, data in prices.items():
                    cache_key = f"price_{symbol}"
                    self.cache.set(cache_key, data, self.redis_ttl)
                
                self._last_update = datetime.now().isoformat()
                self._success_count += 1
                logger.debug(f"📡 WebSocket update: {len(prices)} symbols")
                return True
            else:
                logger.debug("📡 WebSocket update: no prices received")
                return False
                
        except Exception as e:
            logger.error(f"❌ WebSocket update error: {e}")
            self._error_count += 1
            return False
    
    def _update_from_coinstats(self) -> None:
        """بروزرسانی قیمت‌ها از CoinStats (Fallback)"""
        # فقط اگر زمان Fallback رسیده باشد
        if self._last_fallback:
            elapsed = (datetime.now() - datetime.fromisoformat(self._last_fallback)).total_seconds()
            if elapsed < self.fallback_interval:
                return
        
        symbols = self._get_watch_symbols()
        if not symbols:
            return
        
        # فقط ارزهایی که در Redis نیستند یا منقضی شده‌اند
        missing_symbols = []
        for symbol in symbols:
            cache_key = f"price_{symbol}"
            cached = self.cache.get(cache_key)
            if not cached:
                missing_symbols.append(symbol)
        
        if not missing_symbols:
            return
        
        # دریافت از CoinStats با مدیریت خطا
        try:
            batch_size = 10
            for i in range(0, len(missing_symbols), batch_size):
                batch = missing_symbols[i:i+batch_size]
                for symbol in batch:
                    try:
                        coin_data = coinstats_client.get_coin(symbol.lower())
                        if coin_data and "error" not in coin_data:
                            price_data = {
                                "price": coin_data.get("price", 0),
                                "change_24h": coin_data.get("priceChange1d", 0),
                                "high_24h": coin_data.get("high24h", 0),
                                "low_24h": coin_data.get("low24h", 0),
                                "volume": coin_data.get("volume24h", 0),
                                "timestamp": datetime.now().isoformat(),
                                "source": "coinstats"
                            }
                            cache_key = f"price_{symbol.upper()}"
                            self.cache.set(cache_key, price_data, self.redis_ttl)
                            self._fallback_count += 1
                            logger.debug(f"🔄 Fallback: {symbol} from CoinStats")
                        else:
                            logger.warning(f"⚠️ CoinStats returned error for {symbol}: {coin_data}")
                    except Exception as e:
                        logger.error(f"❌ CoinStats error for {symbol}: {e}")
                        self._error_count += 1
            
            self._last_fallback = datetime.now().isoformat()
            
        except Exception as e:
            logger.error(f"❌ CoinStats fallback error: {e}")
            self._error_count += 1
    
    def _try_reconnect_websocket(self) -> None:
        """تلاش برای reconnect WebSocket"""
        try:
            logger.info("🔄 Attempting to reconnect WebSocket...")
            self.free_client.stop()
            time.sleep(2)
            self.free_client.connect()
            time.sleep(3)
            if self.free_client.is_connected:
                logger.info("✅ WebSocket reconnected successfully")
            else:
                logger.warning("⚠️ WebSocket reconnect failed")
        except Exception as e:
            logger.error(f"❌ WebSocket reconnect error: {e}")
    
    def _get_watch_symbols(self) -> List[str]:
        """دریافت لیست ارزهای مورد نظر برای بروزرسانی"""
        coins_list = self.cache.get("coins_list")
        if not coins_list:
            return ["BTC", "ETH", "SOL", "ADA", "XRP"]
        
        symbols = []
        for coin in coins_list:
            symbol = coin.get("symbol", "").upper()
            if symbol:
                symbols.append(symbol)
        
        return symbols[:100]  # حداکثر ۱۰۰ ارز
    
    def get_price(self, symbol: str) -> Optional[Dict[str, Any]]:
        """دریافت قیمت یک ارز (از کش Redis)"""
        symbol = symbol.upper()
        cache_key = f"price_{symbol}"
        cached = self.cache.get(cache_key)
        if cached:
            return cached
        
        # اگر در Redis نبود، از WebSocket کش دریافت کن
        if self.free_client.is_connected:
            ws_price = self.free_client.get_price(symbol)
            if ws_price:
                self.cache.set(cache_key, ws_price, self.redis_ttl)
                return ws_price
        
        return None
    
    def get_prices(self, symbols: Optional[List[str]] = None) -> Dict[str, Dict[str, Any]]:
        """دریافت قیمت‌های چند ارز"""
        result = {}
        
        if symbols:
            for symbol in symbols:
                price = self.get_price(symbol)
                if price:
                    result[symbol.upper()] = price
        else:
            # دریافت همه قیمت‌ها از Redis
            try:
                keys = self.cache.keys("price_*")
                for key in keys:
                    symbol = key.replace("price_", "")
                    price = self.cache.get(key)
                    if price:
                        result[symbol] = price
            except Exception as e:
                logger.error(f"❌ Error getting prices from Redis: {e}")
        
        return result
    
    def get_stats(self) -> Dict[str, Any]:
        """دریافت آمار"""
        return {
            "is_running": self.is_running,
            "last_update": self._last_update,
            "last_fallback": self._last_fallback,
            "fallback_count": self._fallback_count,
            "success_count": self._success_count,
            "error_count": self._error_count,
            "websocket_connected": self.free_client.is_connected,
            "websocket_stats": self.free_client.get_stats(),
            "cache_keys": len(self.cache.keys("price_*")) if self.cache else 0
        }
