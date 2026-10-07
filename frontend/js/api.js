// ============================================================
// api.js - Unified API Client v12.0
// هماهنگ با api_routes.py + model_routes.py
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
    // ۱۱. دیتابیس - Schema & Migration (🆕 v12.0)
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
    // ۱۲. OHLCV Repository (🆕 v12.0)
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
    // ۱۳. مدل - Status & Info (MODEL)
    // ============================================================

    getModelHome() {
        return this.request('/api/model/');
    }

    getModelStatus() {
        return this.request('/api/model/status');
    }

    getModelStats() {
        return this.request('/api/model/stats');
    }

    getTrainerStats() {
        return this.request('/api/model/trainer-stats');
    }

    // ============================================================
    // ۱۴. مدل - Rules (🆕 v12.0)
    // ============================================================

    getModelRules() {
        return this.request('/api/model/rules');
    }

    getModelRule(name) {
        return this.request(`/api/model/rules/${encodeURIComponent(name)}`);
    }

    // ============================================================
    // ۱۵. مدل - Config (🆕 v12.0)
    // ============================================================

    getModelConfig() {
        return this.request('/api/model/config');
    }

    updateModelConfig(data) {
        return this.request('/api/model/config', {
            method: 'POST',
            body: JSON.stringify(data)
        });
    }

    updateRuntimeConfig(data) {
        return this.request('/api/model/config/runtime', {
            method: 'PATCH',
            body: JSON.stringify(data)
        });
    }

    resetRuntimeConfig() {
        return this.request('/api/model/config/runtime', {
            method: 'DELETE'
        });
    }

    validateConfig(data) {
        return this.request('/api/model/config/validate', {
            method: 'POST',
            body: JSON.stringify(data)
        });
    }

    // ============================================================
    // ۱۶. مدل - Calibration (🆕 v12.0)
    // ============================================================

    getCalibrationProfiles() {
        return this.request('/api/model/calibrate/profiles');
    }

    calibrateModel(data = {}) {
        return this.request('/api/model/calibrate', {
            method: 'POST',
            body: JSON.stringify(data)
        });
    }

    forceCalibrate(data = {}) {
        return this.request('/api/model/calibrate/force', {
            method: 'POST',
            body: JSON.stringify(data)
        });
    }

    getCalibrationHistory(options = {}) {
        const { limit = 20, period = '' } = options;
        const params = new URLSearchParams({ limit });
        if (period) params.append('period', period);
        return this.request(`/api/model/calibrate/history?${params}`);
    }

    // ============================================================
    // ۱۷. مدل - Versions (🆕 v12.0)
    // ============================================================

    getVersions(options = {}) {
        const { limit = 50, model_type = 'rule_config' } = options;
        const params = new URLSearchParams({ limit, model_type });
        return this.request(`/api/model/versions?${params}`);
    }

    getVersionDetail(version) {
        return this.request(`/api/model/versions/${encodeURIComponent(version)}`);
    }

    activateVersion(version) {
        return this.request(`/api/model/versions/${encodeURIComponent(version)}/activate`, {
            method: 'POST'
        });
    }

    deleteVersion(version) {
        return this.request(`/api/model/versions/${encodeURIComponent(version)}`, {
            method: 'DELETE'
        });
    }

    exportVersion(version, download = false) {
        const params = download ? '?download=true' : '';
        if (download) {
            window.open(`/api/model/export/${encodeURIComponent(version)}${params}`, '_blank');
            return Promise.resolve({ success: true, message: 'Download started' });
        }
        return this.request(`/api/model/export/${encodeURIComponent(version)}${params}`);
    }

    // ============================================================
    // ۱۸. مدل - Schedule (🆕 v12.0)
    // ============================================================

    getScheduleStatus() {
        return this.request('/api/model/schedule/status');
    }

    startSchedule(options = {}) {
        const {
            interval_hours = 6,
            period = '1m',
            profile_name = 'balanced',
            coins = null
        } = options;
        return this.request('/api/model/schedule/start', {
            method: 'POST',
            body: JSON.stringify({ interval_hours, period, profile_name, coins })
        });
    }

    stopSchedule() {
        return this.request('/api/model/schedule/stop', {
            method: 'POST'
        });
    }

    // ============================================================
    // ۱۹. مدل - Screener (🆕 v12.0)
    // ============================================================

    screenerScan(data = {}) {
        return this.request('/api/model/screener/scan', {
            method: 'POST',
            body: JSON.stringify(data)
        });
    }

    screenerLatest() {
        return this.request('/api/model/screener/scan/latest');
    }

    screenerResult(scanId) {
        return this.request(`/api/model/screener/scan/${encodeURIComponent(scanId)}`);
    }

    screenerSingle(data) {
        return this.request('/api/model/screener/scan/single', {
            method: 'POST',
            body: JSON.stringify(data)
        });
    }

    screenerHistory(options = {}) {
        const { limit = 20 } = options;
        return this.request(`/api/model/screener/history?limit=${limit}`);
    }

    screenerHistoryStats() {
        return this.request('/api/model/screener/history/stats');
    }

    screenerConfig() {
        return this.request('/api/model/screener/config');
    }

    updateScreenerConfig(data) {
        return this.request('/api/model/screener/config', {
            method: 'PATCH',
            body: JSON.stringify(data)
        });
    }

    validateScreenerConfig(data) {
        return this.request('/api/model/screener/config/validate', {
            method: 'POST',
            body: JSON.stringify(data)
        });
    }

    // ============================================================
    // ۲۰. مدل - State Machine (🆕 v12.0)
    // ============================================================

    stateHome() {
        return this.request('/api/model/state/');
    }

    stateSummary(symbols = null) {
        const params = symbols ? `?symbols=${symbols.join(',')}` : '';
        return this.request(`/api/model/state/summary${params}`);
    }

    stateTransitions(options = {}) {
        const { limit = 50, from_state = '', to_state = '' } = options;
        const params = new URLSearchParams({ limit });
        if (from_state) params.append('from_state', from_state);
        if (to_state) params.append('to_state', to_state);
        return this.request(`/api/model/state/transitions?${params}`);
    }

    stateSnapshots(limit = 100) {
        return this.request(`/api/model/state/snapshots?limit=${limit}`);
    }

    stateSymbol(symbol) {
        return this.request(`/api/model/state/${encodeURIComponent(symbol)}`);
    }

    stateSymbolTransitions(symbol, limit = 50) {
        return this.request(`/api/model/state/${encodeURIComponent(symbol)}/transitions?limit=${limit}`);
    }

    stateSymbolReset(symbol) {
        return this.request(`/api/model/state/${encodeURIComponent(symbol)}/reset`, {
            method: 'POST'
        });
    }

    stateSymbolActivate(symbol, data = {}) {
        return this.request(`/api/model/state/${encodeURIComponent(symbol)}/activate`, {
            method: 'POST',
            body: JSON.stringify(data)
        });
    }

    stateSymbolCooling(symbol, data = {}) {
        return this.request(`/api/model/state/${encodeURIComponent(symbol)}/cooling`, {
            method: 'POST',
            body: JSON.stringify(data)
        });
    }

    // ============================================================
    // ۲۱. پیش‌بینی (PREDICTIONS)
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

    getPredictionHistory(limit = 50, coin = null) {
        const params = new URLSearchParams({ limit });
        if (coin) params.append('coin', coin);
        return this.request(`/api/predict/history?${params}`);
    }

    getPredictionHistoryStats() {
        return this.request('/api/predict/history/stats');
    }

    // ============================================================
    // ۲۲. کوین‌استتس (COINSTATS)
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

    getGlobalMarket() {
        return this.request('/api/coinstats/global-market');
    }
    
    getAllCoinStats() {
        return this.request('/api/coinstats/all');
    }

    getChartData(coin, period = '1m') {
        return this.request(`/api/coinstats/chart/${coin}?period=${period}`);
    }

    // ============================================================
    // OHLCV — داده کندل واقعی (از DB یا CoinStats)
    // ============================================================

    /**
     * دریافت OHLCV کندل‌ها
     * @param {string} coin - 'bitcoin' یا 'BTC' یا 'BTC/USDT'
     * @param {string} interval - '5m' | '15m' | '30m' | '1h' | '4h' | '1d' | '1w'
     * @param {string} range - '1h' | '6h' | '24h' | '1w' | '1mo' | '3mo' | '6mo' | '1y' | 'all'
     * @param {number} limit - حداکثر تعداد (پیش‌فرض: 1000)
     */
    async getOHLCV(coin, interval = '1h', range = '1mo', limit = 1000, minCandles = 50) {
        const params = new URLSearchParams({
            coin,
            interval,
            range,
            limit,
            min_candles: minCandles,
        });
        return this.request(`/api/coinstats/ohlcv?${params}`);
    },

    /**
     * آمار OHLCV (برای دیباگ)
     */
    async getOHLCVStats() {
        return this.request('/api/coinstats/ohlcv-stats');
    },

    /**
     * پاکسازی رکوردهای قدیمی OHLCV
     * @param {number} retentionDays - مدت نگهداری (پیش‌فرض: 90)
     * @param {string} interval - فقط یک interval خاص (اختیاری)
     */
    async cleanupOHLCV(retentionDays = 90, interval = null) {
        const body = { retention_days: retentionDays };
        if (interval) body.interval = interval;
    
        return this.request('/api/coinstats/ohlcv-cleanup', {
            method: 'POST',
            body: JSON.stringify(body),
        });
    }
    // ============================================================
    // ۲۳. قیمت‌های لحظه‌ای (CRYPTO)
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
    // ۲۵. هشدارها (ALERTS)
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
    // ۲۶. کاربر (USER)
    // ============================================================

    getUserInfo() {
        return this.request('/api/user');
    }

    getCredits() {
        return this.request('/api/credits');
    }

    // ============================================================
    // ۲۷. احراز هویت (AUTH)
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
    // ۲۸. تنظیمات (SETTINGS)
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
    // ۲۹. Self-Healing
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

    // ============================================================
    // ۳۰. دیباگ (DEBUG)
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

console.log('✅ API Client v12.0 loaded');
