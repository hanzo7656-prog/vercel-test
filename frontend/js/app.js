// ============================================================
// app.js - Core Application v10.0
// مدیریت State، تم، و بروزرسانی خودکار
// ============================================================

class App {
    constructor() {
        this.state = {
            user: null,
            metrics: null,
            alerts: [],
            isLoading: false,
            theme: localStorage.getItem('theme') || 'dark',
            isInitialized: false
        };

        this.listeners = [];
        this.updateIntervals = [];
        this.init();
    }

    async init() {
        if (this.state.isInitialized) return;

        console.log('🚀 App initializing...');

        // اعمال تم
        this.applyTheme(this.state.theme);

        try {
            // دریافت اطلاعات کاربر
            await this.loadUser();

            // دریافت متریک‌ها
            await this.loadMetrics();

            // دریافت هشدارها
            await this.loadAlerts();

            // راه‌اندازی آپدیت خودکار
            this.startAutoUpdate();

            this.state.isInitialized = true;
            this.notifyListeners();

            console.log('✅ App initialized successfully');
        } catch (err) {
            console.error('❌ App initialization failed:', err);
        }
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

    getState() {
        return this.state;
    }

    // ===== API CALLS =====

    async loadUser() {
        try {
            const data = await api.getUserInfo();
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
            const data = await api.getAlerts({ limit: 5, resolved: false });
            if (data.success) {
                this.setState({ alerts: data.data || [] });
                return data.data;
            }
        } catch (err) {
            console.error('Failed to load alerts:', err);
        }
        return [];
    }

    async refresh() {
        this.setState({ isLoading: true });
        try {
            await Promise.all([
                this.loadUser(),
                this.loadMetrics(),
                this.loadAlerts()
            ]);
            showToast('✅ بروزرسانی شد', 'success');
        } catch (err) {
            showToast('❌ خطا در بروزرسانی', 'error');
        } finally {
            this.setState({ isLoading: false });
        }
    }

    // ===== THEME =====

    applyTheme(theme) {
        document.documentElement.setAttribute('data-theme', theme);
        this.state.theme = theme;
        localStorage.setItem('theme', theme);
        
        // بروزرسانی آیکون تم در نویگیشن
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
    }

    toggleTheme() {
        const newTheme = this.state.theme === 'dark' ? 'light' : 'dark';
        this.applyTheme(newTheme);
        this.notifyListeners();
        showToast(`🌓 حالت ${newTheme === 'dark' ? 'تیره' : 'روشن'}`, 'info');
        return newTheme;
    }

    // ===== AUTO UPDATE =====

    startAutoUpdate() {
        // آپدیت متریک‌ها هر ۱۰ ثانیه
        const metricsInterval = setInterval(() => {
            this.loadMetrics();
        }, 10000);
        this.updateIntervals.push(metricsInterval);

        // آپدیت هشدارها هر ۳۰ ثانیه
        const alertsInterval = setInterval(() => {
            this.loadAlerts();
        }, 30000);
        this.updateIntervals.push(alertsInterval);
    }

    stopAutoUpdate() {
        this.updateIntervals.forEach(interval => clearInterval(interval));
        this.updateIntervals = [];
    }

    // ===== UTILITY =====

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
}

// ===== SINGLETON =====
const app = new App();
window.app = app;

// ===== EXPOSE FOR OTHER SCRIPTS =====
window.getState = () => app.getState();
window.loadMetrics = () => app.loadMetrics();
window.loadAlerts = () => app.loadAlerts();
window.toggleTheme = () => app.toggleTheme();
window.refreshApp = () => app.refresh();

console.log('✅ App v10.0 loaded');
