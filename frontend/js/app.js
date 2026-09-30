// ============================================================
// app.js - Core Application v13.0
// RuleEngine Aware + OHLCV + Screener + State + Calibration
// ============================================================

(function() {
    'use strict';

    // ============================================================
    // Default Settings
    // ============================================================

    const DEFAULT_SCHEDULER = {
        metrics: { enabled: true, interval: 10000 },
        appStats: { enabled: true, interval: 3000 },
        alerts: { enabled: true, interval: 30000 },
        dbHealth: { enabled: true, interval: 60000 },
        modelStatus: { enabled: false, interval: 15000 },
        quotas: { enabled: false, interval: 120000 },
    };

    const DEFAULT_THEME = {
        mode: 'dark',
        accent: 'cyan',
        fontSize: 16,
        font: 'Vazir',
    };

    const DEFAULT_CACHE = {
        coinsList: 86400,
        prices: 60,
        fearGreed: 300,
        btcDominance: 300,
        modelStatus: 10,
        chart: 3600,
    };

    const DEFAULT_NOTIFICATIONS = {
        enabled: true,
        sound: true,
        criticalOnly: false,
        doNotDisturb: false,
        dndStart: '22:00',
        dndEnd: '08:00',
    };

    const DEFAULT_DASHBOARD = {
        showMetrics: true,
        showPrices: true,
        showAlerts: true,
        showModel: true,
        defaultTab: 'dashboard',
    };

    // ============================================================
    // App Class
    // ============================================================

    class App {
        constructor() {
            // ============================================================
            // State
            // ============================================================
            
            this.state = {
                // کاربر
                user: null,
                isAuthenticated: false,
                
                // سیستم
                metrics: null,
                appStats: null,
                dbHealth: null,
                health: null,
                schemaStatus: null,           // 🆕
                ohlcvStats: null,             // 🆕
                
                // مدل (RuleEngine)
                modelStatus: null,
                modelStats: null,             // 🆕
                trainerStats: null,
                modelRules: [],               // 🆕
                modelConfig: null,            // 🆕
                runtimeConfigActive: false,   // 🆕
                
                // Calibration
                calibrationProfiles: [],      // 🆕
                calibrationHistory: [],       // 🆕
                calibrationRunning: false,    // 🆕
                
                // Versions
                versions: [],                 // 🆕
                
                // Schedule
                scheduleStatus: null,         // 🆕
                
                // Screener
                screenerLatest: null,         // 🆕
                screenerHistory: [],          // 🆕
                screenerConfig: null,         // 🆕
                screenerRunning: false,       // 🆕
                
                // State Machine
                stateSummary: null,           // 🆕
                stateSnapshots: [],           // 🆕
                stateTransitions: [],         // 🆕
                
                // دیتابیس
                databases: {},
                quotas: {},
                dbList: [],
                routerStats: null,
                registrySummary: null,
                
                // هشدارها
                alerts: [],
                unreadAlertsCount: 0,
                
                // کش
                cache: {
                    coinsList: null,
                    fearGreed: null,
                    prices: {},
                },
                
                // وضعیت
                isLoading: false,
                errors: [],
                theme: 'dark',
                isInitialized: false,
                isOnline: navigator.onLine,
                
                // تنظیمات
                settings: {
                    scheduler: JSON.parse(JSON.stringify(DEFAULT_SCHEDULER)),
                    theme: JSON.parse(JSON.stringify(DEFAULT_THEME)),
                    cache: JSON.parse(JSON.stringify(DEFAULT_CACHE)),
                    notifications: JSON.parse(JSON.stringify(DEFAULT_NOTIFICATIONS)),
                    dashboard: JSON.parse(JSON.stringify(DEFAULT_DASHBOARD)),
                },
            };
            
            // ============================================================
            // Event Bus
            // ============================================================
            
            this.events = (typeof mitt !== 'undefined') 
                ? mitt() 
                : this._createFallbackEventBus();
            
            // ============================================================
            // Scheduler
            // ============================================================
            
            this._tasks = new Map();
            this._isPaused = false;
            
            // ============================================================
            // Cache Layer
            // ============================================================
            
            this._cache = new Map();
            
            // ============================================================
            // Metrics (Self)
            // ============================================================
            
            this._appMetrics = {
                totalRequests: 0,
                successfulRequests: 0,
                failedRequests: 0,
                totalResponseTime: 0,
                avgResponseTime: 0,
                lastRequestTime: null,
            };
            
            this.listeners = [];
            
            // ============================================================
            // Init
            // ============================================================
            
            this.init();
        }

        // ============================================================
        // Settings System - API Based
        // ============================================================

        async _loadSettingsFromAPI(category) {
            const defaults = {
                scheduler: DEFAULT_SCHEDULER,
                theme: DEFAULT_THEME,
                cache: DEFAULT_CACHE,
                notifications: DEFAULT_NOTIFICATIONS,
                dashboard: DEFAULT_DASHBOARD,
            }[category];
            
            if (!defaults) return {};
            
            try {
                const data = await window.api.getSettingsCategory(category);
                
                if (data.success && data.data?.value) {
                    return this._deepMerge(defaults, data.data.value);
                }
            } catch (e) {
                console.warn(`Failed to load settings '${category}' from API:`, e);
            }
            
            return JSON.parse(JSON.stringify(defaults));
        }

        async _loadAllSettings() {
            const categories = ['scheduler', 'theme', 'cache', 'notifications', 'dashboard'];
            
            const results = await Promise.allSettled(
                categories.map(cat => this._loadSettingsFromAPI(cat))
            );
            
            for (let i = 0; i < categories.length; i++) {
                const cat = categories[i];
                const result = results[i];
                
                if (result.status === 'fulfilled') {
                    this.state.settings[cat] = result.value;
                }
            }
            
            this.events.emit('settings:loaded', this.state.settings);
        }

        _deepMerge(target, source) {
            const result = { ...target };
            for (const key in source) {
                if (source[key] && typeof source[key] === 'object' && !Array.isArray(source[key])) {
                    result[key] = this._deepMerge(target[key] || {}, source[key]);
                } else {
                    result[key] = source[key];
                }
            }
            return result;
        }

        getSettings(category) {
            return this.state.settings[category];
        }

        async saveSettings(category, values) {
            this.state.settings[category] = {
                ...this.state.settings[category],
                ...values,
            };
            
            try {
                const result = await window.api.saveSettingsCategory(
                    category,
                    this.state.settings[category]
                );
                
                if (!result.success) {
                    console.warn('Failed to save settings:', result.error);
                    this.events.emit('settings:saveFailed', { category, error: result.error });
                    return false;
                }
                
                this.events.emit('settings:saved', { category, values });
            } catch (e) {
                console.warn(`Failed to save settings '${category}':`, e);
                this.events.emit('settings:saveFailed', { category, error: e.message });
                return false;
            }
            
            this.applySettings(category);
            this.events.emit(`settings:${category}:changed`, this.state.settings[category]);
            this.notifyListeners();
            
            return true;
        }

        async saveAllSettings() {
            const categories = ['scheduler', 'theme', 'cache', 'notifications', 'dashboard'];
            
            const results = await Promise.allSettled(
                categories.map(cat => 
                    window.api.saveSettingsCategory(cat, this.state.settings[cat])
                )
            );
            
            return results.every(r => 
                r.status === 'fulfilled' && r.value.success
            );
        }

        async resetSettings(category) {
            const defaults = {
                scheduler: DEFAULT_SCHEDULER,
                theme: DEFAULT_THEME,
                cache: DEFAULT_CACHE,
                notifications: DEFAULT_NOTIFICATIONS,
                dashboard: DEFAULT_DASHBOARD,
            }[category];
            
            if (!defaults) return;
            
            try {
                await window.api.resetSettingsCategory(category);
                this.state.settings[category] = JSON.parse(JSON.stringify(defaults));
                this.applySettings(category);
                this.events.emit(`settings:${category}:reset`, defaults);
            } catch (e) {
                console.error(`Reset settings '${category}' error:`, e);
            }
        }

        async resetAllSettings() {
            try {
                await window.api.resetAllSettings();
                
                this.state.settings = {
                    scheduler: JSON.parse(JSON.stringify(DEFAULT_SCHEDULER)),
                    theme: JSON.parse(JSON.stringify(DEFAULT_THEME)),
                    cache: JSON.parse(JSON.stringify(DEFAULT_CACHE)),
                    notifications: JSON.parse(JSON.stringify(DEFAULT_NOTIFICATIONS)),
                    dashboard: JSON.parse(JSON.stringify(DEFAULT_DASHBOARD)),
                };
                
                this.events.emit('settings:allReset');
                return true;
            } catch (e) {
                console.error('Reset all settings error:', e);
                return false;
            }
        }

        applySettings(category) {
            if (category === 'scheduler') {
                this._applySchedulerSettings();
            } else if (category === 'theme') {
                this.applyTheme(this.state.settings.theme.mode);
            }
        }

        // ============================================================
        // Scheduler
        // ============================================================

        _applySchedulerSettings() {
            const { scheduler } = this.state.settings;
            
            for (const name of this._tasks.keys()) {
                this._unscheduleTask(name);
            }
            
            const taskFunctions = {
                metrics: () => this.loadMetrics(),
                appStats: () => this.loadAppStats(),
                alerts: () => this.loadAlerts(),
                dbHealth: () => this.loadDatabaseHealth(),
                modelStatus: () => this.loadModelStatus(),
                quotas: () => this.loadQuotas(),
            };
            
            for (const [name, config] of Object.entries(scheduler)) {
                if (config.enabled && taskFunctions[name]) {
                    this.scheduleTask(name, taskFunctions[name], config.interval);
                }
            }
        }

        scheduleTask(name, fn, interval) {
            this._unscheduleTask(name);
            
            const timer = setInterval(() => {
                if (!this._isPaused && document.visibilityState === 'visible') {
                    try {
                        fn();
                    } catch (e) {
                        console.error(`Task '${name}' error:`, e);
                    }
                }
            }, interval);
            
            this._tasks.set(name, { timer, fn, interval, enabled: true });
        }

        _unscheduleTask(name) {
            const task = this._tasks.get(name);
            if (task && task.timer) {
                clearInterval(task.timer);
            }
            this._tasks.delete(name);
        }

        unscheduleTask(name) {
            this._unscheduleTask(name);
        }

        pauseAllTasks() {
            this._isPaused = true;
            this.events.emit('scheduler:paused');
        }

        resumeAllTasks() {
            this._isPaused = false;
            this.events.emit('scheduler:resumed');
        }

        getTasksStatus() {
            const result = {};
            for (const [name, task] of this._tasks) {
                result[name] = {
                    interval: task.interval,
                    enabled: task.enabled,
                };
            }
            return result;
        }

        // ============================================================
        // Cache Layer
        // ============================================================

        cacheSet(key, value, ttlSeconds = 60) {
            this._cache.set(key, {
                value,
                expires: Date.now() + (ttlSeconds * 1000),
            });
        }

        cacheGet(key, defaultValue = null) {
            const item = this._cache.get(key);
            if (!item) return defaultValue;
            if (item.expires && Date.now() > item.expires) {
                this._cache.delete(key);
                return defaultValue;
            }
            return item.value;
        }

        cacheInvalidate(pattern) {
            if (typeof pattern === 'string') {
                for (const key of this._cache.keys()) {
                    if (key.includes(pattern)) {
                        this._cache.delete(key);
                    }
                }
            } else if (pattern instanceof RegExp) {
                for (const key of this._cache.keys()) {
                    if (pattern.test(key)) {
                        this._cache.delete(key);
                    }
                }
            }
        }

        cacheClear() {
            this._cache.clear();
        }

        cacheStats() {
            return {
                size: this._cache.size,
                keys: Array.from(this._cache.keys()),
            };
        }

        // ============================================================
        // Init
        // ============================================================

        async init() {
            if (this.state.isInitialized) return;

            console.log('🚀 App v13.0 initializing...');

            try {
                // ۱. تنظیمات
                await this._loadAllSettings();
                this.applyTheme(this.state.settings.theme.mode);
                this._applySchedulerSettings();
                
                // ۲. Listeners
                this._setupVisibilityListeners();
                this._setupOnlineListeners();
                this._setupErrorHandlers();
                
                // ۳. اطلاعات پایه
                await this.loadUser();
                await this.loadMetrics();
                await this.loadAppStats();
                await this.loadDatabaseHealth();
                await this.loadAlerts();
                
                // ۴. مدل (RuleEngine-aware)
                await this.loadModelStatus();
                await this.loadModelRules();
                await this.loadModelConfig();
                await this.loadCalibrationProfiles();
                await this.loadVersions();
                
                // ۵. Schema & OHLCV
                await this.loadSchemaStatus();
                await this.loadOHLCVStats();
                
                // ۶. علامت‌گذاری
                this.state.isInitialized = true;
                this.notifyListeners();
                this.events.emit('app:ready', this.state);
                
                console.log('✅ App v13.0 initialized successfully');
            } catch (err) {
                console.error('❌ App initialization failed:', err);
                this.events.emit('app:error', err);
            }
        }

        _setupVisibilityListeners() {
            document.addEventListener('visibilitychange', () => {
                if (document.hidden) {
                    this.events.emit('app:hidden');
                } else {
                    this.events.emit('app:visible');
                    this.loadMetrics();
                }
            });
        }

        _setupOnlineListeners() {
            window.addEventListener('online', () => {
                this.setState({ isOnline: true });
                this.events.emit('app:online');
                window.showToast?.('🟢 اتصال برقرار شد', 'success');
            });
            
            window.addEventListener('offline', () => {
                this.setState({ isOnline: false });
                this.events.emit('app:offline');
                window.showToast?.('🔴 اتصال قطع شد', 'error');
            });
        }

        _setupErrorHandlers() {
            window.addEventListener('error', (e) => {
                console.error('Global error:', e.error);
                this._appMetrics.failedRequests++;
                this.events.emit('app:error', e.error);
            });
            
            window.addEventListener('unhandledrejection', (e) => {
                console.error('Unhandled promise rejection:', e.reason);
                this.events.emit('app:unhandledError', e.reason);
            });
        }

        // ============================================================
        // State Management
        // ============================================================

        setState(newState) {
            this.state = { ...this.state, ...newState };
            this.notifyListeners();
        }

        subscribe(listener) {
            this.listeners.push(listener);
            return () => {
                this.listeners = this.listeners.filter(l => l !== listener);
            };
        }

        notifyListeners() {
            this.listeners.forEach(listener => {
                try {
                    listener(this.state);
                } catch (err) {
                    console.error('Listener error:', err);
                }
            });
        }

        getState() {
            return this.state;
        }

        // ============================================================
        // Event Bus
        // ============================================================

        on(event, handler) {
            this.events.on(event, handler);
            return () => this.events.off(event, handler);
        }

        off(event, handler) {
            this.events.off(event, handler);
        }

        emit(event, data) {
            this.events.emit(event, data);
        }

        _createFallbackEventBus() {
            const handlers = new Map();
            return {
                on: (event, handler) => {
                    if (!handlers.has(event)) handlers.set(event, new Set());
                    handlers.get(event).add(handler);
                },
                off: (event, handler) => {
                    handlers.get(event)?.delete(handler);
                },
                emit: (event, data) => {
                    handlers.get(event)?.forEach(h => {
                        try { h(data); } catch (e) { console.error(e); }
                    });
                },
            };
        }

        _trackRequest(startTime, success) {
            const elapsed = Date.now() - startTime;
            this._appMetrics.totalRequests++;
            if (success) this._appMetrics.successfulRequests++;
            else this._appMetrics.failedRequests++;
            this._appMetrics.totalResponseTime += elapsed;
            this._appMetrics.avgResponseTime = 
                this._appMetrics.totalResponseTime / this._appMetrics.totalRequests;
            this._appMetrics.lastRequestTime = new Date().toISOString();
        }

        getAppMetrics() {
            return { ...this._appMetrics };
        }

        // ============================================================
        // API Calls - User & System
        // ============================================================

        async loadUser() {
            const start = Date.now();
            try {
                const data = await window.api.getUserInfo();
                if (data.success) {
                    this.setState({
                        user: data.data,
                        isAuthenticated: true,
                    });
                    this._trackRequest(start, true);
                    return data.data;
                }
                this._trackRequest(start, false);
            } catch (err) {
                console.error('Failed to load user:', err);
                this._trackRequest(start, false);
            }
            return null;
        }

        async loadMetrics() {
            const start = Date.now();
            try {
                const data = await window.api.getMetrics();
                if (data.success) {
                    this.setState({ metrics: data.data });
                    this._trackRequest(start, true);
                    this.events.emit('metrics:loaded', data.data);
                    return data.data;
                }
                this._trackRequest(start, false);
            } catch (err) {
                console.error('Failed to load metrics:', err);
                this._trackRequest(start, false);
            }
            return null;
        }

        async loadAppStats() {
            const start = Date.now();
            try {
                const data = await window.api.getAppStats();
                if (data.success) {
                    this.setState({ appStats: data.data });
                    this._trackRequest(start, true);
                    return data.data;
                }
                this._trackRequest(start, false);
            } catch (err) {
                console.error('Failed to load app stats:', err);
                this._trackRequest(start, false);
            }
            return null;
        }

        async loadDatabaseHealth() {
            const start = Date.now();
            try {
                const data = await window.api.getHealthSummary();
                if (data.success) {
                    this.setState({ dbHealth: data.data });
                    this._trackRequest(start, true);
                    this.events.emit('db:health', data.data);
                    return data.data;
                }
                this._trackRequest(start, false);
            } catch (err) {
                console.error('Failed to load database health:', err);
                this._trackRequest(start, false);
            }
            return null;
        }

        async loadAlerts() {
            const start = Date.now();
            try {
                const data = await window.api.getAlerts({ limit: 5, resolved: false });
                if (data.success) {
                    const alerts = data.data || [];
                    this.setState({ 
                        alerts,
                        unreadAlertsCount: alerts.length,
                    });
                    this._trackRequest(start, true);
                    this.events.emit('alerts:loaded', alerts);
                    return alerts;
                }
                this._trackRequest(start, false);
            } catch (err) {
                console.error('Failed to load alerts:', err);
                this._trackRequest(start, false);
            }
            return [];
        }

        // ============================================================
        // Model Loaders (RuleEngine)
        // ============================================================

        async loadModelStatus() {
            try {
                const data = await window.api.getModelStatus();
                if (data.success) {
                    this.setState({
                        modelStatus: data.data,
                        runtimeConfigActive: data.data?.runtime_config_active || false,
                    });
                    this.events.emit('model:status', data.data);
                    return data.data;
                }
            } catch (err) {
                console.error('Failed to load model status:', err);
            }
            return null;
        }

        async loadModelStats() {
            try {
                const data = await window.api.getModelStats();
                if (data.success) {
                    this.setState({ modelStats: data.data });
                    this.events.emit('model:stats', data.data);
                    return data.data;
                }
            } catch (err) {
                console.error('Failed to load model stats:', err);
            }
            return null;
        }

        async loadTrainerStats() {
            try {
                const data = await window.api.getTrainerStats();
                if (data.success) {
                    this.setState({ trainerStats: data.data });
                    this.events.emit('trainer:stats', data.data);
                    return data.data;
                }
            } catch (err) {
                console.error('Failed to load trainer stats:', err);
            }
            return null;
        }

        async loadModelRules() {
            try {
                const data = await window.api.getModelRules();
                if (data.success) {
                    this.setState({ modelRules: data.data || [] });
                    this.events.emit('model:rules', data.data);
                    return data.data;
                }
            } catch (err) {
                console.error('Failed to load model rules:', err);
            }
            return [];
        }

        async loadModelConfig() {
            try {
                const data = await window.api.getModelConfig();
                if (data.success) {
                    this.setState({ modelConfig: data.data });
                    this.events.emit('model:config', data.data);
                    return data.data;
                }
            } catch (err) {
                console.error('Failed to load model config:', err);
            }
            return null;
        }

        async updateModelConfig(updates) {
            try {
                const data = await window.api.updateModelConfig(updates);
                if (data.success) {
                    await this.loadModelConfig();
                    await this.loadModelRules();
                    this.events.emit('model:configUpdated', data.data);
                    return data;
                }
                return data;
            } catch (err) {
                console.error('Failed to update model config:', err);
                throw err;
            }
        }

        async updateRuntimeConfig(updates) {
            try {
                const data = await window.api.updateRuntimeConfig(updates);
                if (data.success) {
                    await this.loadModelConfig();
                    await this.loadModelRules();
                    this.setState({ runtimeConfigActive: true });
                    this.events.emit('model:runtimeConfigUpdated', data.data);
                    return data;
                }
                return data;
            } catch (err) {
                console.error('Failed to update runtime config:', err);
                throw err;
            }
        }

        async resetRuntimeConfig() {
            try {
                const data = await window.api.resetRuntimeConfig();
                if (data.success) {
                    await this.loadModelConfig();
                    await this.loadModelRules();
                    this.setState({ runtimeConfigActive: false });
                    this.events.emit('model:runtimeConfigReset');
                    return data;
                }
                return data;
            } catch (err) {
                console.error('Failed to reset runtime config:', err);
                throw err;
            }
        }

        async validateConfig(data) {
            try {
                const result = await window.api.validateConfig(data);
                return result;
            } catch (err) {
                console.error('Failed to validate config:', err);
                throw err;
            }
        }

        // ============================================================
        // Calibration Loaders
        // ============================================================

        async loadCalibrationProfiles() {
            try {
                const data = await window.api.getCalibrationProfiles();
                if (data.success) {
                    this.setState({ calibrationProfiles: data.data || [] });
                    this.events.emit('calibration:profiles', data.data);
                    return data.data;
                }
            } catch (err) {
                console.error('Failed to load calibration profiles:', err);
            }
            return [];
        }

        async loadCalibrationHistory(options = {}) {
            try {
                const data = await window.api.getCalibrationHistory(options);
                if (data.success) {
                    this.setState({ calibrationHistory: data.data || [] });
                    this.events.emit('calibration:history', data.data);
                    return data.data;
                }
            } catch (err) {
                console.error('Failed to load calibration history:', err);
            }
            return [];
        }

        async calibrate(data = {}) {
            this.setState({ calibrationRunning: true });
            this.events.emit('calibration:started', data);
            
            try {
                const result = await window.api.calibrateModel(data);
                
                if (result.success) {
                    await this.loadModelStatus();
                    await this.loadVersions();
                    await this.loadCalibrationHistory();
                    this.events.emit('calibration:completed', result.data);
                    window.showToast?.('🎉 کالیبراسیون با موفقیت انجام شد', 'success', 4000);
                } else {
                    this.events.emit('calibration:failed', result);
                    window.showToast?.(`❌ کالیبراسیون ناموفق: ${result.error}`, 'error', 5000);
                }
                
                return result;
            } catch (err) {
                console.error('Calibration error:', err);
                this.events.emit('calibration:failed', err);
                window.showToast?.('❌ خطا در کالیبراسیون', 'error', 5000);
                throw err;
            } finally {
                this.setState({ calibrationRunning: false });
            }
        }

        async forceCalibrate(data = {}) {
            this.setState({ calibrationRunning: true });
            this.events.emit('calibration:started', data);
            
            try {
                const result = await window.api.forceCalibrate(data);
                
                if (result.success) {
                    await this.loadModelStatus();
                    await this.loadVersions();
                    this.events.emit('calibration:completed', result.data);
                    window.showToast?.('⚡ کالیبراسیون اجباری انجام شد', 'success', 4000);
                } else {
                    window.showToast?.(`❌ ${result.error}`, 'error', 5000);
                }
                
                return result;
            } catch (err) {
                console.error('Force calibration error:', err);
                window.showToast?.('❌ خطا در کالیبراسیون اجباری', 'error', 5000);
                throw err;
            } finally {
                this.setState({ calibrationRunning: false });
            }
        }

        // ============================================================
        // Versions Loaders
        // ============================================================

        async loadVersions(options = {}) {
            try {
                const data = await window.api.getVersions(options);
                if (data.success) {
                    this.setState({ versions: data.data || [] });
                    this.events.emit('versions:loaded', data.data);
                    return data.data;
                }
            } catch (err) {
                console.error('Failed to load versions:', err);
            }
            return [];
        }

        async activateVersion(version) {
            try {
                const data = await window.api.activateVersion(version);
                if (data.success) {
                    await this.loadModelStatus();
                    await this.loadVersions();
                    await this.loadModelConfig();
                    await this.loadModelRules();
                    this.events.emit('version:activated', version);
                    window.showToast?.(`✅ نسخه ${version} فعال شد`, 'success');
                }
                return data;
            } catch (err) {
                console.error('Failed to activate version:', err);
                window.showToast?.('❌ خطا در فعال‌سازی نسخه', 'error');
                throw err;
            }
        }

        async deleteVersion(version) {
            try {
                const data = await window.api.deleteVersion(version);
                if (data.success) {
                    await this.loadVersions();
                    this.events.emit('version:deleted', version);
                    window.showToast?.(`🗑️ نسخه ${version} حذف شد`, 'success');
                }
                return data;
            } catch (err) {
                console.error('Failed to delete version:', err);
                window.showToast?.('❌ خطا در حذف نسخه', 'error');
                throw err;
            }
        }

        // ============================================================
        // Schedule Loaders
        // ============================================================

        async loadScheduleStatus() {
            try {
                const data = await window.api.getScheduleStatus();
                if (data.success) {
                    this.setState({ scheduleStatus: data.data });
                    this.events.emit('schedule:status', data.data);
                    return data.data;
                }
            } catch (err) {
                console.error('Failed to load schedule status:', err);
            }
            return null;
        }

        async startSchedule(options = {}) {
            try {
                const data = await window.api.startSchedule(options);
                if (data.success) {
                    await this.loadScheduleStatus();
                    this.events.emit('schedule:started', data);
                    window.showToast?.('⏰ کالیبراسیون خودکار فعال شد', 'success');
                }
                return data;
            } catch (err) {
                console.error('Failed to start schedule:', err);
                window.showToast?.('❌ خطا در شروع زمان‌بندی', 'error');
                throw err;
            }
        }

        async stopSchedule() {
            try {
                const data = await window.api.stopSchedule();
                if (data.success) {
                    await this.loadScheduleStatus();
                    this.events.emit('schedule:stopped');
                    window.showToast?.('⏹️ کالیبراسیون خودکار متوقف شد', 'info');
                }
                return data;
            } catch (err) {
                console.error('Failed to stop schedule:', err);
                window.showToast?.('❌ خطا در توقف زمان‌بندی', 'error');
                throw err;
            }
        }

        // ============================================================
        // Screener Loaders (🆕)
        // ============================================================

        async loadScreenerLatest() {
            try {
                const data = await window.api.screenerLatest();
                if (data.success) {
                    this.setState({ screenerLatest: data.data });
                    this.events.emit('screener:latest', data.data);
                    return data.data;
                }
            } catch (err) {
                // اگه هنوز اسکنی انجام نشده، خطا نمی‌دیم
                if (!err.message?.includes('No recent scan')) {
                    console.error('Failed to load latest scan:', err);
                }
            }
            return null;
        }

        async loadScreenerHistory(options = {}) {
            try {
                const data = await window.api.screenerHistory(options);
                if (data.success) {
                    this.setState({ screenerHistory: data.data || [] });
                    this.events.emit('screener:history', data.data);
                    return data.data;
                }
            } catch (err) {
                console.error('Failed to load scan history:', err);
            }
            return [];
        }

        async loadScreenerConfig() {
            try {
                const data = await window.api.screenerConfig();
                if (data.success) {
                    this.setState({ screenerConfig: data.data });
                    this.events.emit('screener:config', data.data);
                    return data.data;
                }
            } catch (err) {
                console.error('Failed to load screener config:', err);
            }
            return null;
        }

        async runScreenerScan(options = {}) {
            this.setState({ screenerRunning: true });
            this.events.emit('screener:started', options);
            
            try {
                const data = await window.api.screenerScan(options);
                
                if (data.success) {
                    this.setState({ screenerLatest: data.data });
                    await this.loadScreenerHistory({ limit: 20 });
                    this.events.emit('screener:completed', data.data);
                    window.showToast?.(
                        `🎯 اسکن کامل شد: ${data.data?.passed_count || 0} از ${data.data?.total_scanned || 0}`,
                        'success',
                        4000
                    );
                } else {
                    window.showToast?.(`❌ ${data.error}`, 'error', 5000);
                }
                
                return data;
            } catch (err) {
                console.error('Screener scan error:', err);
                window.showToast?.('❌ خطا در اسکن', 'error', 5000);
                throw err;
            } finally {
                this.setState({ screenerRunning: false });
            }
        }

        async runScreenerSingle(coinId, period = '24h') {
            try {
                const data = await window.api.screenerSingle({
                    coin_id: coinId,
                    period,
                });
                return data;
            } catch (err) {
                console.error('Screener single error:', err);
                throw err;
            }
        }

        async updateScreenerConfig(updates) {
            try {
                const data = await window.api.updateScreenerConfig(updates);
                if (data.success) {
                    await this.loadScreenerConfig();
                    this.events.emit('screener:configUpdated', data);
                    return data;
                }
                return data;
            } catch (err) {
                console.error('Failed to update screener config:', err);
                throw err;
            }
        }

        // ============================================================
        // State Machine Loaders (🆕)
        // ============================================================

        async loadStateSummary(symbols = null) {
            try {
                const data = await window.api.stateSummary(symbols);
                if (data.success) {
                    this.setState({ stateSummary: data.data });
                    this.events.emit('state:summary', data.data);
                    return data.data;
                }
            } catch (err) {
                console.error('Failed to load state summary:', err);
            }
            return null;
        }

        async loadStateSnapshots(limit = 100) {
            try {
                const data = await window.api.stateSnapshots(limit);
                if (data.success) {
                    this.setState({ stateSnapshots: data.data || [] });
                    this.events.emit('state:snapshots', data.data);
                    return data.data;
                }
            } catch (err) {
                console.error('Failed to load state snapshots:', err);
            }
            return [];
        }

        async loadStateTransitions(options = {}) {
            try {
                const data = await window.api.stateTransitions(options);
                if (data.success) {
                    this.setState({ stateTransitions: data.data || [] });
                    this.events.emit('state:transitions', data.data);
                    return data.data;
                }
            } catch (err) {
                console.error('Failed to load state transitions:', err);
            }
            return [];
        }

        async getStateSymbol(symbol) {
            try {
                const data = await window.api.stateSymbol(symbol);
                return data;
            } catch (err) {
                console.error('Failed to get symbol state:', err);
                throw err;
            }
        }

        async resetStateSymbol(symbol) {
            try {
                const data = await window.api.stateSymbolReset(symbol);
                if (data.success) {
                    await this.loadStateSummary();
                    this.events.emit('state:symbolReset', symbol);
                    window.showToast?.(`🔄 State ${symbol} ریست شد`, 'info');
                }
                return data;
            } catch (err) {
                console.error('Failed to reset symbol state:', err);
                throw err;
            }
        }

        async activateStateSymbol(symbol, context = {}) {
            try {
                const data = await window.api.stateSymbolActivate(symbol, context);
                if (data.success) {
                    await this.loadStateSummary();
                    this.events.emit('state:symbolActivated', { symbol, context });
                    window.showToast?.(`🔥 ${symbol} → ACTIVE`, 'success');
                }
                return data;
            } catch (err) {
                console.error('Failed to activate symbol:', err);
                throw err;
            }
        }

        async coolingStateSymbol(symbol, context = {}) {
            try {
                const data = await window.api.stateSymbolCooling(symbol, context);
                if (data.success) {
                    await this.loadStateSummary();
                    this.events.emit('state:symbolCooling', { symbol, context });
                    window.showToast?.(`❄️ ${symbol} → COOLING`, 'info');
                }
                return data;
            } catch (err) {
                console.error('Failed to cool symbol:', err);
                throw err;
            }
        }

        // ============================================================
        // Schema & OHLCV Loaders (🆕)
        // ============================================================

        async loadSchemaStatus() {
            try {
                const data = await window.api.getSchemaStatus();
                if (data.success) {
                    this.setState({ schemaStatus: data.data });
                    this.events.emit('schema:status', data.data);
                    return data.data;
                }
            } catch (err) {
                console.error('Failed to load schema status:', err);
            }
            return null;
        }

        async loadOHLCVStats() {
            try {
                const data = await window.api.getOHLCVStats();
                if (data.success) {
                    this.setState({ ohlcvStats: data.data });
                    this.events.emit('ohlcv:stats', data.data);
                    return data.data;
                }
            } catch (err) {
                console.error('Failed to load OHLCV stats:', err);
            }
            return null;
        }

        async initAllDatabases() {
            window.showToast?.('🔄 راه‌اندازی دیتابیس‌ها...', 'info', 5000);
            
            try {
                const data = await window.api.initAllDatabases();
                
                if (data.success) {
                    await this.loadSchemaStatus();
                    await this.loadDatabaseHealth();
                    window.showToast?.('✅ همه دیتابیس‌ها راه‌اندازی شدند', 'success', 4000);
                } else {
                    window.showToast?.('⚠️ برخی دیتابیس‌ها راه‌اندازی نشدند', 'warning', 5000);
                }
                
                return data;
            } catch (err) {
                console.error('Failed to init databases:', err);
                window.showToast?.('❌ خطا در راه‌اندازی دیتابیس‌ها', 'error', 5000);
                throw err;
            }
        }

        // ============================================================
        // Database Loaders
        // ============================================================

        async loadQuotas() {
            try {
                const data = await window.api.getAllQuotas();
                if (data.success) {
                    this.setState({ quotas: data.data });
                    this.events.emit('quotas:loaded', data.data);
                    return data.data;
                }
            } catch (err) {
                console.error('Failed to load quotas:', err);
            }
            return null;
        }

        async loadDBList() {
            try {
                const data = await window.api.getDBList();
                if (data.success) {
                    this.setState({ dbList: data.data });
                    return data.data;
                }
            } catch (err) {
                console.error('Failed to load DB list:', err);
            }
            return null;
        }

        // ============================================================
        // Refresh
        // ============================================================

        async refresh() {
            this.setState({ isLoading: true });
            window.progress?.start();
            
            try {
                await Promise.allSettled([
                    this.loadUser(),
                    this.loadMetrics(),
                    this.loadAppStats(),
                    this.loadDatabaseHealth(),
                    this.loadAlerts(),
                    this.loadModelStatus(),
                    this.loadModelRules(),
                    this.loadModelConfig(),
                    this.loadVersions(),
                ]);
                window.showToast?.('✅ بروزرسانی شد', 'success', 1500);
                this.events.emit('app:refreshed');
            } catch (err) {
                window.showToast?.('❌ خطا در بروزرسانی', 'error');
            } finally {
                this.setState({ isLoading: false });
                window.progress?.done();
            }
        }

        // ============================================================
        // Theme
        // ============================================================

        applyTheme(theme) {
            if (theme === 'auto') {
                const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
                theme = prefersDark ? 'dark' : 'light';
            }
            
            document.documentElement.setAttribute('data-theme', theme);
            this.state.theme = theme;
            
            const icon = document.getElementById('themeIcon');
            const label = document.getElementById('themeLabel');
            if (icon && label) {
                if (theme === 'dark') {
                    icon.className = 'fas fa-moon';
                    label.textContent = 'تیره';
                } else {
                    icon.className = 'fas fa-sun';
                    label.textContent = 'روشن';
                }
            }
            
            this.events.emit('theme:changed', theme);
        }

        async toggleTheme() {
            const newTheme = this.state.theme === 'dark' ? 'light' : 'dark';
            await this.saveSettings('theme', { mode: newTheme });
            this.applyTheme(newTheme);
            this.notifyListeners();
            window.showToast?.(`🌓 حالت ${newTheme === 'dark' ? 'تیره' : 'روشن'}`, 'info', 1500);
            return newTheme;
        }

        // ============================================================
        // Utility
        // ============================================================

        async waitForInit() {
            while (!this.state.isInitialized) {
                await new Promise(resolve => setTimeout(resolve, 100));
            }
        }

        getUsername() {
            return this.state.user?.username || 'کاربر';
        }

        getUserRole() {
            return this.state.user?.role || 'guest';
        }

        isAdmin() {
            return this.getUserRole() === 'admin';
        }

        getAppStats() {
            return this.state.appStats;
        }

        getMetrics() {
            return this.state.metrics;
        }

        getAlerts() {
            return this.state.alerts;
        }

        // ============================================================
        // Destroy
        // ============================================================

        destroy() {
            for (const name of this._tasks.keys()) {
                this._unscheduleTask(name);
            }
            this._cache.clear();
            this.state.isInitialized = false;
        }
    }

    // ============================================================
    // Singleton
    // ============================================================

    const app = new App();
    window.app = app;

    // ============================================================
    // Expose Globals
    // ============================================================

    window.getState = () => app.getState();
    window.setState = (s) => app.setState(s);
    window.loadMetrics = () => app.loadMetrics();
    window.loadAppStats = () => app.loadAppStats();
    window.loadAlerts = () => app.loadAlerts();
    window.toggleTheme = () => app.toggleTheme();
    window.refreshApp = () => app.refresh();

    // ============================================================
    // Settings API
    // ============================================================

    window.appSettings = {
        get: (cat) => app.getSettings(cat),
        save: (cat, vals) => app.saveSettings(cat, vals),
        saveAll: () => app.saveAllSettings(),
        reset: (cat) => app.resetSettings(cat),
        resetAll: () => app.resetAllSettings(),
    };

    // ============================================================
    // Cache API
    // ============================================================

    window.appCache = {
        set: (key, val, ttl) => app.cacheSet(key, val, ttl),
        get: (key, def) => app.cacheGet(key, def),
        invalidate: (pattern) => app.cacheInvalidate(pattern),
        clear: () => app.cacheClear(),
        stats: () => app.cacheStats(),
    };

    // ============================================================
    // Events API
    // ============================================================

    window.appEvents = {
        on: (event, handler) => app.on(event, handler),
        off: (event, handler) => app.off(event, handler),
        emit: (event, data) => app.emit(event, data),
    };

    // ============================================================
    // Tasks API
    // ============================================================

    window.appTasks = {
        status: () => app.getTasksStatus(),
        pause: () => app.pauseAllTasks(),
        resume: () => app.resumeAllTasks(),
    };

    // ============================================================
    // Metrics API
    // ============================================================

    window.appMetrics = {
        get: () => app.getAppMetrics(),
    };

    // ============================================================
    // 🆕 Model API (RuleEngine)
    // ============================================================

    window.appModel = {
        // Status
        status: () => app.loadModelStatus(),
        stats: () => app.loadModelStats(),
        trainerStats: () => app.loadTrainerStats(),
        
        // Rules
        rules: () => app.loadModelRules(),
        
        // Config
        config: () => app.loadModelConfig(),
        updateConfig: (updates) => app.updateModelConfig(updates),
        updateRuntime: (updates) => app.updateRuntimeConfig(updates),
        resetRuntime: () => app.resetRuntimeConfig(),
        validateConfig: (data) => app.validateConfig(data),
        
        // Calibration
        profiles: () => app.loadCalibrationProfiles(),
        calibrate: (data) => app.calibrate(data),
        forceCalibrate: (data) => app.forceCalibrate(data),
        calibrationHistory: (opts) => app.loadCalibrationHistory(opts),
        
        // Versions
        versions: (opts) => app.loadVersions(opts),
        activateVersion: (v) => app.activateVersion(v),
        deleteVersion: (v) => app.deleteVersion(v),
        
        // Schedule
        scheduleStatus: () => app.loadScheduleStatus(),
        startSchedule: (opts) => app.startSchedule(opts),
        stopSchedule: () => app.stopSchedule(),
    };

    // ============================================================
    // 🆕 Screener API
    // ============================================================

    window.appScreener = {
        latest: () => app.loadScreenerLatest(),
        history: (opts) => app.loadScreenerHistory(opts),
        config: () => app.loadScreenerConfig(),
        updateConfig: (updates) => app.updateScreenerConfig(updates),
        scan: (opts) => app.runScreenerScan(opts),
        scanSingle: (coinId, period) => app.runScreenerSingle(coinId, period),
    };

    // ============================================================
    // 🆕 State API
    // ============================================================

    window.appStateMachine = {
        summary: (symbols) => app.loadStateSummary(symbols),
        snapshots: (limit) => app.loadStateSnapshots(limit),
        transitions: (opts) => app.loadStateTransitions(opts),
        getSymbol: (symbol) => app.getStateSymbol(symbol),
        resetSymbol: (symbol) => app.resetStateSymbol(symbol),
        activateSymbol: (symbol, ctx) => app.activateStateSymbol(symbol, ctx),
        coolingSymbol: (symbol, ctx) => app.coolingStateSymbol(symbol, ctx),
    };

    // ============================================================
    // 🆕 Schema & OHLCV API
    // ============================================================

    window.appSchema = {
        status: () => app.loadSchemaStatus(),
        initAll: () => app.initAllDatabases(),
        ohlcvStats: () => app.loadOHLCVStats(),
    };

    console.log('✅ App v13.0 loaded');
})();
