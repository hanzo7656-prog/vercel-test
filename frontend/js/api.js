// ============================================================
// api.js - Unified API Client v4.0
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
            console.error(`API Error [${endpoint}]:`, error);
            throw error;
        }
    }
    
    // ===== AUTH =====
    login(username, password) {
        return this.request('/api/login', {
            method: 'POST',
            body: JSON.stringify({ username, password })
        });
    }
    
    logout() {
        return this.request('/logout', { method: 'POST' });
    }
    
    getUser() {
        return this.request('/api/user');
    }
    
    // ===== METRICS =====
    getMetrics() {
        return this.request('/api/metrics');
    }
    
    getHealth() {
        return this.request('/api/health');
    }
    
    getHealthDatabase() {
        return this.request('/api/health/database');
    }
    
    getStats() {
        return this.request('/stats');
    }
    
    // ===== PREDICTIONS =====
    predict(coin, period = '24h') {
        return this.request(`/api/predict?coin=${encodeURIComponent(coin)}&period=${period}`);
    }
    
    predictMultiple(coins, period = '24h') {
        return this.request('/api/predict/multiple', {
            method: 'POST',
            body: JSON.stringify({ coins, period })
        });
    }
    
    // ===== MODEL =====
    getModelStatus() {
        return this.request('/api/model?section=status');
    }
    
    getModelHistory(limit = 20) {
        return this.request(`/api/model?section=history&limit=${limit}`);
    }
    
    getModelFeatures() {
        return this.request('/api/model?section=features');
    }
    
    getModelData() {
        return this.request('/api/model?section=data');
    }
    
    trainModel(period = '1m', coins = ['bitcoin', 'ethereum'], incremental = false) {
        return this.request('/api/model', {
            method: 'POST',
            body: JSON.stringify({
                action: 'train',
                period,
                coins,
                incremental
            })
        });
    }
    
    toggleSchedule(enabled, interval = 6, period = '1m', coins = ['bitcoin', 'ethereum'], incremental = true) {
        return this.request('/api/model/schedule', {
            method: 'POST',
            body: JSON.stringify({
                enabled,
                interval,
                period,
                coins,
                incremental
            })
        });
    }
    
    getModelSchedule() {
        return this.request('/api/model/schedule');
    }
    
    stopTraining() {
        return this.request('/api/model/schedule', {
            method: 'DELETE'
        });
    }
    
    exportModel(version = null) {
        const url = version ? `/api/model/export?version=${version}` : '/api/model/export';
        window.open(url, '_blank');
    }
    
    // ===== DATABASE =====
    getTables() {
        return this.request('/api/db?table=');
    }
    
    getTableData(table, limit = 100, offset = 0, format = 'json') {
        return this.request(`/api/db?table=${encodeURIComponent(table)}&limit=${limit}&offset=${offset}&format=${format}`);
    }
    
    searchDatabase(query, tables = '') {
        const url = tables 
            ? `/api/db/search?q=${encodeURIComponent(query)}&tables=${encodeURIComponent(tables)}`
            : `/api/db/search?q=${encodeURIComponent(query)}`;
        return this.request(url);
    }
    
    getRedisKeys() {
        return this.request('/api/db/redis/keys');
    }
    
    getSQLiteTables() {
        return this.request('/api/db/sqlite/tables');
    }
    
    getDBStats(section = 'tables') {
        return this.request(`/api/db/stats?section=${section}`);
    }
    
    getDBBackup() {
        window.open('/api/db/backup', '_blank');
    }
    
    // ===== ALERTS =====
    getAlerts(limit = 20, resolved = null) {
        let url = `/api/alerts?limit=${limit}`;
        if (resolved !== null) {
            url += `&resolved=${resolved}`;
        }
        return this.request(url);
    }
    
    resolveAlert(id) {
        return this.request(`/api/alerts/${id}/resolve`, {
            method: 'POST'
        });
    }
    
    // ===== COINSTATS =====
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
    
    // ===== CREDITS =====
    getCredits() {
        return this.request('/api/credits');
    }
    
    // ===== DEBUG =====
    getDebugStatus() {
        return this.request('/api/debug?section=status');
    }
    
    getDebugLogs(limit = 50) {
        return this.request(`/api/debug?section=logs&limit=${limit}`);
    }
    
    getDebugSystem() {
        return this.request('/api/debug?section=system');
    }
    
    getDebugProcesses() {
        return this.request('/api/debug?section=processes');
    }
    
    getDebugCache() {
        return this.request('/api/debug?section=cache');
    }
    
    executeCommand(command) {
        return this.request('/api/debug', {
            method: 'POST',
            body: JSON.stringify({
                action: 'exec',
                command
            })
        });
    }
    
    setLogLevel(level) {
        return this.request('/api/debug', {
            method: 'POST',
            body: JSON.stringify({
                action: 'set_loglevel',
                level
            })
        });
    }
    
    clearCache() {
        return this.request('/api/debug', {
            method: 'DELETE',
            body: JSON.stringify({ target: 'cache' })
        });
    }
    
    clearLogs() {
        return this.request('/api/debug', {
            method: 'DELETE',
            body: JSON.stringify({ target: 'logs' })
        });
    }
    
    clearErrors() {
        return this.request('/api/debug', {
            method: 'DELETE',
            body: JSON.stringify({ target: 'errors' })
        });
    }
}

// ===== SINGLETON =====
const api = new ApiClient();
window.api = api;

console.log('✅ API Client v4.0 loaded');
