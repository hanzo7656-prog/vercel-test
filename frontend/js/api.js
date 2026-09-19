// ============================================================
// api.js - Unified API Client v11.0
// کاملاً هماهنگ با اندپوینت‌های جدید backend
// ============================================================

class ApiClient {
    constructor(baseURL = '') {
        this.baseURL = baseURL;
        this.defaultOptions = {
            credentials: 'include',
            headers: {
                'Content-Type': 'application/json'
            }
        };
    }

    async request(endpoint, options = {}) {
        const url = `${this.baseURL}${endpoint}`;
        const config = {
            ...this.defaultOptions,
            ...options,
            headers: {
                ...this.defaultOptions.headers,
                ...options.headers
            }
        };

        try {
            const response = await fetch(url, config);
            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.error || `HTTP ${response.status}: ${response.statusText}`);
            }

            return data;
        } catch (error) {
            console.error(`❌ API Error [${endpoint}]:`, error);
            throw error;
        }
    }

    // ============================================================
    // ۱. سیستم (SYSTEM)
    // ============================================================

    getHealth() {
        return this.request('/api/health');
    }

    getHealthSimple() {
        return this.request('/api/health/simple');
    }

    getStats() {
        return this.request('/api/stats');
    }

    getMetrics() {
        return this.request('/api/metrics');
    }

    getMetricsSummary() {
        return this.request('/api/metrics/summary');
    }

    getDashboardMetrics() {
        return this.request('/api/metrics/dashboard');
    }

    // ============================================================
    // ۲. آمار اپلیکیشن (APP STATS)
    // ============================================================

    getAppStats() {
        return this.request('/api/app/stats');
    }

    // ============================================================
    // ۳. Quota Management (🆕)
    // ============================================================

    getAllQuotas() {
        return this.request('/api/db/quota');
    }

    getDBQuota(dbName) {
        return this.request(`/api/db/quota/${dbName}`);
    }

    getDBQuotaStatus(dbName) {
        return this.request(`/api/db/quota/${dbName}/status`);
    }

    setDBQuota(dbName, data) {
        return this.request(`/api/db/quota/${dbName}`, {
            method: 'POST',
            body: JSON.stringify(data)
        });
    }

    setTableQuota(dbName, tableName, data) {
        return this.request(`/api/db/quota/${dbName}/table/${tableName}`, {
            method: 'POST',
            body: JSON.stringify(data)
        });
    }

    resetDBQuota(dbName) {
        return this.request(`/api/db/quota/${dbName}`, {
            method: 'DELETE'
        });
    }

    resetAllQuotas() {
        return this.request('/api/db/quota', {
            method: 'DELETE'
        });
    }

    getQuotaStats() {
        return this.request('/api/db/quota/stats');
    }

    // ============================================================
    // ۴. دیتابیس - PostgreSQL (🆕 Multi-DB)
    // ============================================================

    getPostgreSQLTables(dbName = 'primary') {
        return this.request(`/api/db/postgresql/${dbName}/tables`);
    }

    getPostgreSQLTableData(dbName, tableName, options = {}) {
        const { limit = 100, offset = 0, search = '', sort_by = 'id', sort_order = 'DESC', format = 'json' } = options;
        const params = new URLSearchParams({ limit, offset, search, sort_by, sort_order, format });
        return this.request(`/api/db/postgresql/${dbName}/tables/${tableName}?${params}`);
    }

    getPostgreSQLTableSizes(dbName = 'primary') {
        return this.request(`/api/db/postgresql/${dbName}/table-sizes`);
    }

    getPostgreSQLStats(dbName = 'primary') {
        return this.request(`/api/db/postgresql/${dbName}/stats`);
    }

    exportPostgreSQLTable(dbName, tableName, format = 'csv', limit = 10000) {
        return this.request(`/api/db/postgresql/${dbName}/export/${tableName}?format=${format}&limit=${limit}`);
    }

    exportPostgreSQLTableCSV(dbName, tableName) {
        window.open(`/api/db/postgresql/${dbName}/export/${tableName}?format=csv`, '_blank');
    }

    exportPostgreSQLRow(dbName, tableName, rowId, format = 'json') {
        const params = new URLSearchParams({ format });
        return this.request(`/api/db/postgresql/${dbName}/tables/${tableName}/row/${rowId}?${params}`);
    }

    executePostgreSQLQuery(dbName, query) {
        return this.request(`/api/db/postgresql/${dbName}/query`, {
            method: 'POST',
            body: JSON.stringify({ query })
        });
    }

    // ============================================================
    // ۵. دیتابیس - Redis
    // ============================================================

    getRedisKeys(options = {}) {
        const { pattern = '*', limit = 100, search = '' } = options;
        const params = new URLSearchParams({ pattern, limit, search });
        return this.request(`/api/db/redis/keys?${params}`);
    }

    getRedisStats() {
        return this.request('/api/db/redis/stats');
    }

    getRedisNamespaces() {
        return this.request('/api/db/redis/namespaces');
    }

    getRedisKey(key) {
        return this.request(`/api/db/redis/keys/${encodeURIComponent(key)}`);
    }

    deleteRedisKey(key) {
        return this.request(`/api/db/redis/keys/${encodeURIComponent(key)}`, {
            method: 'DELETE'
        });
    }

    exportRedisKey(key) {
        return this.request(`/api/db/redis/keys/${encodeURIComponent(key)}/export`);
    }

    clearRedisNamespace(namespace) {
        return this.request(`/api/db/redis/namespace/${encodeURIComponent(namespace)}`, {
            method: 'DELETE'
        });
    }

    clearRedis(confirm = true) {
        return this.request(`/api/db/redis/flush?confirm=${confirm}`, {
            method: 'DELETE'
        });
    }

    // ============================================================
    // ۶. دیتابیس - Archive (🆕 جایگزین SQLite)
    // ============================================================

    getArchiveTables() {
        return this.request('/api/db/archive/tables');
    }

    getArchiveTableData(tableName, options = {}) {
        const { limit = 100, offset = 0, search = '', format = 'json' } = options;
        const params = new URLSearchParams({ limit, offset, search, format });
        return this.request(`/api/db/archive/tables/${tableName}?${params}`);
    }

    getArchiveStats() {
        return this.request('/api/db/archive/stats');
    }

    exportArchiveTable(tableName, format = 'csv', limit = 10000) {
        return this.request(`/api/db/archive/tables/${tableName}/export?format=${format}&limit=${limit}`);
    }

    exportArchiveRow(tableName, rowId, format = 'json') {
        const params = new URLSearchParams({ format });
        return this.request(`/api/db/archive/tables/${tableName}/row/${rowId}?${params}`);
    }

    archiveCleanup(data) {
        return this.request('/api/db/archive/cleanup', {
            method: 'POST',
            body: JSON.stringify(data)
        });
    }

    getArchiveFeatures() {
        return this.request('/api/db/archive/features');
    }

    // ============================================================
    // ۷. دیتابیس - Health & Status (🆕)
    // ============================================================

    getHealthSummary() {
        return this.request('/api/db/health/summary');
    }

    getHealthFull() {
        return this.request('/api/db/health/full');
    }

    getDBList() {
        return this.request('/api/db/list');
    }

    pingDatabase(dbName) {
        return this.request(`/api/db/${dbName}/ping`);
    }

    isReady() {
        return this.request('/api/db/ready');
    }

    getFactoryStatus() {
        return this.request('/api/db/factory/status');
    }

    forceReconnect(dbName = null) {
        const url = dbName ? `/api/db/${dbName}/reconnect` : '/api/db/reconnect';
        return this.request(url, { method: 'POST' });
    }

    reloadConfig() {
        return this.request('/api/db/reload-config', { method: 'POST' });
    }

    // ============================================================
    // ۸. دیتابیس - Router & Registry (🆕)
    // ============================================================

    getRouterStats() {
        return this.request('/api/db/router/stats');
    }

    getRouterRules() {
        return this.request('/api/db/router/rules');
    }

    getRegistrySummary() {
        return this.request('/api/db/registry/summary');
    }

    // ============================================================
    // ۹. دیتابیس - Maintenance (🆕)
    // ============================================================

    vacuumDatabase(dbName, full = false, analyze = true) {
        const params = new URLSearchParams({ full, analyze });
        return this.request(`/api/db/${dbName}/vacuum?${params}`, {
            method: 'POST'
        });
    }

    vacuumAllDatabases(full = false, analyze = true) {
        const params = new URLSearchParams({ full, analyze });
        return this.request(`/api/db/vacuum-all?${params}`, {
            method: 'POST'
        });
    }

    analyzeDatabase(dbName, table = null) {
        const params = table ? `?table=${table}` : '';
        return this.request(`/api/db/${dbName}/analyze${params}`, {
            method: 'POST'
        });
    }

    createBackup(data) {
        return this.request('/api/db/backup/create', {
            method: 'POST',
            body: JSON.stringify(data)
        });
    }

    listBackups(options = {}) {
        const { limit = 50, source_table = '', status = '' } = options;
        const params = new URLSearchParams({ limit, source_table, status });
        return this.request(`/api/db/backup/list?${params}`);
    }

    deleteOldRecords(dbName, tableName, data) {
        return this.request(`/api/db/${dbName}/tables/${tableName}/delete-old`, {
            method: 'POST',
            body: JSON.stringify(data)
        });
    }

    getTableCount(dbName, tableName, where = '') {
        const params = where ? `?where=${encodeURIComponent(where)}` : '';
        return this.request(`/api/db/${dbName}/tables/${tableName}/count${params}`);
    }

    getTableSize(dbName, tableName) {
        return this.request(`/api/db/${dbName}/tables/${tableName}/size`);
    }

    truncateTable(dbName, tableName, cascade = false) {
        const params = new URLSearchParams({ confirm: true, cascade });
        return this.request(`/api/db/${dbName}/tables/${tableName}/truncate?${params}`, {
            method: 'POST'
        });
    }

    runTransaction(data) {
        return this.request('/api/db/transaction', {
            method: 'POST',
            body: JSON.stringify(data)
        });
    }

    // ============================================================
    // ۱۰. دیتابیس - عمومی
    // ============================================================

    searchDatabase(query, tables = '') {
        const params = new URLSearchParams({ q: query });
        if (tables) params.append('tables', tables);
        return this.request(`/api/db/search?${params}`);
    }

    getDatabaseHealth() {
        return this.request('/api/db/health/summary');  // جایگزین
    }

    // ============================================================
    // ۱۱. مدل (MODEL)
    // ============================================================

    getModelStatus() {
        return this.request('/api/model/status');
    }

    getTrainerStats() {
        return this.request('/api/model/trainer-stats');
    }

    getModelHistory(limit = 20) {
        return this.request(`/api/model/history?limit=${limit}`);
    }

    getModelFeatures() {
        return this.request('/api/model/features');
    }

    getModelData() {
        return this.request('/api/model/data');
    }

    getModelImportance() {
        return this.request('/api/model/importance');
    }

    getModelPerformance() {
        return this.request('/api/model/performance');
    }

    getModelAnalyticsStats(days = 30) {
        return this.request(`/api/model/analytics-stats?days=${days}`);
    }

    trainModel(options = {}) {
        const { period = '1m', coins = ['bitcoin', 'ethereum'], incremental = false, profile_name = null, strategy = null, save = true } = options;
        return this.request('/api/model/train', {
            method: 'POST',
            body: JSON.stringify({ period, coins, incremental, profile_name, strategy, save })
        });
    }

    trainBatch(options = {}) {
        const { profiles, period = '1m', coins = null } = options;
        return this.request('/api/model/train-batch', {
            method: 'POST',
            body: JSON.stringify({ profiles, period, coins })
        });
    }

    analyzeTraining(data) {
        return this.request('/api/model/analyze-training', {
            method: 'POST',
            body: JSON.stringify(data)
        });
    }

    exportModel(version = null) {
        const url = version ? `/api/model/export?version=${version}` : '/api/model/export';
        window.open(url, '_blank');
    }

    importModel(file, accuracy = 0.5, period = '1m') {
        const formData = new FormData();
        formData.append('file', file);
        formData.append('accuracy', accuracy);
        formData.append('period', period);

        return fetch('/api/model/import', {
            method: 'POST',
            credentials: 'include',
            body: formData
        }).then(res => res.json());
    }

    activateModel(version) {
        return this.request('/api/model/activate', {
            method: 'POST',
            body: JSON.stringify({ version })
        });
    }

    deleteModel(version) {
        return this.request('/api/model/delete', {
            method: 'DELETE',
            body: JSON.stringify({ version })
        });
    }

    getLatestReport() {
        return this.request('/api/model/latest-report');
    }

    getReportByVersion(version) {
        return this.request(`/api/model/report/${version}`);
    }

    // ============================================================
    // ۱۲. Model Profiles (🆕)
    // ============================================================

    getTrainingPresets() {
        return this.request('/api/model/profiles/presets');
    }

    getTrainingPreset(presetId) {
        return this.request(`/api/model/profiles/presets/${presetId}`);
    }

    getLearningStrategies() {
        return this.request('/api/model/profiles/strategies');
    }

    getHyperparameterLimits() {
        return this.request('/api/model/profiles/hyperparameter-limits');
    }

    getCurrentProfile() {
        return this.request('/api/model/profiles/current');
    }

    setCurrentProfile(data) {
        return this.request('/api/model/profiles/current', {
            method: 'POST',
            body: JSON.stringify(data)
        });
    }

    validateProfile(data) {
        return this.request('/api/model/profiles/validate', {
            method: 'POST',
            body: JSON.stringify(data)
        });
    }

    listSavedProfiles() {
        return this.request('/api/model/profiles/saved');
    }

    saveProfile(data) {
        return this.request('/api/model/profiles/saved', {
            method: 'POST',
            body: JSON.stringify(data)
        });
    }

    loadProfile(name) {
        return this.request(`/api/model/profiles/saved/${name}`);
    }

    deleteProfile(name) {
        return this.request(`/api/model/profiles/saved/${name}`, {
            method: 'DELETE'
        });
    }

    // ============================================================
    // ۱۳. زمان‌بندی (SCHEDULE)
    // ============================================================

    getScheduleStatus() {
        return this.request('/api/schedule/status');
    }

    startSchedule(options = {}) {
        const { interval = 6, period = '1m', coins = ['bitcoin', 'ethereum'], profile_name = 'balanced', incremental = false } = options;
        return this.request('/api/schedule/start', {
            method: 'POST',
            body: JSON.stringify({ interval, period, coins, profile_name, incremental })
        });
    }

    stopSchedule() {
        return this.request('/api/schedule/stop', {
            method: 'POST'
        });
    }

    // ============================================================
    // ۱۴. پیش‌بینی (PREDICTIONS)
    // ============================================================

    predictSingle(coin, period = '24h') {
        return this.request(`/api/predict/single?coin=${encodeURIComponent(coin)}&period=${period}`);
    }

    predictMultiple(coins, period = '24h') {
        return this.request('/api/predict/multiple', {
            method: 'POST',
            body: JSON.stringify({ coins, period })
        });
    }

    predictExplain(coin) {
        return this.request(`/api/predict/explain?coin=${encodeURIComponent(coin)}`);
    }

    getPredictionHistory(limit = 50, coin = null) {
        const params = new URLSearchParams({ limit });
        if (coin) params.append('coin', coin);
        return this.request(`/api/predict/history?${params}`);
    }

    getPredictionHistoryStats() {
        return this.request('/api/predict/history/stats');
    }

    // ============================================================
    // ۱۵. کوین‌استتس (COINSTATS)
    // ============================================================

    getCoinsList(options = {}) {
        const { limit = 50, page = 1, currency = 'USD', search = '' } = options;
        const params = new URLSearchParams({ limit, page, currency });
        if (search) params.append('search', search);
        return this.request(`/api/coinstats/coins?${params}`);
    }

    getCoinPrice(coin) {
        return this.request(`/api/coinstats/price/${coin}`);
    }

    getPrices() {
        return this.request('/api/coinstats/prices');
    }

    getFearGreed() {
        return this.request('/api/coinstats/fear-greed');
    }

    getBTCDominance() {
        return this.request('/api/coinstats/btc-dominance');
    }

    getAllCoinStats() {
        return this.request('/api/coinstats/all');
    }

    getChartData(coin, period = '1m') {
        return this.request(`/api/coinstats/chart/${coin}?period=${period}`);
    }

    // ============================================================
    // ۱۶. قیمت‌های لحظه‌ای (CRYPTO)
    // ============================================================

    getRealtimePrices(symbols = null) {
        const params = new URLSearchParams();
        if (symbols && symbols.length > 0) {
            params.append('symbols', symbols.join(','));
        }
        return this.request(`/api/crypto/prices?${params}`);
    }

    getRealtimePrice(symbol) {
        return this.request(`/api/crypto/price/${symbol}`);
    }

    getCryptoStats() {
        return this.request('/api/crypto/stats');
    }

    sendHeartbeat() {
        return this.request('/api/crypto/heartbeat', {
            method: 'POST'
        });
    }


    // ============================================================
    // ۲۴. Binance WebSocket Real-time
    // ============================================================

    getWSStats() {
        return this.request('/api/crypto/ws-stats');
    }

    getWSPrices() {
        return this.request('/api/crypto/ws-prices');
    }

    getWSPrice(symbol) {
        return this.request(`/api/crypto/ws-price/${encodeURIComponent(symbol)}`);
    }

    getWSOrderbook(symbol, levels = null) {
        const params = levels ? `?levels=${levels}` : '';
        return this.request(`/api/crypto/ws-orderbook/${encodeURIComponent(symbol)}${params}`);
    }

    subscribeWS(symbol) {
        return this.request('/api/crypto/ws-subscribe', {
            method: 'POST',
            body: JSON.stringify({ symbol })
        });
    }

    unsubscribeWS(symbol) {
        return this.request('/api/crypto/ws-unsubscribe', {
            method: 'POST',
            body: JSON.stringify({ symbol })
        });
    }
    // ============================================================
    // ۱۷. هشدارها (ALERTS)
    // ============================================================

    getAlerts(options = {}) {
        const { limit = 20, resolved = null, level = null, source = null } = options;
        const params = new URLSearchParams({ limit });
        if (resolved !== null) params.append('resolved', resolved);
        if (level) params.append('level', level);
        if (source) params.append('source', source);
        return this.request(`/api/alerts?${params}`);
    }

    resolveAlert(id) {
        return this.request(`/api/alerts/${id}/resolve`, {
            method: 'POST'
        });
    }

    resolveAllAlerts(level = null) {
        const params = level ? `?level=${level}` : '';
        return this.request(`/api/alerts/resolve-all${params}`, {
            method: 'POST'
        });
    }

    // ============================================================
    // ۱۸. کاربر (USER)
    // ============================================================

    getUserInfo() {
        return this.request('/api/user');
    }

    getCredits() {
        return this.request('/api/credits');
    }

    // ============================================================
    // ۱۹. احراز هویت (AUTH)
    // ============================================================

    login(username, password) {
        return this.request('/api/login', {
            method: 'POST',
            body: JSON.stringify({ username, password })
        });
    }

    logout() {
        return this.request('/logout', { method: 'POST' });
    }

    // ============================================================
    // ۲۰. دیباگ (DEBUG)
    // ============================================================

    getDebugStatus() {
        return this.request('/api/debug/status');
    }

    getDebugLogs(options = {}) {
        const { limit = 50, level = 'ALL', since = '' } = options;
        const params = new URLSearchParams({ limit, level });
        if (since) params.append('since', since);
        return this.request(`/api/debug/logs?${params}`);
    }

    clearDebugLogs(confirm = true) {
        return this.request(`/api/debug/logs/clear?confirm=${confirm}`, {
            method: 'DELETE'
        });
    }

    getDebugSystem() {
        return this.request('/api/debug/system');
    }

    getDebugProcesses(options = {}) {
        const { search = '', sort_by = 'cpu_percent', sort_order = 'desc', limit = 50 } = options;
        const params = new URLSearchParams({ search, sort_by, sort_order, limit });
        return this.request(`/api/debug/processes?${params}`);
    }

    executeDebugCommand(command, type = 'python', timeout = 15) {
        return this.request('/api/debug/exec', {
            method: 'POST',
            body: JSON.stringify({ command, type, timeout })
        });
    }

    getDebugCache(options = {}) {
        const { pattern = '*', limit = 20 } = options;
        const params = new URLSearchParams({ pattern, limit });
        return this.request(`/api/debug/cache?${params}`);
    }

    clearDebugCache(confirm = true) {
        return this.request(`/api/debug/cache/clear?confirm=${confirm}`, {
            method: 'DELETE'
        });
    }

    setDebugLogLevel(level) {
        return this.request('/api/debug/loglevel', {
            method: 'POST',
            body: JSON.stringify({ level })
        });
    }

    getProcessDetails(pid) {
        return this.request(`/api/debug/processes/${pid}/details`);
    }

    killProcess(pid) {
        return this.request(`/api/debug/processes/${pid}/kill`, {
            method: 'POST'
        });
    }

    // ============================================================
    // ۲۱. Self-Healing
    // ============================================================

    getHealingStatus() {
        return this.request('/api/healing/status');
    }

    triggerHealing() {
        return this.request('/api/healing/trigger', {
            method: 'POST'
        });
    }

    resetHealing() {
        return this.request('/api/healing/reset', {
            method: 'POST'
        });
    }

    // در ApiClient class اضافه کن:

