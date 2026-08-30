#!/usr/bin/env python3
# test_api.py
# ============================================================
# تست کامل API سیستم - بدون نیاز به فرانت‌اند
# ============================================================

import requests
import json
import sys
from datetime import datetime
from typing import Dict, Any

# ============================================================
# تنظیمات
# ============================================================

BASE_URL = "https://vercel-test-f4bv.onrender.com"  # یا آدرس محلی شما
# BASE_URL = "http://localhost:5000"  # برای تست محلی

TIMEOUT = 15
COLORS = {
    "GREEN": "\033[92m",
    "RED": "\033[91m",
    "YELLOW": "\033[93m",
    "BLUE": "\033[94m",
    "PURPLE": "\033[95m",
    "CYAN": "\033[96m",
    "RESET": "\033[0m"
}


def print_header(text: str):
    print(f"\n{COLORS['CYAN']}{'='*80}{COLORS['RESET']}")
    print(f"{COLORS['CYAN']}🚀 {text}{COLORS['RESET']}")
    print(f"{COLORS['CYAN']}{'='*80}{COLORS['RESET']}")


def print_subheader(text: str):
    print(f"\n{COLORS['PURPLE']}📌 {text}{COLORS['RESET']}")
    print(f"{COLORS['PURPLE']}{'-'*40}{COLORS['RESET']}")


def print_success(text: str):
    print(f"{COLORS['GREEN']}  ✅ {text}{COLORS['RESET']}")


def print_error(text: str):
    print(f"{COLORS['RED']}  ❌ {text}{COLORS['RESET']}")


def print_warning(text: str):
    print(f"{COLORS['YELLOW']}  ⚠️ {text}{COLORS['RESET']}")


def print_info(text: str):
    print(f"{COLORS['BLUE']}  ℹ️ {text}{COLORS['RESET']}")


def print_json(data: Dict, max_depth: int = 2):
    print(f"{COLORS['CYAN']}{json.dumps(data, indent=2, ensure_ascii=False)[:1000]}{COLORS['RESET']}")
    if len(json.dumps(data, indent=2)) > 1000:
        print(f"{COLORS['YELLOW']}  ... (ادامه در فایل خروجی){COLORS['RESET']}")


def test_endpoint(name: str, url: str, method: str = "GET", payload: Dict = None) -> Dict:
    """تست یک اندپوینت"""
    print(f"\n  🔄 {name}")
    print(f"     📡 {method} {url}")
    
    try:
        if method.upper() == "GET":
            response = requests.get(url, timeout=TIMEOUT)
        elif method.upper() == "POST":
            response = requests.post(url, json=payload, timeout=TIMEOUT)
        else:
            return {"success": False, "error": f"Method {method} not supported"}
        
        if response.status_code == 200:
            data = response.json()
            print_success(f"Status: {response.status_code}")
            return {"success": True, "status": response.status_code, "data": data}
        else:
            print_error(f"Status: {response.status_code}")
            try:
                data = response.json()
                print_info(f"Error: {data.get('error', 'Unknown')}")
                return {"success": False, "status": response.status_code, "data": data}
            except:
                print_error(f"Response: {response.text[:200]}")
                return {"success": False, "status": response.status_code}
    except requests.exceptions.Timeout:
        print_error("Timeout")
        return {"success": False, "error": "Timeout"}
    except requests.exceptions.ConnectionError:
        print_error("Connection Error")
        return {"success": False, "error": "Connection Error"}
    except Exception as e:
        print_error(f"Error: {e}")
        return {"success": False, "error": str(e)}


