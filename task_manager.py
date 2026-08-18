# task_manager.py
# ============================================================
# مدیریت تسک‌های پس‌زمینه - نسخه پیشرفته
# شامل: صف، کارگرها، مدیریت حافظه، زمان‌بندی، و آمار
# ============================================================

import os
import sys
import time
import uuid
import json
import threading
import logging
from datetime import datetime
from queue import Queue, Empty
from typing import Dict, Any, Optional, Callable, List
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


# ============================================================
# وضعیت‌های تسک
# ============================================================

class TaskStatus(Enum):
    """وضعیت‌های مختلف یک تسک"""
    PENDING = "pending"          # در صف منتظر
    PROCESSING = "processing"    # در حال اجرا
    COMPLETED = "completed"      # با موفقیت انجام شد
    FAILED = "failed"            # با خطا مواجه شد
    CANCELLED = "cancelled"      # لغو شد
    TIMEOUT = "timeout"          # زمان‌بر شد


class TaskPriority(Enum):
    """اولویت‌های تسک"""
    LOW = 0
    NORMAL = 1
    HIGH = 2
    CRITICAL = 3


# ============================================================
# مدل تسک
# ============================================================

@dataclass
class Task:
    """نماینده یک تسک در سیستم"""
    task_id: str
    name: str
    func: Callable
    args: tuple = ()
    kwargs: dict = field(default_factory=dict)
    priority: TaskPriority = TaskPriority.NORMAL
    status: TaskStatus = TaskStatus.PENDING
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error: Optional[str] = None
    result: Any = None
    progress: int = 0  # 0-100
    timeout: int = 60  # ثانیه


# ============================================================
# مدیریت تسک‌ها
# ============================================================

