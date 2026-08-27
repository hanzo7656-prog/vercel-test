#!/usr/bin/env python3
# scripts/train_model.py
# ============================================================
# اسکریپت خط فرمان برای آموزش مدل
# ============================================================

"""
استفاده:
    python scripts/train_model.py --period 1m
    python scripts/train_model.py --period 3m --no-save
"""

import os
import sys

# اضافه کردن مسیر پروژه
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.trainer.manual_trainer import main

if __name__ == "__main__":
    main()
