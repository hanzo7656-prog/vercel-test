# core/rule_engine/batch_processor.py
# ============================================================
# Batch Processor - پردازش موازی دسته‌ای symbolها
# نسخه ۱.۰
# ============================================================
# 
# نقش:
#   ۱. تقسیم symbolها به batch
#   ۲. Fetch موازی OHLCV (async + semaphore)
#   ۳. محاسبه اندیکاتورها (thread pool)
#   ۴. ارزیابی قوانین
#   ۵. برگرداندن لیست Prediction
# 
# چرا batch؟
#   - محدودیت rate limit API
#   - مدیریت مصرف CPU
#   - قابل تنظیم (۱۵، ۳۰، ۴۵)
# ============================================================

import asyncio
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

import pandas as pd

from core.rule_engine.models import Prediction
from core.rule_engine.engine import RuleEngine

logger = logging.getLogger(__name__)


# ============================================================
# BatchProcessor
# ============================================================

class BatchProcessor:
    """
    پردازشگر دسته‌ای symbolها
    
    Attributes:
        engine: RuleEngine برای ارزیابی
        data_fetcher: تابع fetch OHLCV (callable)
        batch_size: اندازه هر batch
        max_concurrent_fetches: حداکثر fetch همزمان
        max_workers: تعداد thread برای CPU
    """
    
    DEFAULT_BATCH_SIZE = 30
    DEFAULT_MAX_CONCURRENT = 10
    DEFAULT_MAX_WORKERS = 4
    
    def __init__(
        self,
        engine: RuleEngine,
        data_fetcher: Callable[[str, str], Optional[pd.DataFrame]],
        batch_size: int = DEFAULT_BATCH_SIZE,
        max_concurrent_fetches: int = DEFAULT_MAX_CONCURRENT,
        max_workers: int = DEFAULT_MAX_WORKERS,
        timeframe: str = "4h",
        candle_limit: int = 100,
    ) -> None:
        """
        Args:
            engine: RuleEngine
            data_fetcher: تابع (symbol, timeframe) → DataFrame
            batch_size: اندازه batch (۱۵، ۳۰، ۴۵)
            max_concurrent_fetches: حداکثر fetch همزمان
            max_workers: تعداد thread برای compute
            timeframe: تایم‌فریم OHLCV
            candle_limit: تعداد کندل
        """
        self.engine = engine
        self.data_fetcher = data_fetcher
        self.batch_size = int(batch_size)
        self.max_concurrent = int(max_concurrent_fetches)
        self.max_workers = int(max_workers)
        self.timeframe = timeframe
        self.candle_limit = candle_limit
        
        logger.info(
            f"✅ BatchProcessor initialized "
            f"(batch_size={batch_size}, "
            f"concurrent={max_concurrent_fetches}, "
            f"workers={max_workers})"
        )
    
    # ============================================================
    # Main Public API
    # ============================================================
    
    def process(
        self,
        symbols: List[Dict[str, str]],
        update_state: bool = True,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> List[Prediction]:
        """
        پردازش کامل لیست symbolها
        
        Args:
            symbols: لیست دیکشنری {symbol, coin_id}
            update_state: آپدیت state؟
            progress_callback: (done, total) برای نمایش پیشرفت
        
        Returns:
            لیست Predictionهای مرتب‌شده
        """
        start_time = time.time()
        total = len(symbols)
        
        logger.info(
            f"🔄 Batch processing started: "
            f"{total} symbols, batch_size={self.batch_size}"
        )
        
        # تقسیم به batch
        batches = self._chunk(symbols, self.batch_size)
        
        # جمع‌آوری نتایج
        all_predictions: List[Prediction] = []
        processed = 0
        errors = 0
        
        for batch_idx, batch in enumerate(batches, 1):
            try:
                batch_predictions = self._process_batch(
                    batch=batch,
                    update_state=update_state,
                )
                all_predictions.extend(batch_predictions)
                processed += len(batch)
                
                logger.debug(
                    f"  Batch {batch_idx}/{len(batches)}: "
                    f"{len(batch_predictions)} passed "
                    f"(from {len(batch)})"
                )
                
                if progress_callback:
                    try:
                        progress_callback(processed, total)
                    except Exception:
                        pass
                        
            except Exception as e:
                errors += len(batch)
                logger.error(f"❌ Batch {batch_idx} failed: {e}", exc_info=True)
        
        # مرتب‌سازی نهایی
        all_predictions.sort(key=lambda p: p.score, reverse=True)
        for i, pred in enumerate(all_predictions, 1):
            pred.rank = i
        
        duration = time.time() - start_time
        
        logger.info(
            f"✅ Batch processing done: "
            f"{len(all_predictions)} passed "
            f"from {total} symbols "
            f"({duration:.2f}s, {errors} errors)"
        )
        
        return all_predictions
    
    # ============================================================
    # Internal - Batch Processing
    # ============================================================
    
    def _process_batch(
        self,
        batch: List[Dict[str, str]],
        update_state: bool = True,
    ) -> List[Prediction]:
        """
        پردازش یک batch
        
        مراحل:
            ۱. Fetch موازی OHLCV (async)
            ۲. محاسبه موازی اندیکاتورها (thread)
            ۳. ارزیابی سری قوانین
        """
        # ============================================================
        # ۱. Fetch موازی
        # ============================================================
        
        data_map = self._fetch_batch_parallel(batch)
        
        if not data_map:
            return []
        
        # ============================================================
        # ۲. ارزیابی با RuleEngine
        # ============================================================
        
        # فیلتر symbolهایی که داده داریم
        valid_symbols = [
            item for item in batch
            if item["symbol"] in data_map
        ]
        
        if not valid_symbols:
            return []
        
        try:
            predictions = self.engine.evaluate_batch(
                symbols=valid_symbols,
                data_map=data_map,
                update_state=update_state,
            )
            return predictions
        except Exception as e:
            logger.error(f"❌ Engine batch evaluation failed: {e}", exc_info=True)
            return []
    
    # ============================================================
    # Internal - Parallel Fetch
    # ============================================================
    
    def _fetch_batch_parallel(
        self,
        batch: List[Dict[str, str]],
    ) -> Dict[str, pd.DataFrame]:
        """
        Fetch موازی OHLCV برای یک batch
        
        استفاده از asyncio.run با semaphore
        """
        data_map: Dict[str, pd.DataFrame] = {}
        
        try:
            results = asyncio.run(
                self._async_fetch_all(batch)
            )
            
            for symbol, df in results:
                if df is not None and not df.empty:
                    data_map[symbol] = df
                    
        except RuntimeError as e:
            # اگه داخل event loop هستیم
            logger.warning(
                f"⚠️ Cannot use asyncio.run (already in loop): {e}. "
                f"Falling back to thread pool."
            )
            data_map = self._fetch_batch_threaded(batch)
        except Exception as e:
            logger.error(f"❌ Parallel fetch failed: {e}", exc_info=True)
            data_map = self._fetch_batch_threaded(batch)
        
        return data_map
    
    async def _async_fetch_all(
        self,
        batch: List[Dict[str, str]],
    ) -> List[Tuple[str, Optional[pd.DataFrame]]]:
        """
        Fetch همه symbolها با محدودیت همزمانی
        """
        semaphore = asyncio.Semaphore(self.max_concurrent)
        
        async def fetch_one(symbol: str) -> Tuple[str, Optional[pd.DataFrame]]:
            async with semaphore:
                try:
                    # اجرا در thread تا event loop بلاک نشه
                    df = await asyncio.to_thread(
                        self._safe_fetch,
                        symbol,
                    )
                    return (symbol, df)
                except Exception as e:
                    logger.debug(f"Fetch failed for {symbol}: {e}")
                    return (symbol, None)
        
        tasks = [
            fetch_one(item["symbol"])
            for item in batch
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # فیلتر exceptionها
        clean_results: List[Tuple[str, Optional[pd.DataFrame]]] = []
        for item in results:
            if isinstance(item, Exception):
                continue
            clean_results.append(item)
        
        return clean_results
    
    def _fetch_batch_threaded(
        self,
        batch: List[Dict[str, str]],
    ) -> Dict[str, pd.DataFrame]:
        """
        Fallback: fetch موازی با ThreadPoolExecutor
        """
        data_map: Dict[str, pd.DataFrame] = {}
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(self._safe_fetch, item["symbol"]): item["symbol"]
                for item in batch
            }
            
            for future in as_completed(futures):
                symbol = futures[future]
                try:
                    df = future.result(timeout=30)
                    if df is not None and not df.empty:
                        data_map[symbol] = df
                except Exception as e:
                    logger.debug(f"Threaded fetch failed for {symbol}: {e}")
        
        return data_map
    
    def _safe_fetch(self, symbol: str) -> Optional[pd.DataFrame]:
        """
        Fetch ایمن یه symbol با error handling
        """
        try:
            df = self.data_fetcher(
                symbol=symbol,
                timeframe=self.timeframe,
            )
            
            if df is None or df.empty:
                return None
            
            # برش به candle_limit
            if len(df) > self.candle_limit:
                df = df.iloc[-self.candle_limit:]
            
            return df
        except Exception as e:
            logger.debug(f"Safe fetch failed for {symbol}: {e}")
            return None
    
    # ============================================================
    # Internal - Helpers
    # ============================================================
    
    @staticmethod
    def _chunk(
        items: List[Any],
        size: int,
    ) -> List[List[Any]]:
        """تقسیم لیست به chunkهای با اندازه مشخص"""
        if size <= 0:
            size = 1
        return [items[i:i + size] for i in range(0, len(items), size)]
    
    # ============================================================
    # Config
    # ============================================================
    
    def update_config(
        self,
        batch_size: Optional[int] = None,
        max_concurrent: Optional[int] = None,
        max_workers: Optional[int] = None,
        timeframe: Optional[str] = None,
        candle_limit: Optional[int] = None,
    ) -> None:
        """آپدیت runtime تنظیمات"""
        if batch_size is not None:
            self.batch_size = max(1, int(batch_size))
        if max_concurrent is not None:
            self.max_concurrent = max(1, int(max_concurrent))
        if max_workers is not None:
            self.max_workers = max(1, int(max_workers))
        if timeframe is not None:
            self.timeframe = timeframe
        if candle_limit is not None:
            self.candle_limit = max(20, int(candle_limit))
        
        logger.info(
            f"🔄 BatchProcessor config updated: "
            f"batch_size={self.batch_size}, "
            f"concurrent={self.max_concurrent}"
        )
    
    def get_stats(self) -> Dict[str, Any]:
        """آمار Batch Processor"""
        return {
            "batch_size": self.batch_size,
            "max_concurrent": self.max_concurrent,
            "max_workers": self.max_workers,
            "timeframe": self.timeframe,
            "candle_limit": self.candle_limit,
        }


__all__ = ["BatchProcessor"]
