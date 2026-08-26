# monitor.py
# ============================================================
# سیستم مانیتورینگ پیشرفته - نسخه ۱.۰
# ============================================================

import os
import time
import psutil
import threading
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List

from alerter import alerter
from logger_config import get_logger

logger = get_logger("monitor")


class SystemMonitor:
    """
    مانیتورینگ پیشرفته سیستم:
    - نظارت بر فضای دیسک
    - نظارت بر مصرف دیتابیس
    - نظارت بر تعداد درخواست‌ها
    - نظارت بر خطاها
    - گزارش‌های دوره‌ای
    """
    
    def __init__(self):
        self._running = False
        self._thread = None
        self._metrics_history = []
        self._max_history = 1440  # ۲۴ ساعت (هر ۱ دقیقه)
        
        # آمار خطاها
        self.error_counts = {
            "api": 0,
            "database": 0,
            "model": 0,
            "system": 0
        }
        
        # زمان آخرین گزارش
        self._last_report_time = 0
        
        logger.info("✅ SystemMonitor initialized")
    
    def start(self, interval: int = 60):
        """شروع مانیتورینگ (هر X ثانیه)"""
        if self._running:
            return
        
        self._running = True
        
        def monitor_loop():
            while self._running:
                try:
                    self._collect_metrics()
                    self._check_disk_space()
                    self._check_database_size()
                    self._send_periodic_report()
                    time.sleep(interval)
                except Exception as e:
                    logger.error(f"❌ Monitor error: {e}")
                    time.sleep(interval)
        
        self._thread = threading.Thread(target=monitor_loop, daemon=True)
        self._thread.start()
        logger.info(f"✅ SystemMonitor started (interval: {interval}s)")
    
    def stop(self):
        """متوقف کردن مانیتورینگ"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
        logger.info("⏹️ SystemMonitor stopped")
    
    def _collect_metrics(self):
        """جمع‌آوری متریک‌های سیستم"""
        try:
            metrics = {
                "timestamp": datetime.now().isoformat(),
                "cpu": psutil.cpu_percent(interval=0.5),
                "ram": psutil.virtual_memory().percent,
                "disk": psutil.disk_usage('/').percent,
                "connections": len(psutil.net_connections()),
                "processes": len(psutil.pids()),
                "errors": self.error_counts.copy()
            }
            
            self._metrics_history.append(metrics)
            if len(self._metrics_history) > self._max_history:
                self._metrics_history = self._metrics_history[-self._max_history:]
            
            # لاگ در صورت بالا بودن مصرف
            if metrics["cpu"] > 80:
                logger.warning(f"⚠️ CPU high: {metrics['cpu']}%")
            if metrics["ram"] > 80:
                logger.warning(f"⚠️ RAM high: {metrics['ram']}%")
            if metrics["disk"] > 85:
                logger.warning(f"⚠️ Disk high: {metrics['disk']}%")
                
        except Exception as e:
            logger.error(f"❌ Error collecting metrics: {e}")
    
    def _check_disk_space(self):
        """بررسی فضای خالی دیسک"""
        try:
            usage = psutil.disk_usage('/')
            free_gb = usage.free / (1024**3)
            
            # هشدار اگر فضای خالی کمتر از ۲ گیگ باشد
            if free_gb < 2:
                logger.critical(f"🚨 Disk space low: {free_gb:.1f}GB remaining")
                alerter._send_alert({
                    "level": "CRITICAL",
                    "source": "system",
                    "message": f"فضای دیسک کمتر از ۲GB: {free_gb:.1f}GB باقیمانده",
                    "timestamp": datetime.now().isoformat()
                })
            
            # هشدار اگر فضای خالی کمتر از ۵ گیگ باشد
            elif free_gb < 5:
                logger.warning(f"⚠️ Disk space warning: {free_gb:.1f}GB remaining")
                
        except Exception as e:
            logger.error(f"❌ Disk space check error: {e}")
    
    def _check_database_size(self):
        """بررسی حجم دیتابیس (هر ۱۰ دقیقه یکبار)"""
        # فقط هر ۱۰ دقیقه یکبار
        if int(time.time()) % 600 > 10:
            return
        
        try:
            from database import get_primary
            db = get_primary()
            if db and db.is_connected():
                result = db.execute("""
                    SELECT 
                        pg_database_size(current_database()) / 1024 / 1024 as size_mb
                """)
                if result:
                    size_mb = result[0].get('size_mb', 0)
                    if size_mb > 500:  # بیشتر از ۵۰۰ مگابایت
                        logger.warning(f"⚠️ Database size: {size_mb:.1f}MB")
                    if size_mb > 1000:  # بیشتر از ۱ گیگابایت
                        logger.critical(f"🚨 Database size critical: {size_mb:.1f}MB")
                        
        except Exception as e:
            logger.error(f"❌ Database size check error: {e}")
    
    def _send_periodic_report(self):
        """ارسال گزارش دوره‌ای (هر ۶ ساعت یکبار)"""
        now = time.time()
        if now - self._last_report_time < 21600:  # ۶ ساعت
            return
        
        self._last_report_time = now
        
        # جمع‌آوری خلاصه
        if not self._metrics_history:
            return
        
        last_metrics = self._metrics_history[-1]
        avg_cpu = sum(m["cpu"] for m in self._metrics_history[-60:]) / min(60, len(self._metrics_history))
        avg_ram = sum(m["ram"] for m in self._metrics_history[-60:]) / min(60, len(self._metrics_history))
        
        # گزارش
        report = f"""
📊 *گزارش دوره‌ای سیستم*
📅 زمان: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

⚙️ *مصرف منابع*
- CPU: {last_metrics.get('cpu', 0)}% (avg: {avg_cpu:.1f}%)
- RAM: {last_metrics.get('ram', 0)}% (avg: {avg_ram:.1f}%)
- Disk: {last_metrics.get('disk', 0)}%

🔌 *اتصالات*
- تعداد اتصالات: {last_metrics.get('connections', 0)}
- تعداد پردازش‌ها: {last_metrics.get('processes', 0)}

❌ *خطاها*
- API: {self.error_counts.get('api', 0)}
- Database: {self.error_counts.get('database', 0)}
- Model: {self.error_counts.get('model', 0)}
- System: {self.error_counts.get('system', 0)}
"""
        logger.info(f"📊 Period report generated")
        
        # ارسال به تلگرام (اگر تنظیم شده باشد)
        try:
            from alerter import alerter
            if alerter.telegram_enabled:
                alerter._send_telegram({
                    "level": "INFO",
                    "source": "system",
                    "message": report,
                    "timestamp": datetime.now().isoformat()
                })
        except Exception as e:
            logger.error(f"❌ Report send error: {e}")
    
    def increment_error(self, error_type: str):
        """افزایش شمارنده خطا"""
        if error_type in self.error_counts:
            self.error_counts[error_type] += 1
    
    def get_metrics_history(self, limit: int = 100) -> List[Dict]:
        """دریافت تاریخچه متریک‌ها"""
        return self._metrics_history[-limit:]
    
    def get_summary(self) -> Dict:
        """دریافت خلاصه وضعیت"""
        if not self._metrics_history:
            return {"status": "no_data"}
        
        last = self._metrics_history[-1]
        return {
            "status": "ok",
            "cpu": last.get("cpu", 0),
            "ram": last.get("ram", 0),
            "disk": last.get("disk", 0),
            "connections": last.get("connections", 0),
            "errors": self.error_counts,
            "timestamp": datetime.now().isoformat()
        }


# ایجاد نمونه
monitor = SystemMonitor()
