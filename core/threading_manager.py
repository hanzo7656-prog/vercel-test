# core/threading_manager.py
# ============================================================
# مدیریت یکپارچه Threadها با قابلیت Watchdog
# ============================================================

import threading
import time
import logging
from typing import Dict, Callable, Optional, Any
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class ThreadStatus(Enum):
    STOPPED = "stopped"
    RUNNING = "running"
    ERROR = "error"
    STOPPING = "stopping"


class ManagedThread:
    """کلاس مدیریت یک Thread با قابلیت نظارت"""
    
    def __init__(
        self, 
        name: str, 
        target: Callable, 
        args: tuple = (),
        kwargs: dict = None,
        daemon: bool = False,
        auto_restart: bool = True,
        max_restarts: int = 5
    ):
        self.name = name
        self.target = target
        self.args = args
        self.kwargs = kwargs or {}
        self.daemon = daemon
        self.auto_restart = auto_restart
        self.max_restarts = max_restarts
        
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._status = ThreadStatus.STOPPED
        self._restart_count = 0
        self._last_error: Optional[str] = None
        self._last_run: Optional[datetime] = None
        self._lock = threading.Lock()
        
        self.stats = {
            "runs": 0,
            "errors": 0,
            "restarts": 0,
            "last_heartbeat": None
        }
    
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
            self._status = ThreadStatus.RUNNING
            self._thread = threading.Thread(
                target=self._run_wrapper,
                name=self.name,
                daemon=self.daemon
            )
            self._thread.start()
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
        
        with self._lock:
            self._status = ThreadStatus.STOPPED
            logger.info(f"✅ Thread {self.name} stopped")
    
    def _run_wrapper(self):
        """Wrapper برای اجرای target با مدیریت خطا و Restart"""
        while not self._stop_event.is_set():
            try:
                self.stats["last_heartbeat"] = datetime.now().isoformat()
                self.stats["runs"] += 1
                self._last_run = datetime.now()
                
                # اجرای تابع هدف
                self.target(*self.args, **self.kwargs)
                
                # اگر تابع برگشت (حلقه تمام شد) و Auto Restart فعال است
                if self.auto_restart and not self._stop_event.is_set():
                    logger.info(f"🔄 Thread {self.name} completed, restarting...")
                    self.stats["restarts"] += 1
                    time.sleep(1)
                    continue
                else:
                    break
                    
            except Exception as e:
                self.stats["errors"] += 1
                self._last_error = str(e)
                logger.error(f"❌ Error in Thread {self.name}: {e}")
                
                if self.auto_restart and self._restart_count < self.max_restarts:
                    self._restart_count += 1
                    self.stats["restarts"] += 1
                    wait_time = min(5 * self._restart_count, 60)
                    logger.info(f"🔄 Restarting Thread {self.name} in {wait_time}s (attempt {self._restart_count}/{self.max_restarts})")
                    time.sleep(wait_time)
                else:
                    with self._lock:
                        self._status = ThreadStatus.ERROR
                    logger.error(f"❌ Thread {self.name} stopped due to errors")
                    break
        
        with self._lock:
            if self._status != ThreadStatus.ERROR:
                self._status = ThreadStatus.STOPPED
    
    def health_check(self) -> Dict[str, Any]:
        """بررسی سلامت Thread"""
        return {
            "name": self.name,
            "status": self.status.value,
            "alive": self.is_alive,
            "restart_count": self._restart_count,
            "last_error": self._last_error,
            "last_run": self._last_run.isoformat() if self._last_run else None,
            "stats": self.stats,
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
            logger.info("✅ ThreadingManager initialized")
    
    def register(
        self, 
        name: str, 
        target: Callable, 
        args: tuple = (),
        kwargs: dict = None,
        daemon: bool = False,
        auto_restart: bool = True,
        max_restarts: int = 5,
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
                max_restarts=max_restarts
            )
            self._threads[name] = thread
            
            if start_now:
                thread.start()
            
            return thread
    
    def stop(self, name: str):
        """متوقف کردن یک Thread خاص"""
        if name in self._threads:
            self._threads[name].stop()
    
    def stop_all(self):
        """متوقف کردن همه Threadها"""
        for name, thread in self._threads.items():
            thread.stop()
    
    def get_status(self, name: str) -> Optional[Dict]:
        """دریافت وضعیت یک Thread"""
        if name in self._threads:
            return self._threads[name].health_check()
        return None
    
    def get_all_status(self) -> Dict[str, Dict]:
        """دریافت وضعیت همه Threadها"""
        return {name: thread.health_check() for name, thread in self._threads.items()}
    
    def start_watchdog(self, check_interval: int = 10):
        """راه‌اندازی Watchdog برای نظارت بر همه Threadها"""
        if self._watchdog_thread and self._watchdog_thread.is_alive:
            logger.warning("⚠️ Watchdog already running")
            return
        
        def watchdog_loop():
            while True:
                try:
                    for name, thread in self._threads.items():
                        if not thread.is_alive and thread.status != ThreadStatus.STOPPED:
                            logger.warning(f"⚠️ Thread {name} is dead, restarting...")
                            thread.start()
                    time.sleep(check_interval)
                except Exception as e:
                    logger.error(f"❌ Watchdog error: {e}")
                    time.sleep(5)
        
        self._watchdog_thread = self.register(
            name="watchdog",
            target=watchdog_loop,
            daemon=True,
            auto_restart=True,
            max_restarts=10,
            start_now=True
        )
        logger.info(f"✅ Watchdog started (interval: {check_interval}s)")


# نمونه Singleton
threading_manager = ThreadingManager()