// ============================================================
// ۲۳. تنظیمات (SETTINGS)
// ============================================================

    getSettings() {
        return this.request('/api/settings');
    }

    getSettingsCategories() {
        return this.request('/api/settings/categories');
    }

    getSettingsCategory(category) {
        return this.request(`/api/settings/${category}`);
    }

    saveSettingsCategory(category, data) {
        return this.request(`/api/settings/${category}`, {
            method: 'POST',
            body: JSON.stringify(data)
        });
    }

    resetSettingsCategory(category) {
        return this.request(`/api/settings/${category}`, {
            method: 'DELETE'
        });
    }

    resetAllSettings() {
        return this.request('/api/settings/reset', {
            method: 'POST'
        });
    }

    changePassword(currentPassword, newPassword) {
        return this.request('/api/user/change-password', {
            method: 'POST',
            body: JSON.stringify({
                current_password: currentPassword,
                new_password: newPassword
            })
        });
    }
    // ============================================================
    // ۲۲. Debug - جدید (🆕)
    // ============================================================

    getDebugEnv() {
        return this.request('/api/debug/env');
    }

    getDebugDbDetail() {
        return this.request('/api/debug/db-detail');
    }

    getDebugFullStatus() {
        return this.request('/api/debug/full-status');
    }
}

// ===== SINGLETON =====
const api = new ApiClient();
window.api = api;

console.log('✅ API Client v11.0 loaded');
