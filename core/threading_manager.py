# core/threading_manager.py
# ============================================================
# مدیریت یکپارچه Threadها - نسخه ۲.۰ با قابلیت‌های جدید
# ============================================================

import threading
import time
import logging
from typing import Dict, Callable, Optional, Any, List
from datetime import datetime
from enum import Enum
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


class ThreadStatus(Enum):
    STOPPED = "stopped"
    RUNNING = "running"
    ERROR = "error"
    STOPPING = "stopping"
    PAUSED = "paused"


@dataclass
class ThreadStats:
    """آمار یک Thread"""
    runs: int = 0
    errors: int = 0
    restarts: int = 0
    last_heartbeat: Optional[str] = None
    total_execution_time: float = 0
    avg_execution_time: float = 0


class ManagedThread:
    """کلاس مدیریت یک Thread با قابلیت‌های پیشرفته"""
    
    def __init__(
        self, 
        name: str, 
        target: Callable, 
        args: tuple = (),
        kwargs: dict = None,
        daemon: bool = False,
        auto_restart: bool = True,
        max_restarts: int = 5,
        restart_delay: int = 5,
        max_execution_time: Optional[int] = None
    ):
        self.name = name
        self.target = target
        self.args = args
        self.kwargs = kwargs or {}
        self.daemon = daemon
        self.auto_restart = auto_restart
        self.max_restarts = max_restarts
        self.restart_delay = restart_delay
        self.max_execution_time = max_execution_time
        
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self._status = ThreadStatus.STOPPED
        self._restart_count = 0
        self._last_error: Optional[str] = None
        self._last_run: Optional[datetime] = None
        self._lock = threading.Lock()
        
        self.stats = ThreadStats()
        
        # Heartbeat
        self._heartbeat_thread: Optional[threading.Thread] = None
        self._heartbeat_interval = 5
        
        logger.debug(f"✅ ManagedThread {name} created")
    
    @property
    def status(self) -> ThreadStatus:
        with self._lock:
            return self._status
    
    @property
    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()
    
    def start(self):
        """شروع Thread"""
        with self._lock:
            if self.is_alive:
                logger.warning(f"⚠️ Thread {self.name} already running")
                return
            
            self._stop_event.clear()
            self._pause_event.clear()
            self._status = ThreadStatus.RUNNING
            self._restart_count = 0
            
            self._thread = threading.Thread(
                target=self._run_wrapper,
                name=f"ManagedThread-{self.name}",
                daemon=self.daemon
            )
            self._thread.start()
            
            # شروع Heartbeat
            self._start_heartbeat()
            
            logger.info(f"✅ Thread {self.name} started (daemon: {self.daemon})")
    
    def stop(self, timeout: float = 5.0):
        """متوقف کردن Thread"""
        with self._lock:
            if not self.is_alive:
                return
            
            self._status = ThreadStatus.STOPPING
            self._stop_event.set()
            logger.info(f"⏹️ Stopping Thread {self.name}...")
        
        if self._thread:
            self._thread.join(timeout=timeout)
            if self._thread.is_alive():
                logger.warning(f"⚠️ Thread {self.name} did not stop gracefully")
        
        self._stop_heartbeat()
        
        with self._lock:
            self._status = ThreadStatus.STOPPED
            logger.info(f"✅ Thread {self.name} stopped")
    
    def pause(self):
        """مکث موقت Thread"""
        with self._lock:
            if self._status == ThreadStatus.RUNNING:
                self._pause_event.set()
                self._status = ThreadStatus.PAUSED
                logger.info(f"⏸️ Thread {self.name} paused")
    
    def resume(self):
        """ادامه Thread از حالت مکث"""
        with self._lock:
            if self._status == ThreadStatus.PAUSED:
                self._pause_event.clear()
                self._status = ThreadStatus.RUNNING
                logger.info(f"▶️ Thread {self.name} resumed")
    
    def _run_wrapper(self):
        """Wrapper برای اجرای target با مدیریت خطا"""
        start_time = time.time()
        
        while not self._stop_event.is_set():
            try:
                # بررسی مکث
                if self._pause_event.is_set():
                    time.sleep(1)
                    continue
                
                # اجرای تابع هدف
                self.stats.runs += 1
                self._last_run = datetime.now()
                
                task_start = time.time()
                self.target(*self.args, **self.kwargs)
                task_time = time.time() - task_start
                
                # به‌روزرسانی آمار
                self.stats.total_execution_time += task_time
                self.stats.avg_execution_time = (
                    self.stats.total_execution_time / self.stats.runs
                )
                
                # بررسی زمان اجرا
                if self.max_execution_time and task_time > self.max_execution_time:
                    logger.warning(f"⚠️ Thread {self.name} exceeded max execution time: {task_time:.2f}s")
                
                # اگر تابع برگشت و Auto Restart فعال است
                if self.auto_restart and not self._stop_event.is_set():
                    logger.info(f"🔄 Thread {self.name} completed, restarting...")
                    self.stats.restarts += 1
                    time.sleep(self.restart_delay)
                    continue
                else:
                    break
                    
            except Exception as e:
                self.stats.errors += 1
                self._last_error = str(e)
                logger.error(f"❌ Error in Thread {self.name}: {e}")
                
                if self.auto_restart and self._restart_count < self.max_restarts:
                    self._restart_count += 1
                    self.stats.restarts += 1
                    wait_time = min(self.restart_delay * self._restart_count, 60)
                    logger.info(f"🔄 Restarting Thread {self.name} in {wait_time}s "
                               f"(attempt {self._restart_count}/{self.max_restarts})")
                    time.sleep(wait_time)
                else:
                    with self._lock:
                        self._status = ThreadStatus.ERROR
                    logger.error(f"❌ Thread {self.name} stopped due to errors")
                    break
        
        with self._lock:
            if self._status != ThreadStatus.ERROR:
                self._status = ThreadStatus.STOPPED
    
    def _start_heartbeat(self):
        """شروع Heartbeat برای نظارت"""
        def heartbeat_loop():
            while self.is_alive:
                self.stats.last_heartbeat = datetime.now().isoformat()
                time.sleep(self._heartbeat_interval)
        
        self._heartbeat_thread = threading.Thread(
            target=heartbeat_loop,
            daemon=True,
            name=f"Heartbeat-{self.name}"
        )
        self._heartbeat_thread.start()
    
    def _stop_heartbeat(self):
        """توقف Heartbeat"""
        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            # Heartbeat thread در پس‌زمینه اجرا می‌شود
            pass
    
    def health_check(self) -> Dict[str, Any]:
        """بررسی سلامت Thread"""
        return {
            "name": self.name,
            "status": self.status.value,
            "alive": self.is_alive,
            "restart_count": self._restart_count,
            "last_error": self._last_error,
            "last_run": self._last_run.isoformat() if self._last_run else None,
            "stats": {
                "runs": self.stats.runs,
                "errors": self.stats.errors,
                "restarts": self.stats.restarts,
                "last_heartbeat": self.stats.last_heartbeat,
                "avg_execution_time": round(self.stats.avg_execution_time, 3)
            },
            "max_restarts": self.max_restarts,
            "auto_restart": self.auto_restart
        }


