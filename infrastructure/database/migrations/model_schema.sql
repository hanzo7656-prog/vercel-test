-- ============================================================
-- infrastructure/database/migrations/models_schema.sql
-- ایجاد جدول‌های مورد نیاز برای مدل و تاریخچه
-- ============================================================

-- ۱. جدول اصلی مدل‌ها
CREATE TABLE IF NOT EXISTS models (
    id SERIAL PRIMARY KEY,
    version VARCHAR(50) UNIQUE NOT NULL,
    model_data BYTEA NOT NULL,
    accuracy FLOAT NOT NULL,
    training_samples INTEGER DEFAULT 0,
    period VARCHAR(10) DEFAULT '1m',
    coins TEXT[] DEFAULT '{"bitcoin","ethereum"}',
    features TEXT[] DEFAULT ARRAY[
        'return_1','return_3','return_5','return_10',
        'sma_5','sma_10','sma_20',
        'volatility','fear_greed',
        'trend_5','trend_10','trend_20','r2'
    ],
    is_active BOOLEAN DEFAULT FALSE,
    is_ensemble BOOLEAN DEFAULT FALSE,
    training_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata JSONB DEFAULT '{}'::jsonb
);

-- ۲. جدول تاریخچه ترس و طمع
CREATE TABLE IF NOT EXISTS fear_greed_history (
    id SERIAL PRIMARY KEY,
    value INTEGER NOT NULL,
    classification VARCHAR(50),
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ۳. جدول تاریخچه سلطه بیت‌کوین
CREATE TABLE IF NOT EXISTS btc_dominance_history (
    id SERIAL PRIMARY KEY,
    value DECIMAL(5,2) NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ۴. جدول تاریخچه بازار جهانی
CREATE TABLE IF NOT EXISTS global_market_history (
    id SERIAL PRIMARY KEY,
    market_cap DECIMAL(20,2),
    volume DECIMAL(20,2),
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ۵. جدول تاریخچه آموزش
CREATE TABLE IF NOT EXISTS model_training_history (
    id SERIAL PRIMARY KEY,
    model_id INTEGER REFERENCES models(id) ON DELETE CASCADE,
    action VARCHAR(50) NOT NULL,
    old_accuracy FLOAT,
    new_accuracy FLOAT,
    improvement_percent FLOAT,
    samples_used INTEGER,
    training_time_seconds FLOAT,
    reason TEXT,
    status VARCHAR(20) DEFAULT 'success',
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP
);

-- ۶. ایندکس‌ها
CREATE INDEX IF NOT EXISTS idx_models_version ON models(version);
CREATE INDEX IF NOT EXISTS idx_models_active ON models(is_active);
CREATE INDEX IF NOT EXISTS idx_models_training_date ON models(training_date DESC);
CREATE INDEX IF NOT EXISTS idx_fear_greed_timestamp ON fear_greed_history(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_btc_dominance_timestamp ON btc_dominance_history(timestamp DESC);
