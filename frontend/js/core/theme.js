// ============================================================
// theme.js — Theme Manager
// نسخه ۱.۰ — سیستم تحلیلگر
// مدیریت تم (dark/light/auto) + accent color
// ============================================================

(function() {
    'use strict';

    // ============================================================
    // تنظیمات پیش‌فرض
    // ============================================================

    const DEFAULT_THEME = {
        mode: 'dark',           // dark | light | auto
        accent: 'cyan',         // cyan | purple | green | orange | pink
    };

    const STORAGE_KEY = 'app_theme';

    const ACCENT_COLORS = {
        cyan: '#00d4ff',
        purple: '#8b5cf6',
        green: '#22d3ee',
        orange: '#f59e0b',
        pink: '#ec4899',
    };

    // ============================================================
    // کلاس ThemeManager
    // ============================================================

    class ThemeManager {
        constructor() {
            this.state = {
                mode: DEFAULT_THEME.mode,
                accent: DEFAULT_THEME.accent,
                effective: 'dark',      // تم واقعی اعمال‌شده (بعد از حل auto)
            };

            this.listeners = [];
            this._mediaQuery = null;
            this._onMediaChange = null;

            this._load();
            this._setupMediaListener();
            this.apply();
        }

        // ========================================================
        // بارگذاری از localStorage
        // ========================================================

        _load() {
            try {
                const saved = localStorage.getItem(STORAGE_KEY);
                if (saved) {
                    const parsed = JSON.parse(saved);
                    this.state.mode = parsed.mode || DEFAULT_THEME.mode;
                    this.state.accent = parsed.accent || DEFAULT_THEME.accent;
                }
            } catch (e) {
                console.warn('⚠️ ThemeManager: failed to load from storage', e);
            }
        }

        // ========================================================
        // ذخیره در localStorage
        // ========================================================

        _save() {
            try {
                localStorage.setItem(STORAGE_KEY, JSON.stringify({
                    mode: this.state.mode,
                    accent: this.state.accent,
                }));
            } catch (e) {
                console.warn('⚠️ ThemeManager: failed to save', e);
            }
        }

        // ========================================================
        // تشخیص تم سیستم
        // ========================================================

        _getSystemTheme() {
            if (typeof window === 'undefined' || !window.matchMedia) {
                return 'dark';
            }
            return window.matchMedia('(prefers-color-scheme: dark)').matches
                ? 'dark'
                : 'light';
        }

        _setupMediaListener() {
            if (typeof window === 'undefined' || !window.matchMedia) return;

            this._mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
            this._onMediaChange = () => {
                if (this.state.mode === 'auto') {
                    this.apply();
                }
            };

            if (this._mediaQuery.addEventListener) {
                this._mediaQuery.addEventListener('change', this._onMediaChange);
            } else if (this._mediaQuery.addListener) {
                // برای مرورگرهای قدیمی
                this._mediaQuery.addListener(this._onMediaChange);
            }
        }

        // ========================================================
        // محاسبه‌ی تم واقعی
        // ========================================================

        _resolveEffective() {
            if (this.state.mode === 'auto') {
                return this._getSystemTheme();
            }
            return this.state.mode;
        }

        // ========================================================
        // اعمال تم روی DOM
        // ========================================================

        apply() {
            if (typeof document === 'undefined') return;

            const effective = this._resolveEffective();
            this.state.effective = effective;

            // اعمال data-theme روی html
            document.documentElement.setAttribute('data-theme', effective);

            // اعمال data-accent
            document.documentElement.setAttribute('data-accent', this.state.accent);

            // اعمال CSS variable رنگ اصلی
            const accentHex = ACCENT_COLORS[this.state.accent];
            if (accentHex) {
                document.documentElement.style.setProperty('--color-cyan', accentHex);
                // نسخه‌های روشن و تیره‌تر
                document.documentElement.style.setProperty(
                    '--color-cyan-light',
                    this._lighten(accentHex, 20)
                );
                document.documentElement.style.setProperty(
                    '--color-cyan-dark',
                    this._darken(accentHex, 15)
                );
            }

            // اطلاع به listenerها
            this._notify();

            // لاگ
            console.log(
                `🎨 Theme applied: mode=${this.state.mode} → ${effective}, accent=${this.state.accent}`
            );
        }

        // ========================================================
        // Helpers برای روشن/تیره کردن رنگ
        // ========================================================

        _hexToRgb(hex) {
            const h = hex.replace('#', '');
            const bigint = parseInt(h, 16);
            return {
                r: (bigint >> 16) & 255,
                g: (bigint >> 8) & 255,
                b: bigint & 255,
            };
        }

        _rgbToHex({ r, g, b }) {
            return '#' + [r, g, b]
                .map(x => Math.max(0, Math.min(255, x)).toString(16).padStart(2, '0'))
                .join('');
        }

        _lighten(hex, percent) {
            const { r, g, b } = this._hexToRgb(hex);
            const amount = Math.round(2.55 * percent);
            return this._rgbToHex({
                r: r + amount,
                g: g + amount,
                b: b + amount,
            });
        }

        _darken(hex, percent) {
            const { r, g, b } = this._hexToRgb(hex);
            const amount = Math.round(2.55 * percent);
            return this._rgbToHex({
                r: r - amount,
                g: g - amount,
                b: b - amount,
            });
        }

        // ========================================================
        // API عمومی
        // ========================================================

        setMode(mode) {
            if (!['dark', 'light', 'auto'].includes(mode)) {
                console.warn(`⚠️ Invalid theme mode: ${mode}`);
                return;
            }
            this.state.mode = mode;
            this._save();
            this.apply();
        }

        setAccent(accent) {
            if (!ACCENT_COLORS[accent]) {
                console.warn(`⚠️ Invalid accent: ${accent}`);
                return;
            }
            this.state.accent = accent;
            this._save();
            this.apply();
        }

        toggle() {
            // چرخه: dark → light → auto → dark
            const cycle = { dark: 'light', light: 'auto', auto: 'dark' };
            this.setMode(cycle[this.state.mode]);
        }

        getMode() {
            return this.state.mode;
        }

        getAccent() {
            return this.state.accent;
        }

        getEffective() {
            return this.state.effective;
        }

        isDark() {
            return this.state.effective === 'dark';
        }

        isLight() {
            return this.state.effective === 'light';
        }

        getState() {
            return { ...this.state };
        }

        // ========================================================
        // Listeners
        // ========================================================

        on(callback) {
            if (typeof callback !== 'function') return () => {};
            this.listeners.push(callback);
            return () => {
                this.listeners = this.listeners.filter(l => l !== callback);
            };
        }

        _notify() {
            this.listeners.forEach(cb => {
                try {
                    cb(this.getState());
                } catch (e) {
                    console.error('❌ Theme listener error:', e);
                }
            });
        }

        // ========================================================
        // پاک‌سازی
        // ========================================================

        destroy() {
            if (this._mediaQuery && this._onMediaChange) {
                if (this._mediaQuery.removeEventListener) {
                    this._mediaQuery.removeEventListener('change', this._onMediaChange);
                } else if (this._mediaQuery.removeListener) {
                    this._mediaQuery.removeListener(this._onMediaChange);
                }
            }
            this.listeners = [];
        }
    }

    // ============================================================
    // Singleton
    // ============================================================

    const themeManager = new ThemeManager();

    // ============================================================
    // Expose to window
    // ============================================================

    window.themeManager = themeManager;

    // Helpers برای استفاده سریع
    window.theme = {
        set: (mode) => themeManager.setMode(mode),
        setAccent: (accent) => themeManager.setAccent(accent),
        toggle: () => themeManager.toggle(),
        isDark: () => themeManager.isDark(),
        isLight: () => themeManager.isLight(),
        get: () => themeManager.getState(),
        on: (cb) => themeManager.on(cb),
    };

    console.log('✅ ThemeManager v1.0 loaded');
})();
