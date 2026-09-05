# infrastructure/api/coinstats_client.py
# ============================================================
# کلاینت API کوین‌استیتس - نسخه ۴.۰
# ============================================================

import os
import time
import requests
import logging
from typing import Dict, Any, Optional, List, Union

from domain.interfaces.api_client import APIClient

# ✅ Import مستقیم از cache_manager (نه از __init__)
from infrastructure.api.cache_manager import cache_manager

logger = logging.getLogger(__name__)


class CoinStatsClient(APIClient):
    """
    کلاینت رسمی API کوین‌استیتس
    پیاده‌سازی Interface APIClient
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
            "start_time": time.time()
        }
        
        self.rate_limit_remaining: int = 30
        self.rate_limit_reset: float = time.time()
        
        logger.info("✅ CoinStatsClient v4.0 initialized")
    
    def _request(self, method: str, endpoint: str, params: Optional[Dict] = None, retries: int = 2) -> Dict:
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
                timeout=15
            )
            
            self.rate_limit_remaining = int(response.headers.get('X-RateLimit-Remaining', 30))
            reset_time: Optional[str] = response.headers.get('X-RateLimit-Reset')
            if reset_time:
                self.rate_limit_reset = float(reset_time)
            
            if response.status_code == 429:
                self._stats["error_count"] += 1
                if retries > 0:
                    wait_time = (3 - retries) * 2 + 1
                    logger.info(f"⏳ Rate Limit! waiting {wait_time}s...")
                    time.sleep(wait_time)
                    return self._request(method, endpoint, params, retries - 1)
                else:
                    return {"error": "Rate Limit exceeded"}
            
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
    # متدهای اصلی API
    # ============================================================
    
    def get_chart(self, coin_id: str, period: str = "24h", currency: str = "USD") -> Union[List[List], Dict]:
        """دریافت داده‌های تاریخی (TTL: ۱ ساعت)"""
        cache_key: str = f"chart_{coin_id}_{period}"
        
        cached = cache_manager.get(cache_key)
        if cached is not None:
            self._stats["cache_hits"] += 1
            return cached
        
        self._stats["cache_misses"] += 1
        result: Dict = self._request("GET", f"/v1/coins/{coin_id}/charts", {
            "period": period,
            "currency": currency
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
        result: Dict = self._request("GET", f"/v1/coins/{coin_id}", {"currency": currency})
        
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
    
    def get_btc_dominance(self, period: str = "24h", use_cache: bool = True) -> Optional[Dict]:
        """دریافت سلطه بیت‌کوین (TTL: ۵ دقیقه)"""
        cache_key: str = f"btc_dom_{period}"
        
        if use_cache:
            cached = cache_manager.get(cache_key)
            if cached is not None:
                self._stats["cache_hits"] += 1
                return cached
        
        self._stats["cache_misses"] += 1
        result: Dict = self._request("GET", "/v1/insights/btc-dominance", {"type": period})
        
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
    
    def get_coins_list(self, limit: int = 50, page: int = 1, currency: str = "USD", search: str = None) -> Optional[List[Dict]]:
        """دریافت لیست ارزها (TTL: ۲۴ ساعت)"""
        cache_key: str = f"coins_list_{limit}_{page}_{currency}_{search}"
        
        cached = cache_manager.get(cache_key)
        if cached is not None:
            self._stats["cache_hits"] += 1
            return cached
        
        self._stats["cache_misses"] += 1
        params = {"limit": limit, "page": page, "currency": currency}
        if search:
            params["search"] = search
        
        result: Dict = self._request("GET", "/v1/coins", params)
        
        if result and "result" in result:
            coins = result.get("result", [])
            cache_manager.set(cache_key, coins, 86400)  # ۲۴ ساعت
            return coins
        
        return None
    
    def get_stats(self) -> Dict[str, Any]:
        """دریافت آمار کلاینت"""
        uptime: int = int(time.time() - self._stats["start_time"])
        return {
            "total_requests": self._stats["total_requests"],
            "error_count": self._stats["error_count"],
            "cache_hits": self._stats["cache_hits"],
            "cache_misses": self._stats["cache_misses"],
            "hit_ratio": round(
                self._stats["cache_hits"] / max(self._stats["cache_hits"] + self._stats["cache_misses"], 1) * 100,
                2
            ),
            "uptime_seconds": uptime,
            "rate_limit_remaining": self.rate_limit_remaining,
            "cache_stats": cache_manager.get_stats()
        }


# ============================================================
# نمونه Singleton
# ============================================================

coinstats_client: CoinStatsClient = CoinStatsClient()
