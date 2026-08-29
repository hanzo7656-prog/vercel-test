# services/batch_processor.py
# ============================================================
# پردازشگر دسته‌ای - برای عملیات سنگین
# ============================================================

import logging
import time
from typing import List, Dict, Any, Callable, Optional
from datetime import datetime
from dataclasses import dataclass
from enum import Enum

from core.parallel_processor import parallel_processor

logger = logging.getLogger(__name__)


class BatchStatus(Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class BatchJob:
    """یک Job دسته‌ای"""
    job_id: str
    status: BatchStatus
    total_items: int
    processed_items: int
    success_items: int
    failed_items: int
    start_time: datetime
    end_time: Optional[datetime]
    results: List[Any]
    errors: List[str]


class BatchProcessor:
    """
    پردازشگر دسته‌ای برای عملیات سنگین و طولانی
    """
    
    _instance = None
    _jobs: Dict[str, BatchJob] = {}
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if hasattr(self, '_initialized'):
            return
        self._initialized = True
        self._job_counter = 0
        logger.info("✅ BatchProcessor initialized")
    
    # ============================================================
    # ۱. ایجاد و اجرای Job
    # ============================================================
    
    def submit_batch(
        self,
        items: List[Any],
        processor: Callable[[Any], Any],
        batch_size: int = 10,
        max_workers: int = 5
    ) -> str:
        """
        ثبت و اجرای یک Job دسته‌ای
        
        پارامترها:
            items: آیتم‌های پردازش
            processor: تابع پردازش
            batch_size: اندازه هر Batch
            max_workers: تعداد Threadها
        
        خروجی:
            job_id: شناسه Job
        """
        if not items:
            logger.warning("⚠️ No items to process")
            return ""
        
        self._job_counter += 1
        job_id = f"batch_{self._job_counter}_{int(time.time())}"
        
        job = BatchJob(
            job_id=job_id,
            status=BatchStatus.PROCESSING,
            total_items=len(items),
            processed_items=0,
            success_items=0,
            failed_items=0,
            start_time=datetime.now(),
            end_time=None,
            results=[],
            errors=[]
        )
        
        self._jobs[job_id] = job
        
        # پردازش در پس‌زمینه با Thread
        def process_job():
            try:
                # پردازش موازی با Batch
                results = parallel_processor.process_batch(
                    items,
                    processor,
                    batch_size=batch_size,
                    max_workers=max_workers
                )
                
                # به‌روزرسانی Job
                job.processed_items = len(results)
                job.results = []
                job.errors = []
                
                for result in results:
                    if result.success:
                        job.success_items += 1
                        job.results.append(result.result)
                    else:
                        job.failed_items += 1
                        job.errors.append(result.error or "Unknown error")
                
                job.status = BatchStatus.COMPLETED
                job.end_time = datetime.now()
                
                logger.info(f"✅ Batch job {job_id} completed "
                           f"(Success: {job.success_items}, Failed: {job.failed_items})")
                           
            except Exception as e:
                job.status = BatchStatus.FAILED
                job.end_time = datetime.now()
                job.errors.append(str(e))
                logger.error(f"❌ Batch job {job_id} failed: {e}")
        
        # اجرا در Thread Pool
        from concurrent.futures import ThreadPoolExecutor
        executor = ThreadPoolExecutor(max_workers=1)
        executor.submit(process_job)
        
        return job_id
    
    # ============================================================
    # ۲. دریافت وضعیت Job
    # ============================================================
    
    def get_job_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        """دریافت وضعیت یک Job"""
        job = self._jobs.get(job_id)
        if not job:
            return None
        
        return {
            "job_id": job.job_id,
            "status": job.status.value,
            "total_items": job.total_items,
            "processed_items": job.processed_items,
            "success_items": job.success_items,
            "failed_items": job.failed_items,
            "progress": round(
                job.processed_items / job.total_items * 100 
                if job.total_items > 0 else 0,
                2
            ),
            "start_time": job.start_time.isoformat(),
            "end_time": job.end_time.isoformat() if job.end_time else None,
            "duration_seconds": (
                (job.end_time - job.start_time).total_seconds() 
                if job.end_time else None
            ),
            "errors": job.errors[-5:],  # فقط ۵ خطای آخر
            "results_count": len(job.results)
        }
    
    def get_all_jobs(self) -> List[Dict[str, Any]]:
        """دریافت همه Jobs"""
        return [self.get_job_status(job_id) for job_id in self._jobs.keys()]
    
    def get_job_results(self, job_id: str) -> Optional[List[Any]]:
        """دریافت نتایج یک Job"""
        job = self._jobs.get(job_id)
        if job and job.status in [BatchStatus.COMPLETED]:
            return job.results
        return None
    
    # ============================================================
    # ۳. پاکسازی
    # ============================================================
    
    def cleanup_old_jobs(self, max_age_hours: int = 24):
        """پاکسازی Jobs قدیمی"""
        now = datetime.now()
        to_remove = []
        
        for job_id, job in self._jobs.items():
            if job.end_time:
                age_hours = (now - job.end_time).total_seconds() / 3600
                if age_hours > max_age_hours:
                    to_remove.append(job_id)
        
        for job_id in to_remove:
            del self._jobs[job_id]
        
        if to_remove:
            logger.info(f"🧹 Cleaned up {len(to_remove)} old jobs")


# نمونه Singleton
batch_processor = BatchProcessor()
