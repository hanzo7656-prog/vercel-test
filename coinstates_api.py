"""
ماژول ارتباط با CoinStats API
مدیریت درخواست‌ها، خطاها، Retry و دریافت داده
"""

import requests
import time
import logging
from typing import Optional, Dict, List, Any

# تنظیم لاگر اختصاصی برای این ماژول
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
    
    def _request(self, method: str, endpoint: str, params: Optional[Dict] = None) -> Dict:
        """
        ارسال درخواست با مدیریت Retry و خطا
        """
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        
        for attempt in range(self.max_retries):
            try:
                response = self.session.request(
                    method=method,
                    url=url,
                    params=params,
                    timeout=10
                )
                
                # اگر درخواست موفق بود
                if response.status_code == 200:
                    return response.json()
                
                # اگر خطای اعتبار بود (401) یا محدودیت نرخ (429)
                if response.status_code in (401, 429):
                    logger.warning(f"خطای {response.status_code} در تلاش {attempt+1}: {response.text}")
                    if attempt < self.max_retries - 1:
                        time.sleep(self.retry_delays[attempt])
                        continue
                    else:
                        return {"error": f"HTTP {response.status_code}", "detail": response.text}
                
                # سایر خطاها
                return {"error": f"HTTP {response.status_code}", "detail": response.text}
            
            except requests.exceptions.Timeout:
                logger.warning(f"Timeout در تلاش {attempt+1}")
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delays[attempt])
                    continue
                return {"error": "Timeout", "detail": "درخواست به دلیل زمان‌بری ناموفق بود"}
            
            except requests.exceptions.ConnectionError:
                logger.warning(f"خطای اتصال در تلاش {attempt+1}")
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delays[attempt])
                    continue
                return {"error": "ConnectionError", "detail": "اتصال به سرور برقرار نشد"}
            
            except Exception as e:
                logger.error(f"خطای ناشناخته: {str(e)}")
                return {"error": "UnknownError", "detail": str(e)}
        
        return {"error": "MaxRetriesExceeded", "detail": "همه‌ی تلاش‌ها ناموفق بود"}
    
    # ==================== اندپوینت‌های ضروری ====================
    
    def get_status(self) -> Dict:
        """بررسی وضعیت API (بدون مصرف اعتبار)"""
        return self._request("GET", "/status")
    
    def get_credits(self) -> Dict:
        """دریافت میزان اعتبار باقی‌مانده"""
        return self._request("GET", "/usage/credits")
    
    def get_coins_charts(self, coin_ids: List[str], period: str = "24h", currency: str = "USD") -> Dict:
        """
        دریافت داده‌های نمودار برای چندین ارز به‌صورت همزمان
        هزینه: ۳ اعتبار به‌ازای هر درخواست (تقسیم بر تعداد ارزها)
        """
        params = {
            "coinIds": ",".join(coin_ids),
            "period": period,
            "currency": currency
        }
        return self._request("GET", "/coins/charts", params=params)
    
    def get_coins(self, 
                  limit: int = 10, 
                  currency: str = "USD", 
                  sort_by: str = "marketCap",
                  sort_dir: str = "desc") -> Dict:
        """
        دریافت لیست ارزها با اطلاعات لحظه‌ای
        هزینه: ۲ اعتبار
        """
        params = {
            "limit": limit,
            "currency": currency,
            "sortBy": sort_by,
            "sortDir": sort_dir,
            "page": 1
        }
        return self._request("GET", "/coins", params=params)

    # ==================== تسهیل‌گرها (Helper Methods) ====================
    
    def is_api_healthy(self) -> bool:
        """بررسی ساده‌ی سلامت API"""
        result = self.get_status()
        return result.get("status") == "ok"
    
    def get_credits_remaining(self) -> int:
        """دریافت عدد اعتبار باقی‌مانده (در صورت خطا، ۰ برمی‌گرداند)"""
        result = self.get_credits()
        return result.get("remainingCredits", 0)
    
    def parse_chart_data(self, raw_data: Dict) -> Dict[str, List[float]]:
        """
        تبدیل داده‌ی خام نمودار به ساختار قابل‌استفاده
        ورودی: خروجی get_coins_charts
        خروجی: دیکشنری {coin_id: [price_list]}
        """
        result = {}
        if "error" in raw_data:
            return result
        
        # اگر داده‌ها به‌صورت لیست برگشتند
        if isinstance(raw_data, list):
            for item in raw_data:
                coin_id = item.get("coinId", "unknown")
                chart = item.get("chart", [])
                # استخراج قیمت‌ها (ستون دوم: USD)
                prices = [row[1] for row in chart if len(row) > 1]
                result[coin_id] = prices
        else:
            # یا به‌صورت دیکشنری
            for coin_id, chart in raw_data.items():
                if isinstance(chart, list):
                    prices = [row[1] for row in chart if len(row) > 1]
                    result[coin_id] = prices
        
        return result


# ==================== استفاده‌ی آسان (برای تست سریع) ====================

if __name__ == "__main__":
    # تست ماژول با کلید واقعی
    import os
    API_KEY = "40QRC4gdyzWIGwsvGkqWtcDOf0bk+FV217KmLxQ/Wmw="
    
    api = CoinStatsAPI(API_KEY)
    
    print("🧪 تست CoinStats API")
    print("-" * 40)
    
    # ۱. تست وضعیت
    status = api.get_status()
    print(f"✅ وضعیت API: {status.get('status', 'نامشخص')}")
    
    # ۲. تست اعتبار
    credits = api.get_credits()
    print(f"💳 اعتبار باقی‌مانده: {credits.get('remainingCredits', 0)}")
    
    # ۳. تست دریافت نمودار (فقط ۳ ارز برای کاهش مصرف اعتبار)
    if api.is_api_healthy():
        print("📊 دریافت داده‌های نمودار برای ۳ ارز...")
        charts = api.get_coins_charts(["bitcoin", "ethereum", "solana"])
        parsed = api.parse_chart_data(charts)
        for coin, prices in parsed.items():
            print(f"   {coin}: {len(prices)} نقطه‌ی داده")
    else:
        print("❌ API در دسترس نیست")
