# infrastructure/repositories/prediction_repository.py
# ============================================================
# Repository: Prediction (پیش‌بینی‌ها)
# ============================================================

import logging
from typing import Optional, List, Dict, Any
from datetime import datetime

from domain.interfaces.repository import Repository
from domain.entities.prediction import Prediction
from infrastructure.database import get_primary

logger = logging.getLogger(__name__)


class PredictionRepository(Repository):
    """
    Repository برای مدیریت پیش‌بینی‌ها
    
    مسئولیت:
        - ذخیره پیش‌بینی‌ها
        - بازیابی پیش‌بینی‌ها
        - جستجوی پیش‌بینی‌ها
    """
    
    def __init__(self):
        self.db = get_primary()
        logger.info("✅ PredictionRepository initialized")
    
    def _ensure_db(self) -> bool:
        """اطمینان از اتصال دیتابیس"""
        if not self.db or not self.db.is_connected():
            self.db = get_primary()
            return self.db is not None and self.db.is_connected()
        return True
    
    # ============================================================
    # پیاده‌سازی Interface Repository
    # ============================================================
    
    def save(self, prediction: Prediction) -> Prediction:
        """
        ذخیره یک پیش‌بینی
        
        پارامترها:
            prediction: Entity Prediction
        
        خروجی:
            Prediction ذخیره شده
        """
        if not self._ensure_db():
            logger.error("Cannot save prediction: database not connected")
            return prediction
        
        try:
            query: str = """
                INSERT INTO predictions (
                    coin, coin_name, current_price, signal_type, confidence,
                    prediction_score, period, model_mode, timestamp, processing_time_ms, data_points
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """
            
            result = self.db.execute(query, (
                prediction.coin,
                prediction.coin_name,
                prediction.current_price,
                prediction.signal_type.value,
                prediction.confidence,
                prediction.prediction_score,
                prediction.period,
                prediction.model_mode,
                prediction.timestamp,
                prediction.processing_time_ms,
                prediction.data_points
            ))
            
            if result:
                prediction.id = result[0]['id']
                logger.debug(f"✅ Prediction saved: {prediction.coin} - {prediction.signal_type.value}")
            
            return prediction
            
        except Exception as e:
            logger.error(f"❌ Save prediction error: {e}", exc_info=True)
            return prediction
    
    def save_batch(self, predictions: List[Prediction]) -> List[Prediction]:
        """ذخیره چندین پیش‌بینی"""
        saved: List[Prediction] = []
        for prediction in predictions:
            saved.append(self.save(prediction))
        return saved
    
    def find_by_id(self, entity_id: int) -> Optional[Prediction]:
        """پیدا کردن پیش‌بینی با ID"""
        if not self._ensure_db():
            return None
        
        try:
            result = self.db.execute(
                "SELECT * FROM predictions WHERE id = %s",
                (entity_id,)
            )
            
            if not result:
                return None
            
            return self._row_to_prediction(result[0])
            
        except Exception as e:
            logger.error(f"❌ Find prediction by ID error: {e}")
            return None
    
    def find_all(self, limit: int = 100, offset: int = 0) -> List[Prediction]:
        """دریافت همه پیش‌بینی‌ها"""
        if not self._ensure_db():
            return []
        
        try:
            result = self.db.execute(
                "SELECT * FROM predictions ORDER BY id DESC LIMIT %s OFFSET %s",
                (limit, offset)
            )
            
            return [self._row_to_prediction(row) for row in result]
            
        except Exception as e:
            logger.error(f"❌ Find all predictions error: {e}")
            return []
    
    def delete(self, entity_id: int) -> bool:
        """حذف پیش‌بینی با ID"""
        if not self._ensure_db():
            return False
        
        try:
            self.db.execute("DELETE FROM predictions WHERE id = %s", (entity_id,))
            return True
        except Exception as e:
            logger.error(f"❌ Delete prediction error: {e}")
            return False
    
    def count(self) -> int:
        """تعداد کل پیش‌بینی‌ها"""
        if not self._ensure_db():
            return 0
        
        try:
            result = self.db.execute("SELECT COUNT(*) as count FROM predictions")
            return result[0]['count'] if result else 0
        except Exception as e:
            logger.error(f"❌ Count predictions error: {e}")
            return 0
    
    def find_by_criteria(self, criteria: Dict[str, Any]) -> List[Prediction]:
        """جستجوی پیش‌بینی‌ها با معیارها"""
        if not self._ensure_db():
            return []
        
        try:
            conditions: List[str] = []
            params: List[Any] = []
            
            for key, value in criteria.items():
                if key == 'coin':
                    conditions.append("coin = %s")
                    params.append(value)
                elif key == 'signal_type':
                    conditions.append("signal_type = %s")
                    params.append(value)
                elif key == 'period':
                    conditions.append("period = %s")
                    params.append(value)
                elif key == 'from_date':
                    conditions.append("timestamp >= %s")
                    params.append(value)
                elif key == 'to_date':
                    conditions.append("timestamp <= %s")
                    params.append(value)
                elif key == 'min_confidence':
                    conditions.append("confidence >= %s")
                    params.append(value)
            
            where_clause = " AND ".join(conditions) if conditions else "1=1"
            query = f"SELECT * FROM predictions WHERE {where_clause} ORDER BY timestamp DESC"
            
            result = self.db.execute(query, tuple(params))
            return [self._row_to_prediction(row) for row in result]
            
        except Exception as e:
            logger.error(f"❌ Find predictions by criteria error: {e}")
            return []
    
    def find_by_coin(self, coin: str, limit: int = 10) -> List[Prediction]:
        """دریافت پیش‌بینی‌های یک ارز"""
        return self.find_by_criteria({'coin': coin, 'limit': limit})
    
    def find_recent(self, limit: int = 10) -> List[Prediction]:
        """دریافت آخرین پیش‌بینی‌ها"""
        return self.find_all(limit=limit)
    
    def get_stats(self) -> Dict[str, Any]:
        """دریافت آمار پیش‌بینی‌ها"""
        if not self._ensure_db():
            return {"error": "Database not connected"}
        
        try:
            total = self.count()
            
            # تعداد بر اساس سیگنال
            signal_stats = self.db.execute("""
                SELECT signal_type, COUNT(*) as count
                FROM predictions
                GROUP BY signal_type
            """)
            
            # میانگین اطمینان
            confidence_stats = self.db.execute("""
                SELECT AVG(confidence) as avg_confidence,
                       MIN(confidence) as min_confidence,
                       MAX(confidence) as max_confidence
                FROM predictions
            """)
            
            return {
                "total_predictions": total,
                "signal_distribution": {row['signal_type']: row['count'] for row in signal_stats},
                "confidence": confidence_stats[0] if confidence_stats else {},
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"❌ Get prediction stats error: {e}")
            return {"error": str(e)}
    
    def _row_to_prediction(self, row: Dict[str, Any]) -> Prediction:
        """تبدیل ردیف دیتابیس به Entity Prediction"""
        from domain.entities.prediction import SignalType
        
        return Prediction(
            id=row['id'],
            coin=row['coin'],
            coin_name=row['coin_name'],
            current_price=float(row['current_price']),
            signal_type=SignalType(row['signal_type']),
            confidence=int(row['confidence']),
            prediction_score=float(row['prediction_score']),
            period=row['period'],
            model_mode=row['model_mode'],
            timestamp=row['timestamp'],
            processing_time_ms=float(row['processing_time_ms']),
            data_points=int(row['data_points'])
        )