def run_tests():
    """اجرای همه تست‌ها"""
    results = {
        "total": 0,
        "success": 0,
        "failed": 0,
        "errors": []
    }

    print_header("تست کامل سیستم - JSON API")
    print(f"📡 سرور: {BASE_URL}")
    print(f"⏱️ زمان: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"🔧 تایم‌اوت: {TIMEOUT}s")

    # ============================================================
    # ۱. سلامت سیستم
    # ============================================================
    print_subheader("۱️⃣ سلامت سیستم")
    results["total"] += 1
    r = test_endpoint("Health Check", f"{BASE_URL}/api/health")
    if r.get("success"):
        results["success"] += 1
        data = r.get("data", {})
        print_info(f"Status: {data.get('status', 'unknown')}")
        if data.get("components"):
            for name, info in data["components"].items():
                status = info.get("status", "unknown")
                icon = "✅" if status == "healthy" else "⚠️" if status == "degraded" else "❌"
                print(f"    {icon} {name}: {status}")
    else:
        results["failed"] += 1
        results["errors"].append({"endpoint": "health", "error": r.get("error")})

    # ============================================================
    # ۲. متریک‌ها
    # ============================================================
    print_subheader("۲️⃣ متریک‌های سیستم")
    results["total"] += 1
    r = test_endpoint("Metrics", f"{BASE_URL}/api/metrics")
    if r.get("success"):
        results["success"] += 1
        data = r.get("data", {})
        if data.get("success"):
            metrics = data.get("data", {}).get("metrics", {})
            print_info(f"💻 CPU: {metrics.get('cpu', {}).get('value', 0)}%")
            print_info(f"💾 RAM: {metrics.get('ram', {}).get('value', 0)}%")
            print_info(f"⏱️ آپتایم: {metrics.get('uptime', {}).get('value', '0s')}")
            print_info(f"💰 اعتبار: {metrics.get('api_credits', {}).get('value', 0)}")
            print_info(f"🔌 API: {metrics.get('api_status', {}).get('value', 'unknown')}")
            
            btc = metrics.get('btc_price', {})
            if btc:
                print_info(f"₿ BTC: ${btc.get('value', 0):,.2f} (تغییر: {btc.get('change_24h', 0):.2f}%)")
            eth = metrics.get('eth_price', {})
            if eth:
                print_info(f"⟠ ETH: ${eth.get('value', 0):,.2f} (تغییر: {eth.get('change_24h', 0):.2f}%)")
            
            fg = metrics.get('fear_greed', {})
            if fg:
                print_info(f"😨 ترس و طمع: {fg.get('value', 50)} ({fg.get('classification', 'Neutral')})")
            
            dom = metrics.get('btc_dominance', {})
            if dom:
                print_info(f"📊 سلطه BTC: {dom.get('value', 0)}%")
        else:
            print_error("Metrics data not available")
    else:
        results["failed"] += 1
        results["errors"].append({"endpoint": "metrics", "error": r.get("error")})

    # ============================================================
    # ۳. قیمت‌های CoinStats
    # ============================================================
    print_subheader("۳️⃣ قیمت‌های لحظه‌ای")
    results["total"] += 1
    r = test_endpoint("Prices", f"{BASE_URL}/api/coinstats/prices")
    if r.get("success"):
        results["success"] += 1
        data = r.get("data", {})
        if data.get("success"):
            prices = data.get("data", {})
            btc = prices.get("btc", {})
            eth = prices.get("eth", {})
            if btc:
                print_info(f"₿ BTC: ${btc.get('price', 0):,.2f} (تغییر: {btc.get('change_24h', 0):.2f}%)")
            if eth:
                print_info(f"⟠ ETH: ${eth.get('price', 0):,.2f} (تغییر: {eth.get('change_24h', 0):.2f}%)")
        else:
            print_error("Prices data not available")
    else:
        results["failed"] += 1
        results["errors"].append({"endpoint": "prices", "error": r.get("error")})

    # ============================================================
    # ۴. ترس و طمع
    # ============================================================
    print_subheader("۴️⃣ شاخص ترس و طمع")
    results["total"] += 1
    r = test_endpoint("Fear & Greed", f"{BASE_URL}/api/coinstats/fear-greed")
    if r.get("success"):
        results["success"] += 1
        data = r.get("data", {})
        if data.get("success"):
            fg = data.get("data", {})
            print_info(f"😨 مقدار: {fg.get('value', 50)}")
            print_info(f"📌 وضعیت: {fg.get('classification', 'Neutral')}")
        else:
            print_error("Fear & Greed data not available")
    else:
        results["failed"] += 1
        results["errors"].append({"endpoint": "fear-greed", "error": r.get("error")})

    # ============================================================
    # ۵. وضعیت مدل
    # ============================================================
    print_subheader("۵️⃣ وضعیت مدل")
    results["total"] += 1
    r = test_endpoint("Model Status", f"{BASE_URL}/api/model/status")
    if r.get("success"):
        results["success"] += 1
        data = r.get("data", {})
        if data.get("success"):
            status = data.get("data", {})
            model_status = status.get("stats", {})
            loaded = model_status.get("mode") == "BETA" or status.get("model_exists", False)
            print_info(f"🧠 مدل: {'✅ فعال' if loaded else '📦 دمو'}")
            print_info(f"📌 نسخه: {status.get('current_version', 'N/A')}")
            print_info(f"📊 آموزش‌ها: {model_status.get('total_trainings', 0)}")
        else:
            print_error("Model status not available")
    else:
        results["failed"] += 1
        results["errors"].append({"endpoint": "model-status", "error": r.get("error")})

    # ============================================================
    # ۶. اعتبار API
    # ============================================================
    print_subheader("۶️⃣ اعتبار API")
    results["total"] += 1
    r = test_endpoint("Credits", f"{BASE_URL}/api/credits")
    if r.get("success"):
        results["success"] += 1
        data = r.get("data", {})
        if data.get("success"):
            credits = data.get("data", {})
            print_info(f"💰 اعتبار باقیمانده: {credits.get('remainingCredits', 0)}")
            print_info(f"📊 کل اعتبار: {credits.get('totalCredits', 0)}")
            print_info(f"📈 مصرف شده: {credits.get('usedCredits', 0)}")
        else:
            print_error("Credits data not available")
    else:
        results["failed"] += 1
        results["errors"].append({"endpoint": "credits", "error": r.get("error")})

    # ============================================================
    # ۷. هشدارها
    # ============================================================
    print_subheader("۷️⃣ هشدارهای سیستم")
    results["total"] += 1
    r = test_endpoint("Alerts", f"{BASE_URL}/api/alerts")
    if r.get("success"):
        results["success"] += 1
        data = r.get("data", {})
        if data.get("success"):
            alerts = data.get("data", [])
            print_info(f"📋 تعداد هشدارها: {len(alerts)}")
            for alert in alerts[:5]:
                level = alert.get('level', 'info')
                icon = "🚨" if level == "CRITICAL" else "⚠️" if level == "WARNING" else "ℹ️"
                resolved = "✅" if alert.get('resolved') else "⏳"
                print(f"    {icon} {alert.get('message', '')[:50]}... {resolved}")
        else:
            print_error("Alerts data not available")
    else:
        results["failed"] += 1
        results["errors"].append({"endpoint": "alerts", "error": r.get("error")})

    # ============================================================
    # ۸. همه داده‌های CoinStats
    # ============================================================
    print_subheader("۸️⃣ همه داده‌های CoinStats")
    results["total"] += 1
    r = test_endpoint("CoinStats All", f"{BASE_URL}/api/coinstats/all")
    if r.get("success"):
        results["success"] += 1
        data = r.get("data", {})
        if data.get("success"):
            all_data = data.get("data", {})
            btc = all_data.get("btc", {})
            eth = all_data.get("eth", {})
            fg = all_data.get("fear_greed", {})
            print_info(f"₿ BTC: ${btc.get('price', 0):,.2f}")
            print_info(f"⟠ ETH: ${eth.get('price', 0):,.2f}")
            print_info(f"😨 ترس و طمع: {fg.get('value', 50)} ({fg.get('classification', 'Neutral')})")
            print_info(f"📊 سلطه BTC: {all_data.get('btc_dominance', 0)}%")
            print_info(f"💰 اعتبار: {all_data.get('credits', 0)}")
            print_info(f"🔌 API: {all_data.get('api_status', 'unknown')}")
        else:
            print_error("CoinStats all data not available")
    else:
        results["failed"] += 1
        results["errors"].append({"endpoint": "coinstats-all", "error": r.get("error")})

    # ============================================================
    # ۹. پیش‌بینی
    # ============================================================
    print_subheader("۹️⃣ پیش‌بینی (DEMO)")
    results["total"] += 1
    r = test_endpoint("Predict BTC", f"{BASE_URL}/api/predict?coin=bitcoin")
    if r.get("success"):
        results["success"] += 1
        data = r.get("data", {})
        if data.get("success"):
            pred = data.get("data", {})
            print_info(f"🪙 ارز: {pred.get('coin', 'N/A')}")
            print_info(f"💰 قیمت: ${pred.get('current_price', 0):,.2f}")
            print_info(f"📊 سیگنال: {pred.get('signal', 'N/A')}")
            print_info(f"🎯 اطمینان: {pred.get('confidence', 'N/A')}")
            print_info(f"🧠 مدل: {pred.get('model_mode', 'N/A')}")
        else:
            print_error("Prediction not available (maybe need auth)")
    else:
        results["failed"] += 1
        results["errors"].append({"endpoint": "predict", "error": r.get("error")})

    # ============================================================
    # خلاصه
    # ============================================================
    print_header("📊 خلاصه نتایج")
    print(f"  📋 کل تست‌ها: {results['total']}")
    print(f"  {COLORS['GREEN']}✅ موفق: {results['success']}{COLORS['RESET']}")
    print(f"  {COLORS['RED']}❌ ناموفق: {results['failed']}{COLORS['RESET']}")

    if results["failed"] > 0:
        print(f"\n{COLORS['YELLOW']}⚠️ خطاها:{COLORS['RESET']}")
        for error in results["errors"]:
            print(f"    ❌ {error.get('endpoint', 'unknown')}: {error.get('error', 'Unknown error')}")

    success_rate = (results["success"] / results["total"] * 100) if results["total"] > 0 else 0
    if success_rate == 100:
        print(f"\n{COLORS['GREEN']}🎉 همه تست‌ها با موفقیت انجام شد!{COLORS['RESET']}")
    elif success_rate >= 70:
        print(f"\n{COLORS['YELLOW']}⚠️ {success_rate:.1f}% تست‌ها موفق بودند.{COLORS['RESET']}")
    else:
        print(f"\n{COLORS['RED']}❌ {success_rate:.1f}% تست‌ها موفق بودند.{COLORS['RESET']}")

    print(f"\n{COLORS['CYAN']}{'='*80}{COLORS['RESET']}")
    print(f"{COLORS['CYAN']}🏁 پایان تست - {datetime.now().strftime('%H:%M:%S')}{COLORS['RESET']}")
    print(f"{COLORS['CYAN']}{'='*80}{COLORS['RESET']}")

    return results


if __name__ == "__main__":
    if len(sys.argv) > 1:
        BASE_URL = sys.argv[1]
    run_tests()
