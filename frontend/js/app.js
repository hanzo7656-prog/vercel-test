// ============================================================
// app.js - Core Application
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
        this.init();
    }
    
    async init() {
        // بارگذاری تم
        this.applyTheme(this.state.theme);
        
        // دریافت اطلاعات کاربر
        await this.loadUser();
        
        // دریافت متریک‌ها
        await this.loadMetrics();
        
        // دریافت هشدارها
        await this.loadAlerts();
        
        // راه‌اندازی آپدیت خودکار
        this.startAutoUpdate();
        
        // راه‌اندازی event listeners
        this.setupEventListeners();
        
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
        this.listeners.forEach(listener => listener(this.state));
    }
    
    // ===== API CALLS =====
    async loadUser() {
        try {
            const res = await fetch('/api/user', { credentials: 'include' });
            const data = await res.json();
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
            const res = await fetch('/api/metrics', { credentials: 'include' });
            const data = await res.json();
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
            const res = await fetch('/api/alerts?limit=5', { credentials: 'include' });
            const data = await res.json();
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
    }
    
    // ===== AUTO UPDATE =====
    startAutoUpdate() {
        // آپدیت متریک‌ها هر ۱۰ ثانیه
        setInterval(() => this.loadMetrics(), 10000);
        
        // آپدیت هشدارها هر ۳۰ ثانیه
        setInterval(() => this.loadAlerts(), 30000);
    }
    
    // ===== EVENT LISTENERS =====
    setupEventListeners() {
        // دکمه تغییر تم
        document.addEventListener('click', (e) => {
            if (e.target.closest('[data-theme-toggle]')) {
                this.toggleTheme();
                e.preventDefault();
            }
        });
        
        // کلیدهای میانبر
        document.addEventListener('keydown', (e) => {
            if (e.ctrlKey && e.key === 'r') {
                e.preventDefault();
                this.loadMetrics();
                showToast('🔄 بروزرسانی شد', 'info');
            }
        });
    }
}

// ===== SINGLETON =====
const app = new App();
window.app = app;

// ===== EXPOSE FOR OTHER SCRIPTS =====
window.getState = () => app.state;
window.loadMetrics = () => app.loadMetrics();
window.loadAlerts = () => app.loadAlerts();
window.toggleTheme = () => app.toggleTheme();
