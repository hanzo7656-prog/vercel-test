# task_manager.py
# ============================================================
# مدیریت تسک‌های پس‌زمینه - نسخه پیشرفته با شروع پلکانی و لاگ‌گیری
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


class TaskStatus(Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


class TaskPriority(Enum):
    LOW = 0
    NORMAL = 1
    HIGH = 2
    CRITICAL = 3


@dataclass
class Task:
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
    progress: int = 0
    timeout: int = 60
    is_auto: bool = False


class AutoTask:
    def __init__(self, name: str, func: Callable, interval: int, args: tuple = (), kwargs: dict = None):
        self.name = name
        self.func = func
        self.interval = interval
        self.args = args
        self.kwargs = kwargs or {}
        self.running = False
        self.last_run: Optional[datetime] = None
        self.last_result: Any = None
        self.last_error: Optional[str] = None
        self.total_runs = 0
        self.successful_runs = 0
        self.failed_runs = 0
        self.thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self.logs: List[Dict[str, Any]] = []  # لاگ‌های تسک
        self.current_progress = 0  # درصد پیشرفت
        self.remaining_time = 0  # زمان باقیمانده تا اجرای بعدی


class TaskManager:
    def __init__(self, num_workers: int = 1, max_tasks: int = 100, task_ttl: int = 300):
        self.num_workers = max(1, min(num_workers, os.cpu_count() or 1))
        self.max_tasks = max_tasks
        self.task_ttl = task_ttl
        
        self.tasks: Dict[str, Task] = {}
        self.queue = Queue()
        self.workers: List[threading.Thread] = []
        self.running = True
        
        self.auto_tasks: Dict[str, AutoTask] = {}
        
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
        self._start_progress_updater()
        
        logger.info(f"✅ TaskManager initialized with {self.num_workers} workers")
    
    def _start_workers(self):
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
        while self.running:
            try:
                task_id = self.queue.get(timeout=1)
                
                with self._lock:
                    task = self.tasks.get(task_id)
                    if not task:
                        continue
                    task.status = TaskStatus.PROCESSING
                    task.started_at = datetime.now().isoformat()
                
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
        total = self.stats["total_completed"]
        avg = self.stats["avg_processing_time"]
        self.stats["avg_processing_time"] = ((avg * (total - 1)) + new_time) / total if total > 0 else new_time
    
    def _start_cleaner(self):
        def cleaner():
            while self.running:
                time.sleep(60)
                self._cleanup_old_tasks()
        
        cleaner_thread = threading.Thread(target=cleaner, daemon=True)
        cleaner_thread.start()
    
    def _cleanup_old_tasks(self):
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
    
    def _start_progress_updater(self):
        """بروزرسانی خودکار پیشرفت و زمان باقیمانده تسک‌های خودکار"""
        def updater():
            while self.running:
                time.sleep(1)
                # بدون لاک (چون فقط میخونیم)
                for auto_task in self.auto_tasks.values():
                    if auto_task.running and auto_task.last_run:
                        elapsed = (datetime.now() - auto_task.last_run).total_seconds()
                        remaining = max(0, auto_task.interval - elapsed)
                        auto_task.remaining_time = int(remaining)
                        auto_task.current_progress = min(100, int((elapsed / auto_task.interval) * 100))
                    elif auto_task.running:
                        auto_task.remaining_time = auto_task.interval
                        auto_task.current_progress = 0
                    else:
                        auto_task.remaining_time = 0
                        auto_task.current_progress = 0
                        
        updater_thread = threading.Thread(target=updater, daemon=True)
        updater_thread.start()
    
    def submit(self, func: Callable, name: str = None, 
               args: tuple = (), kwargs: dict = None,
               priority: TaskPriority = TaskPriority.NORMAL,
               timeout: int = 60, is_auto: bool = False) -> str:
        
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
            is_auto=is_auto,
        )
        
        with self._lock:
            if len(self.tasks) >= self.max_tasks:
                self._cleanup_old_tasks()
            
            self.tasks[task_id] = task
            self.stats["total_submitted"] += 1
            self.queue.put(task_id)
            
            queue_size = self.queue.qsize()
            if queue_size > self.stats["peak_queue_size"]:
                self.stats["peak_queue_size"] = queue_size
        
        logger.debug(f"📝 Task {task_id} submitted: {task_name}")
        return task_id
    
    def get_result(self, task_id: str) -> Optional[Dict[str, Any]]:
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
                "is_auto": task.is_auto,
            }
    
    def cancel(self, task_id: str) -> bool:
        with self._lock:
            task = self.tasks.get(task_id)
            if not task:
                return False
            if task.status == TaskStatus.PENDING:
                task.status = TaskStatus.CANCELLED
                task.completed_at = datetime.now().isoformat()
                self.stats["total_cancelled"] += 1
                return True
            return False
    
    def clear_completed(self):
        with self._lock:
            to_delete = [
                task_id for task_id, task in self.tasks.items()
                if task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]
                and not task.is_auto
            ]
            for task_id in to_delete:
                del self.tasks[task_id]
    
    def register_auto_task(self, name: str, func: Callable, interval: int, 
                           args: tuple = (), kwargs: dict = None, delay: int = 0) -> str:
        """ثبت تسک خودکار با تاخیر شروع (برای شروع پلکانی)"""
        if kwargs is None:
            kwargs = {}
        
        auto_task = AutoTask(name, func, interval, args, kwargs)
        self.auto_tasks[name] = auto_task
        
        # لاگ ثبت
        auto_task.logs.append({
            "time": datetime.now().isoformat(),
            "event": "registered",
            "message": f"تسک با فاصله {interval} ثانیه ثبت شد"
        })
        
        logger.info(f"✅ Auto task registered: {name} (interval: {interval}s, delay: {delay}s)")
        return name
    
    def start_auto_task(self, name: str, delay: int = 0):
        """شروع تسک خودکار با تاخیر دلخواه"""
        auto_task = self.auto_tasks.get(name)
        if not auto_task:
            return False
        
        if auto_task.running:
            return False
        
        auto_task.running = True
        auto_task._stop_event.clear()
        
        def run_auto():
            # تاخیر اولیه برای شروع پلکانی
            if delay > 0:
                time.sleep(delay)
            
            while auto_task.running and not auto_task._stop_event.is_set():
                try:
                    start_time = time.time()
                    auto_task.last_run = datetime.now()
                    result = auto_task.func(*auto_task.args, **auto_task.kwargs)
                    auto_task.last_result = result
                    auto_task.last_error = None
                    auto_task.successful_runs += 1
                    
                    # لاگ موفقیت
                    auto_task.logs.append({
                        "time": datetime.now().isoformat(),
                        "event": "success",
                        "message": f"اجرا موفق در {time.time() - start_time:.2f} ثانیه"
                    })
                    if len(auto_task.logs) > 50:
                        auto_task.logs = auto_task.logs[-50:]
                    
                    logger.debug(f"✅ Auto task '{name}' completed in {time.time() - start_time:.2f}s")
                except Exception as e:
                    auto_task.last_error = str(e)
                    auto_task.failed_runs += 1
                    
                    # لاگ خطا
                    auto_task.logs.append({
                        "time": datetime.now().isoformat(),
                        "event": "error",
                        "message": f"خطا: {str(e)}"
                    })
                    if len(auto_task.logs) > 50:
                        auto_task.logs = auto_task.logs[-50:]
                    
                    logger.error(f"❌ Auto task '{name}' failed: {e}")
                
                auto_task.total_runs += 1
                
                # منتظر ماندن تا فاصله بعدی
                for _ in range(auto_task.interval):
                    if auto_task._stop_event.is_set() or not auto_task.running:
                        break
                    time.sleep(1)
        
        auto_task.thread = threading.Thread(target=run_auto, daemon=True)
        auto_task.thread.start()
        logger.info(f"▶️ Auto task started: {name} (delay: {delay}s)")
        return True
    
    def stop_auto_task(self, name: str):
        auto_task = self.auto_tasks.get(name)
        if not auto_task or not auto_task.running:
            return False
        
        auto_task.running = False
        auto_task._stop_event.set()
        
        if auto_task.thread and auto_task.thread.is_alive():
            auto_task.thread.join(timeout=2)
        
        # لاگ توقف
        auto_task.logs.append({
            "time": datetime.now().isoformat(),
            "event": "stopped",
            "message": "تسک متوقف شد"
        })
        if len(auto_task.logs) > 50:
            auto_task.logs = auto_task.logs[-50:]
        
        logger.info(f"⏹️ Auto task stopped: {name}")
        return True
    
    def start_all_auto_tasks(self, stagger: int = 5):
        """شروع همه تسک‌ها با تاخیر پلکانی (هر تسک ۵ ثانیه بعد از قبلی)"""
        delay = 0
        for name in self.auto_tasks.keys():
            self.start_auto_task(name, delay)
            delay += stagger
        logger.info(f"✅ All auto tasks started with {stagger}s stagger")
    
    def stop_all_auto_tasks(self):
        for name in self.auto_tasks.keys():
            self.stop_auto_task(name)
    
    def get_auto_tasks_status(self) -> List[Dict[str, Any]]:
        result = []
        for name, auto_task in self.auto_tasks.items():
            result.append({
                "name": name,
                "running": auto_task.running,
                "interval": auto_task.interval,
                "last_run": auto_task.last_run.isoformat() if auto_task.last_run else None,
                "last_error": auto_task.last_error,
                "last_result": auto_task.last_result,
                "total_runs": auto_task.total_runs,
                "successful_runs": auto_task.successful_runs,
                "failed_runs": auto_task.failed_runs,
                "progress": auto_task.current_progress,
                "remaining_time": auto_task.remaining_time,
                "logs": auto_task.logs[-10:] if auto_task.logs else [],  # آخرین ۱۰ لاگ
            })
        return result
    
    def get_stats(self) -> Dict[str, Any]:
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
                "auto_tasks": self.get_auto_tasks_status(),
                "config": {
                    "max_tasks": self.max_tasks,
                    "task_ttl": self.task_ttl,
                    "running": self.running,
                },
                "timestamp": datetime.now().isoformat(),
            }
    
    def shutdown(self):
        self.running = False
        self.stop_all_auto_tasks()
        for worker in self.workers:
            worker.join(timeout=2)
        logger.info("🛑 TaskManager shutdown complete")


_task_manager_instance = None

def get_task_manager(num_workers: int = 1, max_tasks: int = 100, task_ttl: int = 300) -> TaskManager:
    global _task_manager_instance
    if _task_manager_instance is None:
        _task_manager_instance = TaskManager(num_workers, max_tasks, task_ttl)
    return _task_manager_instance


def reset_task_manager():
    global _task_manager_instance
    if _task_manager_instance:
        _task_manager_instance.shutdown()
        _task_manager_instance = None
