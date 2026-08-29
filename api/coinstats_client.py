# api/coinstats_client.py
# ============================================================
# کلاینت API کوین‌استیتس - نسخه ۳.۰ با کش Redis
# ============================================================

import os
import time
import requests
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List

from api.cache_manager import cache_manager

logger = logging.getLogger(__name__)


class CoinStatsClient:
    """
    کلاینت رسمی API کوین‌استیتس
    ✅ استفاده از Redis برای کش
    ✅ مدیریت Rate Limit پیشرفته
    ✅ Retry با Backoff
    """
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("COINSTATS_API_KEY")
        if not self.api_key:
            logger.warning("⚠️ COINSTATS_API_KEY not set in environment!")
            # ⚠️ NOTE: این مورد طبق درخواست شما اصلاح نشد
        
        self.base_url = "https://api.coinstats.app"
        self.session = requests.Session()
        self.session.headers.update({
            "X-API-KEY": self.api_key,
            "Content-Type": "application/json",
            "Accept": "application/json"
        })
        
        # آمار
        self.stats = {
            "total_requests": 0,
            "error_count": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "start_time": time.time()
        }
        
        # Rate Limit
        self.rate_limit_remaining = 30
        self.rate_limit_reset = time.time()
        
        logger.info("✅ CoinStatsClient v3.0 initialized")
    
    def _request(self, method: str, endpoint: str, params: Optional[Dict] = None, retries: int = 2):
        """ارسال درخواست با مدیریت Retry"""
        url = f"{self.base_url}{endpoint}"
        self.stats["total_requests"] += 1
        
        # بررسی Rate Limit
        if self.rate_limit_remaining <= 0 and time.time() < self.rate_limit_reset:
            wait_time = self.rate_limit_reset - time.time() + 1
            logger.warning(f"⏳ Rate limit exceeded, waiting {wait_time:.1f}s")
            time.sleep(wait_time)
        
        try:
            response = self.session.request(
                method,
                url,
                params=params,
                timeout=15
            )
            
            # به‌روزرسانی Rate Limit
            self.rate_limit_remaining = int(response.headers.get('X-RateLimit-Remaining', 30))
            reset_time = response.headers.get('X-RateLimit-Reset')
            if reset_time:
                self.rate_limit_reset = float(reset_time)
            
            if response.status_code == 429:
                self.stats["error_count"] += 1
                if retries > 0:
                    wait_time = (3 - retries) * 2 + 1
                    logger.info(f"⏳ Rate Limit! waiting {wait_time}s...")
                    time.sleep(wait_time)
                    return self._request(method, endpoint, params, retries - 1)
                else:
                    return {"error": "Rate Limit exceeded"}
            
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.Timeout:
            self.stats["error_count"] += 1
            if retries > 0:
                logger.info("⏳ Timeout! retrying...")
                time.sleep(1)
                return self._request(method, endpoint, params, retries - 1)
            return {"error": "Timeout"}
            
        except requests.exceptions.RequestException as e:
            self.stats["error_count"] += 1
            return {"error": str(e)}
    
    # ============================================================
    # اندپوینت‌ها با کش Redis
    # ============================================================
    
    def get_chart(self, coin_id: str, period: str = "24h", currency: str = "USD"):
        """دریافت داده‌های تاریخی (TTL: ۱ ساعت)"""
        cache_key = f"chart_{coin_id}_{period}"
        
        # ✅ استفاده از Redis
        cached = cache_manager.get(cache_key)
        if cached is not None:
            self.stats["cache_hits"] += 1
            return cached
        
        self.stats["cache_misses"] += 1
        result = self._request("GET", f"/v1/coins/{coin_id}/charts", {
            "period": period,
            "currency": currency
        })
        
        if result and isinstance(result, list) and len(result) > 0:
            cache_manager.set(cache_key, result, 3600)  # ۱ ساعت
        
        return result
    
    def get_coin(self, coin_id: str, currency: str = "USD"):
        """دریافت اطلاعات لحظه‌ای (TTL: ۶۰ ثانیه)"""
        cache_key = f"coin_{coin_id}_{currency}"
        
        cached = cache_manager.get(cache_key)
        if cached is not None:
            self.stats["cache_hits"] += 1
            return cached
        
        self.stats["cache_misses"] += 1
        result = self._request("GET", f"/v1/coins/{coin_id}", {"currency": currency})
        
        if result and "error" not in result:
            cache_manager.set(cache_key, result, 60)
        
        return result
    
    def get_fear_greed(self, use_cache: bool = True):
        """دریافت شاخص ترس و طمع (TTL: ۵ دقیقه)"""
        cache_key = "fear_greed"
        
        if use_cache:
            cached = cache_manager.get(cache_key)
            if cached is not None:
                self.stats["cache_hits"] += 1
                return cached
        
        self.stats["cache_misses"] += 1
        result = self._request("GET", "/v1/insights/fear-and-greed")
        
        if result and "error" not in result:
            cache_manager.set(cache_key, result, 300)
        
        return result
    
    def get_btc_dominance(self, period: str = "24h", use_cache: bool = True):
        """دریافت سلطه بیت‌کوین (TTL: ۵ دقیقه)"""
        cache_key = f"btc_dom_{period}"
        
        if use_cache:
            cached = cache_manager.get(cache_key)
            if cached is not None:
                self.stats["cache_hits"] += 1
                return cached
        
        self.stats["cache_misses"] += 1
        result = self._request("GET", "/v1/insights/btc-dominance", {"type": period})
        
        if result and "error" not in result:
            cache_manager.set(cache_key, result, 300)
        
        return result
    
    def get_credits(self):
        """دریافت اعتبار باقیمانده (TTL: ۵ دقیقه)"""
        cache_key = "credits"
        
        cached = cache_manager.get(cache_key)
        if cached is not None:
            self.stats["cache_hits"] += 1
            return cached
        
        self.stats["cache_misses"] += 1
        result = self._request("GET", "/v1/usage/credits")
        
        if result and "error" not in result:
            cache_manager.set(cache_key, result, 300)
        
        return result
    
    def get_status(self):
        """بررسی سلامت API (TTL: ۳ دقیقه)"""
        cache_key = "api_status"
        
        cached = cache_manager.get(cache_key)
        if cached is not None:
            self.stats["cache_hits"] += 1
            return cached
        
        self.stats["cache_misses"] += 1
        result = self._request("GET", "/v1/status")
        
        if result and "error" not in result:
            cache_manager.set(cache_key, result, 180)
        
        return result
    
    def get_news(self, limit: int = 10):
        """دریافت اخبار (TTL: ۱۰ دقیقه)"""
        cache_key = f"news_{limit}"
        
        cached = cache_manager.get(cache_key)
        if cached is not None:
            self.stats["cache_hits"] += 1
            return cached
        
        self.stats["cache_misses"] += 1
        result = self._request("GET", "/v1/news", {"limit": limit})
        
        if result and "error" not in result:
            cache_manager.set(cache_key, result, 600)
        
        return result
    
    def get_stats(self) -> Dict[str, Any]:
        """دریافت آمار کلاینت"""
        uptime = int(time.time() - self.stats["start_time"])
        return {
            "total_requests": self.stats["total_requests"],
            "error_count": self.stats["error_count"],
            "cache_hits": self.stats["cache_hits"],
            "cache_misses": self.stats["cache_misses"],
            "hit_ratio": round(
                self.stats["cache_hits"] / max(self.stats["cache_hits"] + self.stats["cache_misses"], 1) * 100,
                2
            ),
            "uptime_seconds": uptime,
            "rate_limit_remaining": self.rate_limit_remaining,
            "cache_stats": cache_manager.get_stats()
        }


# نمونه Singleton
coinstats_client = CoinStatsClient()
