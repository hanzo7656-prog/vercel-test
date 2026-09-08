# core/price_manager.py
# ============================================================
# مدیریت قیمت‌های لحظه‌ای با معماری دوگانه (Hybrid)
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
    مدیریت قیمت‌های لحظه‌ای با معماری دوگانه:
    - اولویت اول: FreeCryptoAPI REST (هر ۱۰ ثانیه)
    - Fallback: CoinStats API (هر ۳۰ ثانیه در صورت قطع FreeCryptoAPI)
    - کش در Redis برای دسترسی سریع
    - فقط زمانی که کاربر آنلاین است بروزرسانی می‌شود
    """
    
    def __init__(
        self,
        free_client: FreeCryptoClient,  # ✅ اصلاح شد
        user_tracker: UserTracker,
        cache=None,
        primary_interval: int = 10,
        fallback_interval: int = 30,
        redis_ttl: int = 60
    ):
        self.free_client = free_client
        self.user_tracker = user_tracker
        self.cache = cache or get_cache()
        self.primary_interval = primary_interval
        self.fallback_interval = fallback_interval
        self.redis_ttl = redis_ttl
        
        self.is_running = False
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        
        # آمار
        self._last_update = None
        self._last_fallback = None
        self._fallback_count = 0
        self._error_count = 0
        self._success_count = 0
        self._primary_failures = 0
        
        # لیست ارزهایی که باید بروزرسانی شوند
        self._watch_symbols: List[str] = []
        
        logger.info("✅ PriceManager initialized with Hybrid architecture")
        logger.info(f"   Primary: FreeCryptoAPI (every {primary_interval}s)")
        logger.info(f"   Fallback: CoinStats (every {fallback_interval}s if primary fails)")
    
    def start(self) -> None:
        """شروع بروزرسانی قیمت‌ها"""
        if self.is_running:
            logger.warning("⚠️ PriceManager already running")
            return
        
        self.is_running = True
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        logger.info("🔄 PriceManager started (Hybrid mode)")
    
    def stop(self) -> None:
        """توقف بروزرسانی قیمت‌ها"""
        self.is_running = False
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("⏹️ PriceManager stopped")
    
    def _run(self) -> None:
        """حلقه اصلی بروزرسانی"""
        primary_failures = 0
        max_failures_before_fallback = 3
        
        while not self._stop_event.is_set():
            try:
                online_users = self.user_tracker.get_online_count()
                
                if online_users > 0:
                    # ۱. بروزرسانی از FreeCryptoAPI
                    success = self._update_from_freecrypto()
                    
                    if success:
                        primary_failures = 0
                    else:
                        primary_failures += 1
                        logger.warning(f"⚠️ FreeCryptoAPI failure #{primary_failures}")
                    
                    # ۲. Fallback به CoinStats
                    if primary_failures >= max_failures_before_fallback:
                        logger.info(f"🔄 Switching to Fallback (CoinStats) after {primary_failures} failures")
                        self._update_from_coinstats()
                        primary_failures = 0
                    
                    # ۳. بروزرسانی دوره‌ای CoinStats
                    if self._last_fallback:
                        elapsed = (datetime.now() - datetime.fromisoformat(self._last_fallback)).total_seconds()
                        if elapsed >= self.fallback_interval:
                            self._update_from_coinstats()
                    
                    time.sleep(self.primary_interval)
                else:
                    logger.debug("💤 No online users, waiting...")
                    time.sleep(30)
                    
            except Exception as e:
                logger.error(f"❌ PriceManager error: {e}")
                self._error_count += 1
                time.sleep(5)
    
    def _update_from_freecrypto(self) -> bool:
        """بروزرسانی قیمت‌ها از FreeCryptoAPI REST"""
        try:
            symbols = self._get_watch_symbols()
            if not symbols:
                return True
            
            prices = self.free_client.get_prices(symbols)
            
            if prices:
                for symbol, data in prices.items():
                    cache_key = f"price_{symbol}"
                    self.cache.set(cache_key, data, self.redis_ttl)
                
                self._last_update = datetime.now().isoformat()
                self._success_count += 1
                return True
            else:
                logger.warning("⚠️ FreeCryptoAPI returned no data")
                return False
                
        except Exception as e:
            logger.error(f"❌ FreeCryptoAPI error: {e}")
            self._error_count += 1
            return False
    
    def _update_from_coinstats(self) -> None:
        """بروزرسانی قیمت‌ها از CoinStats (Fallback)"""
        try:
            symbols = self._get_watch_symbols()
            if not symbols:
                return
            
            missing_symbols = []
            for symbol in symbols[:10]:
                cache_key = f"price_{symbol}"
                cached = self.cache.get(cache_key)
                if not cached:
                    missing_symbols.append(symbol)
            
            if not missing_symbols:
                return
            
            for symbol in missing_symbols:
                try:
                    coin_data = coinstats_client.get_coin(symbol.lower())
                    if coin_data and "error" not in coin_data:
                        price_data = {
                            "price": coin_data.get("price", 0),
                            "change_24h": coin_data.get("priceChange1d", 0),
                            "high_24h": coin_data.get("high24h", 0),
                            "low_24h": coin_data.get("low24h", 0),
                            "timestamp": datetime.now().isoformat(),
                            "source": "coinstats_fallback"
                        }
                        cache_key = f"price_{symbol.upper()}"
                        self.cache.set(cache_key, price_data, self.redis_ttl)
                        self._fallback_count += 1
                except Exception as e:
                    logger.error(f"❌ CoinStats error for {symbol}: {e}")
                    self._error_count += 1
            
            self._last_fallback = datetime.now().isoformat()
            
        except Exception as e:
            logger.error(f"❌ CoinStats fallback error: {e}")
            self._error_count += 1
    
    def _get_watch_symbols(self) -> List[str]:
        """دریافت لیست ارزهای مورد نظر"""
        coins_list = self.cache.get("coins_list_50_1_USD_None")
        if not coins_list:
            return ["BTC", "ETH", "SOL", "ADA", "XRP"]
        
        symbols = []
        for coin in coins_list[:20]:
            symbol = coin.get("symbol", "").upper()
            if symbol:
                symbols.append(symbol)
        
        return symbols or ["BTC", "ETH", "SOL", "ADA", "XRP"]
    
    def set_watch_symbols(self, symbols: List[str]) -> None:
        self._watch_symbols = [s.upper() for s in symbols]
        logger.info(f"📡 Watch symbols updated: {len(self._watch_symbols)} symbols")
    
    def get_price(self, symbol: str) -> Optional[Dict[str, Any]]:
        symbol = symbol.upper()
        cache_key = f"price_{symbol}"
        cached = self.cache.get(cache_key)
        if cached:
            return cached
        return None
    
    def get_prices(self, symbols: Optional[List[str]] = None) -> Dict[str, Dict[str, Any]]:
        result = {}
        
        if symbols:
            for symbol in symbols:
                price = self.get_price(symbol)
                if price:
                    result[symbol.upper()] = price
        else:
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
        return {
            "is_running": self.is_running,
            "last_update": self._last_update,
            "last_fallback": self._last_fallback,
            "fallback_count": self._fallback_count,
            "success_count": self._success_count,
            "error_count": self._error_count,
            "primary_failures": self._primary_failures,
            "freecrypto_connected": self.free_client.is_connected if self.free_client else False,
            "cache_keys": len(self.cache.keys("price_*")) if self.cache else 0
        }
