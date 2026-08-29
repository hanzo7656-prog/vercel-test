# core/parallel_processor.py
# ============================================================
# پردازش موازی پیشرفته - نسخه ۱.۰
# ============================================================

import asyncio
import concurrent.futures
import logging
import time
from typing import List, Dict, Any, Callable, Optional, TypeVar, Generic
from dataclasses import dataclass
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor

T = TypeVar('T')
R = TypeVar('R')

logger = logging.getLogger(__name__)


@dataclass
class TaskResult(Generic[T]):
    """نتیجه یک تسک"""
    task_id: str
    success: bool
    result: Optional[T]
    error: Optional[str]
    execution_time: float
    timestamp: str


class ParallelProcessor:
    """
    پردازشگر موازی پیشرفته
    پشتیبانی از:
    - Thread Pool برای I/O-bound
    - Process Pool برای CPU-bound
    - Async برای عملیات غیرمترقبه
    - Batch Processing
    """
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if hasattr(self, '_initialized'):
            return
        self._initialized = True
        
        # Thread Pool برای I/O-bound
        self.thread_pool = ThreadPoolExecutor(
            max_workers=10,
            thread_name_prefix="ParallelProcessor"
        )
        
        # Process Pool برای CPU-bound
        self.process_pool = ProcessPoolExecutor(
            max_workers=4,
            mp_context=None
        )
        
        # آمار
        self.stats = {
            "total_tasks": 0,
            "successful": 0,
            "failed": 0,
            "total_time": 0,
            "avg_time": 0
        }
        
        logger.info("✅ ParallelProcessor initialized (Threads: 10, Processes: 4)")
    
    # ============================================================
    # ۱. پردازش موازی با Thread Pool
    # ============================================================
    
    def process_parallel(
        self,
        items: List[Any],
        func: Callable[[Any], R],
        max_workers: Optional[int] = None,
        timeout: float = 60.0
    ) -> List[TaskResult[R]]:
        """
        پردازش موازی آیتم‌ها با Thread Pool
        
        پارامترها:
            items: لیست آیتم‌ها برای پردازش
            func: تابع پردازش
            max_workers: تعداد Threadها (پیش‌فرض: ۱۰)
            timeout: زمان تایم‌اوت برای هر تسک
        
        خروجی:
            لیستی از TaskResult
        """
        if not items:
            return []
        
        max_workers = max_workers or min(10, len(items))
        results = []
        start_time = time.time()
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # ارسال همه تسک‌ها
            future_to_item = {
                executor.submit(func, item): idx 
                for idx, item in enumerate(items)
            }
            
            # دریافت نتایج
            for future in concurrent.futures.as_completed(future_to_item):
                idx = future_to_item[future]
                task_start = time.time()
                
                try:
                    result = future.result(timeout=timeout)
                    results.append(TaskResult(
                        task_id=f"task_{idx}",
                        success=True,
                        result=result,
                        error=None,
                        execution_time=time.time() - task_start,
                        timestamp=datetime.now().isoformat()
                    ))
                    self.stats["successful"] += 1
                except Exception as e:
                    results.append(TaskResult(
                        task_id=f"task_{idx}",
                        success=False,
                        result=None,
                        error=str(e),
                        execution_time=time.time() - task_start,
                        timestamp=datetime.now().isoformat()
                    ))
                    self.stats["failed"] += 1
                
                self.stats["total_tasks"] += 1
        
        total_time = time.time() - start_time
        self.stats["total_time"] += total_time
        self.stats["avg_time"] = self.stats["total_time"] / max(self.stats["total_tasks"], 1)
        
        logger.info(f"✅ Processed {len(results)} items in {total_time:.2f}s "
                   f"(Success: {self.stats['successful']}, Failed: {self.stats['failed']})")
        
        return results
    
    # ============================================================
    # ۲. پردازش دسته‌ای (Batch)
    # ============================================================
    
    def process_batch(
        self,
        items: List[Any],
        func: Callable[[List[Any]], List[R]],
        batch_size: int = 5,
        max_workers: Optional[int] = None
    ) -> List[TaskResult[R]]:
        """
        پردازش دسته‌ای با تقسیم به Batch
        
        پارامترها:
            items: لیست آیتم‌ها
            func: تابع پردازش دسته‌ای
            batch_size: اندازه هر Batch
            max_workers: تعداد Threadها
        
        خروجی:
            لیستی از TaskResult
        """
        if not items:
            return []
        
        # تقسیم به Batch
        batches = []
        for i in range(0, len(items), batch_size):
            batches.append(items[i:i+batch_size])
        
        # پردازش موازی Batchها
        def process_batch(batch: List[Any]) -> List[R]:
            return func(batch)
        
        results = self.process_parallel(
            batches,
            process_batch,
            max_workers=max_workers
        )
        
        # flatten کردن نتایج
        flat_results = []
        for result in results:
            if result.success and result.result:
                for item_result in result.result:
                    flat_results.append(TaskResult(
                        task_id=result.task_id,
                        success=True,
                        result=item_result,
                        error=None,
                        execution_time=result.execution_time,
                        timestamp=result.timestamp
                    ))
            else:
                flat_results.append(result)
        
        return flat_results
    
    # ============================================================
    # ۳. پردازش Async (غیرمترقبه)
    # ============================================================
    
    async def process_async(
        self,
        items: List[Any],
        func: Callable[[Any], R],
        max_concurrent: int = 10
    ) -> List[TaskResult[R]]:
        """
        پردازش غیرمترقبه با asyncio
        
        پارامترها:
            items: لیست آیتم‌ها
            func: تابع async پردازش
            max_concurrent: تعداد همزمانی
        
        خروجی:
            لیستی از TaskResult
        """
        if not items:
            return []
        
        semaphore = asyncio.Semaphore(max_concurrent)
        results = []
        
        async def process_item(item: Any) -> TaskResult:
            async with semaphore:
                task_start = time.time()
                try:
                    if asyncio.iscoroutinefunction(func):
                        result = await func(item)
                    else:
                        result = func(item)  # Fallback
                    
                    return TaskResult(
                        task_id=f"async_{id(item)}",
                        success=True,
                        result=result,
                        error=None,
                        execution_time=time.time() - task_start,
                        timestamp=datetime.now().isoformat()
                    )
                except Exception as e:
                    return TaskResult(
                        task_id=f"async_{id(item)}",
                        success=False,
                        result=None,
                        error=str(e),
                        execution_time=time.time() - task_start,
                        timestamp=datetime.now().isoformat()
                    )
        
        # اجرای همزمان همه تسک‌ها
        tasks = [process_item(item) for item in items]
        results = await asyncio.gather(*tasks)
        
        # به‌روزرسانی آمار
        successful = sum(1 for r in results if r.success)
        failed = len(results) - successful
        self.stats["total_tasks"] += len(results)
        self.stats["successful"] += successful
        self.stats["failed"] += failed
        
        logger.info(f"✅ Async processed {len(results)} items "
                   f"(Success: {successful}, Failed: {failed})")
        
        return results
    
    # ============================================================
    # ۴. پردازش سنگین با Process Pool
    # ============================================================
    
    def process_heavy(
        self,
        items: List[Any],
        func: Callable[[Any], R],
        max_workers: int = 4
    ) -> List[TaskResult[R]]:
        """
        پردازش سنگین (CPU-bound) با Process Pool
        
        پارامترها:
            items: لیست آیتم‌ها
            func: تابع پردازش
            max_workers: تعداد Processها
        
        خروجی:
            لیستی از TaskResult
        """
        if not items:
            return []
        
        results = []
        start_time = time.time()
        
        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(func, item) for item in items]
            
            for idx, future in enumerate(futures):
                task_start = time.time()
                try:
                    result = future.result(timeout=120)  # ۲ دقیقه برای عملیات سنگین
                    results.append(TaskResult(
                        task_id=f"heavy_{idx}",
                        success=True,
                        result=result,
                        error=None,
                        execution_time=time.time() - task_start,
                        timestamp=datetime.now().isoformat()
                    ))
                except Exception as e:
                    results.append(TaskResult(
                        task_id=f"heavy_{idx}",
                        success=False,
                        result=None,
                        error=str(e),
                        execution_time=time.time() - task_start,
                        timestamp=datetime.now().isoformat()
                    ))
        
        total_time = time.time() - start_time
        logger.info(f"✅ Heavy processing completed in {total_time:.2f}s")
        
        return results
    
    # ============================================================
    # ۵. ابزارهای کمکی
    # ============================================================
    
    def get_stats(self) -> Dict[str, Any]:
        """دریافت آمار"""
        return {
            **self.stats,
            "thread_pool": {
                "max_workers": self.thread_pool._max_workers
            },
            "process_pool": {
                "max_workers": self.process_pool._max_workers
            },
            "timestamp": datetime.now().isoformat()
        }
    
    def shutdown(self):
        """خاموش کردن ایمن Poolها"""
        self.thread_pool.shutdown(wait=True)
        self.process_pool.shutdown(wait=True)
        logger.info("✅ ParallelProcessor shutdown complete")


# نمونه Singleton
parallel_processor = ParallelProcessor()
