# application/use_cases/train_model.py
# ============================================================
# Use Case: Train Model - نسخه ۲.۰
# Profile Support + Strategy + Batch
# ============================================================

import logging
from typing import Optional, Dict, Any, List
from datetime import datetime

from domain.interfaces.api_client import APIClient
from models.manager.model_manager import ModelManager
from models.trainer.auto_trainer import AutoTrainer

logger = logging.getLogger(__name__)


class TrainModelUseCase:
    """
    Use Case آموزش مدل
    
    ارتقاها:
        - Profile support (preset یا custom)
        - Strategy support
        - Batch training (A/B)
        - Quota check
        - Analytics recording
    """
    
    def __init__(
        self,
        api_client: APIClient,
        model_manager: ModelManager,
        trainer: AutoTrainer,
    ) -> None:
        self.api_client = api_client
        self.model_manager = model_manager
        self.trainer = trainer
        
        logger.info("✅ TrainModelUseCase v2.0 initialized")
    
    # ============================================================
    # Execute - Single Training
    # ============================================================
    
    def execute(
        self,
        period: str = "1m",
        coins: Optional[List[str]] = None,
        profile_name: Optional[str] = None,
        profile: Optional[Dict[str, Any]] = None,
        strategy: Optional[str] = None,
        save: bool = True,
    ) -> Dict[str, Any]:
        """
        اجرای آموزش
        
        پارامترها:
            period: بازه
            coins: لیست ارزها
            profile_name: نام پروفایل (preset یا DB)
            profile: پروفایل مستقیم
            strategy: استراتژی (override)
            save: ذخیره بشه؟
        
        خروجی:
            نتیجه آموزش
        """
        logger.info(
            f"🔄 Starting training "
            f"(period: {period}, "
            f"profile: {profile_name or profile.get('name') if profile else 'active'}, "
            f"strategy: {strategy}, "
            f"coins: {coins})"
        )
        
        try:
            # آموزش
            result = self.trainer.train_model(
                period=period,
                coins=coins,
                profile_name=profile_name,
                profile=profile,
                strategy=strategy,
                save=save,
            )
            
            # افزودن metadata
            result["timestamp"] = datetime.now().isoformat()
            result["coins_requested"] = coins
            result["period"] = period
            result["profile_name"] = profile_name
            result["strategy"] = strategy
            
            if result.get("success"):
                logger.info(
                    f"✅ Training completed: "
                    f"version={result.get('version')}, "
                    f"accuracy={result.get('accuracy', 0):.3f}"
                )
            else:
                logger.warning(
                    f"❌ Training failed: {result.get('error')}"
                )
            
            return result
            
        except Exception as e:
            logger.error(f"❌ Training failed: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            }
    
    # ============================================================
    # Execute - Batch Training (A/B Testing) 🆕
    # ============================================================
    
    def execute_batch(
        self,
        profiles: List[str],
        period: str = "1m",
        coins: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        A/B Testing (آموزش با چند پروفایل)
        
        پارامترها:
            profiles: لیست نام پروفایل‌ها
            period: بازه
            coins: ارزها
        
        خروجی:
            دیکشنری با بهترین profile
        """
        logger.info(
            f"🧪 A/B Testing started "
            f"(profiles: {profiles}, period: {period})"
        )
        
        try:
            result = self.trainer.train_batch(
                profiles=profiles,
                period=period,
                coins=coins,
            )
            
            result["timestamp"] = datetime.now().isoformat()
            
            if result.get("success"):
                logger.info(
                    f"✅ A/B Testing completed: "
                    f"best_profile={result.get('best_profile')}, "
                    f"accuracy={result.get('best_accuracy', 0):.3f}"
                )
            
            return result
            
        except Exception as e:
            logger.error(f"❌ Batch training failed: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            }
    
    # ============================================================
    # Execute - Auto Training
    # ============================================================
    
    def execute_auto(
        self,
        interval_hours: int = 6,
        period: str = "1m",
        profile_name: str = "balanced",
        coins: Optional[List[str]] = None,
        incremental: bool = False,
    ) -> Dict[str, Any]:
        """
        شروع آموزش خودکار
        
        پارامترها:
            interval_hours: فاصله (ساعت)
            period: بازه
            profile_name: نام پروفایل
            coins: ارزها
            incremental: افزایشی؟
        
        خروجی:
            نتیجه شروع
        """
        try:
            result = self.trainer.start_auto_train(
                interval_hours=interval_hours,
                period=period,
                profile_name=profile_name,
                coins=coins,
                incremental=incremental,
            )
            
            result["timestamp"] = datetime.now().isoformat()
            
            return result
            
        except Exception as e:
            logger.error(f"❌ Auto training start failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            }
    
    def stop_auto(self) -> Dict[str, Any]:
        """متوقف کردن آموزش خودکار"""
        try:
            result = self.trainer.stop_auto_train()
            result["timestamp"] = datetime.now().isoformat()
            return result
        except Exception as e:
            logger.error(f"❌ Auto training stop failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            }
    
    # ============================================================
    # Status
    # ============================================================
    
    def get_status(self) -> Dict[str, Any]:
        """دریافت وضعیت آموزش"""
        try:
            stats = (
                self.trainer.get_stats()
                if hasattr(self.trainer, "get_stats") else {}
            )
            
            return {
                "is_training": stats.get("is_training", False),
                "is_running": stats.get("is_running", False),
                "model_loaded": self.model_manager.current_model is not None,
                "model_version": self.model_manager.current_version,
                "last_score": stats.get("stats", {}).get("last_score"),
                "total_trainings": stats.get("stats", {}).get("total_trainings", 0),
                "successful_trainings": stats.get("stats", {}).get("successful_trainings", 0),
                "failed_trainings": stats.get("stats", {}).get("failed_trainings", 0),
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            logger.error(f"❌ Get status error: {e}")
            return {
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            }
