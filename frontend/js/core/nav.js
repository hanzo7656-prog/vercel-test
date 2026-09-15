// ============================================================
// nav.js — Navigation Manager
// نسخه ۱.۰ — سیستم تحلیلگر
// مدیریت مشترک نویگیشن بار در همه صفحات
// ============================================================

(function() {
    'use strict';

    // ============================================================
    // کلاس NavManager
    // ============================================================

    class NavManager {
        /**
         * @param {Object} [config]
         * @param {string} [config.containerId]  - id ظرف نویگیشن (پیش‌فرض: 'navContainer')
         * @param {string} [config.navUrl]       - مسیر nav.html (پیش‌فرض: '/nav.html')
         * @param {boolean} [config.autoLoad]    - لود خودکار (پیش‌فرض: true)
         */
        constructor(config = {}) {
            this.config = {
                containerId: config.containerId || 'navContainer',
                navUrl: config.navUrl || '/nav.html',
                autoLoad: config.autoLoad !== false,
            };

            // State
            this.isLoaded = false;
            this.container = null;
            this.user = null;
            this.statusInterval = null;
            this.clockInterval = null;
            this.loadingPromise = null;

            // Bind
            this._onLogout = this._onLogout.bind(this);
            this._onThemeToggle = this._onThemeToggle.bind(this);
        }

        // ========================================================
        // لود نویگیشن
        // ========================================================

        async load() {
            if (this.isLoaded) return;
            if (this.loadingPromise) return this.loadingPromise;

            this.loadingPromise = this._doLoad();
            return this.loadingPromise;
        }

        async _doLoad() {
            this.container = document.getElementById(this.config.containerId);

            if (!this.container) {
                console.warn(`⚠️ NavManager: container #${this.config.containerId} پیدا نشد`);
                return;
            }

            try {
                const res = await fetch(this.config.navUrl);
                if (!res.ok) throw new Error(`HTTP ${res.status}`);

                const html = await res.text();
                this.container.innerHTML = html;

                // اجرای اسکریپت‌های inline (اگه بود)
                const scripts = this.container.querySelectorAll('script');
                scripts.forEach(oldScript => {
                    const newScript = document.createElement('script');
                    if (oldScript.src) {
                        newScript.src = oldScript.src;
                    } else {
                        newScript.textContent = oldScript.textContent;
                    }
                    oldScript.parentNode.replaceChild(newScript, oldScript);
                });

                // setup
                this._setup();
                this.isLoaded = true;

                console.log('✅ NavManager: loaded');

            } catch (err) {
                console.error('❌ NavManager: failed to load', err);
                this.container.innerHTML = `
                    <div class="loading-container">
                        <p class="loading-text" style="color:var(--color-red);">
                            ⚠️ خطا در بارگذاری نویگیشن
                        </p>
                    </div>
                `;
            }
        }

        // ========================================================
        // Setup نویگیشن
        // ========================================================

        _setup() {
            this._setupMobileMenu();
            this._setupActivePage();
            this._setupThemeToggle();
            this._setupLogout();
            this._loadUser();
            this._startClock();
            this._startStatusUpdate();
        }

        // ========================================================
        // منوی موبایل
        // ========================================================

        _setupMobileMenu() {
            const toggle = document.getElementById('navbarToggle');
            const menu = document.getElementById('navbarMenu');

            if (!toggle || !menu) return;

            const closeMenu = () => {
                menu.classList.remove('open');
                toggle.classList.remove('active');
                document.body.style.overflow = '';
            };

            toggle.addEventListener('click', (e) => {
                e.stopPropagation();
                const isOpen = menu.classList.toggle('open');
                toggle.classList.toggle('active', isOpen);
                document.body.style.overflow = isOpen ? 'hidden' : '';
            });

            // بستن با کلیک بیرون
            document.addEventListener('click', (e) => {
                if (!menu.classList.contains('open')) return;
                if (menu.contains(e.target) || toggle.contains(e.target)) return;
                closeMenu();
            });

            // بستن با کلیک روی لینک
            menu.querySelectorAll('.nav-link').forEach(link => {
                link.addEventListener('click', closeMenu);
            });

            // بستن با Escape
            document.addEventListener('keydown', (e) => {
                if (e.key === 'Escape') closeMenu();
            });
        }

        // ========================================================
        // فعال‌سازی صفحه فعلی
        // ========================================================

        _setupActivePage() {
            const currentPath = window.location.pathname;
            const navLinks = document.querySelectorAll('.nav-link[data-page]');

            navLinks.forEach(link => {
                const page = link.dataset.page;
                let isActive = false;

                if (page === 'dashboard') {
                    isActive = currentPath === '/' || currentPath === '/dashboard';
                } else {
                    isActive = currentPath.includes(page);
                }

                link.classList.toggle('active', isActive);
            });
        }

        // ========================================================
        // Theme Toggle
        // ========================================================

        _setupThemeToggle() {
            const btn = document.getElementById('themeToggle');
            if (!btn) return;

            btn.addEventListener('click', this._onThemeToggle);
            this._updateThemeButton();
        }

        _onThemeToggle(e) {
            e.preventDefault();
            if (window.themeManager) {
                window.themeManager.toggle();
                this._updateThemeButton();
            }
        }

        _updateThemeButton() {
            const btn = document.getElementById('themeToggle');
            if (!btn) return;

            const icon = btn.querySelector('i');
            const label = btn.querySelector('span');
            const mode = window.themeManager?.getMode() || 'dark';

            const configs = {
                dark: { icon: 'fas fa-moon', label: 'تیره' },
                light: { icon: 'fas fa-sun', label: 'روشن' },
                auto: { icon: 'fas fa-circle-half-stroke', label: 'خودکار' },
            };

            const cfg = configs[mode] || configs.dark;

            if (icon) icon.className = cfg.icon;
            if (label) label.textContent = cfg.label;
        }

        // ========================================================
        // Logout
        // ========================================================

        _setupLogout() {
            const btn = document.getElementById('logoutBtn');
            if (!btn) return;

            btn.addEventListener('click', this._onLogout);
        }

        async _onLogout(e) {
            e.preventDefault();

            // تأیید
            let confirmed = false;
            if (typeof window.confirm === 'function') {
                try {
                    confirmed = await window.confirm(
                        'خروج از حساب',
                        'آیا از خروج اطمینان دارید؟',
                        'بله، خروج',
                        'انصراف'
                    );
                } catch (err) {
                    confirmed = window.confirm('آیا از خروج اطمینان دارید؟');
                }
            } else {
                confirmed = window.confirm('آیا از خروج اطمینان دارید؟');
            }

            if (!confirmed) return;

            try {
                if (window.api?.logout) {
                    await window.api.logout();
                }
            } catch (err) {
                console.warn('⚠️ Logout API error:', err);
            }

            // پاک کردن session
            document.cookie = 'session_id=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT';
            localStorage.removeItem('session_id');
            localStorage.removeItem('username');

            // ریدایرکت
            window.location.href = '/';
        }

        // ========================================================
        // لود کاربر
        // ========================================================

        async _loadUser() {
            if (!window.api?.getUserInfo) return;

            try {
                const data = await window.api.getUserInfo();
                if (data && data.success) {
                    this.user = data.data;
                    this._updateUserDisplay(data.data);
                }
            } catch (err) {
                console.warn('⚠️ NavManager: user load error', err.message);
            }
        }

        _updateUserDisplay(user) {
            const display = document.getElementById('userDisplay');
            if (!display) return;

            const roleMap = {
                'admin': '👑 ادمین',
                'vip': '⭐ VIP',
                'guest': '👤 مهمان',
                'user': '👤 کاربر',
            };

            const roleLabel = roleMap[user?.role] || 'کاربر';
            const username = user?.username || 'کاربر';

            display.innerHTML = `
                <i class="fas fa-user-circle"></i>
                <span>${this._escapeHtml(username)}</span>
            `;
        }

        // ========================================================
        // آپتایم
        // ========================================================

        _startClock() {
            if (this.clockInterval) clearInterval(this.clockInterval);

            const update = async () => {
                if (!window.api?.getStats) return;
                try {
                    const data = await window.api.getStats();
                    if (data && data.success && data.data) {
                        const el = document.getElementById('uptimeDisplay');
                        if (el) el.textContent = data.data.uptime || '۰s';
                    }
                } catch (err) { /* ignore */ }
            };

            update();
            this.clockInterval = setInterval(update, 30000);
        }

        // ========================================================
        // وضعیت سیستم
        // ========================================================

        _startStatusUpdate() {
            if (this.statusInterval) clearInterval(this.statusInterval);

            const update = async () => {
                if (!window.api?.getMetrics) return;
                try {
                    const data = await window.api.getMetrics();
                    if (!data || !data.success) return;

                    const metrics = data.data?.metrics || {};
                    const apiStatus = metrics.api_status?.value || 'unknown';

                    const dot = document.getElementById('statusDot');
                    const text = document.getElementById('statusText');

                    if (dot && text) {
                        dot.className = 'status-indicator';
                        if (apiStatus === 'ok') {
                            dot.classList.add('online');
                            text.textContent = 'پایدار';
                        } else if (apiStatus === 'degraded') {
                            dot.classList.add('warning');
                            text.textContent = 'ضعیف';
                        } else {
                            dot.classList.add('offline');
                            text.textContent = 'قطع';
                        }
                    }

                    // هشدارها
                    if (window.api?.getAlerts) {
                        const alertData = await window.api.getAlerts({ limit: 1, resolved: false });
                        const badge = document.getElementById('alertBadge');
                        if (badge && alertData?.data) {
                            const count = alertData.data.length || 0;
                            badge.textContent = count;
                            badge.style.display = count > 0 ? 'inline' : 'none';
                        }
                    }
                } catch (err) { /* ignore */ }
            };

            update();
            this.statusInterval = setInterval(update, 15000);
        }

        // ========================================================
        // Public API
        // ========================================================

        getUser() {
            return this.user;
        }

        isUserAdmin() {
            return this.user?.role === 'admin';
        }

        async refresh() {
            await this._loadUser();
            await this._startStatusUpdate();
        }

        destroy() {
            if (this.clockInterval) {
                clearInterval(this.clockInterval);
                this.clockInterval = null;
            }
            if (this.statusInterval) {
                clearInterval(this.statusInterval);
                this.statusInterval = null;
            }

            const btn = document.getElementById('logoutBtn');
            if (btn) btn.removeEventListener('click', this._onLogout);

            const themeBtn = document.getElementById('themeToggle');
            if (themeBtn) themeBtn.removeEventListener('click', this._onThemeToggle);

            this.isLoaded = false;
            console.log('🧹 NavManager destroyed');
        }

        // ========================================================
        // Helpers
        // ========================================================

        _escapeHtml(str) {
            if (!str) return '';
            return String(str)
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#39;');
        }
    }

    // ============================================================
    // Expose to window
    // ============================================================

    window.NavManager = NavManager;

    console.log('✅ NavManager v1.0 loaded');
})();
