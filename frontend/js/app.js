// ============================================================
// app.js - Core Application v4.0
// ============================================================

class App {
    constructor() {
        this.state = {
            user: null,
            metrics: null,
            alerts: [],
            isLoading: false,
            theme: localStorage.getItem('theme') || 'dark'
        };
        
        this.listeners = [];
        this.isInitialized = false;
        this.init();
    }
    
    async init() {
        if (this.isInitialized) return;
        
        // اعمال تم
        this.applyTheme(this.state.theme);
        
        // دریافت اطلاعات کاربر
        await this.loadUser();
        
        // دریافت متریک‌ها
        await this.loadMetrics();
        
        // دریافت هشدارها
        await this.loadAlerts();
        
        // راه‌اندازی آپدیت خودکار
        this.startAutoUpdate();
        
        this.isInitialized = true;
        console.log('🚀 App initialized');
    }
    
    // ===== STATE MANAGEMENT =====
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
    
    // ===== API CALLS =====
    async loadUser() {
        try {
            const data = await api.getUser();
            if (data.success) {
                this.setState({ user: data.data });
                return data.data;
            }
        } catch (err) {
            console.error('Failed to load user:', err);
        }
        return null;
    }
    
    async loadMetrics() {
        try {
            const data = await api.getMetrics();
            if (data.success) {
                this.setState({ metrics: data.data });
                return data.data;
            }
        } catch (err) {
            console.error('Failed to load metrics:', err);
        }
        return null;
    }
    
    async loadAlerts() {
        try {
            const data = await api.getAlerts(5);
            if (data.success) {
                this.setState({ alerts: data.data || [] });
                return data.data;
            }
        } catch (err) {
            console.error('Failed to load alerts:', err);
        }
        return [];
    }
    
    // ===== THEME =====
    applyTheme(theme) {
        document.documentElement.setAttribute('data-theme', theme);
        this.state.theme = theme;
        localStorage.setItem('theme', theme);
    }
    
    toggleTheme() {
        const newTheme = this.state.theme === 'dark' ? 'light' : 'dark';
        this.applyTheme(newTheme);
        this.notifyListeners();
        return newTheme;
    }
    
    // ===== AUTO UPDATE =====
    startAutoUpdate() {
        // آپدیت متریک‌ها هر ۱۰ ثانیه
        setInterval(() => {
            this.loadMetrics();
        }, 10000);
        
        // آپدیت هشدارها هر ۳۰ ثانیه
        setInterval(() => {
            this.loadAlerts();
        }, 30000);
    }
    
    // ===== UTILITY =====
    getState() {
        return this.state;
    }
}

// ===== SINGLETON =====
const app = new App();
window.app = app;

// ===== EXPOSE FOR OTHER SCRIPTS =====
window.getState = () => app.getState();
window.loadMetrics = () => app.loadMetrics();
window.loadAlerts = () => app.loadAlerts();
window.toggleTheme = () => app.toggleTheme();

console.log('✅ App v4.0 loaded');
