import os
import sys

# اضافه کردن مسیر فعلی به PATH
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mother_health import MotherHealth

# دریافت کلید API از متغیر محیطی
API_KEY = os.environ.get("API_KEY", "40QRC4gdyzWIGwsvGkqWtcDOf0bk+FV217KmLxQ/Wmw=")

# ایجاد نمونه
health = MotherHealth(api_key=API_KEY, port=0)
app = health.app

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
