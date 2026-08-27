-- ============================================================
-- database/migrations/models_schema.sql
-- ============================================================
-- شرح: ساختار کامل دیتابیس برای مدیریت مدل‌های XGBoost
-- تاریخ: ۲۰۲۶-۰۸-۲۷
-- نسخه: ۲.۰ (یکپارچه با سیستم جدید)
-- ============================================================

-- ============================================================
-- ۱. جدول اصلی مدل‌ها (models)
-- ============================================================

DROP TABLE IF EXISTS models CASCADE;

CREATE TABLE IF NOT EXISTS models (
    -- شناسه اصلی
    id SERIAL PRIMARY KEY,
    
    -- اطلاعات نسخه
    version VARCHAR(50) UNIQUE NOT NULL,
    version_major INTEGER DEFAULT 1,
    version_minor INTEGER DEFAULT 0,
    version_patch INTEGER DEFAULT 0,
    
    -- داده مدل (ذخیره به صورت باینری)
    model_data BYTEA NOT NULL,
    model_format VARCHAR(10) DEFAULT 'json',  -- json, ubj, pickle
    
    -- متریک‌های عملکرد
    accuracy FLOAT NOT NULL,
    precision FLOAT,
    recall FLOAT,
    f1_score FLOAT,
    auc_roc FLOAT,
    
    -- اطلاعات آموزش
    training_samples INTEGER DEFAULT 0,
    training_epochs INTEGER DEFAULT 0,
    training_time_seconds FLOAT DEFAULT 0,
    
    -- پارامترهای آموزش
    period VARCHAR(10) DEFAULT '1m',  -- 1w, 1m, 3m, 6m, 1y
    learning_rate FLOAT DEFAULT 0.1,
    max_depth INTEGER DEFAULT 4,
    n_estimators INTEGER DEFAULT 50,
    
    -- داده‌های استفاده شده
    coins TEXT[] DEFAULT '{"bitcoin","ethereum","solana","cardano","ripple"}',
    features TEXT[] DEFAULT ARRAY[
        'return_1','return_3','return_5','return_10',
        'sma_5','sma_10','sma_20',
        'volatility','fear_greed',
        'trend_5','trend_10','trend_20','r2'
    ],
    
    -- وضعیت
    is_active BOOLEAN DEFAULT FALSE,
    is_ensemble BOOLEAN DEFAULT FALSE,
    is_best BOOLEAN DEFAULT FALSE,  -- بهترین مدل تا کنون
    
    -- Ensemble (اگر ترکیبی باشد)
    ensemble_weights JSONB,  -- {'model1': 0.7, 'model2': 0.3}
    parent_versions TEXT[],  -- نسخه‌های والد در Ensemble
    
    -- زمان‌ها
    training_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_used_at TIMESTAMP,
    
    -- متادیتا
    metadata JSONB DEFAULT '{}'::jsonb,  -- اطلاعات اضافی
    notes TEXT,
    created_by VARCHAR(50) DEFAULT 'system'
);

-- ============================================================
-- ۲. جدول تاریخچه آموزش (model_training_history)
-- ============================================================

DROP TABLE IF EXISTS model_training_history CASCADE;

CREATE TABLE IF NOT EXISTS model_training_history (
    id SERIAL PRIMARY KEY,
    model_id INTEGER REFERENCES models(id) ON DELETE CASCADE,
    
    -- نوع اقدام
    action VARCHAR(50) NOT NULL,  -- 'train', 'restore', 'ensemble', 'rollback', 'incremental'
    
    -- متریک‌های قبل و بعد
    old_accuracy FLOAT,
    new_accuracy FLOAT,
    improvement_percent FLOAT,
    
    -- اطلاعات دقیق
    old_version VARCHAR(50),
    new_version VARCHAR(50),
    samples_used INTEGER,
    training_time_seconds FLOAT,
    
    -- دلیل (برای restore یا rollback)
    reason TEXT,
    
    -- وضعیت
    status VARCHAR(20) DEFAULT 'success',  -- 'success', 'failed', 'partial'
    error_message TEXT,
    
    -- زمان
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    
    -- متادیتا
    metadata JSONB DEFAULT '{}'::jsonb
);

