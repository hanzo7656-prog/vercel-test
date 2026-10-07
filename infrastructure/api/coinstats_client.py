# infrastructure/api/coinstats_client.py
# ============================================================
# کلاینت API کوین‌استیتس - نسخه ۵.۱
# OHLCV Candles + Interval Cap + Smart Pair Mapping
# ============================================================

import os
import time
import requests
import logging
from typing import Dict, Any, Optional, List, Union

from domain.interfaces.api_client import APIClient
from infrastructure.api.cache_manager import cache_manager

logger = logging.getLogger(__name__)


# ============================================================
# Constants
# ============================================================

# ============================================================
# ۱. Hard-coded mapping برای top coins (سریع، صفر credit)
# ============================================================
# این لیست فقط برای سرعت هست
# fallback به API برای بقیه داریم
COIN_TO_PAIR: Dict[str, str] = {
    # Top 20
    "bitcoin": "BTC/USDT",
    "ethereum": "ETH/USDT",
    "tether": "USDT/USD",
    "binancecoin": "BNB/USDT",
    "solana": "SOL/USDT",
    "usd-coin": "USDC/USD",
    "ripple": "XRP/USDT",
    "dogecoin": "DOGE/USDT",
    "cardano": "ADA/USDT",
    "tron": "TRX/USDT",
    "avalanche-2": "AVAX/USDT",
    "shiba-inu": "SHIB/USDT",
    "polkadot": "DOT/USDT",
    "chainlink": "LINK/USDT",
    "polygon": "MATIC/USDT",
    "litecoin": "LTC/USDT",
    "uniswap": "UNI/USDT",
    "bitcoin-cash": "BCH/USDT",
    "stellar": "XLM/USDT",
    "near": "NEAR/USDT",
    
    # Top 21-50
    "aptos": "APT/USDT",
    "arbitrum": "ARB/USDT",
    "optimism": "OP/USDT",
    "filecoin": "FIL/USDT",
    "hedera-hashgraph": "HBAR/USDT",
    "internet-computer": "ICP/USDT",
    "cosmos": "ATOM/USDT",
    "immutable-x": "IMX/USDT",
    "injective-protocol": "INJ/USDT",
    "render-token": "RENDER/USDT",
    "vechain": "VET/USDT",
    "algorand": "ALGO/USDT",
    "fantom": "FTM/USDT",
    "the-graph": "GRT/USDT",
    "decentraland": "MANA/USDT",
    "sandbox": "SAND/USDT",
    "aave": "AAVE/USDT",
    "maker": "MKR/USDT",
    "curve-dao-token": "CRV/USDT",
    "the-open-network": "TON/USDT",
    "pepe": "PEPE/USDT",
    "bonk": "BONK/USDT",
    "sei-network": "SEI/USDT",
    "sui": "SUI/USDT",
    "celestia": "TIA/USDT",
    "jupiter-exchange-solana": "JUP/USDT",
    "pyth-network": "PYTH/USDT",
    "stacks": "STX/USDT",
    "thorchain": "RUNE/USDT",
    "dydx": "DYDX/USDT",
}


# ============================================================
# ۲. محدودیت interval → max range (100k candles limit)
# ============================================================
# CoinStats: max 100,000 candles per request
# اگه range بزرگ‌تر باشه → 400 error
# این جدول بزرگ‌ترین range امن رو نگه می‌داره
INTERVAL_MAX_RANGE: Dict[str, str] = {
    "5m":  "6mo",    # ~۵۲k کندل
    "15m": "1y",     # ~۳۵k کندل
    "30m": "1y",     # ~۱۷k کندل
    "1h":  "1y",     # ~۸.۷k کندل
    "4h":  "all",    # کاملاً امن (چون تاریخچه Binance از ۲۰۱۷)
    "1d":  "all",    # کاملاً امن
    "1w":  "all",    # کاملاً امن
}

# ترتیب range از کوچیک به بزرگ
RANGE_ORDER: List[str] = [
    "1h", "6h", "24h", "1w", "1mo", "3mo", "6mo", "1y", "all"
]

