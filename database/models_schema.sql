-- database/models_schema.sql
-- ============================================================
-- فاز ۱: ایجاد جدول‌های جدید برای سیستم تحلیلگر
-- ============================================================

-- ============================================================
-- ۱. جدول اصلی مدل‌های XGBoost
-- ============================================================
CREATE TABLE IF NOT EXISTS models (
    id SERIAL PRIMARY KEY,
    version VARCHAR(30) NOT NULL UNIQUE,
    model_data BYTEA NOT NULL,
    model_size INTEGER,
    accuracy FLOAT,
    precision FLOAT,
    recall FLOAT,
    f1_score FLOAT,
    training_samples INTEGER,
    training_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    period VARCHAR(10),
    coins TEXT[],
    features TEXT[],
    is_active BOOLEAN DEFAULT FALSE,
    is_ensemble BOOLEAN DEFAULT FALSE,
    parent_version VARCHAR(30),
    weight FLOAT DEFAULT 1.0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- ۲. تاریخچه آموزش
-- ============================================================
CREATE TABLE IF NOT EXISTS model_training_history (
    id SERIAL PRIMARY KEY,
    model_id INTEGER REFERENCES models(id) ON DELETE CASCADE,
    action VARCHAR(20),
    old_accuracy FLOAT,
    new_accuracy FLOAT,
    improvement_percent FLOAT,
    training_time_seconds FLOAT,
    reason TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- ۳. ثبت پیش‌بینی‌ها
-- ============================================================
CREATE TABLE IF NOT EXISTS model_predictions (
    id SERIAL PRIMARY KEY,
    model_id INTEGER REFERENCES models(id) ON DELETE SET NULL,
    coin VARCHAR(30),
    period VARCHAR(10),
    prediction_score FLOAT,
    signal_type VARCHAR(10),
    actual_result VARCHAR(10),
    predicted_price FLOAT,
    actual_price FLOAT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- ۴. کش داده‌های بازار
-- ============================================================
CREATE TABLE IF NOT EXISTS market_data_cache (
    id SERIAL PRIMARY KEY,
    coin VARCHAR(30) NOT NULL,
    data_type VARCHAR(20),
    data_json JSONB,
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP
);

-- ============================================================
-- ۵. ثبت دستورات کاربران
-- ============================================================
CREATE TABLE IF NOT EXISTS commands_log (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(50),
    command TEXT,
    response TEXT,
    coin VARCHAR(30),
    processing_time_ms INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- ۶. تنظیمات کاربران
-- ============================================================
CREATE TABLE IF NOT EXISTS user_preferences (
    user_id VARCHAR(50) PRIMARY KEY,
    default_coin VARCHAR(30) DEFAULT 'bitcoin',
    favorite_coins TEXT[],
    theme VARCHAR(10) DEFAULT 'dark',
    notification_enabled BOOLEAN DEFAULT TRUE,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- ایندکس‌ها
-- ============================================================
CREATE INDEX idx_models_version ON models(version);
CREATE INDEX idx_models_active ON models(is_active) WHERE is_active = TRUE;
CREATE INDEX idx_models_date ON models(training_date DESC);
CREATE INDEX idx_models_ensemble ON models(is_ensemble) WHERE is_ensemble = TRUE;
CREATE INDEX idx_predictions_coin ON model_predictions(coin);
CREATE INDEX idx_predictions_date ON model_predictions(created_at DESC);
CREATE INDEX idx_commands_user ON commands_log(user_id);
CREATE INDEX idx_commands_date ON commands_log(created_at DESC);
CREATE INDEX idx_cache_coin ON market_data_cache(coin);
CREATE INDEX idx_cache_expires ON market_data_cache(expires_at);

-- ============================================================
-- توابع کمکی
-- ============================================================

-- تابع برای گرفتن آخرین مدل فعال
CREATE OR REPLACE FUNCTION get_active_model()
RETURNS TABLE(
    id INTEGER,
    version VARCHAR,
    model_data BYTEA,
    accuracy FLOAT,
    training_date TIMESTAMP
) AS $$
BEGIN
    RETURN QUERY
    SELECT m.id, m.version, m.model_data, m.accuracy, m.training_date
    FROM models m
    WHERE m.is_active = TRUE
    ORDER BY m.training_date DESC
    LIMIT 1;
END;
$$ LANGUAGE plpgsql;

-- تابع برای پاک کردن مدل‌های قدیمی (قابل اجرا توسط مدیر)
CREATE OR REPLACE FUNCTION cleanup_old_models(days_to_keep INTEGER DEFAULT 30)
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM models
    WHERE is_active = FALSE
      AND is_ensemble = FALSE
      AND training_date < NOW() - (days_to_keep || ' days')::INTERVAL
      AND id NOT IN (
          SELECT parent_id FROM model_training_history
      );
    
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;
