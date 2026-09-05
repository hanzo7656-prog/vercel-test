// ============================================================
// api.js - Unified API Client v10.1
// کاملاً هماهنگ با اندپوینت‌های تفکیک شده بک‌اند
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

    getHealthDatabase() {
        return this.request('/api/health/database');
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
    // ۲. آمار واقعی اپلیکیشن (APP STATS)
    // ============================================================

    getAppStats() {
        return this.request('/api/app/stats');
    }

    // ============================================================
    // ۳. دیتابیس - PostgreSQL
    // ============================================================

    getPostgreSQLTables() {
        return this.request('/api/db/postgresql/tables');
    }

    getPostgreSQLTableData(tableName, options = {}) {
        const { limit = 100, offset = 0, search = '', sort_by = 'id', sort_order = 'DESC', format = 'json' } = options;
        const params = new URLSearchParams({ limit, offset, search, sort_by, sort_order, format });
        return this.request(`/api/db/postgresql/table/${tableName}?${params}`);
    }

    getPostgreSQLStats() {
        return this.request('/api/db/postgresql/stats');
    }

    exportPostgreSQLTable(tableName, format = 'csv', limit = 10000) {
        return this.request(`/api/db/postgresql/export/${tableName}?format=${format}&limit=${limit}`);
    }

    exportPostgreSQLTableCSV(tableName) {
        window.open(`/api/db/postgresql/export/${tableName}?format=csv`, '_blank');
    }

    backupPostgreSQL() {
        window.open('/api/db/postgresql/backup', '_blank');
    }

    exportPostgreSQLRow(tableName, rowId, format = 'json') {
        const params = new URLSearchParams({ format });
        return this.request(`/api/db/postgresql/table/${tableName}/export/row/${rowId}?${params}`);
    }

    // ============================================================
    // ۴. دیتابیس - Redis
    // ============================================================

    getRedisKeys(options = {}) {
        const { pattern = '*', limit = 100, search = '' } = options;
        const params = new URLSearchParams({ pattern, limit, search });
        return this.request(`/api/db/redis/keys?${params}`);
    }

    getRedisStats() {
        return this.request('/api/db/redis/stats');
    }

    clearRedis(confirm = true) {
        return this.request(`/api/db/redis/clear?confirm=${confirm}`, {
            method: 'DELETE'
        });
    }

    getRedisKey(key) {
        return this.request(`/api/db/redis/key/${encodeURIComponent(key)}`);
    }

    exportRedisKey(key) {
        return this.request(`/api/db/redis/key/${encodeURIComponent(key)}/export`);
    }

    // ============================================================
    // ۵. دیتابیس - SQLite
    // ============================================================

    getSQLiteTables() {
        return this.request('/api/db/sqlite/tables');
    }

    getSQLiteTableData(tableName, options = {}) {
        const { limit = 100, offset = 0, search = '', format = 'json' } = options;
        const params = new URLSearchParams({ limit, offset, search, format });
        return this.request(`/api/db/sqlite/table/${tableName}?${params}`);
    }

    getSQLiteStats() {
        return this.request('/api/db/sqlite/stats');
    }

    exportSQLiteTable(tableName, format = 'csv', limit = 10000) {
        return this.request(`/api/db/sqlite/export/${tableName}?format=${format}&limit=${limit}`);
    }

    exportSQLiteTableCSV(tableName) {
        window.open(`/api/db/sqlite/export/${tableName}?format=csv`, '_blank');
    }

    exportSQLiteRow(tableName, rowId, format = 'json') {
        const params = new URLSearchParams({ format });
        return this.request(`/api/db/sqlite/table/${tableName}/export/row/${rowId}?${params}`);
    }

    // ============================================================
    // ۶. دیتابیس - عمومی
    // ============================================================

    searchDatabase(query, tables = '') {
        const params = new URLSearchParams({ q: query });
        if (tables) params.append('tables', tables);
        return this.request(`/api/db/search?${params}`);
    }

    executeQuery(query) {
        return this.request('/api/db/query', {
            method: 'POST',
            body: JSON.stringify({ query })
        });
    }

    getDatabaseHealth() {
        return this.request('/api/db/health');
    }

    getDBMonitor() {
        return this.request('/api/db/monitor');
    }

    // ===== جدید: دیتابیس عمومی =====
    getDBTables() {
        return this.request('/api/db/tables');
    }

    getDBStats() {
        return this.request('/api/db/stats');
    }

    runDBMigration() {
        return this.request('/api/db/migrate', {
            method: 'POST'
        });
    }

    // ============================================================
    // ۷. مدل (MODEL)
    // ============================================================

    getModelStatus() {
        return this.request('/api/model/status');
    }

    getModelHistory(limit = 20) {
        return this.request(`/api/model/history?limit=${limit}`);
    }

    getModelFeatures() {
        return this.request('/api/model/features');
    }

    // ===== جدید: داده‌های آموزشی مدل =====
    getModelData() {
        return this.request('/api/model/data');
    }

    // ===== جدید: اهمیت ویژگی‌ها =====
    getModelImportance() {
        return this.request('/api/model/importance');
    }

    // ===== جدید: عملکرد مدل برای نمودار =====
    getModelPerformance() {
        return this.request('/api/model/performance');
    }

    trainModel(options = {}) {
        const { period = '1m', coins = ['bitcoin', 'ethereum'], incremental = false } = options;
        return this.request('/api/model/train', {
            method: 'POST',
            body: JSON.stringify({ period, coins, incremental })
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

    // ============================================================
    // ۸. زمان‌بندی (SCHEDULE)
    // ============================================================

    getScheduleStatus() {
        return this.request('/api/schedule/status');
    }

    startSchedule(options = {}) {
        const { interval = 6, period = '1m', coins = ['bitcoin', 'ethereum'], incremental = true } = options;
        return this.request('/api/schedule/start', {
            method: 'POST',
            body: JSON.stringify({ interval, period, coins, incremental })
        });
    }

    stopSchedule() {
        return this.request('/api/schedule/stop', {
            method: 'POST'
        });
    }

    // ============================================================
    // ۹. پیش‌بینی (PREDICTIONS)
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

    // ===== جدید: تاریخچه پیش‌بینی‌ها =====
    getPredictionHistory(limit = 50, coin = null) {
        const params = new URLSearchParams({ limit });
        if (coin) params.append('coin', coin);
        return this.request(`/api/predict/history?${params}`);
    }

    // ============================================================
    // ۱۰. کوین‌استتس (COINSTATS)
    // ============================================================
    // ===== دریافت لیست ارزها =====
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

    // ============================================================
    // ۱۱. هشدارها (ALERTS)
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
    // ۱۲. کاربر (USER)
    // ============================================================

    getUserInfo() {
        return this.request('/api/user');
    }

    getCredits() {
        return this.request('/api/credits');
    }

    // ============================================================
    // ۱۳. احراز هویت (AUTH)
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
    // ۱۴. دیباگ (DEBUG)
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

    searchCache(pattern = '*', limit = 50) {
        const params = new URLSearchParams({ pattern, limit });
        return this.request(`/api/debug/cache/search?${params}`);
    }

    deleteCacheKey(key) {
        const params = new URLSearchParams({ key });
        return this.request(`/api/debug/cache/key?${params}`, {
            method: 'DELETE'
        });
    }

    purgeCache() {
        return this.request('/api/debug/cache/purge', {
            method: 'POST'
        });
    }

    // ============================================================
    // ۱۵. Self-Healing (خودترمیمی)
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
}

// ===== SINGLETON =====
const api = new ApiClient();
window.api = api;

console.log('✅ API Client v10.1 loaded');
