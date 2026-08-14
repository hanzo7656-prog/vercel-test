# api_handler.py
# ============================================================
# کلاینت ارتباط با API کوین‌استیتس
# شامل: همه اندپوینت‌های مورد نیاز
# ============================================================

import os
import time
import json
import requests
from datetime import datetime
from functools import lru_cache


class CoinStatsAPI:
    """
    کلاینت رسمی API کوین‌استیتس
    مدیریت: احراز هویت، Rate Limit، کش، و خطاها
    """

    def __init__(self, api_key=None):
        """
        راه‌اندازی کلاینت با کلید API
        """
        self.api_key = api_key or os.getenv(
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

    def _request(self, method, endpoint, params=None, retries=2):
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

    def _cache_get(self, key, ttl_seconds=3600):
        """دریافت از کش با اعتبارسنجی زمان"""
        if key in self.cache:
            if time.time() - self.cache_ttl.get(key, 0) < ttl_seconds:
                return self.cache[key]
        return None

    def _cache_set(self, key, value):
        """ذخیره در کش"""
        self.cache[key] = value
        self.cache_ttl[key] = time.time()

    # ============================================================
    # اندپوینت‌های اصلی (Market Data)
    # ============================================================

    def get_chart(self, coin_id, period="24h", currency="USD"):
        """
        دریافت داده‌های تاریخی قیمت
        period: 24h, 1w, 1m, 3m, 6m, 1y, all
        هزینه: ۳ اعتبار
        """
        cache_key = f"chart_{coin_id}_{period}"
        cached = self._cache_get(cache_key, 60)
        if cached:
            return cached

        endpoint = f"/v1/coins/{coin_id}/charts"
        params = {
            "period": period,
            "currency": currency
        }
        result = self._request("GET", endpoint, params)

        if result and isinstance(result, list) and len(result) > 0:
            self._cache_set(cache_key, result)

        return result

    def get_coin(self, coin_id, currency="USD"):
        """
        دریافت اطلاعات لحظه‌ای یک ارز
        هزینه: ۱ اعتبار
        """
        cache_key = f"coin_{coin_id}_{currency}"
        cached = self._cache_get(cache_key, 30)
        if cached:
            return cached

        endpoint = f"/v1/coins/{coin_id}"
        params = {"currency": currency}
        result = self._request("GET", endpoint, params)

        if result and "error" not in result:
            self._cache_set(cache_key, result)

        return result

    def get_coins_list(self, limit=20, currency="USD"):
        """
        دریافت لیست ارزها (برای داشبورد)
        هزینه: ۲ اعتبار
        """
        cache_key = f"coins_list_{limit}_{currency}"
        cached = self._cache_get(cache_key, 60)
        if cached:
            return cached

        endpoint = "/v1/coins"
        params = {
            "limit": limit,
            "currency": currency,
            "sortBy": "rank",
            "sortDir": "desc"
        }
        result = self._request("GET", endpoint, params)

        if result and "error" not in result:
            self._cache_set(cache_key, result)

        return result

    def get_global_market(self):
        """
        دریافت وضعیت کلی بازار (مارکت‌کپ، حجم، سلطه)
        هزینه: ۱ اعتبار
        """
        cache_key = "global_market"
        cached = self._cache_get(cache_key, 60)
        if cached:
            return cached

        endpoint = "/v1/markets"
        result = self._request("GET", endpoint)

        if result and "error" not in result:
            self._cache_set(cache_key, result)

        return result

    # ============================================================
    # اندپوینت‌های Insights (شاخص‌ها)
    # ============================================================

    def get_fear_greed(self, use_cache=True):
        """
        دریافت شاخص ترس و طمع
        هزینه: ۱۰ اعتبار
        کش: ۱ ساعته
        """
        if use_cache:
            cached = self._cache_get("fear_greed", 3600)
            if cached:
                return cached

        endpoint = "/v1/insights/fear-and-greed"
        result = self._request("GET", endpoint)

        if result and "error" not in result:
            self._cache_set("fear_greed", result)

        return result

    def get_btc_dominance(self, period="24h", use_cache=True):
        """
        دریافت سلطه بیت‌کوین در بازار
        period: 24h, 1w, 1m, 3m, 6m, 1y, all
        هزینه: ۱۰ اعتبار
        کش: ۱ ساعته
        """
        cache_key = f"btc_dom_{period}"

        if use_cache:
            cached = self._cache_get(cache_key, 3600)
            if cached:
                return cached

        endpoint = "/v1/insights/btc-dominance"
        params = {"type": period}
        result = self._request("GET", endpoint, params)

        if result and "error" not in result:
            self._cache_set(cache_key, result)

        return result

    # ============================================================
    # اندپوینت‌های News
    # ============================================================

    def get_news(self, limit=10):
        """
        دریافت اخبار
        هزینه: نامشخص
        """
        cache_key = f"news_{limit}"
        cached = self._cache_get(cache_key, 300)
        if cached:
            return cached

        endpoint = "/v1/news"
        params = {"limit": limit}
        result = self._request("GET", endpoint, params)

        if result and "error" not in result:
            self._cache_set(cache_key, result)

        return result

    # ============================================================
    # اندپوینت‌های مدیریتی
    # ============================================================

    def get_credits(self):
        """
        دریافت اعتبار باقیمانده
        هزینه: رایگان
        """
        endpoint = "/v1/usage/credits"
        return self._request("GET", endpoint)

    def get_status(self):
        """
        بررسی سلامت API
        هزینه: رایگان
        """
        endpoint = "/v1/status"
        return self._request("GET", endpoint)

    def get_stats(self):
        """
        دریافت آمار درخواست‌ها
        """
        return {
            "total_requests": self.request_count,
            "errors": self.error_count,
            "cache_size": len(self.cache),
            "cache_keys": list(self.cache.keys())
        }
