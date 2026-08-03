"""
ماژول ارتباط با CoinStats API
مدیریت درخواست‌ها، خطاها، Retry و دریافت داده
"""

import requests
import time
import logging
from typing import Optional, Dict, List, Any

# تنظیم لاگر
logger = logging.getLogger("CoinStatsAPI")

class CoinStatsAPI:
    """
    کلاس اصلی برای ارتباط با CoinStats API
    """
    
    def __init__(self, api_key: str, base_url: str = "https://api.coinstats.app/v1"):
        self.api_key = api_key
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({
            "X-API-KEY": self.api_key,
            "Content-Type": "application/json",
            "Accept": "application/json"
        })
        self.max_retries = 3
        self.retry_delays = [1, 2, 4]  # Backoff نمایی
        self._last_latency = 0
    
    def _request(self, method: str, endpoint: str, params: Optional[Dict] = None) -> Dict:
        """
        ارسال درخواست با مدیریت Retry و خطا
        """
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        
        for attempt in range(self.max_retries):
            try:
                start_time = time.time()
                response = self.session.request(
                    method=method,
                    url=url,
                    params=params,
                    timeout=10
                )
                latency = round((time.time() - start_time) * 1000, 1)  # میلی‌ثانیه
                self._last_latency = latency
                
                if response.status_code == 200:
                    result = response.json()
                    result["_latency"] = latency
                    return result
                
                # خطاهای قابل بازیابی
                if response.status_code in (401, 429, 503):
                    logger.warning(f"خطای {response.status_code} در تلاش {attempt+1}: {response.text[:100]}")
                    if attempt < self.max_retries - 1:
                        time.sleep(self.retry_delays[attempt])
                        continue
                
                # سایر خطاها
                return {
                    "error": f"HTTP {response.status_code}",
                    "detail": response.text[:200],
                    "_latency": latency
                }
            
            except requests.exceptions.Timeout:
                logger.warning(f"Timeout در تلاش {attempt+1}")
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delays[attempt])
                    continue
                return {"error": "Timeout", "detail": "درخواست زمان‌بر بود", "_latency": 0}
            
            except requests.exceptions.ConnectionError:
                logger.warning(f"خطای اتصال در تلاش {attempt+1}")
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delays[attempt])
                    continue
                return {"error": "ConnectionError", "detail": "اتصال به سرور برقرار نشد", "_latency": 0}
            
            except Exception as e:
                logger.error(f"خطای ناشناخته: {str(e)}")
                return {"error": "UnknownError", "detail": str(e), "_latency": 0}
        
        return {"error": "MaxRetriesExceeded", "detail": "همه‌ی تلاش‌ها ناموفق بود", "_latency": 0}
    
    # ==================== اندپوینت‌های ضروری ====================
    
    def get_status(self) -> Dict:
        """بررسی وضعیت API (بدون مصرف اعتبار)"""
        return self._request("GET", "/status")
    
    def get_credits(self) -> Dict:
        """دریافت میزان اعتبار باقی‌مانده"""
        return self._request("GET", "/usage/credits")
    
    def get_coins(self, limit: int = 10, currency: str = "USD") -> Dict:
        """دریافت لیست ارزها با اطلاعات لحظه‌ای (۲ اعتبار)"""
        params = {
            "limit": limit,
            "currency": currency,
            "sortBy": "marketCap",
            "sortDir": "desc"
        }
        return self._request("GET", "/coins", params=params)
    
    def get_coins_charts(self, coin_ids: List[str], period: str = "24h", currency: str = "USD") -> Dict:
        """دریافت داده‌های نمودار برای چندین ارز (۳ اعتبار × تعداد ارزها)"""
        params = {
            "coinIds": ",".join(coin_ids[:10]),  # حداکثر ۱۰ ارز
            "period": period,
            "currency": currency
        }
        return self._request("GET", "/coins/charts", params=params)
    
    # ==================== توابع کمکی (Helper) ====================
    
    def is_api_healthy(self) -> bool:
        """بررسی ساده‌ی سلامت API"""
        result = self.get_status()
        return result.get("status") == "ok"
    
    def get_credits_remaining(self) -> int:
        """دریافت عدد اعتبار باقی‌مانده"""
        result = self.get_credits()
        return result.get("remainingCredits", 0)
    
    def get_credits_info(self) -> Dict:
        """دریافت اطلاعات کامل اعتبار"""
        result = self.get_credits()
        return {
            "remaining": result.get("remainingCredits", 0),
            "total": result.get("totalCredits", 10000),
            "percent": round((result.get("remainingCredits", 0) / max(1, result.get("totalCredits", 10000))) * 100, 1)
        }
    
    def get_api_latency(self) -> float:
        """دریافت آخرین تأخیر API"""
        return self._last_latency
    
    def parse_chart_data(self, raw_data: Dict) -> Dict[str, List[float]]:
        """تبدیل داده‌ی خام نمودار به ساختار قابل‌استفاده"""
        result = {}
        if "error" in raw_data:
            return result
        
        # اگر داده‌ها به‌صورت لیست برگشتند
        if isinstance(raw_data, list):
            for item in raw_data:
                coin_id = item.get("coinId", "unknown")
                chart = item.get("chart", [])
                prices = [row[1] for row in chart if len(row) > 1]
                result[coin_id] = prices
        else:
            # یا به‌صورت دیکشنری
            for coin_id, chart in raw_data.items():
                if isinstance(chart, list) and len(chart) > 0 and isinstance(chart[0], list):
                    prices = [row[1] for row in chart if len(row) > 1]
                    result[coin_id] = prices
        
        return result


# ==================== تست سریع ====================
if __name__ == "__main__":
    import os
    API_KEY = os.environ.get("API_KEY", "40QRC4gdyzWIGwsvGkqWtcDOf0bk+FV217KmLxQ/Wmw=")
    
    api = CoinStatsAPI(API_KEY)
    
    print("🧪 تست CoinStats API")
    print("-" * 40)
    
    # ۱. تست وضعیت
    status = api.get_status()
    print(f"✅ وضعیت API: {status.get('status', 'نامشخص')}")
    print(f"   تأخیر: {status.get('_latency', 0)} ms")
    
    # ۲. تست اعتبار
    credits = api.get_credits()
    print(f"💳 اعتبار باقی‌مانده: {credits.get('remainingCredits', 0)}")
    
    # ۳. تست لیست ارزها
    coins = api.get_coins(limit=5)
    if "error" not in coins:
        print(f"📊 تعداد ارزها: {len(coins.get('result', []))}")
        for coin in coins.get('result', [])[:3]:
            print(f"   {coin.get('name')} (${coin.get('price', 0):,.2f})")