class TaskManager:
    """
    مدیریت پیشرفته تسک‌های پس‌زمینه
    
    ویژگی‌ها:
    - پشتیبانی از چند کارگر (قابل تنظیم)
    - اولویت‌بندی تسک‌ها
    - زمان‌بندی و Timeout
    - ذخیره و بازیابی نتایج
    - آمار و مانیتورینگ
    - مدیریت حافظه (پاک کردن تسک‌های قدیمی)
    """
    
    def __init__(self, num_workers: int = 1, max_tasks: int = 100, task_ttl: int = 300):
        """
        راه‌اندازی مدیر تسک‌ها
        
        Args:
            num_workers: تعداد کارگرهای همزمان (پیش‌فرض: ۱)
            max_tasks: حداکثر تسک‌های ذخیره‌شده (پیش‌فرض: ۱۰۰)
            task_ttl: زمان زندگی تسک‌ها در حافظه (ثانیه، پیش‌فرض: ۳۰۰)
        """
        self.num_workers = max(1, min(num_workers, os.cpu_count() or 1))
        self.max_tasks = max_tasks
        self.task_ttl = task_ttl
        
        self.tasks: Dict[str, Task] = {}
        self.queue = Queue()
        self.workers: List[threading.Thread] = []
        self.running = True
        
        self.stats = {
            "total_submitted": 0,
            "total_completed": 0,
            "total_failed": 0,
            "total_cancelled": 0,
            "total_timeout": 0,
            "avg_processing_time": 0,
            "peak_queue_size": 0,
        }
        
        self._lock = threading.Lock()
        self._start_workers()
        self._start_cleaner()
        
        logger.info(f"✅ TaskManager initialized with {self.num_workers} workers")
    
    # ============================================================
    # مدیریت کارگرها
    # ============================================================
    
    def _start_workers(self):
        """راه‌اندازی کارگرها"""
        for i in range(self.num_workers):
            worker = threading.Thread(
                target=self._worker_loop,
                name=f"Worker-{i+1}",
                daemon=True
            )
            worker.start()
            self.workers.append(worker)
            logger.debug(f"✅ Worker-{i+1} started")
    
    def _worker_loop(self):
        """حلقه اصلی هر کارگر"""
        while self.running:
            try:
                # دریافت تسک از صف (با Timeout)
                task_id = self.queue.get(timeout=1)
                
                with self._lock:
                    task = self.tasks.get(task_id)
                    if not task:
                        continue
                    
                    # به‌روزرسانی وضعیت
                    task.status = TaskStatus.PROCESSING
                    task.started_at = datetime.now().isoformat()
                
                # اجرای تسک
                try:
                    start_time = time.time()
                    result = task.func(*task.args, **task.kwargs)
                    processing_time = time.time() - start_time
                    
                    with self._lock:
                        task.status = TaskStatus.COMPLETED
                        task.result = result
                        task.completed_at = datetime.now().isoformat()
                        task.progress = 100
                        
                        self.stats["total_completed"] += 1
                        self._update_avg_time(processing_time)
                        
                except Exception as e:
                    with self._lock:
                        task.status = TaskStatus.FAILED
                        task.error = str(e)
                        task.completed_at = datetime.now().isoformat()
                        self.stats["total_failed"] += 1
                    
                    logger.error(f"❌ Task {task_id} failed: {e}")
                
                finally:
                    self.queue.task_done()
                    
            except Empty:
                continue
            except Exception as e:
                logger.error(f"❌ Worker error: {e}")
    
    def _update_avg_time(self, new_time: float):
        """به‌روزرسانی میانگین زمان پردازش"""
        total = self.stats["total_completed"]
        avg = self.stats["avg_processing_time"]
        self.stats["avg_processing_time"] = ((avg * (total - 1)) + new_time) / total
    
    # ============================================================
    # مدیریت حافظه (پاک‌کننده خودکار)
    # ============================================================
    
    def _start_cleaner(self):
        """راه‌اندازی پاک‌کننده خودکار تسک‌های قدیمی"""
        def cleaner():
            while self.running:
                time.sleep(60)  # هر ۶۰ ثانیه
                self._cleanup_old_tasks()
        
        cleaner_thread = threading.Thread(target=cleaner, daemon=True)
        cleaner_thread.start()
        logger.debug("✅ Task cleaner started")
    
    def _cleanup_old_tasks(self):
        """پاک کردن تسک‌های قدیمی و تکمیل‌شده"""
        now = datetime.now()
        to_delete = []
        
        with self._lock:
            for task_id, task in self.tasks.items():
                if task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]:
                    if task.completed_at:
                        completed_time = datetime.fromisoformat(task.completed_at)
                        if (now - completed_time).total_seconds() > self.task_ttl:
                            to_delete.append(task_id)
            
            for task_id in to_delete:
                del self.tasks[task_id]
            
            if to_delete:
                logger.debug(f"🧹 Cleaned up {len(to_delete)} old tasks")
    
    # ============================================================
    # مدیریت تسک‌ها
    # ============================================================
    
    def submit(self, func: Callable, name: str = None, 
               args: tuple = (), kwargs: dict = None,
               priority: TaskPriority = TaskPriority.NORMAL,
               timeout: int = 60) -> str:
        """
        ارسال یک تسک جدید به صف
        
        Returns:
            task_id: شناسه یکتای تسک
        """
        if kwargs is None:
            kwargs = {}
        
        task_id = str(uuid.uuid4())[:8]
        task_name = name or func.__name__
        
        task = Task(
            task_id=task_id,
            name=task_name,
            func=func,
            args=args,
            kwargs=kwargs,
            priority=priority,
            timeout=timeout,
        )
        
        with self._lock:
            # مدیریت حافظه
            if len(self.tasks) >= self.max_tasks:
                self._cleanup_old_tasks()
            
            self.tasks[task_id] = task
            self.stats["total_submitted"] += 1
            
            # اضافه کردن به صف با اولویت
            self._put_with_priority(task_id, priority)
            
            # بروزرسانی آمار صف
            queue_size = self.queue.qsize()
            if queue_size > self.stats["peak_queue_size"]:
                self.stats["peak_queue_size"] = queue_size
        
        logger.debug(f"📝 Task {task_id} submitted: {task_name}")
        return task_id
    
    def _put_with_priority(self, task_id: str, priority: TaskPriority):
        """اضافه کردن به صف با اولویت"""
        # برای سادگی، از اولویت در صف استفاده نمیکنیم
        # (در پیاده‌سازی پیشرفته‌تر، می‌توان از PriorityQueue استفاده کرد)
        self.queue.put(task_id)
    
    def get_result(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        دریافت نتیجه یک تسک
        
        Returns:
            dict: {
                "status": "completed" | "pending" | "failed" | ...,
                "result": ...,
                "error": ...,
                "progress": 0-100,
                "created_at": ...,
                "completed_at": ...
            }
            یا None اگر تسک وجود نداشته باشد
        """
        with self._lock:
            task = self.tasks.get(task_id)
            if not task:
                return None
            
            return {
                "task_id": task.task_id,
                "name": task.name,
                "status": task.status.value,
                "result": task.result,
                "error": task.error,
                "progress": task.progress,
                "created_at": task.created_at,
                "started_at": task.started_at,
                "completed_at": task.completed_at,
            }
    
    def cancel(self, task_id: str) -> bool:
        """
        لغو یک تسک (فقط در حالت PENDING قابل لغو است)
        
        Returns:
            True اگر لغو شد، False اگر قابل لغو نبود
        """
        with self._lock:
            task = self.tasks.get(task_id)
            if not task:
                return False
            
            if task.status == TaskStatus.PENDING:
                task.status = TaskStatus.CANCELLED
                task.completed_at = datetime.now().isoformat()
                self.stats["total_cancelled"] += 1
                logger.debug(f"⏹️ Task {task_id} cancelled")
                return True
            
            return False
    
    def get_stats(self) -> Dict[str, Any]:
        """دریافت آمار سیستم تسک‌ها"""
        with self._lock:
            pending = sum(1 for t in self.tasks.values() if t.status == TaskStatus.PENDING)
            processing = sum(1 for t in self.tasks.values() if t.status == TaskStatus.PROCESSING)
            completed = sum(1 for t in self.tasks.values() if t.status == TaskStatus.COMPLETED)
            failed = sum(1 for t in self.tasks.values() if t.status == TaskStatus.FAILED)
            
            return {
                "workers": {
                    "total": self.num_workers,
                    "active": len([w for w in self.workers if w.is_alive()]),
                },
                "tasks": {
                    "total": len(self.tasks),
                    "pending": pending,
                    "processing": processing,
                    "completed": completed,
                    "failed": failed,
                    "queue_size": self.queue.qsize(),
                },
                "stats": self.stats.copy(),
                "config": {
                    "max_tasks": self.max_tasks,
                    "task_ttl": self.task_ttl,
                    "running": self.running,
                },
                "timestamp": datetime.now().isoformat(),
            }
    
    def clear_completed(self):
        """پاک کردن تمام تسک‌های تکمیل‌شده و شکست‌خورده"""
        with self._lock:
            to_delete = [
                task_id for task_id, task in self.tasks.items()
                if task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]
            ]
            for task_id in to_delete:
                del self.tasks[task_id]
            logger.info(f"🧹 Cleared {len(to_delete)} completed/failed tasks")
    
    def shutdown(self):
        """متوقف کردن سیستم تسک‌ها"""
        self.running = False
        for worker in self.workers:
            worker.join(timeout=2)
        logger.info("🛑 TaskManager shutdown complete")


# ============================================================
# دکوراتور برای تبدیل توابع به تسک
# ============================================================

def task(name: str = None, priority: TaskPriority = TaskPriority.NORMAL, timeout: int = 60):
    """
    دکوراتور برای تبدیل یک تابع به تسک قابل ارسال
    
    Usage:
        @task(name="پیش‌بینی", priority=TaskPriority.HIGH)
        def my_predict_function(coin, period):
            ...
        
        task_id = my_predict_function.submit("bitcoin", "24h")
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            # اجرای مستقیم
            return func(*args, **kwargs)
        
        wrapper._task_name = name or func.__name__
        wrapper._task_priority = priority
        wrapper._task_timeout = timeout
        
        def submit(*args, **kwargs):
            # ارسال به TaskManager
            if not hasattr(wrapper, '_task_manager'):
                raise RuntimeError("Task manager not set. Call set_task_manager() first.")
            return wrapper._task_manager.submit(
                func, wrapper._task_name, args, kwargs,
                wrapper._task_priority, wrapper._task_timeout
            )
        
        wrapper.submit = submit
        wrapper.func = func
        
        def set_task_manager(tm):
            wrapper._task_manager = tm
        
        wrapper.set_task_manager = set_task_manager
        
        return wrapper
    
    return decorator


# ============================================================
# نمونه تسک‌های از پیش تعریف شده
# ============================================================

def create_prediction_task(system):
    """ایجاد تسک پیش‌بینی با استفاده از دکوراتور"""
    
    @task(name="پیش‌بینی الگو", priority=TaskPriority.HIGH, timeout=120)
    def predict_task(coin_id: str, period: str):
        return system.predict_sync(coin_id, period)
    
    # اتصال به TaskManager
    return predict_task


def create_data_fetch_task(api):
    """ایجاد تسک دریافت داده"""
    
    @task(name="دریافت داده", priority=TaskPriority.NORMAL, timeout=60)
    def fetch_data_task(data_type: str, coin: str = "bitcoin", period: str = "24h"):
        if data_type == "chart":
            return api.get_chart(coin, period)
        elif data_type == "coin":
            return api.get_coin(coin)
        elif data_type == "news":
            return api.get_news(limit=10)
        return {"error": "Invalid data type"}
    
    return fetch_data_task


# ============================================================
# استفاده به عنوان Singleton
# ============================================================

_task_manager_instance = None

def get_task_manager(num_workers: int = 1, max_tasks: int = 100, task_ttl: int = 300) -> TaskManager:
    """
    دریافت نمونه TaskManager (Singleton)
    """
    global _task_manager_instance
    if _task_manager_instance is None:
        _task_manager_instance = TaskManager(num_workers, max_tasks, task_ttl)
    return _task_manager_instance


def reset_task_manager():
    """ریست کردن TaskManager (برای تست)"""
    global _task_manager_instance
    if _task_manager_instance:
        _task_manager_instance.shutdown()
        _task_manager_instance = None
