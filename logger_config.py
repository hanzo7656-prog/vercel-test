# logger_config.py
# ============================================================
# پیکربندی پیشرفته لاگینگ - نسخه ۱.۰
# ============================================================

import os
import logging
import logging.handlers
from pathlib import Path
from datetime import datetime


class LoggerConfig:
    """پیکربندی مرکزی لاگینگ برای کل سیستم"""
    
    _instance = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        
        # ایجاد پوشه لاگ
        self.log_dir = Path("logs")
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # پیکربندی لاگر اصلی
        self.logger = logging.getLogger("system")
        self.logger.setLevel(logging.INFO)
        
        # فرمت لاگ
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # ۱. لاگ در فایل (با چرخش روزانه)
        log_file = self.log_dir / "system.log"
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=10_485_760,  # 10 MB
            backupCount=5,
            encoding='utf-8'
        )
        file_handler.setFormatter(formatter)
        self.logger.addHandler(file_handler)
        
        # ۲. لاگ خطاها در فایل جداگانه
        error_file = self.log_dir / "errors.log"
        error_handler = logging.handlers.RotatingFileHandler(
            error_file,
            maxBytes=5_242_880,  # 5 MB
            backupCount=3,
            encoding='utf-8'
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(formatter)
        self.logger.addHandler(error_handler)
        
        # ۳. لاگ در کنسول (برای دیباگ)
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)
        
        # لاگرهای جداگانه برای بخش‌های مختلف
        self.loggers = {
            "api": self._create_logger("api"),
            "model": self._create_logger("model"),
            "database": self._create_logger("database"),
            "alert": self._create_logger("alert"),
            "command": self._create_logger("command"),
        }
        
        self.logger.info("✅ LoggerConfig initialized")
    
    def _create_logger(self, name: str) -> logging.Logger:
        """ایجاد لاگر برای بخش خاص"""
        logger = logging.getLogger(f"system.{name}")
        logger.setLevel(logging.INFO)
        
        # فایل جداگانه برای هر بخش
        log_file = self.log_dir / f"{name}.log"
        handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=5_242_880,  # 5 MB
            backupCount=3,
            encoding='utf-8'
        )
        handler.setFormatter(
            logging.Formatter(
                '%(asctime)s - %(levelname)s - %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
        )
        logger.addHandler(handler)
        
        return logger
    
    def get_logger(self, name: str = None) -> logging.Logger:
        """دریافت لاگر"""
        if name and name in self.loggers:
            return self.loggers[name]
        return self.logger
    
    def get_logs(self, log_type: str = "system", lines: int = 100) -> list:
        """خواندن لاگ‌های اخیر"""
        log_file = self.log_dir / f"{log_type}.log"
        if not log_file.exists():
            return []
        
        try:
            with open(log_file, 'r', encoding='utf-8') as f:
                lines_list = f.readlines()
                return lines_list[-lines:]
        except Exception as e:
            return [f"⚠️ خطا در خواندن لاگ: {e}"]


# نمونه Singleton
logger_config = LoggerConfig()

# توابع کمکی برای استفاده آسان
def get_logger(name: str = None):
    return logger_config.get_logger(name)

def get_recent_logs(log_type: str = "system", lines: int = 100):
    return logger_config.get_logs(log_type, lines)