# TTL بر اساس interval (ثانیه)
OHLCV_TTL_MAP: Dict[str, int] = {
    "5m": 60,
    "15m": 300,
    "30m": 600,
    "1h": 1800,
    "4h": 3600,
    "1d": 7200,
    "1w": 86400,
}


# ============================================================
# CoinStatsClient
# ============================================================

class CoinStatsClient(APIClient):
    """
    کلاینت رسمی API کوین‌استیتس
    
    نسخه ۵.۱:
        - get_ohlcv_candles برای OHLCV واقعی
        - interval cap خودکار (100k limit)
        - smart pair mapping (hard-coded + API fallback)
    """
    
    def __init__(self, api_key: Optional[str] = None) -> None:
        self.api_key: str = api_key or os.getenv("COINSTATS_API_KEY", "")
        if not self.api_key:
            logger.warning("⚠️ COINSTATS_API_KEY not set in environment!")
        
        self.base_url: str = "https://api.coinstats.app"
        self.session: requests.Session = requests.Session()
        self.session.headers.update({
            "X-API-KEY": self.api_key,
            "Content-Type": "application/json",
            "Accept": "application/json"
        })
        
        self._stats: Dict[str, Any] = {
            "total_requests": 0,
            "error_count": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "start_time": time.time(),
            "ohlcv_requests": 0,
            "ohlcv_candles_total": 0,
            "ohlcv_range_caps": 0,
        }
        
        self.rate_limit_remaining: int = 30
        self.rate_limit_reset: float = time.time()
        
        # cache داخلی برای symbol mapping
        self._symbol_map_cache: Optional[Dict[str, str]] = None
        
        logger.info("✅ CoinStatsClient v5.1 initialized")
    
    # ============================================================
    # Internal Request
    # ============================================================
    
    def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict] = None,
        retries: int = 2,
    ) -> Dict:
        """ارسال درخواست با مدیریت Retry"""
        url: str = f"{self.base_url}{endpoint}"
        self._stats["total_requests"] += 1
        
        if self.rate_limit_remaining <= 0 and time.time() < self.rate_limit_reset:
            wait_time: float = self.rate_limit_reset - time.time() + 1
            logger.warning(f"⏳ Rate limit exceeded, waiting {wait_time:.1f}s")
            time.sleep(wait_time)
        
        try:
            response: requests.Response = self.session.request(
                method,
                url,
                params=params,
                timeout=30,  # ← بیشتر برای OHLCV سنگین
            )
            
            self.rate_limit_remaining = int(
                response.headers.get('X-RateLimit-Remaining', 30)
            )
            reset_time: Optional[str] = response.headers.get('X-RateLimit-Reset')
            if reset_time:
                self.rate_limit_reset = float(reset_time)
            
            # Rate limit
            if response.status_code == 429:
                self._stats["error_count"] += 1
                if retries > 0:
                    wait_time = (3 - retries) * 2 + 1
                    logger.info(f"⏳ Rate Limit! waiting {wait_time}s...")
                    time.sleep(wait_time)
                    return self._request(method, endpoint, params, retries - 1)
                return {"error": "Rate Limit exceeded"}
            
            # Interval too small
            if response.status_code == 422:
                return {"error": "Interval too small for this pair"}
            
            # Bad request (100k limit violation)
            if response.status_code == 400:
                try:
                    err_data = response.json()
                    msg = err_data.get("message", "Bad Request")
                except Exception:
                    msg = "Bad Request"
                return {"error": msg}
            
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.Timeout as e:
            self._stats["error_count"] += 1
            if retries > 0:
                logger.info("⏳ Timeout! retrying...")
                time.sleep(1)
                return self._request(method, endpoint, params, retries - 1)
            return {"error": f"Timeout: {str(e)}"}
            
        except requests.exceptions.ConnectionError as e:
            self._stats["error_count"] += 1
            if retries > 0:
                logger.info("⏳ Connection error! retrying...")
                time.sleep(2)
                return self._request(method, endpoint, params, retries - 1)
            return {"error": f"ConnectionError: {str(e)}"}
            
        except requests.exceptions.RequestException as e:
            self._stats["error_count"] += 1
            return {"error": str(e)}
    
    # ============================================================
    # OHLCV Candles
    # ============================================================
    
    def get_ohlcv_candles(
        self,
        exchange: str = "Binance",
        pair: str = "BTC/USDT",
        interval: str = "4h",
        range: Optional[str] = None,
        start: Optional[str] = None,
        end: Optional[str] = None,
        use_cache: bool = True,
        auto_cap: bool = True,
    ) -> Optional[Dict]:
        """
        دریافت OHLCV واقعی از صرافی
        
        Args:
            exchange: نام صرافی
            pair: جفت معاملاتی (BTC/USDT)
            interval: بازه (5m, 15m, 30m, 1h, 4h, 1d, 1w)
            range: بازه رولینگ
            start: تاریخ شروع ISO 8601 (با end)
            end: تاریخ پایان ISO 8601 (با start)
            use_cache: استفاده از cache
            auto_cap: خودکار range رو cap کنه اگه از ۱۰۰k بگذره
        
        Returns:
            dict پاسخ یا None در صورت خطا
        """
        # ============================================================
        # اعتبارسنجی
        # ============================================================
        
        valid_intervals = ["5m", "15m", "30m", "1h", "4h", "1d", "1w"]
        if interval not in valid_intervals:
            logger.error(f"❌ Invalid interval: {interval}")
            return None
        
        # تعیین mode
        if not range and not (start and end):
            range = "1mo"  # پیش‌فرض
        
        if range and (start or end):
            logger.warning("Both range and start/end given; using range")
            start = None
            end = None
        
        # ============================================================
        # Auto Cap Range (مهم!)
        # ============================================================
        
        original_range = range
        was_capped = False
        
        if range and auto_cap:
            range, was_capped = self._cap_range(interval, range)
            
            if was_capped:
                self._stats["ohlcv_range_caps"] += 1
                logger.warning(
                    f"⚠️ Range capped: '{original_range}' → '{range}' "
                    f"(interval={interval}, 100k limit)"
                )
        
        # ============================================================
        # Cache key
        # ============================================================
        
        pair_key = pair.replace("/", "_")
        cache_parts = ["ohlcv", exchange, pair_key, interval]
        
        if range:
            cache_parts.append(f"r_{range}")
        else:
            start_date = start[:10] if start else "?"
            end_date = end[:10] if end else "?"
            cache_parts.append(f"s_{start_date}_e_{end_date}")
        
        cache_key = "_".join(cache_parts)
        
        # ============================================================
        # Cache check
        # ============================================================
        
        if use_cache:
            cached = cache_manager.get(cache_key)
            if cached is not None and isinstance(cached, dict):
                self._stats["cache_hits"] += 1
                logger.debug(f"⚡ OHLCV from cache: {pair} {interval}")
                
                # اگه cap شده، توی پاسخ cache شده هم علامت بزن
                if was_capped:
                    cached = dict(cached)
                    cached["warning"] = (
                        f"Range capped from '{original_range}' to '{range}'"
                    )
                    cached["original_range"] = original_range
                
                return cached
        
        self._stats["cache_misses"] += 1
        
        # ============================================================
        # Request
        # ============================================================
        
        params: Dict[str, Any] = {
            "exchange": exchange,
            "pair": pair,
            "interval": interval,
        }
        
        if range:
            params["range"] = range
        else:
            params["start"] = start
            params["end"] = end
        
        self._stats["ohlcv_requests"] += 1
        
        result = self._request("GET", "/v1/ohlcv/candles", params)
        
        # ============================================================
        # Handle response
        # ============================================================
        
        if not result or "error" in result:
            logger.warning(
                f"⚠️ OHLCV failed for {pair} {interval}: "
                f"{result.get('error') if result else 'no response'}"
            )
            return None
        
        candles = result.get("candles", [])
        if not candles:
            logger.warning(f"⚠️ OHLCV empty for {pair} {interval}")
            return None
        
        # آمار
        self._stats["ohlcv_candles_total"] += len(candles)
        
        # اضافه کردن warning اگه cap شده
        if was_capped:
            result["warning"] = (
                f"Range capped from '{original_range}' to '{range}' "
                f"due to 100k candle limit"
            )
            result["original_range"] = original_range
        
        # Cache
        if use_cache:
            ttl = OHLCV_TTL_MAP.get(interval, 3600)
            cache_manager.set(cache_key, result, ttl)
        
        logger.info(
            f"✅ OHLCV: {pair} {interval} "
            f"({len(candles)} candles, range={range or 'custom'}"
            f"{', capped' if was_capped else ''})"
        )
        
        return result
    
    # ============================================================
    # Auto Cap Helper
    # ============================================================
    
    def _cap_range(
        self,
        interval: str,
        range: str,
    ) -> tuple[str, bool]:
        """
        Cap range اگه از ۱۰۰k کندل بگذره
        
        Returns:
            (final_range, was_capped)
        """
        if interval not in INTERVAL_MAX_RANGE:
            return range, False
        
        max_safe = INTERVAL_MAX_RANGE[interval]
        
        # اگه range ناشناخته‌ست، دست نزن
        if range not in RANGE_ORDER or max_safe not in RANGE_ORDER:
            return range, False
        
        range_idx = RANGE_ORDER.index(range)
        max_idx = RANGE_ORDER.index(max_safe)
        
        if range_idx > max_idx:
            return max_safe, True
        
        return range, False
    
    # ============================================================
    # Pair Mapping (smart)
    # ============================================================
    
    def coin_id_to_pair(self, coin_id: str) -> Optional[str]:
        """
        تبدیل coin_id به pair با smart mapping
        
        استراتژی:
            ۱. hard-coded (سریع)
            ۲. از coins_list API (cache ۲۴h)
            ۳. fallback با uppercase
        
        Args:
            coin_id: "bitcoin", "pepe", ...
        
        Returns:
            "BTC/USDT" یا None
        """
        if not coin_id:
            return None
        
        cid = coin_id.lower().strip()
        
        # ۱. hard-coded
        if cid in COIN_TO_PAIR:
            return COIN_TO_PAIR[cid]
        
        # ۲. از API
        symbol = self._get_symbol_from_api(cid)
        if symbol:
            return f"{symbol}/USDT"
        
        # ۳. fallback: اگه coin_id کوتاهه (۲-۶ کاراکتر)، احتمالاً symbol هست
        if 2 <= len(cid) <= 6 and cid.isalpha():
            return f"{cid.upper()}/USDT"
        
        # نمی‌تونیم تشخیص بدیم
        logger.warning(f"⚠️ Cannot map coin_id '{coin_id}' to pair")
        return None
    
    def _get_symbol_from_api(self, coin_id: str) -> Optional[str]:
        """
        گرفتن symbol از coins_list (با cache)
        """
        # cache داخلی memory
        if self._symbol_map_cache is None:
            # تلاش از Redis
            cache_key = "coinstats_symbol_map"
            cached = cache_manager.get(cache_key)
            
            if cached and isinstance(cached, dict):
                self._symbol_map_cache = cached
                logger.debug("⚡ Symbol map from cache")
            else:
                # از API
                logger.info("📥 Fetching coins list for symbol map...")
                coins = self.get_coins_list(limit=500, page=1)
                
                if coins:
                    mapping = {
                        c.get("id", "").lower(): c.get("symbol", "").upper()
                        for c in coins
                        if c.get("id") and c.get("symbol")
                    }
                    self._symbol_map_cache = mapping
                    cache_manager.set(cache_key, mapping, 86400)  # ۲۴ ساعت
                    logger.info(f"✅ Symbol map built: {len(mapping)} coins")
                else:
                    self._symbol_map_cache = {}
        
        return self._symbol_map_cache.get(coin_id)
    
    # ============================================================
    # متدهای قبلی (بدون تغییر)
    # ============================================================
    
    def get_chart(
        self,
        coin_id: str,
        period: str = "24h",
        currency: str = "USD",
    ) -> Union[List[List], Dict]:
        """دریافت داده‌های تاریخی (فقط قیمت) — TTL: ۱ ساعت"""
        cache_key: str = f"chart_{coin_id}_{period}"
        
        cached = cache_manager.get(cache_key)
        if cached is not None:
            self._stats["cache_hits"] += 1
            return cached
        
        self._stats["cache_misses"] += 1
        result: Dict = self._request("GET", f"/v1/coins/{coin_id}/charts", {
            "period": period,
            "currency": currency,
        })
        
        if result and isinstance(result, list) and len(result) > 0:
            cache_manager.set(cache_key, result, 3600)
        
        return result
    
    def get_coin(self, coin_id: str, currency: str = "USD") -> Optional[Dict]:
        """دریافت اطلاعات لحظه‌ای (TTL: ۶۰ ثانیه)"""
        cache_key: str = f"coin_{coin_id}_{currency}"
        
        cached = cache_manager.get(cache_key)
        if cached is not None:
            self._stats["cache_hits"] += 1
            return cached
        
        self._stats["cache_misses"] += 1
        result: Dict = self._request(
            "GET", f"/v1/coins/{coin_id}", {"currency": currency}
        )
        
        if result and "error" not in result:
            cache_manager.set(cache_key, result, 60)
        
        return result
    
    def get_fear_greed(self, use_cache: bool = True) -> Optional[Dict]:
        """دریافت شاخص ترس و طمع (TTL: ۵ دقیقه)"""
        cache_key: str = "fear_greed"
        
        if use_cache:
            cached = cache_manager.get(cache_key)
            if cached is not None:
                self._stats["cache_hits"] += 1
                return cached
        
        self._stats["cache_misses"] += 1
        result: Dict = self._request("GET", "/v1/insights/fear-and-greed")
        
        if result and "error" not in result:
            cache_manager.set(cache_key, result, 300)
        
        return result
    
    def get_btc_dominance(
        self,
        period: str = "24h",
        use_cache: bool = True,
    ) -> Optional[Dict]:
        """دریافت سلطه بیت‌کوین (TTL: ۵ دقیقه)"""
        cache_key: str = f"btc_dom_{period}"
        
        if use_cache:
            cached = cache_manager.get(cache_key)
            if cached is not None:
                self._stats["cache_hits"] += 1
                return cached
        
        self._stats["cache_misses"] += 1
        result: Dict = self._request(
            "GET", "/v1/insights/btc-dominance", {"type": period}
        )
        
        if result and "error" not in result:
            cache_manager.set(cache_key, result, 300)
        
        return result
    
    def get_credits(self) -> Optional[Dict]:
        """دریافت اعتبار باقیمانده (TTL: ۵ دقیقه)"""
        cache_key: str = "credits"
        
        cached = cache_manager.get(cache_key)
        if cached is not None:
            self._stats["cache_hits"] += 1
            return cached
        
        self._stats["cache_misses"] += 1
        result: Dict = self._request("GET", "/v1/usage/credits")
        
        if result and "error" not in result:
            cache_manager.set(cache_key, result, 300)
        
        return result
    
    def get_status(self) -> Optional[Dict]:
        """بررسی سلامت API (TTL: ۳ دقیقه)"""
        cache_key: str = "api_status"
        
        cached = cache_manager.get(cache_key)
        if cached is not None:
            self._stats["cache_hits"] += 1
            return cached
        
        self._stats["cache_misses"] += 1
        result: Dict = self._request("GET", "/v1/status")
        
        if result and "error" not in result:
            cache_manager.set(cache_key, result, 180)
        
        return result
    
    def get_news(self, limit: int = 10) -> Optional[Dict]:
        """دریافت اخبار (TTL: ۱۰ دقیقه)"""
        cache_key: str = f"news_{limit}"
        
        cached = cache_manager.get(cache_key)
        if cached is not None:
            self._stats["cache_hits"] += 1
            return cached
        
        self._stats["cache_misses"] += 1
        result: Dict = self._request("GET", "/v1/news", {"limit": limit})
        
        if result and "error" not in result:
            cache_manager.set(cache_key, result, 600)
        
        return result
    
    def get_global_market(self) -> Optional[Dict]:
        """دریافت وضعیت کلی بازار (TTL: ۶۰ ثانیه)"""
        cache_key: str = "global_market"
        
        cached = cache_manager.get(cache_key)
        if cached is not None:
            self._stats["cache_hits"] += 1
            return cached
        
        self._stats["cache_misses"] += 1
        result: Dict = self._request("GET", "/v1/markets")
        
        if result and "error" not in result:
            cache_manager.set(cache_key, result, 60)
        
        return result
    
    def get_coins_list(self, limit=50, page=1, currency="USD", search=None):
        """
        دریافت لیست ارزها (با cache بهینه‌شده)
    
        نکات:
            - همیشه از cache_limit=250 استفاده می‌کند
            - search روی cache انجام می‌شود (نه cache key جدا)
            - cache key: coins_list_250_1_USD
        """
        # ✅ همیشه از یک cache key استفاده کن
        cache_limit = max(250, limit)  # حداقل ۲۵۰ (یا بیشتر اگه کسی بیشتر خواست)
        cache_key = f"coins_list_{cache_limit}_{page}_{currency}"

        cached = cache_manager.get(cache_key)

        if cached is not None:
            # search روی cache (بدون cache key جدا)
            if search:
                search_lower = search.lower().strip()
                filtered = [
                    c for c in cached
                    if search_lower in (c.get('name') or '').lower()
                    or search_lower in (c.get('symbol') or '').lower()
                    or search_lower in (c.get('id') or '').lower()
                ]
                return filtered[:limit]
            return cached[:limit]
            
        # fetch از API
        result = self._request("GET", "/v1/coins", {
            "limit": cache_limit,
            "page": page,
            "currency": currency,
        })

        if result and "result" in result:
            coins = result.get("result", [])

            # ✅ TTL = ۶ ساعت (نه ۲۴)
            cache_manager.set(cache_key, coins, 21600)

            # search روی نتیجه
            if search:
                search_lower = search.lower().strip()
                coins = [
                    c for c in coins
                    if search_lower in (c.get('name') or '').lower()
                    or search_lower in (c.get('symbol') or '').lower()
                    or search_lower in (c.get('id') or '').lower()
                ]

            return coins[:limit]

        return None
    
    # ============================================================
    # Stats
    # ============================================================
    
    def get_stats(self) -> Dict[str, Any]:
        """دریافت آمار کلاینت"""
        uptime: int = int(time.time() - self._stats["start_time"])
        return {
            "total_requests": self._stats["total_requests"],
            "error_count": self._stats["error_count"],
            "cache_hits": self._stats["cache_hits"],
            "cache_misses": self._stats["cache_misses"],
            "hit_ratio": round(
                self._stats["cache_hits"] /
                max(self._stats["cache_hits"] + self._stats["cache_misses"], 1) * 100,
                2,
            ),
            "uptime_seconds": uptime,
            "rate_limit_remaining": self.rate_limit_remaining,
            "ohlcv_requests": self._stats.get("ohlcv_requests", 0),
            "ohlcv_candles_total": self._stats.get("ohlcv_candles_total", 0),
            "ohlcv_range_caps": self._stats.get("ohlcv_range_caps", 0),
            "symbol_map_cached": self._symbol_map_cache is not None,
            "cache_stats": cache_manager.get_stats(),
        }


# ============================================================
# Singleton
# ============================================================

coinstats_client: CoinStatsClient = CoinStatsClient()
