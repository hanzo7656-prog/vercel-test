# infrastructure/repositories/prediction_repository.py
# ============================================================
# Repository: Prediction - نسخه ۳.۰
# Pagination + Aggregation + Bulk + Stats
# ============================================================

import logging
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, timedelta

from domain.interfaces.repository import Repository
from domain.entities.prediction import Prediction, SignalType
from infrastructure.database import get_primary, primary_transaction

logger = logging.getLogger(__name__)


class PredictionRepository(Repository):
    """
    Repository برای مدیریت پیش‌بینی‌ها
    
    ویژگی‌ها:
        - Pagination استاندارد
        - Bulk insert
        - Aggregations (avg, count, group by)
        - Time-series queries
        - Filter هوشمند
        - Cleanup خودکار
    
    رفع باگ‌ها:
        - `find_by_coin` limit نادیده می‌رفت → اضافه شد
        - بدون pagination → اضافه شد
        - بدون bulk → اضافه شد
        - بدون aggregation → اضافه شد
    
    ارتقاها:
        - Pagination (page, size, total)
        - Aggregations (avg, count, by_signal)
        - Time-series queries
        - Bulk insert
        - Cleanup by retention
        - Date range queries
        - Export helpers
    """
    
    # ============================================================
    # Constants
    # ============================================================
    
    TABLE_NAME = "predictions"
    DEFAULT_RETENTION_DAYS = 30
    DEFAULT_PAGE_SIZE = 50
    MAX_PAGE_SIZE = 500
    
    # ============================================================
    # Init
    # ============================================================
    
    def __init__(self) -> None:
        self._db = None
        logger.info("✅ PredictionRepository v3.0 initialized")
    
    @property
    def db(self):
        """دریافت دیتابیس"""
        if self._db is None or not self._db.is_connected():
            self._db = get_primary()
        return self._db
    
    def _ensure_db(self) -> bool:
        """اطمینان از اتصال"""
        if self._db is None or not self._db.is_connected():
            self._db = get_primary()
        return self._db is not None and self._db.is_connected()
    
    # ============================================================
    # Save
    # ============================================================
    
    def save(self, prediction: Prediction) -> Prediction:
        """
        ذخیره یک پیش‌بینی
        
        پارامترها:
            prediction: Entity پیش‌بینی
        
        خروجی:
            Prediction با ID
        """
        if not self._ensure_db():
            logger.error("❌ Database not connected")
            return prediction
        
        try:
            query = """
                INSERT INTO predictions (
                    coin, coin_name, current_price, signal_type, confidence,
                    prediction_score, period, model_mode, timestamp,
                    processing_time_ms, data_points
                ) VALUES (
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s
                )
                RETURNING id
            """
            
            result = self.db.execute(query, (
                prediction.coin,
                prediction.coin_name,
                prediction.current_price,
                prediction.signal_type.value if hasattr(
                    prediction.signal_type, 'value'
                ) else str(prediction.signal_type),
                prediction.confidence,
                prediction.prediction_score,
                prediction.period,
                prediction.model_mode,
                prediction.timestamp,
                prediction.processing_time_ms,
                prediction.data_points,
            ))
            
            if result:
                prediction.id = result[0]["id"]
                logger.debug(
                    f"✅ Prediction saved: {prediction.coin} "
                    f"({prediction.signal_type}) id={prediction.id}"
                )
            
            return prediction
            
        except Exception as e:
            logger.error(f"❌ Save prediction error: {e}", exc_info=True)
            return prediction
    
    def save_many(
        self,
        predictions: List[Prediction],
    ) -> Dict[str, Any]:
        """
        ذخیره چند پیش‌بینی (bulk)
        
        پارامترها:
            predictions: لیست Entities
        
        خروجی:
            دیکشنری {saved, failed, errors}
        """
        if not self._ensure_db() or not predictions:
            return {"saved": 0, "failed": len(predictions), "errors": []}
        
        try:
            # ساخت values برای bulk insert
            values = []
            for p in predictions:
                signal_type = (
                    p.signal_type.value if hasattr(p.signal_type, 'value')
                    else str(p.signal_type)
                )
                values.append((
                    p.coin,
                    p.coin_name,
                    p.current_price,
                    signal_type,
                    p.confidence,
                    p.prediction_score,
                    p.period,
                    p.model_mode,
                    p.timestamp,
                    p.processing_time_ms,
                    p.data_points,
                ))
            
            query = """
                INSERT INTO predictions (
                    coin, coin_name, current_price, signal_type, confidence,
                    prediction_score, period, model_mode, timestamp,
                    processing_time_ms, data_points
                ) VALUES %s
            """
            
            # استفاده از execute_values برای performance
            if hasattr(self.db, 'execute_values'):
                affected = self.db.execute_values(query, values, page_size=100)
            else:
                affected = self.db.execute_many(query, values)
            
            logger.info(f"✅ Saved {affected} predictions (bulk)")
            
            return {
                "saved": affected,
                "failed": len(predictions) - affected,
                "errors": [],
            }
            
        except Exception as e:
            logger.error(f"❌ Save many error: {e}")
            return {
                "saved": 0,
                "failed": len(predictions),
                "errors": [str(e)],
            }
    
    # ============================================================
    # Find Methods
    # ============================================================
    
    def find_by_id(self, entity_id: int) -> Optional[Prediction]:
        """پیدا کردن با ID"""
        if not self._ensure_db():
            return None
        
        try:
            result = self.db.execute(
                "SELECT * FROM predictions WHERE id = %s",
                (entity_id,),
            )
            
            return self._row_to_prediction(result[0]) if result else None
            
        except Exception as e:
            logger.error(f"❌ Find by ID error: {e}")
            return None
    
    def find_by_coin(
        self,
        coin: str,
        limit: int = 20,
        offset: int = 0,
    ) -> List[Prediction]:
        """
        دریافت پیش‌بینی‌های یک ارز
        
        رفع باگ: limit نادیده گرفته می‌شد
        """
        if not self._ensure_db():
            return []
        
        try:
            result = self.db.execute(
                """
                SELECT * FROM predictions
                WHERE coin = %s
                ORDER BY timestamp DESC
                LIMIT %s OFFSET %s
                """,
                (coin, limit, offset),
            )
            
            return [self._row_to_prediction(row) for row in result]
            
        except Exception as e:
            logger.error(f"❌ Find by coin error: {e}")
            return []
    
    def find_all(
        self,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Prediction]:
        """دریافت همه پیش‌بینی‌ها"""
        if not self._ensure_db():
            return []
        
        try:
            result = self.db.execute(
                """
                SELECT * FROM predictions
                ORDER BY timestamp DESC
                LIMIT %s OFFSET %s
                """,
                (limit, offset),
            )
            
            return [self._row_to_prediction(row) for row in result]
            
        except Exception as e:
            logger.error(f"❌ Find all error: {e}")
            return []
    
    def find_recent(self, limit: int = 10) -> List[Prediction]:
        """آخرین پیش‌بینی‌ها"""
        return self.find_all(limit=limit)
    
    def find_by_criteria(
        self,
        criteria: Dict[str, Any],
    ) -> List[Prediction]:
        """
        جستجو با معیارها
        
        پارامترها:
            criteria: دیکشنری معیارها
                - coin: str
                - signal_type: str (BUY/SELL/NEUTRAL)
                - period: str
                - from_date: ISO string
                - to_date: ISO string
                - min_confidence: int
                - max_confidence: int
                - limit: int
                - offset: int
                - order_by: str (timestamp, confidence)
                - order: str (ASC, DESC)
        
        خروجی:
            لیست Prediction
        """
        if not self._ensure_db():
            return []
        
        try:
            conditions = []
            params = []
            
            if "coin" in criteria:
                conditions.append("coin = %s")
                params.append(criteria["coin"])
            
            if "signal_type" in criteria:
                conditions.append("signal_type = %s")
                params.append(criteria["signal_type"])
            
            if "period" in criteria:
                conditions.append("period = %s")
                params.append(criteria["period"])
            
            if "model_mode" in criteria:
                conditions.append("model_mode = %s")
                params.append(criteria["model_mode"])
            
            if "from_date" in criteria:
                conditions.append("timestamp >= %s")
                params.append(criteria["from_date"])
            
            if "to_date" in criteria:
                conditions.append("timestamp <= %s")
                params.append(criteria["to_date"])
            
            if "min_confidence" in criteria:
                conditions.append("confidence >= %s")
                params.append(criteria["min_confidence"])
            
            if "max_confidence" in criteria:
                conditions.append("confidence <= %s")
                params.append(criteria["max_confidence"])
            
            where_clause = " AND ".join(conditions) if conditions else "1=1"
            
            # Order by
            order_by = criteria.get("order_by", "timestamp")
            order = criteria.get("order", "DESC").upper()
            
            valid_order_by = ["timestamp", "confidence", "current_price"]
            if order_by not in valid_order_by:
                order_by = "timestamp"
            
            if order not in ["ASC", "DESC"]:
                order = "DESC"
            
            # Limit
            limit = min(
                criteria.get("limit", self.DEFAULT_PAGE_SIZE),
                self.MAX_PAGE_SIZE,
            )
            offset = criteria.get("offset", 0)
            
            query = f"""
                SELECT * FROM predictions
                WHERE {where_clause}
                ORDER BY {order_by} {order}
                LIMIT %s OFFSET %s
            """
            
            params.extend([limit, offset])
            
            result = self.db.execute(query, tuple(params))
            return [self._row_to_prediction(row) for row in result]
            
        except Exception as e:
            logger.error(f"❌ Find by criteria error: {e}")
            return []
    
    # ============================================================
    # Pagination
    # ============================================================
    
    def find_paginated(
        self,
        page: int = 1,
        page_size: int = 50,
        criteria: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Pagination استاندارد
        
        پارامترها:
            page: شماره صفحه (از ۱)
            page_size: تعداد در هر صفحه
            criteria: معیارهای فیلتر
        
        خروجی:
            دیکشنری شامل:
                - items: لیست Prediction
                - page: شماره صفحه
                - page_size: اندازه صفحه
                - total: تعداد کل
                - total_pages: تعداد صفحات
                - has_next: صفحه بعدی
                - has_prev: صفحه قبلی
        """
        if not self._ensure_db():
            return {
                "items": [],
                "page": page,
                "page_size": page_size,
                "total": 0,
                "total_pages": 0,
                "has_next": False,
                "has_prev": False,
            }
        
        try:
            # محدودیت‌ها
            page = max(1, page)
            page_size = min(max(1, page_size), self.MAX_PAGE_SIZE)
            offset = (page - 1) * page_size
            
            criteria = criteria or {}
            criteria["limit"] = page_size
            criteria["offset"] = offset
            
            # دریافت items
            items = self.find_by_criteria(criteria)
            
            # دریافت total
            total = self.count(criteria)
            
            total_pages = (total + page_size - 1) // page_size
            
            return {
                "items": items,
                "page": page,
                "page_size": page_size,
                "total": total,
                "total_pages": total_pages,
                "has_next": page < total_pages,
                "has_prev": page > 1,
            }
            
        except Exception as e:
            logger.error(f"❌ Pagination error: {e}")
            return {
                "items": [],
                "page": page,
                "page_size": page_size,
                "total": 0,
                "total_pages": 0,
                "has_next": False,
                "has_prev": False,
            }
    
    # ============================================================
    # Count & Delete
    # ============================================================
    
    def count(self, criteria: Optional[Dict[str, Any]] = None) -> int:
        """
        تعداد پیش‌بینی‌ها
        
        پارامترها:
            criteria: معیارهای فیلتر
        
        خروجی:
            تعداد
        """
        if not self._ensure_db():
            return 0
        
        try:
            conditions = []
            params = []
            
            if criteria:
                if "coin" in criteria:
                    conditions.append("coin = %s")
                    params.append(criteria["coin"])
                
                if "signal_type" in criteria:
                    conditions.append("signal_type = %s")
                    params.append(criteria["signal_type"])
                
                if "from_date" in criteria:
                    conditions.append("timestamp >= %s")
                    params.append(criteria["from_date"])
                
                if "to_date" in criteria:
                    conditions.append("timestamp <= %s")
                    params.append(criteria["to_date"])
            
            where_clause = " AND ".join(conditions) if conditions else "1=1"
            
            result = self.db.execute(
                f"SELECT COUNT(*) as count FROM predictions WHERE {where_clause}",
                tuple(params),
            )
            
            return result[0]["count"] if result else 0
            
        except Exception as e:
            logger.error(f"❌ Count error: {e}")
            return 0
    
    def delete(self, entity_id: int) -> bool:
        """حذف با ID"""
        if not self._ensure_db():
            return False
        
        try:
            self.db.execute(
                "DELETE FROM predictions WHERE id = %s",
                (entity_id,),
            )
            return True
        except Exception as e:
            logger.error(f"❌ Delete error: {e}")
            return False
    
    def delete_old(
        self,
        retention_days: int = 30,
    ) -> int:
        """
        حذف پیش‌بینی‌های قدیمی
        
        پارامترها:
            retention_days: مدت نگهداری
        
        خروجی:
            تعداد حذف شده
        """
        if not self._ensure_db():
            return 0
        
        try:
            cutoff = datetime.now() - timedelta(days=retention_days)
            
            # شمارش
            count_result = self.db.execute(
                "SELECT COUNT(*) as count FROM predictions "
                "WHERE timestamp < %s",
                (cutoff,),
            )
            count = count_result[0]["count"] if count_result else 0
            
            if count == 0:
                return 0
            
            # حذف
            self.db.execute(
                "DELETE FROM predictions WHERE timestamp < %s",
                (cutoff,),
            )
            
            logger.info(f"✅ Deleted {count} old predictions (>{retention_days}d)")
            return count
            
        except Exception as e:
            logger.error(f"❌ Delete old error: {e}")
            return 0
    
    # ============================================================
    # Aggregations
    # ============================================================
    
    def get_stats(self) -> Dict[str, Any]:
        """
        آمار کلی پیش‌بینی‌ها
        
        خروجی:
            دیکشنری شامل:
                - total: تعداد کل
                - by_signal: تعداد هر سیگنال
                - confidence: میانگین/Min/Max
                - by_coin: تعداد هر ارز
                - by_period: تعداد هر بازه
                - recent_24h: تعداد ۲۴ ساعت اخیر
        """
        if not self._ensure_db():
            return {}
        
        try:
            # آمار کلی
            total_result = self.db.execute(
                "SELECT COUNT(*) as count FROM predictions"
            )
            total = total_result[0]["count"] if total_result else 0
            
            # توسط signal_type
            signal_stats = self.db.execute(
                """
                SELECT signal_type, COUNT(*) as count
                FROM predictions
                GROUP BY signal_type
                """
            )
            
            by_signal = {
                row["signal_type"]: row["count"] for row in signal_stats
            }
            
            # آمار confidence
            conf_stats = self.db.execute(
                """
                SELECT
                    AVG(confidence) as avg_confidence,
                    MIN(confidence) as min_confidence,
                    MAX(confidence) as max_confidence
                FROM predictions
                """
            )
            
            confidence = conf_stats[0] if conf_stats else {}
            
            # توسط coin
            coin_stats = self.db.execute(
                """
                SELECT coin, COUNT(*) as count
                FROM predictions
                GROUP BY coin
                ORDER BY count DESC
                LIMIT 10
                """
            )
            
            by_coin = [
                {"coin": row["coin"], "count": row["count"]}
                for row in coin_stats
            ]
            
            # توسط period
            period_stats = self.db.execute(
                """
                SELECT period, COUNT(*) as count
                FROM predictions
                GROUP BY period
                """
            )
            
            by_period = {
                row["period"]: row["count"] for row in period_stats
            }
            
            # ۲۴ ساعت اخیر
            recent_result = self.db.execute(
                """
                SELECT COUNT(*) as count FROM predictions
                WHERE timestamp >= NOW() - INTERVAL '24 hours'
                """
            )
            recent_24h = recent_result[0]["count"] if recent_result else 0
            
            return {
                "total": total,
                "by_signal": by_signal,
                "by_coin": by_coin,
                "by_period": by_period,
                "confidence": {
                    "avg": round(confidence.get("avg_confidence", 0) or 0, 2),
                    "min": confidence.get("min_confidence", 0) or 0,
                    "max": confidence.get("max_confidence", 0) or 0,
                },
                "recent_24h": recent_24h,
            }
            
        except Exception as e:
            logger.error(f"❌ Get stats error: {e}")
            return {}
    
    def get_accuracy_stats(
        self,
        from_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        آمار دقت پیش‌بینی‌ها (نیاز به labeled data)
        
        توجه: نیاز به جدول جداگانه برای labeled data دارد
        """
        # این متد در فاز بعدی با labeled data کامل می‌شود
        return {}
    
    def get_daily_summary(
        self,
        days: int = 30,
    ) -> List[Dict[str, Any]]:
        """
        خلاصه روزانه
        
        پارامترها:
            days: تعداد روز
        
        خروجی:
            لیست خلاصه روزانه
        """
        if not self._ensure_db():
            return []
        
        try:
            result = self.db.execute(
                """
                SELECT
                    DATE(timestamp) as date,
                    COUNT(*) as count,
                    AVG(confidence) as avg_confidence,
                    SUM(CASE WHEN signal_type = 'BUY' THEN 1 ELSE 0 END) as buy_count,
                    SUM(CASE WHEN signal_type = 'SELL' THEN 1 ELSE 0 END) as sell_count,
                    SUM(CASE WHEN signal_type = 'NEUTRAL' THEN 1 ELSE 0 END) as neutral_count
                FROM predictions
                WHERE timestamp >= NOW() - (%s * INTERVAL '1 day')
                GROUP BY DATE(timestamp)
                ORDER BY date DESC
                """,
                (days,),
            )
            
            return result or []
            
        except Exception as e:
            logger.error(f"❌ Daily summary error: {e}")
            return []
    
    def get_top_coins(
        self,
        limit: int = 10,
        by: str = "count",
    ) -> List[Dict[str, Any]]:
        """
        پرطرفدارترین ارزها
        
        پارامترها:
            limit: تعداد
            by: معیار (count, avg_confidence)
        """
        if not self._ensure_db():
            return []
        
        try:
            if by == "avg_confidence":
                order_clause = "avg_confidence DESC"
            else:
                order_clause = "count DESC"
            
            result = self.db.execute(
                f"""
                SELECT
                    coin,
                    COUNT(*) as count,
                    AVG(confidence) as avg_confidence
                FROM predictions
                GROUP BY coin
                ORDER BY {order_clause}
                LIMIT %s
                """,
                (limit,),
            )
            
            return result or []
            
        except Exception as e:
            logger.error(f"❌ Top coins error: {e}")
            return []
    
    # ============================================================
    # Export
    # ============================================================
    
    def export_to_dict(
        self,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        limit: int = 10000,
    ) -> List[Dict[str, Any]]:
        """
        خروجی به صورت لیست دیکشنری
        
        پارامترها:
            from_date: از تاریخ
            to_date: تا تاریخ
            limit: حداکثر تعداد
        
        خروجی:
            لیست دیکشنری
        """
        if not self._ensure_db():
            return []
        
        try:
            criteria = {"limit": limit}
            if from_date:
                criteria["from_date"] = from_date
            if to_date:
                criteria["to_date"] = to_date
            
            predictions = self.find_by_criteria(criteria)
            
            return [p.to_dict() for p in predictions]
            
        except Exception as e:
            logger.error(f"❌ Export error: {e}")
            return []
    
    # ============================================================
    # Row to Entity
    # ============================================================
    
    def _row_to_prediction(self, row: Dict[str, Any]) -> Prediction:
        """تبدیل ردیف دیتابیس به Entity"""
        try:
            signal_value = row.get("signal_type", "NEUTRAL")
            signal_type = SignalType(signal_value)
        except (ValueError, KeyError):
            signal_type = SignalType.NEUTRAL
        
        return Prediction(
            id=row.get("id"),
            coin=row.get("coin", ""),
            coin_name=row.get("coin_name", ""),
            current_price=float(row.get("current_price", 0) or 0),
            signal=signal_type.value,
            signal_type=signal_type,
            confidence=int(row.get("confidence", 50) or 50),
            confidence_score=int(row.get("confidence", 50) or 50),
            prediction_score=float(row.get("prediction_score", 0.5) or 0.5),
            period=row.get("period", "24h"),
            model_mode=row.get("model_mode", "DEMO"),
            timestamp=row.get("timestamp") or datetime.now(),
            processing_time_ms=float(row.get("processing_time_ms", 0) or 0),
            data_points=int(row.get("data_points", 0) or 0),
            extra=None,
        )
    
    # ============================================================
    # Repository Interface
    # ============================================================
    
    def save_entity(self, entity: Any) -> Any:
        """ذخیره Entity (alias)"""
        return self.save(entity)
