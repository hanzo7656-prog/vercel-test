# core/price_manager.py
# ============================================================
# مدیریت قیمت‌های لحظه‌ای با معماری دوگانه (Hybrid) - نسخه ۲.۰
# ============================================================
# تغییرات نسخه ۲.۰:
# - ✅ رفع مشکل ۱: is_connected حالا درست کار می‌کنه (tolerant)
# - ✅ رفع مشکل ۲: _update_from_freecrypto واقعاً درخواست می‌زنه
# - ✅ رفع مشکل ۳: missing_symbols حالا بر اساس زمان چک می‌کنه
# - ✅ رفع مشکل ۴: get_stats کلید websocket_connected هم داره
# - ✅ رفع مشکل ۵: self._primary_failures آپدیت میشه
# ============================================================

import logging
import time
import threading
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta

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
    
    ✅ نسخه ۲.۰: رفع ۵ باگ بحرانی
    """
    
    # ============================================================
    # تنظیمات
    # ============================================================
    
    # اگه آخرین داده موفق قدیمی‌تر از این باشه، منبع رو "قطع" حساب می‌کنیم
    STALE_THRESHOLD_SECONDS = 60
    
    # اگه داده کش قدیمی‌تر از این باشه، دوباره از منبع می‌گیریم
    PRICE_FRESHNESS_SECONDS = 25
    
    # حداکثر تعداد failure قبل از fallback
    MAX_PRIMARY_FAILURES = 3
    
    def __init__(
        self,
        free_client: FreeCryptoClient,
        user_tracker: UserTracker,
        cache=None,
        primary_interval: int = 10,
        fallback_interval: int = 30,
        redis_ttl: int = 120  # ✅ افزایش از 60 به 120
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
        
        # ===== آمار =====
        self._last_update: Optional[str] = None
        self._last_fallback: Optional[str] = None
        self._last_successful_primary: Optional[float] = None  # timestamp (float)
        self._last_successful_fallback: Optional[float] = None
        self._fallback_count = 0
        self._error_count = 0
        self._success_count = 0
        self._primary_failures = 0  # ✅ حالا به صورت self ذخیره میشه
        
        # لیست ارزهایی که باید بروزرسانی شوند
        self._watch_symbols: List[str] = []
        
        logger.info("✅ PriceManager v2.0 initialized (Hybrid architecture)")
        logger.info(f"   Primary: FreeCryptoAPI (every {primary_interval}s)")
        logger.info(f"   Fallback: CoinStats (every {fallback_interval}s if primary fails)")
        logger.info(f"   Stale threshold: {self.STALE_THRESHOLD_SECONDS}s")
        logger.info(f"   Price freshness: {self.PRICE_FRESHNESS_SECONDS}s")
    
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
    
    # ============================================================
    # حلقه اصلی
    # ============================================================
    
    def _run(self) -> None:
        """حلقه اصلی بروزرسانی"""
        while not self._stop_event.is_set():
            try:
                online_users = self.user_tracker.get_online_count()
                
                if online_users > 0:
                    # ۱. بروزرسانی از FreeCryptoAPI (اولویت اول)
                    success = self._update_from_freecrypto()
                    
                    if success:
                        # ✅ موفق: reset کردن failure counter
                        self._primary_failures = 0
                        self._last_successful_primary = time.time()
                    else:
                        # ❌ ناموفق: افزایش counter
                        self._primary_failures += 1
                        logger.warning(
                            f"⚠️ FreeCryptoAPI failure #{self._primary_failures}"
                        )
                    
                    # ۲. Fallback به CoinStats (اگه چند بار پشت سر هم fail شد)
                    if self._primary_failures >= self.MAX_PRIMARY_FAILURES:
                        logger.info(
                            f"🔄 Switching to Fallback (CoinStats) after "
                            f"{self._primary_failures} failures"
                        )
                        self._update_from_coinstats()
                        self._last_successful_fallback = time.time()
                        self._primary_failures = 0  # reset بعد از fallback
                    
                    # ۳. بروزرسانی دوره‌ای CoinStats (حتی اگه primary کار می‌کنه)
                    if self._last_successful_fallback is None:
                        # اگه هیچوقت fallback نکردیم، یه بار انجام بده
                        self._update_from_coinstats()
                        self._last_successful_fallback = time.time()
                    else:
                        elapsed = time.time() - self._last_successful_fallback
                        if elapsed >= self.fallback_interval * 2:  # هر 60 ثانیه
                            self._update_from_coinstats()
                            self._last_successful_fallback = time.time()
                    
                    time.sleep(self.primary_interval)
                else:
                    # بدون کاربر آنلاین، استراحت بیشتر
                    logger.debug("💤 No online users, waiting...")
                    time.sleep(30)
                    
            except Exception as e:
                logger.error(f"❌ PriceManager error: {e}", exc_info=True)
                self._error_count += 1
                time.sleep(5)
    
    # ============================================================
    # بروزرسانی از FreeCrypto
    # ============================================================
    
    def _update_from_freecrypto(self) -> bool:
        """
        بروزرسانی قیمت‌ها از FreeCryptoAPI
        
        ✅ رفع باگ ۲: حالا واقعاً درخواست می‌زنه، نه اینکه فقط از cache بخونه
        """
        try:
            symbols = self._get_watch_symbols()
            if not symbols:
                logger.debug("No watch symbols, skipping FreeCrypto update")
                return True  # خالی بودن symbol خطا نیست
            
            # ✅ به جای get_prices که از cache می‌خونه،
            #    مستقیم از free_client.get_price استفاده می‌کنیم
            #    که خودش cache داخلی رو چک می‌کنه
            success_count = 0
            failure_count = 0
            fetched_prices = {}
            
            for symbol in symbols[:20]:  # حداکثر ۲۰ symbol
                try:
                    price_data = self.free_client.get_price(symbol)
                    
                    if price_data and price_data.get("price"):
                        fetched_prices[symbol] = price_data
                        success_count += 1
                    else:
                        failure_count += 1
                except Exception as e:
                    logger.debug(f"FreeCrypto error for {symbol}: {e}")
                    failure_count += 1
            
            # ✅ اگه حداقل یه قیمت گرفتیم، موفق حساب میشه
            if success_count > 0:
                # ذخیره در Redis
                for symbol, data in fetched_prices.items():
                    cache_key = f"price_{symbol}"
                    try:
                        self.cache.set(cache_key, data, self.redis_ttl)
                    except Exception as e:
                        logger.error(f"Cache set error for {symbol}: {e}")
                
                # ✅ آپدیت آمار
                self._last_update = datetime.now().isoformat()
                self._success_count += 1
                
                logger.debug(
                    f"✅ FreeCrypto update: {success_count} success, "
                    f"{failure_count} failed"
                )
                return True
            else:
                # هیچ قیمتی نگرفتیم
                logger.warning(
                    f"⚠️ FreeCryptoAPI returned no valid prices "
                    f"({failure_count} failures)"
                )
                return False
                
        except Exception as e:
            logger.error(f"❌ FreeCryptoAPI error: {e}", exc_info=True)
            self._error_count += 1
            return False
    
    # ============================================================
    # بروزرسانی از CoinStats (Fallback)
    # ============================================================
    
    def _update_from_coinstats(self) -> None:
        """
        بروزرسانی قیمت‌ها از CoinStats (Fallback)
        
        ✅ رفع باگ ۳: حالا بر اساس زمان چک می‌کنه، نه بر اساس وجود کلید
        """
        try:
            symbols = self._get_watch_symbols()
            if not symbols:
                return
            
            now = time.time()
            updated_count = 0
            skipped_count = 0
            
            # ✅ فقط symbolهایی که کششون قدیمی شده رو آپدیت کن
            for symbol in symbols[:10]:
                try:
                    cache_key = f"price_{symbol}"
                    cached = self.cache.get(cache_key)
                    
                    # چک کردن freshness
                    should_update = True
                    if cached and isinstance(cached, dict):
                        cached_ts = cached.get("timestamp")
                        cached_source = cached.get("source", "")
                        
                        # اگه از CoinStats قبلی و تازه هست، skip کن
                        if cached_ts and "coinstats" in cached_source:
                            try:
                                cached_dt = datetime.fromisoformat(cached_ts)
                                age = (datetime.now() - cached_dt).total_seconds()
                                if age < self.PRICE_FRESHNESS_SECONDS:
                                    should_update = False
                                    skipped_count += 1
                            except (ValueError, TypeError):
                                pass
                    
                    if not should_update:
                        continue
                    
                    # گرفتن از CoinStats
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
                        self.cache.set(cache_key, price_data, self.redis_ttl)
                        updated_count += 1
                        self._fallback_count += 1
                        
                except Exception as e:
                    logger.error(f"❌ CoinStats error for {symbol}: {e}")
                    self._error_count += 1
            
            if updated_count > 0:
                self._last_fallback = datetime.now().isoformat()
                logger.debug(
                    f"✅ CoinStats fallback: {updated_count} updated, "
                    f"{skipped_count} skipped (fresh)"
                )
            
        except Exception as e:
            logger.error(f"❌ CoinStats fallback error: {e}", exc_info=True)
            self._error_count += 1
    
    # ============================================================
    # Symbol Management
    # ============================================================
    
    def _get_watch_symbols(self) -> List[str]:
        """دریافت لیست ارزهای مورد نظر"""
        # اگه set_watch_symbols صدا زده شده، از اون استفاده کن
        if self._watch_symbols:
            return self._watch_symbols
        
        # وگرنه از کش coins_list بخون
        try:
            coins_list = self.cache.get("coins_list_50_1_USD_None")
            if coins_list:
                symbols = []
                for coin in coins_list[:20]:
                    symbol = coin.get("symbol", "").upper()
                    if symbol:
                        symbols.append(symbol)
                return symbols or ["BTC", "ETH", "SOL", "ADA", "XRP"]
        except Exception as e:
            logger.debug(f"Error reading coins_list from cache: {e}")
        
        return ["BTC", "ETH", "SOL", "ADA", "XRP"]
    
    def set_watch_symbols(self, symbols: List[str]) -> None:
        """تنظیم دستی symbolها"""
        self._watch_symbols = [s.upper() for s in symbols]
        logger.info(f"📡 Watch symbols updated: {len(self._watch_symbols)} symbols")
    
    # ============================================================
    # Get Prices
    # ============================================================
    
    def get_price(self, symbol: str) -> Optional[Dict[str, Any]]:
        """دریافت قیمت یک symbol از کش"""
        symbol = symbol.upper()
        cache_key = f"price_{symbol}"
        try:
            cached = self.cache.get(cache_key)
            if cached:
                return cached
        except Exception as e:
            logger.debug(f"Cache get error for {symbol}: {e}")
        return None
    
    def get_prices(self, symbols: Optional[List[str]] = None) -> Dict[str, Dict[str, Any]]:
        """دریافت قیمت‌های چند symbol از کش"""
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
    
    # ============================================================
    # وضعیت اتصال (✅ رفع باگ ۱ و ۴)
    # ============================================================
    
    def is_primary_connected(self) -> bool:
        """
        آیا FreeCrypto متصل است؟
        
        ✅ رفع باگ ۱: به جای تکیه بر is_connected که ممکنه False بمونه،
        بر اساس زمان آخرین موفقیت چک می‌کنیم.
        """
        if self._last_successful_primary is None:
            # اگه هیچوقت موفق نشده، ببین is_connected خودش چی میگه
            return bool(self.free_client and self.free_client.is_connected)
        
        elapsed = time.time() - self._last_successful_primary
        return elapsed < self.STALE_THRESHOLD_SECONDS
    
    def is_fallback_connected(self) -> bool:
        """آیا CoinStats fallback فعال بوده؟"""
        if self._last_successful_fallback is None:
            return False
        elapsed = time.time() - self._last_successful_fallback
        return elapsed < self.STALE_THRESHOLD_SECONDS * 2  # fallback سخاوتمندانه‌تر
    
    def get_connection_status(self) -> str:
        """
        وضعیت کلی:
        - 'online': FreeCrypto متصل
        - 'degraded': FreeCrypto قطع ولی CoinStats fallback فعال
        - 'offline': هیچکدوم
        - 'unknown': هنوز چیزی چک نشده
        """
        if self._last_successful_primary is None and self._last_successful_fallback is None:
            return 'unknown'
        
        if self.is_primary_connected():
            return 'online'
        elif self.is_fallback_connected():
            return 'degraded'
        else:
            return 'offline'
    
    # ============================================================
    # آمار (✅ رفع باگ ۴ و ۵)
    # ============================================================
    
    def get_stats(self) -> Dict[str, Any]:
        """
        دریافت آمار کامل PriceManager
        
        ✅ رفع باگ ۴: کلید websocket_connected هم اضافه شد (alias برای frontend)
        ✅ رفع باگ ۵: primary_failures درست برمی‌گرده
        """
        primary_connected = self.is_primary_connected()
        fallback_connected = self.is_fallback_connected()
        connection_status = self.get_connection_status()
        
        # ✅ محاسبه تعداد کلیدهای کش
        try:
            cache_keys_count = len(self.cache.keys("price_*"))
        except Exception:
            cache_keys_count = 0
        
        # ✅ زمان آخرین بروزرسانی
        last_update = self._last_update
        last_update_age = None
        if last_update:
            try:
                dt = datetime.fromisoformat(last_update)
                last_update_age = int((datetime.now() - dt).total_seconds())
            except (ValueError, TypeError):
                pass
        
        return {
            # ===== وضعیت اصلی =====
            "is_running": self.is_running,
            "connection_status": connection_status,
            
            # ===== اتصال‌ها =====
            # ✅ کلید اصلی که frontend انتظار داره
            "websocket_connected": primary_connected,
            # ✅ کلید alias برای سازگاری
            "freecrypto_connected": primary_connected,
            "coinstats_connected": fallback_connected,
            "primary_connected": primary_connected,
            "fallback_connected": fallback_connected,
            
            # ===== زمان‌ها =====
            "last_update": self._last_update,
            "last_update_age_seconds": last_update_age,
            "last_fallback": self._last_fallback,
            
            # ===== آمار =====
            "fallback_count": self._fallback_count,
            "success_count": self._success_count,
            "error_count": self._error_count,
            "primary_failures": self._primary_failures,  # ✅ حالا درست
            "cache_keys": cache_keys_count,
            
            # ===== اطلاعات بیشتر =====
            "primary_failures_current": self._primary_failures,
            "max_primary_failures": self.MAX_PRIMARY_FAILURES,
            "stale_threshold_seconds": self.STALE_THRESHOLD_SECONDS,
            "freshness_threshold_seconds": self.PRICE_FRESHNESS_SECONDS
        }
    
    # ============================================================
    # توابع کمکی
    # ============================================================
    
    def refresh_now(self, symbols: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        درخواست بروزرسانی فوری از هر دو منبع.
        برای استفاده در endpoint manual refresh.
        """
        logger.info("🔄 Manual refresh requested")
        
        freecrypto_ok = self._update_from_freecrypto()
        
        # اگه FreeCrypto fail شد، حتماً از CoinStats بگیر
        if not freecrypto_ok:
            self._update_from_coinstats()
        
        return {
            "success": True,
            "freecrypto_success": freecrypto_ok,
            "message": "Refresh completed",
            "timestamp": datetime.now().isoformat()
        }


# ============================================================
# نمونه Singleton (اختیاری - توی container ساخته میشه)
# ============================================================
# اینجا نساخته میشه چون container مسئولشه
# price_manager = PriceManager(...)
