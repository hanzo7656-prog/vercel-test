// ============================================================
// api.js - Unified API Client v13.0
// Gemini-only (RuleEngine legacy حذف شد)
// هماهنگ با api_routes.py + ai_routes.py
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

    getHealthApis() {
        return this.request('/api/health/apis');
    }

    // ============================================================
    // ۲. آمار اپلیکیشن (APP STATS)
    // ============================================================

    getAppStats() {
        return this.request('/api/app/stats');
    }

    // ============================================================
    // ۳. Quota Management
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
    // ۴. دیتابیس - PostgreSQL
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
    // ۶. دیتابیس - Archive
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
    // ۷. دیتابیس - Health & Status
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
    // ۸. دیتابیس - Router & Registry
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
    // ۹. دیتابیس - Maintenance
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
        return this.request('/api/db/health/summary');
    }

    // ============================================================
    // ۱۱. دیتابیس - Schema & Migration
    // ============================================================

    getSchemaStatus() {
        return this.request('/api/db/schema-status');
    }

    migrateDatabases() {
        return this.request('/api/db/migrate', {
            method: 'POST'
        });
    }

    migrateExisting() {
        return this.request('/api/db/migrate-existing', {
            method: 'POST'
        });
    }

    initAllDatabases() {
        return this.request('/api/db/init-all', {
            method: 'POST'
        });
    }

    // ============================================================
    // ۱۲. OHLCV Repository
    // ============================================================

    getOHLCVStats() {
        return this.request('/api/db/ohlcv/stats');
    }

    cleanupOHLCV(data) {
        return this.request('/api/db/ohlcv/cleanup', {
            method: 'POST',
            body: JSON.stringify(data)
        });
    }

    // ============================================================
    // ۱۳. AI (Gemini) 🆕
    // ============================================================

    // ===== AI Home =====
    getAIHome() {
        return this.request('/api/ai');
    }

    getAIStatus() {
        return this.request('/api/ai/status');
    }

    getAIStats() {
        return this.request('/api/ai/stats');
    }

    // ===== Chat =====
    aiChat(message, options = {}) {
        const {
            history = [],
            include_context = true,
            temperature = 0.7
        } = options;
        return this.request('/api/ai/chat', {
            method: 'POST',
            body: JSON.stringify({ message, history, include_context, temperature })
        });
    }

    aiChatStream(message, options = {}) {
        // برای SSE stream، باید از EventSource یا fetch stream استفاده کنی
        // این متد فقط URL رو برمی‌گردونه
        return '/api/ai/chat/stream';
    }

    // ===== Analyze Image =====
    aiAnalyzeImage(imageBase64, options = {}) {
        const {
            mimeType = 'image/jpeg',
            prompt = null,
            includeContext = true
        } = options;
        return this.request('/api/ai/analyze-image', {
            method: 'POST',
            body: JSON.stringify({
                image_base64: imageBase64,
                mime_type: mimeType,
                prompt,
                include_context: includeContext
            })
        });
    }

    aiAnalyzeImageFile(file, options = {}) {
        // برای multipart/form-data
        const formData = new FormData();
        formData.append('image', file);
        if (options.prompt) formData.append('prompt', options.prompt);
        formData.append('include_context', options.includeContext !== false);

        const url = `${this.baseURL}/api/ai/analyze-image`;
        return fetch(url, {
            method: 'POST',
            credentials: 'include',
            body: formData
        }).then(r => r.json());
    }

    // ===== Explain Signal =====
    aiExplain(coin, signalData, includeMarketContext = true) {
        return this.request('/api/ai/explain', {
            method: 'POST',
            body: JSON.stringify({
                coin,
                signal_data: signalData,
                include_market_context: includeMarketContext
            })
        });
    }

    // ============================================================
    // ۱۴. Prediction (با engine انتخاب)
    // ============================================================

    predictSingle(coin = 'bitcoin', period = '24h', engine = 'auto') {
        const params = new URLSearchParams({ coin, period, engine });
        return this.request(`/api/predict/single?${params}`);
    }

    predictMultiple(coins, period = '24h', engine = 'auto') {
        return this.request('/api/predict/multiple', {
            method: 'POST',
            body: JSON.stringify({ coins, period, engine })
        });
    }

    predictEngines() {
        return this.request('/api/predict/engines');
    }

    getPredictionHistory(options = {}) {
        const { limit = 50, coin = '' } = options;
        const params = new URLSearchParams({ limit });
        if (coin) params.append('coin', coin);
        return this.request(`/api/predict/history?${params}`);
    }

    getPredictionHistoryStats() {
        return this.request('/api/predict/history/stats');
    }

    // ============================================================
    // ۱۵. CoinStats
    // ============================================================

    getCoinsList(options = {}) {
        const { limit = 50, page = 1, currency = 'USD', search = '' } = options;
        const params = new URLSearchParams({ limit, page, currency });
        if (search) params.append('search', search);
        return this.request(`/api/coinstats/coins?${params}`);
    }

    getCoinPrice(coin) {
        return this.request(`/api/coinstats/price/${encodeURIComponent(coin)}`);
    }

    getCoinsPrices() {
        return this.request('/api/coinstats/prices');
    }

    getFearGreed() {
        return this.request('/api/coinstats/fear-greed');
    }

    getBTCDominance() {
        return this.request('/api/coinstats/btc-dominance');
    }

    getGlobalMarket() {
        return this.request('/api/coinstats/global-market');
    }

    getAllCoinStats() {
        return this.request('/api/coinstats/all');
    }

    getChartData(coin, period = '1m') {
        return this.request(`/api/coinstats/chart/${encodeURIComponent(coin)}?period=${period}`);
    }

    getOHLCV(options = {}) {
        const {
            coin = '',
            pair = '',
            interval = '1h',
            range = '1mo',
            limit = 1000,
            min_candles = 50
        } = options;
        const params = new URLSearchParams({ interval, range, limit, min_candles });
        if (coin) params.append('coin', coin);
        if (pair) params.append('pair', pair);
        return this.request(`/api/coinstats/ohlcv?${params}`);
    }

    getOHLCVStatsOld() {
        return this.request('/api/coinstats/ohlcv-stats');
    }

    cleanupOHLCVOld(data) {
        return this.request('/api/coinstats/ohlcv-cleanup', {
            method: 'POST',
            body: JSON.stringify(data)
        });
    }

    // ============================================================
    // ۱۶. Crypto (Realtime)
    // ============================================================

    getRealtimePrices(symbols = null) {
        const params = symbols ? `?symbols=${symbols.join(',')}` : '';
        return this.request(`/api/crypto/prices${params}`);
    }

    getRealtimePrice(symbol) {
        return this.request(`/api/crypto/price/${encodeURIComponent(symbol)}`);
    }

    getCryptoStats() {
        return this.request('/api/crypto/stats');
    }

    heartbeat() {
        return this.request('/api/crypto/heartbeat', {
            method: 'POST'
        });
    }

    // ===== Binance WS =====
    getBinanceWSStats() {
        return this.request('/api/crypto/ws-stats');
    }

    getBinanceWSPrices() {
        return this.request('/api/crypto/ws-prices');
    }

    getBinanceWSPrice(symbol) {
        return this.request(`/api/crypto/ws-price/${encodeURIComponent(symbol)}`);
    }

    getBinanceWSOrderbook(symbol, levels = null) {
        const params = levels ? `?levels=${levels}` : '';
        return this.request(`/api/crypto/ws-orderbook/${encodeURIComponent(symbol)}${params}`);
    }

    binanceWSSubscribe(symbol) {
        return this.request('/api/crypto/ws-subscribe', {
            method: 'POST',
            body: JSON.stringify({ symbol })
        });
    }

    binanceWSUnsubscribe(symbol) {
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

    resolveAlert(alertId) {
        return this.request(`/api/alerts/${alertId}/resolve`, {
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
    // ۱۹. ورود (LOGIN)
    // ============================================================

    login(username, password) {
        return this.request('/api/login', {
            method: 'POST',
            body: JSON.stringify({ username, password })
        });
    }

    // ============================================================
    // ۲۰. دیباگ (DEBUG)
    // ============================================================

    debugStatus() {
        return this.request('/api/debug/status');
    }

    debugLogs(options = {}) {
        const { limit = 50, level = 'ALL', since = '' } = options;
        const params = new URLSearchParams({ limit, level });
        if (since) params.append('since', since);
        return this.request(`/api/debug/logs?${params}`);
    }

    debugLogsClear() {
        return this.request('/api/debug/logs/clear?confirm=true', {
            method: 'DELETE'
        });
    }

    debugSystem() {
        return this.request('/api/debug/system');
    }

    debugProcesses(options = {}) {
        const { search = '', sort_by = 'cpu_percent', sort_order = 'desc', limit = 50 } = options;
        const params = new URLSearchParams({ search, sort_by, sort_order, limit });
        return this.request(`/api/debug/processes?${params}`);
    }

    killProcess(pid) {
        return this.request(`/api/debug/processes/${pid}/kill`, {
            method: 'POST'
        });
    }

    processDetails(pid) {
        return this.request(`/api/debug/processes/${pid}/details`);
    }

    debugExec(command, type = 'python', timeout = 15) {
        return this.request('/api/debug/exec', {
            method: 'POST',
            body: JSON.stringify({ command, type, timeout })
        });
    }

    debugCache(options = {}) {
        const { pattern = '*', limit = 20 } = options;
        const params = new URLSearchParams({ pattern, limit });
        return this.request(`/api/debug/cache?${params}`);
    }

    debugCacheClear() {
        return this.request('/api/debug/cache/clear?confirm=true', {
            method: 'DELETE'
        });
    }

    debugLoglevel(level) {
        return this.request('/api/debug/loglevel', {
            method: 'POST',
            body: JSON.stringify({ level })
        });
    }

    cacheSearch(pattern = '*', limit = 50) {
        const params = new URLSearchParams({ pattern, limit });
        return this.request(`/api/debug/cache/search?${params}`);
    }

    cacheDeleteKey(key) {
        return this.request(`/api/debug/cache/key?key=${encodeURIComponent(key)}`, {
            method: 'DELETE'
        });
    }

    cachePurge() {
        return this.request('/api/debug/cache/purge', {
            method: 'POST'
        });
    }

    debugEnv() {
        return this.request('/api/debug/env');
    }

    debugDBDetail() {
        return this.request('/api/debug/db-detail');
    }

    debugFullStatus() {
        return this.request('/api/debug/full-status');
    }

    // ============================================================
    // ۲۱. Cache Monitoring (Dual Redis)
    // ============================================================

    cacheStats() {
        return this.request('/api/debug/cache/stats');
    }

    cacheDetailed() {
        return this.request('/api/debug/cache/detailed');
    }

    cacheSwitch(target = 'auto') {
        return this.request('/api/debug/cache/switch', {
            method: 'POST',
            body: JSON.stringify({ target })
        });
    }

    cacheActive() {
        return this.request('/api/debug/cache/active');
    }

    cacheHealth() {
        return this.request('/api/debug/cache/health');
    }

    // ============================================================
    // ۲۲. Self-Healing 🆕
    // ============================================================

    getHealingStatus() {
        return this.request('/api/healing/status');
    }

    triggerHealing(force = null) {
        const body = force ? { force } : {};
        return this.request('/api/healing/trigger', {
            method: 'POST',
            body: JSON.stringify(body)
        });
    }

    // متدهای convenience برای force actions
    forceHealingClearCache() {
        return this.triggerHealing('cache');
    }

    forceHealingCleanPredictions() {
        return this.triggerHealing('predictions');
    }

    forceHealingCleanOHLCV() {
        return this.triggerHealing('ohlcv');
    }

    forceHealingReconnect() {
        return this.triggerHealing('reconnect');
    }

    resetHealing() {
        return this.request('/api/healing/reset', {
            method: 'POST'
        });
    }
    // ============================================================
    // ۲۲. Settings
    // ============================================================

    getAllSettings() {
        return this.request('/api/settings');
    }

    getSettingsCategories() {
        return this.request('/api/settings/categories');
    }

    getSettingsCategory(category) {
        return this.request(`/api/settings/${encodeURIComponent(category)}`);
    }

    saveSettingsCategory(category, data) {
        return this.request(`/api/settings/${encodeURIComponent(category)}`, {
            method: 'POST',
            body: JSON.stringify(data)
        });
    }

    resetSettingsCategory(category) {
        return this.request(`/api/settings/${encodeURIComponent(category)}`, {
            method: 'DELETE'
        });
    }

    resetAllSettings() {
        return this.request('/api/settings/reset', {
            method: 'POST'
        });
    }
}


// ============================================================
// Singleton Export
// ============================================================

const api = new ApiClient();

// برای استفاده در ماژول‌ها (اگه ES modules داری)
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { ApiClient, api };
}
