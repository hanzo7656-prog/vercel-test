// ============================================================
// app.js - Core Application v12.0
// State غنی + Scheduler پویا + Event Bus + Settings + Cache
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
                
                // مدل
                modelStatus: null,
                trainerStats: null,
                currentProfile: null,
                trainingPresets: [],
                learningStrategies: [],
                
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
                
                // تنظیمات - مقدار اولیه خالی (از API میان)
                settings: {
                    scheduler: JSON.parse(JSON.stringify(DEFAULT_SCHEDULER)),
                    theme: JSON.parse(JSON.stringify(DEFAULT_THEME)),
                    cache: JSON.parse(JSON.stringify(DEFAULT_CACHE)),
                    notifications: JSON.parse(JSON.stringify(DEFAULT_NOTIFICATIONS)),
                    dashboard: JSON.parse(JSON.stringify(DEFAULT_DASHBOARD)),
                },
            };
            
            // ============================================================
            // Event Bus (mitt)
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
            
            // ============================================================
            // Listeners
            // ============================================================
            
            this.listeners = [];
            
            // ============================================================
            // Init
            // ============================================================
            
            this.init();
        }

        // ============================================================
        // Settings System - API Based
        // ============================================================

        /**
         * بارگذاری تنظیمات از API
         */
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
                    // Deep merge با defaults
                    return this._deepMerge(defaults, data.data.value);
                }
            } catch (e) {
                console.warn(`Failed to load settings '${category}' from API:`, e);
            }
            
            return JSON.parse(JSON.stringify(defaults));
        }

        /**
         * بارگذاری همه تنظیمات
         */
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

        /**
         * ذخیره تنظیمات در API
         */
        async saveSettings(category, values) {
            // Update local
            this.state.settings[category] = {
                ...this.state.settings[category],
                ...values,
            };
            
            // Save to API
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
            
            // Apply
            this.applySettings(category);
            this.events.emit(`settings:${category}:changed`, this.state.settings[category]);
            this.notifyListeners();
            
            return true;
        }

        /**
         * ذخیره همه تنظیمات
         */
        async saveAllSettings() {
            const categories = ['scheduler', 'theme', 'cache', 'notifications', 'dashboard'];
            
            const results = await Promise.allSettled(
                categories.map(cat => 
                    window.api.saveSettingsCategory(cat, this.state.settings[cat])
                )
            );
            
            const allSuccess = results.every(r => 
                r.status === 'fulfilled' && r.value.success
            );
            
            return allSuccess;
        }

        /**
         * ریست تنظیمات یک دسته
         */
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

        /**
         * ریست همه تنظیمات
         */
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
            
            // لغو همه
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

            console.log('🚀 App initializing...');

            try {
                // ۱. بارگذاری تنظیمات از API
                await this._loadAllSettings();
                
                // ۲. اعمال تم
                this.applyTheme(this.state.settings.theme.mode);
                
                // ۳. اعمال Scheduler
                this._applySchedulerSettings();
                
                // ۴. Setup listeners
                this._setupVisibilityListeners();
                this._setupOnlineListeners();
                this._setupErrorHandlers();
                
                // ۵. دریافت اطلاعات
                await this.loadUser();
                await this.loadMetrics();
                await this.loadAppStats();
                await this.loadDatabaseHealth();
                await this.loadAlerts();
                
                // ۶. علامت‌گذاری
                this.state.isInitialized = true;
                this.notifyListeners();
                this.events.emit('app:ready', this.state);
                
                console.log('✅ App initialized successfully');
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

        // ============================================================
        // Track API metrics
        // ============================================================

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
        // API Calls
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
        // Model Loaders
        // ============================================================

        async loadModelStatus() {
            try {
                const data = await window.api.getModelStatus();
                if (data.success) {
                    this.setState({ modelStatus: data.data });
                    this.events.emit('model:status', data.data);
                    return data.data;
                }
            } catch (err) {
                console.error('Failed to load model status:', err);
            }
            return null;
        }

        async loadProfiles() {
            try {
                const [presetsRes, strategiesRes, currentRes] = await Promise.allSettled([
                    window.api.getTrainingPresets(),
                    window.api.getLearningStrategies(),
                    window.api.getCurrentProfile(),
                ]);
                
                const updates = {};
                if (presetsRes.status === 'fulfilled' && presetsRes.value.success) {
                    updates.trainingPresets = presetsRes.value.data;
                }
                if (strategiesRes.status === 'fulfilled' && strategiesRes.value.success) {
                    updates.learningStrategies = strategiesRes.value.data;
                }
                if (currentRes.status === 'fulfilled' && currentRes.value.success) {
                    updates.currentProfile = currentRes.value.data;
                }
                
                if (Object.keys(updates).length > 0) {
                    this.setState(updates);
                    this.events.emit('profiles:loaded', updates);
                }
                return updates;
            } catch (err) {
                console.error('Failed to load profiles:', err);
            }
            return {};
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

    // App methods
    window.appSettings = {
        get: (cat) => app.getSettings(cat),
        save: (cat, vals) => app.saveSettings(cat, vals),
        saveAll: () => app.saveAllSettings(),
        reset: (cat) => app.resetSettings(cat),
        resetAll: () => app.resetAllSettings(),
    };

    window.appCache = {
        set: (key, val, ttl) => app.cacheSet(key, val, ttl),
        get: (key, def) => app.cacheGet(key, def),
        invalidate: (pattern) => app.cacheInvalidate(pattern),
        clear: () => app.cacheClear(),
        stats: () => app.cacheStats(),
    };

    window.appEvents = {
        on: (event, handler) => app.on(event, handler),
        off: (event, handler) => app.off(event, handler),
        emit: (event, data) => app.emit(event, data),
    };

    window.appTasks = {
        status: () => app.getTasksStatus(),
        pause: () => app.pauseAllTasks(),
        resume: () => app.resumeAllTasks(),
    };

    window.appMetrics = {
        get: () => app.getAppMetrics(),
    };

    console.log('✅ App v12.0 loaded');
})();
