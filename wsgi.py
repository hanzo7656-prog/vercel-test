import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mother_health import MotherHealth

API_KEY = os.environ.get("API_KEY", "40QRC4gdyzWIGwsvGkqWtcDOf0bk+FV217KmLxQ/Wmw=")
health = MotherHealth(api_key=API_KEY, port=0)
app = health.app
