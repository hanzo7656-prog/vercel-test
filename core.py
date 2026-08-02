"""
هسته مرکزی سیستم (Core Orchestrator)
هماهنگی بین ماژول‌ها و مدیریت خط لوله
"""

import time
import json
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime

# وارد کردن ماژول‌های دیگر
from coinstats_api import CoinStatsAPI
from mother_health import MotherHealth

# تنظیم لاگر
logger = logging.getLogger("CoreOrchestrator")

class CoreOrchestrator:
    """
    هسته مرکزی سیستم
    وظایف:
    1. بارگذاری تنظیمات
    2. برقراری ارتباط با MotherHealth
    3. دریافت داده از CoinStats API
    4. مدیریت خطاها و Retry
    5. ذخیره‌سازی نتایج (placeholder برای آینده)
    """
    
    def __init__(self, api_key: str, config: Optional[Dict] = None):
        self.api_key = api_key
        self.config = config or {}
        
        # تنظیمات پیش‌فرض
        self.default_config = {
            "assets": ["bitcoin", "ethereum", "solana", "binancecoin", "ripple"],
            "period": "24h",
            "max_assets": 10,
            "min_assets": 3,
            "health_check_enabled": True,
            "health_check_url": "http://localhost:5000/api/health",
            "output_dir": "outputs",
            "save_csv": True,
            "log_level": "INFO"
        }
        
        # ادغام تنظیمات
        for key, value in self.default_config.items():
            if key not in self.config:
                self.config[key] = value
        
        # نمونه‌های ماژول‌ها
        self.api = CoinStatsAPI(api_key)
        self.health: Optional[MotherHealth] = None
        
        # وضعیت
        self.running = False
        self.last_run = None
        self.run_count = 0
        
        # لاگ‌ها
        self.logs = []
        self.max_logs = 200
        
        logger.info("🚀 Core Orchestrator راه‌اندازی شد")
        self._add_log("INFO", "🚀 Core Orchestrator راه‌اندازی شد")
    
    def _add_log(self, level: str, message: str):
        """افزودن لاگ به حافظه"""
        self.logs.append({
            "timestamp": datetime.utcnow().isoformat(),
            "level": level,
            "message": message
        })
        if len(self.logs) > self.max_logs:
            self.logs.pop(0)
        # چاپ در کنسول
        log_func = getattr(logger, level.lower(), logger.info)
        log_func(message)
    
    def check_health(self) -> Dict[str, Any]:
        """
        بررسی سلامت سیستم از طریق MotherHealth
        """
        if not self.config.get("health_check_enabled", True):
            return {"status": "healthy", "message": "Health check disabled"}
        
        try:
            import requests
            response = requests.get(
                self.config["health_check_url"],
                timeout=5
            )
            if response.status_code == 200:
                data = response.json()
                status = data.get("status", "healthy")
                self._add_log("INFO", f"✅ سلامت: {status}")
                return data
            else:
                self._add_log("WARNING", f"⚠️ Health check ناموفق: HTTP {response.status_code}")
                return {"status": "degraded", "message": f"HTTP {response.status_code}"}
        
        except requests.exceptions.ConnectionError:
            self._add_log("WARNING", "⚠️ MotherHealth در دسترس نیست (اجرا نمی‌شود یا پورت بسته است)")
            return {"status": "healthy", "message": "MotherHealth not available"}
        except Exception as e:
            self._add_log("ERROR", f"❌ خطا در health check: {str(e)}")
            return {"status": "degraded", "message": str(e)}
    
    def analyze(self, assets: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        اجرای تحلیل (مرحله‌ی اصلی)
        """
        self._add_log("INFO", "📊 شروع تحلیل...")
        self.running = True
        self.run_count += 1
        start_time = time.time()
        
        result = {
            "status": "pending",
            "run_id": self.run_count,
            "timestamp": datetime.utcnow().isoformat(),
            "assets_analyzed": 0,
            "data_points": 0,
            "error": None,
            "duration": 0
        }
        
        try:
            # ۱. بررسی سلامت
            if self.config.get("health_check_enabled", True):
                health_status = self.check_health()
                if health_status.get("status") == "critical":
                    self._add_log("CRITICAL", "🔴 وضعیت بحرانی! تحلیل متوقف شد.")
                    result["status"] = "aborted"
                    result["error"] = "Critical health status"
                    self.running = False
                    return result
            
            # ۲. تعیین لیست ارزها
            coin_list = assets or self.config.get("assets", self.default_config["assets"])
            # محدود کردن تعداد
            max_assets = self.config.get("max_assets", 10)
            coin_list = coin_list[:max_assets]
            result["assets_analyzed"] = len(coin_list)
            
            self._add_log("INFO", f"📡 دریافت داده برای {len(coin_list)} ارز...")
            
            # ۳. دریافت داده از API
            period = self.config.get("period", "24h")
            raw_data = self.api.get_coins_charts(coin_list, period=period)
            
            if "error" in raw_data:
                self._add_log("ERROR", f"❌ خطا در دریافت داده: {raw_data['error']}")
                result["status"] = "failed"
                result["error"] = raw_data['error']
                self.running = False
                return result
            
            # ۴. پردازش داده‌ها (placeholder برای تحلیل‌گر)
            parsed = self.api.parse_chart_data(raw_data)
            total_points = sum(len(prices) for prices in parsed.values())
            result["data_points"] = total_points
            
            self._add_log("INFO", f"✅ داده‌های {len(parsed)} ارز دریافت شد ({total_points} نقطه)")
            
            # ۵. ذخیره‌سازی نتایج (placeholder)
            if self.config.get("save_csv", True):
                import os
                os.makedirs(self.config.get("output_dir", "outputs"), exist_ok=True)
                filename = f"{self.config.get('output_dir', 'outputs')}/analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                with open(filename, 'w') as f:
                    json.dump({
                        "run_id": self.run_count,
                        "timestamp": result["timestamp"],
                        "assets": list(parsed.keys()),
                        "data_points": total_points,
                        "raw": raw_data
                    }, f, indent=2)
                self._add_log("INFO", f"💾 نتایج در {filename} ذخیره شد")
            
            result["status"] = "success"
            result["duration"] = round(time.time() - start_time, 2)
            self._add_log("SUCCESS", f"✅ تحلیل کامل شد! زمان: {result['duration']} ثانیه")
            
        except Exception as e:
            self._add_log("ERROR", f"❌ خطای ناگهانی: {str(e)}")
            result["status"] = "failed"
            result["error"] = str(e)
        
        self.running = False
        self.last_run = datetime.utcnow().isoformat()
        return result
    
    def run(self):
        """حالت تعاملی (منتظر فرمان)"""
        self._add_log("INFO", "⏳ هسته آماده است. منتظر فرمان...")
        print("\n" + "=" * 50)
        print("🔄 Core Orchestrator در حال اجرا")
        print("=" * 50)
        print("دستورات:")
        print("  start        - شروع تحلیل")
        print("  status       - نمایش وضعیت")
        print("  config       - نمایش تنظیمات")
        print("  exit         - خروج")
        print("=" * 50)
        
        while True:
            try:
                cmd = input("\n> ").strip().lower()
                
                if cmd == "start":
                    result = self.analyze()
                    print(f"\n📊 نتیجه: {result['status']} (زمان: {result.get('duration', 0)}s)")
                    if result.get('error'):
                        print(f"❌ خطا: {result['error']}")
                
                elif cmd == "status":
                    print(f"\n📊 وضعیت:")
                    print(f"  اجرا: {'در حال اجرا' if self.running else 'متوقف'}")
                    print(f"  تعداد اجراها: {self.run_count}")
                    print(f"  آخرین اجرا: {self.last_run or 'ندارد'}")
                    print(f"  لاگ‌ها: {len(self.logs)}")
                    
                    # اگر مادر اجرا می‌شود، وضعیت آن را هم بگیر
                    health = self.check_health()
                    print(f"  سلامت: {health.get('status', 'نامشخص')}")
                
                elif cmd == "config":
                    print("\n⚙️ تنظیمات:")
                    for key, value in self.config.items():
                        print(f"  {key}: {value}")
                
                elif cmd == "exit":
                    self._add_log("INFO", "🛑 خروج از هسته")
                    print("🛑 در حال خروج...")
                    break
                
                elif cmd == "help":
                    print("\nدستورات: start, status, config, exit")
                
                else:
                    print(f"⚠️ دستور '{cmd}' شناخته نشد. 'help' برای راهنما.")
            
            except KeyboardInterrupt:
                print("\n🛑 خروج با Ctrl+C...")
                break
            except Exception as e:
                print(f"❌ خطا: {str(e)}")


# ==================== استفاده‌ی آسان برای تست ====================

if __name__ == "__main__":
    import sys
    import logging
    
    # تنظیم لاگینگ
    logging.basicConfig(
        level=logging.INFO,
        format='[%(asctime)s] %(levelname)s: %(message)s'
    )
    
    API_KEY = "40QRC4gdyzWIGwsvGkqWtcDOf0bk+FV217KmLxQ/Wmw="
    
    # تنظیمات
    config = {
        "assets": ["bitcoin", "ethereum", "solana", "binancecoin", "ripple"],
        "period": "24h",
        "max_assets": 5,
        "save_csv": True,
        "health_check_enabled": True,
        "health_check_url": "http://localhost:5000/api/health"
    }
    
    # ایجاد نمونه
    core = CoreOrchestrator(API_KEY, config)
    
    # اجرا
    core.run()
