# models/trainer/manual_trainer.py
# ============================================================
# آموزش دستی مدل - برای اجرای از خط فرمان
# ============================================================

import os
import sys
import argparse
import logging
from datetime import datetime

# اضافه کردن مسیر پروژه
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from api_handler import CoinStatsAPI
from models.manager.model_manager import ModelManager
from models.trainer.auto_trainer import AutoTrainer

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def train_model(period: str = "1m", save: bool = True):
    """
    آموزش دستی مدل
    
    پارامترها:
        period: بازه زمانی (1w, 1m, 3m, 6m)
        save: آیا مدل ذخیره شود؟
    """
    logger.info(f"🚀 شروع آموزش دستی مدل (بازه: {period})")
    
    # راه‌اندازی
    api = CoinStatsAPI()
    model_manager = ModelManager(api)
    trainer = AutoTrainer(api, model_manager)
    
    # آموزش
    result = trainer.train_model(period=period)
    
    if result.get("success"):
        logger.info(f"✅ آموزش با موفقیت انجام شد!")
        logger.info(f"   دقت: {result.get('accuracy', 0):.3f}")
        logger.info(f"   نسخه: {result.get('version', 'N/A')}")
        logger.info(f"   نمونه‌ها: {result.get('samples', 0)}")
    else:
        logger.error(f"❌ آموزش ناموفق: {result.get('message', 'خطای ناشناخته')}")
    
    return result


def main():
    parser = argparse.ArgumentParser(description='آموزش دستی مدل XGBoost')
    parser.add_argument(
        '--period', 
        type=str, 
        default='1m',
        choices=['1w', '1m', '3m', '6m'],
        help='بازه زمانی داده‌ها (پیش‌فرض: 1m)'
    )
    parser.add_argument(
        '--no-save',
        action='store_true',
        help='مدل ذخیره نشود (فقط تست)'
    )
    
    args = parser.parse_args()
    
    train_model(
        period=args.period,
        save=not args.no_save
    )


if __name__ == "__main__":
    main()