class ThreadingManager:
    """مدیریت یکپارچه همه Threadهای سیستم"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not hasattr(self, '_initialized'):
            self._initialized = True
            self._threads: Dict[str, ManagedThread] = {}
            self._lock = threading.Lock()
            self._watchdog_thread: Optional[ManagedThread] = None
            self._watchdog_enabled = True
            
            # شروع Watchdog خودکار
            self.start_watchdog()
            
            logger.info("✅ ThreadingManager v2.0 initialized")
    
    def register(
        self, 
        name: str, 
        target: Callable, 
        args: tuple = (),
        kwargs: dict = None,
        daemon: bool = False,
        auto_restart: bool = True,
        max_restarts: int = 5,
        restart_delay: int = 5,
        max_execution_time: Optional[int] = None,
        start_now: bool = True
    ) -> ManagedThread:
        """ثبت و راه‌اندازی یک Thread جدید"""
        with self._lock:
            if name in self._threads:
                logger.warning(f"⚠️ Thread {name} already registered, stopping old one...")
                self._threads[name].stop()
            
            thread = ManagedThread(
                name=name,
                target=target,
                args=args,
                kwargs=kwargs,
                daemon=daemon,
                auto_restart=auto_restart,
                max_restarts=max_restarts,
                restart_delay=restart_delay,
                max_execution_time=max_execution_time
            )
            self._threads[name] = thread
            
            if start_now:
                thread.start()
            
            return thread
    
    def unregister(self, name: str):
        """حذف یک Thread از مدیریت"""
        with self._lock:
            if name in self._threads:
                self._threads[name].stop()
                del self._threads[name]
                logger.info(f"✅ Thread {name} unregistered")
    
    def stop(self, name: str):
        """متوقف کردن یک Thread خاص"""
        if name in self._threads:
            self._threads[name].stop()
    
    def stop_all(self):
        """متوقف کردن همه Threadها"""
        for name, thread in list(self._threads.items()):
            thread.stop()
        logger.info("✅ All threads stopped")
    
    def pause(self, name: str):
        """مکث یک Thread"""
        if name in self._threads:
            self._threads[name].pause()
    
    def resume(self, name: str):
        """ادامه یک Thread"""
        if name in self._threads:
            self._threads[name].resume()
    
    def get_status(self, name: str) -> Optional[Dict]:
        """دریافت وضعیت یک Thread"""
        if name in self._threads:
            return self._threads[name].health_check()
        return None
    
    def get_all_status(self) -> Dict[str, Dict]:
        """دریافت وضعیت همه Threadها"""
        return {
            name: thread.health_check() 
            for name, thread in self._threads.items()
        }
    
    def get_summary(self) -> Dict[str, Any]:
        """دریافت خلاصه وضعیت"""
        statuses = self.get_all_status()
        total = len(statuses)
        running = sum(1 for s in statuses.values() if s.get('status') == 'running')
        errors = sum(1 for s in statuses.values() if s.get('status') == 'error')
        
        return {
            "total_threads": total,
            "running": running,
            "errors": errors,
            "stopped": total - running - errors,
            "threads": statuses,
            "watchdog_enabled": self._watchdog_enabled,
            "timestamp": datetime.now().isoformat()
        }
    
    # ============================================================
    # Watchdog
    # ============================================================
    
    def start_watchdog(self, check_interval: int = 10):
        """راه‌اندازی Watchdog برای نظارت بر Threadها"""
        if self._watchdog_thread and self._watchdog_thread.is_alive:
            logger.warning("⚠️ Watchdog already running")
            return
        
        def watchdog_loop():
            logger.info("🐕 Watchdog started")
            while self._watchdog_enabled:
                try:
                    for name, thread in self._threads.items():
                        if not thread.is_alive and thread.status != ThreadStatus.STOPPED:
                            logger.warning(f"⚠️ Thread {name} is dead, restarting...")
                            thread.start()
                    time.sleep(check_interval)
                except Exception as e:
                    logger.error(f"❌ Watchdog error: {e}")
                    time.sleep(10)
        
        self._watchdog_thread = ManagedThread(
            name="watchdog",
            target=watchdog_loop,
            daemon=True,
            auto_restart=True,
            max_restarts=10
        )
        self._watchdog_thread.start()
        logger.info(f"✅ Watchdog started (interval: {check_interval}s)")
    
    def stop_watchdog(self):
        """متوقف کردن Watchdog"""
        self._watchdog_enabled = False
        if self._watchdog_thread:
            self._watchdog_thread.stop()
        logger.info("⏹️ Watchdog stopped")


# نمونه Singleton
threading_manager = ThreadingManager()