-- ============================================================
-- ۳. جدول خطاهای مدل (model_errors)
-- ============================================================

DROP TABLE IF EXISTS model_errors CASCADE;

CREATE TABLE IF NOT EXISTS model_errors (
    id SERIAL PRIMARY KEY,
    model_id INTEGER REFERENCES models(id) ON DELETE CASCADE,
    
    error_type VARCHAR(50) NOT NULL,  -- 'prediction', 'loading', 'training', 'memory'
    error_message TEXT NOT NULL,
    error_stack TEXT,
    
    -- اطلاعات زمینه
    input_data JSONB,
    predicted_output JSONB,
    expected_output JSONB,
    
    -- زمان
    occurred_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP,
    resolved_by VARCHAR(50),
    
    -- وضعیت
    is_resolved BOOLEAN DEFAULT FALSE,
    severity VARCHAR(20) DEFAULT 'medium'  -- 'low', 'medium', 'high', 'critical'
);

-- ============================================================
-- ۴. جدول عملکرد مدل (model_performance)
-- ============================================================

DROP TABLE IF EXISTS model_performance CASCADE;

CREATE TABLE IF NOT EXISTS model_performance (
    id SERIAL PRIMARY KEY,
    model_id INTEGER REFERENCES models(id) ON DELETE CASCADE,
    
    -- متریک‌های روزانه
    date DATE NOT NULL,
    daily_accuracy FLOAT,
    daily_precision FLOAT,
    daily_recall FLOAT,
    daily_f1 FLOAT,
    
    -- تعداد پیش‌بینی‌ها
    predictions_count INTEGER DEFAULT 0,
    correct_predictions INTEGER DEFAULT 0,
    wrong_predictions INTEGER DEFAULT 0,
    
    -- زمان پاسخ
    avg_response_time_ms FLOAT,
    max_response_time_ms FLOAT,
    min_response_time_ms FLOAT,
    
    -- وضعیت
    status VARCHAR(20) DEFAULT 'stable',  -- 'stable', 'degraded', 'critical'
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- ۵. جدول کش مدل (model_cache)
-- ============================================================

DROP TABLE IF EXISTS model_cache CASCADE;

CREATE TABLE IF NOT EXISTS model_cache (
    id SERIAL PRIMARY KEY,
    cache_key VARCHAR(255) UNIQUE NOT NULL,
    model_version VARCHAR(50),
    
    -- داده کش
    cache_data JSONB NOT NULL,
    input_hash VARCHAR(64),  -- هش ورودی برای تشخیص کش
    
    -- زمان
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP,
    last_accessed_at TIMESTAMP,
    
    -- آمار
    access_count INTEGER DEFAULT 0,
    hit_count INTEGER DEFAULT 0
);

-- ============================================================
-- ۶. ایندکس‌ها (بهینه‌سازی)
-- ============================================================

-- ایندکس روی نسخه
CREATE INDEX IF NOT EXISTS idx_models_version ON models(version);
CREATE INDEX IF NOT EXISTS idx_models_version_major_minor ON models(version_major, version_minor);

-- ایندکس روی وضعیت
CREATE INDEX IF NOT EXISTS idx_models_active ON models(is_active);
CREATE INDEX IF NOT EXISTS idx_models_best ON models(is_best);
CREATE INDEX IF NOT EXISTS idx_models_ensemble ON models(is_ensemble);

-- ایندکس روی زمان
CREATE INDEX IF NOT EXISTS idx_models_training_date ON models(training_date DESC);
CREATE INDEX IF NOT EXISTS idx_models_created_at ON models(created_at DESC);

-- ایندکس روی دقت
CREATE INDEX IF NOT EXISTS idx_models_accuracy ON models(accuracy DESC);

-- ایندکس‌های تاریخچه
CREATE INDEX IF NOT EXISTS idx_history_model_id ON model_training_history(model_id);
CREATE INDEX IF NOT EXISTS idx_history_action ON model_training_history(action);
CREATE INDEX IF NOT EXISTS idx_history_created_at ON model_training_history(created_at DESC);

-- ایندکس‌های خطاها
CREATE INDEX IF NOT EXISTS idx_errors_model_id ON model_errors(model_id);
CREATE INDEX IF NOT EXISTS idx_errors_type ON model_errors(error_type);
CREATE INDEX IF NOT EXISTS idx_errors_resolved ON model_errors(is_resolved);

-- ایندکس‌های عملکرد
CREATE INDEX IF NOT EXISTS idx_performance_model_id ON model_performance(model_id);
CREATE INDEX IF NOT EXISTS idx_performance_date ON model_performance(date DESC);

-- ایندکس‌های کش
CREATE INDEX IF NOT EXISTS idx_cache_key ON model_cache(cache_key);
CREATE INDEX IF NOT EXISTS idx_cache_expires ON model_cache(expires_at);

-- ============================================================
-- ۷. تریگرها (خودکارسازی)
-- ============================================================

-- تابع به‌روزرسانی updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- تریگر روی جدول models
DROP TRIGGER IF EXISTS update_models_updated_at ON models;
CREATE TRIGGER update_models_updated_at
    BEFORE UPDATE ON models
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================================
-- ۸. ویوها (نمایش‌های آماده)
-- ============================================================

-- ویو: آخرین مدل فعال
CREATE OR REPLACE VIEW v_active_model AS
SELECT 
    id,
    version,
    accuracy,
    period,
    training_samples,
    training_date,
    coins,
    features,
    metadata
FROM models
WHERE is_active = TRUE
ORDER BY id DESC
LIMIT 1;

-- ویو: بهترین مدل‌ها
CREATE OR REPLACE VIEW v_best_models AS
SELECT 
    id,
    version,
    accuracy,
    period,
    training_samples,
    training_date,
    CASE 
        WHEN is_active THEN '✅ فعال'
        ELSE '📦 آرشیو'
    END as status
FROM models
WHERE is_best = TRUE
ORDER BY accuracy DESC, training_date DESC;

-- ویو: آمار آموزش
CREATE OR REPLACE VIEW v_training_stats AS
SELECT 
    DATE(created_at) as date,
    COUNT(*) as total_trainings,
    SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as successful,
    SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed,
    ROUND(AVG(new_accuracy - old_accuracy) * 100, 2) as avg_improvement_percent
FROM model_training_history
GROUP BY DATE(created_at)
ORDER BY date DESC;

-- ============================================================
-- ۹. دیتای اولیه (Seed)
-- ============================================================

-- درج یک مدل نمونه (در صورت خالی بودن جدول)
INSERT INTO models (
    version,
    model_data,
    accuracy,
    period,
    training_samples,
    is_active,
    is_best,
    metadata
)
SELECT 
    'v1.0.0_initial',
    'x\x00\x00\x00...'::bytea,  -- داده خالی (در عمل با داده واقعی جایگزین می‌شود)
    0.50,
    '1m',
    0,
    TRUE,
    TRUE,
    '{"type": "initial", "created_by": "system"}'::jsonb
WHERE NOT EXISTS (SELECT 1 FROM models LIMIT 1);

-- ============================================================
-- ۱۰. دستورات مفید برای مدیریت
-- ============================================================

-- پیدا کردن مدل با بیشترین دقت
-- SELECT * FROM models ORDER BY accuracy DESC LIMIT 1;

-- پیدا کردن آخرین آموزش موفق
-- SELECT * FROM model_training_history WHERE status = 'success' ORDER BY created_at DESC LIMIT 1;

-- آمار کلی مدل‌ها
-- SELECT 
--     COUNT(*) as total_models,
--     ROUND(AVG(accuracy) * 100, 2) as avg_accuracy,
--     MAX(accuracy) as best_accuracy,
--     MIN(accuracy) as worst_accuracy,
--     SUM(CASE WHEN is_active THEN 1 ELSE 0 END) as active_models
-- FROM models;

-- ============================================================
-- پایان فایل
-- ============================================================
