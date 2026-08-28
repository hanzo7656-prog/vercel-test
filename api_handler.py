# api_handler.py
# ============================================================
# کلاینت ارتباط با API کوین‌استیتس - نسخه ۲.۰ (با TTL افزایش یافته)
# ============================================================

import os
import time
import json
import requests
import logging
from datetime import datetime
from functools import lru_cache
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)


class CoinStatsAPI:
    """
    کلاینت رسمی API کوین‌استیتس
    مدیریت: احراز هویت، Rate Limit، کش، و خطاها
    """
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("COINSTATS_API_KEY")
        if not self.api_key:
            logger.warning("⚠️ COINSTATS_API_KEY not set in environment!")
            self.api_key = os.getenv(
                "COINSTATS_API_KEY",
                "40QRC4gdyzWIGwsvGkqWtcDOf0bk+FV217KmLxQ/Wmw="
            )
        
        self.base_url = "https://api.coinstats.app"
        self.session = requests.Session()
        self.session.headers.update({
            "X-API-KEY": self.api_key,
            "Content-Type": "application/json",
            "Accept": "application/json"
        })

        # کش ساده در حافظه با TTL
        self.cache = {}
        self.cache_ttl = {}

        # آمار درخواست‌ها
        self.request_count = 0
        self.error_count = 0
        self._start_time = time.time()
        
        # ثبت آمار در Scheduler
        self._register_with_scheduler()

    def _register_with_scheduler(self):
        try:
            from core.metrics import metrics_scheduler
            logger.info("✅ API stats registered with Metrics Scheduler")
        except ImportError:
            pass
        except Exception as e:
            logger.debug(f"Could not register with scheduler: {e}")

    def _request(self, method: str, endpoint: str, params: Optional[Dict] = None, retries: int = 2):
        """ارسال درخواست به API با مدیریت خطا و Retry"""
        url = f"{self.base_url}{endpoint}"
        self.request_count += 1

        try:
            response = self.session.request(
                method,
                url,
                params=params,
                timeout=15
            )

            if response.status_code == 429:
                self.error_count += 1
                if retries > 0:
                    wait_time = (3 - retries) * 2 + 1
                    print(f"⏳ Rate Limit! صبر {wait_time} ثانیه...")
                    time.sleep(wait_time)
                    return self._request(method, endpoint, params, retries - 1)
                else:
                    return {
                        "error": "Rate Limit exceeded",
                        "message": "تعداد درخواست‌ها بیش از حد مجاز است"
                    }

            response.raise_for_status()
            return response.json()

        except requests.exceptions.Timeout:
            self.error_count += 1
            if retries > 0:
                print("⏳ Timeout! تلاش مجدد...")
                time.sleep(1)
                return self._request(method, endpoint, params, retries - 1)
            return {"error": "Timeout", "message": "زمان درخواست به پایان رسید"}

        except requests.exceptions.RequestException as e:
            self.error_count += 1
            return {
                "error": "RequestFailed",
                "message": str(e),
                "status_code": getattr(response, 'status_code', None)
            }

    def _cache_get(self, key: str, ttl_seconds: int = 3600):
        if key in self.cache:
            if time.time() - self.cache_ttl.get(key, 0) < ttl_seconds:
                return self.cache[key]
        return None

    def _cache_set(self, key: str, value: Any):
        self.cache[key] = value
        self.cache_ttl[key] = time.time()

    def _clear_cache(self):
        self.cache = {}
        self.cache_ttl = {}
        logger.info("✅ API cache cleared")

    # ============================================================
    # اندپوینت‌های اصلی (با TTL افزایش یافته)
    # ============================================================

    def get_chart(self, coin_id: str, period: str = "24h", currency: str = "USD"):
        """دریافت داده‌های تاریخی قیمت (TTL: ۱ ساعت)"""
        cache_key = f"chart_{coin_id}_{period}"
        cached = self._cache_get(cache_key, 3600)  # ✅ ۱ ساعت
        if cached:
            return cached

        endpoint = f"/v1/coins/{coin_id}/charts"
        params = {"period": period, "currency": currency}
        result = self._request("GET", endpoint, params)

        if result and isinstance(result, list) and len(result) > 0:
            self._cache_set(cache_key, result)

        return result

    def get_coin(self, coin_id: str, currency: str = "USD"):
        """دریافت اطلاعات لحظه‌ای یک ارز (TTL: ۶۰ ثانیه)"""
        cache_key = f"coin_{coin_id}_{currency}"
        cached = self._cache_get(cache_key, 60)  # ✅ ۶۰ ثانیه
        if cached:
            return cached

        endpoint = f"/v1/coins/{coin_id}"
        params = {"currency": currency}
        result = self._request("GET", endpoint, params)

        if result and "error" not in result:
            self._cache_set(cache_key, result)

        return result

    def get_global_market(self):
        """دریافت وضعیت کلی بازار (TTL: ۶۰ ثانیه)"""
        cache_key = "global_market"
        cached = self._cache_get(cache_key, 60)
        if cached:
            return cached

        endpoint = "/v1/markets"
        result = self._request("GET", endpoint)

        if result and "error" not in result:
            self._cache_set(cache_key, result)

        return result

    def get_fear_greed(self, use_cache: bool = True):
        """دریافت شاخص ترس و طمع (TTL: ۵ دقیقه)"""
        if use_cache:
            cached = self._cache_get("fear_greed", 300)  # ✅ ۵ دقیقه
            if cached:
                return cached

        endpoint = "/v1/insights/fear-and-greed"
        result = self._request("GET", endpoint)

        if result and "error" not in result:
            self._cache_set("fear_greed", result)

        return result

    def get_btc_dominance(self, period: str = "24h", use_cache: bool = True):
        """دریافت سلطه بیت‌کوین (TTL: ۵ دقیقه)"""
        cache_key = f"btc_dom_{period}"

        if use_cache:
            cached = self._cache_get(cache_key, 300)  # ✅ ۵ دقیقه
            if cached:
                return cached

        endpoint = "/v1/insights/btc-dominance"
        params = {"type": period}
        result = self._request("GET", endpoint, params)

        if result and "error" not in result:
            self._cache_set(cache_key, result)

        return result

    def get_news(self, limit: int = 10):
        """دریافت اخبار (TTL: ۱۰ دقیقه)"""
        cache_key = f"news_{limit}"
        cached = self._cache_get(cache_key, 600)  # ✅ ۱۰ دقیقه
        if cached:
            return cached

        endpoint = "/v1/news"
        params = {"limit": limit}
        result = self._request("GET", endpoint, params)

        if result and "error" not in result:
            self._cache_set(cache_key, result)

        return result

    def get_credits(self):
        """دریافت اعتبار باقیمانده (TTL: ۵ دقیقه)"""
        cache_key = "credits"
        cached = self._cache_get(cache_key, 300)  # ✅ ۵ دقیقه
        if cached:
            return cached

        endpoint = "/v1/usage/credits"
        result = self._request("GET", endpoint)

        if result and "error" not in result:
            self._cache_set(cache_key, result)

        return result

    def get_status(self):
        """بررسی سلامت API (TTL: ۳ دقیقه)"""
        cache_key = "status"
        cached = self._cache_get(cache_key, 180)  # ✅ ۳ دقیقه
        if cached:
            return cached

        endpoint = "/v1/status"
        result = self._request("GET", endpoint)

        if result and "error" not in result:
            self._cache_set(cache_key, result)

        return result

    def get_stats(self) -> Dict[str, Any]:
        return {
            "total_requests": self.request_count,
            "errors": self.error_count,
            "cache_size": len(self.cache),
            "cache_keys": list(self.cache.keys())[:10],
            "uptime_seconds": int(time.time() - self._start_time),
            "error_rate": round((self.error_count / max(self.request_count, 1)) * 100, 2),
            "timestamp": datetime.now().isoformat()
        }
