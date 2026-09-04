# core/__init__.py
# ============================================================
# پکیج Core - با تضمین SelfHealer
# ============================================================

import logging

logger = logging.getLogger(__name__)

# ===== Import های اصلی =====
from core.metrics import MetricsScheduler
from core.threading_manager import threading_manager
from core.feature_engineering import FeatureEngineer

# ===== ساخت metrics_scheduler با تضمین SelfHealer =====
_metrics_scheduler = None

def get_metrics_scheduler():
    """دریافت metrics_scheduler با تضمین SelfHealer"""
    global _metrics_scheduler
    
    if _metrics_scheduler is None:
        logger.info("🔧 Creating metrics_scheduler...")
        _metrics_scheduler = MetricsScheduler()
        
        # ===== تضمین SelfHealer =====
        if _metrics_scheduler.healer is None:
            logger.warning("⚠️ SelfHealer was None, forcing creation...")
            try:
                from infrastructure.api.coinstats_client import coinstats_client
                from models.manager.model_manager import ModelManager
                from models.trainer.auto_trainer import AutoTrainer
                from application.services.self_healer import SelfHealer
                
                model_manager = ModelManager(api=coinstats_client)
                trainer = AutoTrainer(api=coinstats_client, model_manager=model_manager)
                healer = SelfHealer(
                    model_manager=model_manager,
                    trainer=trainer,
                    api_client=coinstats_client
                )
                
                _metrics_scheduler.healer = healer
                logger.info("✅ SelfHealer forced into metrics_scheduler")
                
                # تست
                if healer:
                    status = healer.get_healing_status()
                    logger.info(f"📊 SelfHealer status: {status}")
                
            except Exception as e:
                logger.error(f"❌ SelfHealer force creation failed: {e}")
                import traceback
                logger.error(traceback.format_exc())
    
    return _metrics_scheduler

metrics_scheduler = get_metrics_scheduler()

# ===== system (Lazy Loading) =====
def get_system():
    """دریافت نمونه system با Lazy Loading"""
    from core.system import system
    return system

# ===== Export ها =====
__all__ = [
    'metrics_scheduler',
    'get_metrics_scheduler',
    'threading_manager',
    'FeatureEngineer',
    'get_system'
]
