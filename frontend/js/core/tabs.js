// ============================================================
// tabs.js — Tab Manager (Core)
// نسخه ۱.۰ — سیستم تحلیلگر
// کلاس مشترک مدیریت تب‌ها (جایگزین ۴ لودر تکراری)
// ============================================================

(function() {
    'use strict';

    // ============================================================
    // کلاس TabManager
    // ============================================================

    class TabManager {
        /**
         * @param {Object} config
         * @param {Object} config.tabs           - { tabName: '/path/to/tab.html' }
         * @param {Object} config.labels         - { tabName: 'برچسب' }
         * @param {string} config.containerId    - id ظرف محتوا
         * @param {string} config.tabsNavId      - id نوار تب‌ها
         * @param {string} [config.cacheKey]     - کلید localStorage برای ذخیره تب فعال
         * @param {string} [config.urlParam]     - نام پارامتر URL (پیش‌فرض: 'tab')
         * @param {string} [config.defaultTab]   - تب پیش‌فرض
         * @param {string} [config.initPrefix]   - پیشوند توابع init (پیش‌فرض: 'init_')
         * @param {string} [config.cleanupPrefix]- پیشوند توابع cleanup (پیش‌فرض: 'cleanup_')
         * @param {string} [config.activeClass]  - کلاس تب فعال (پیش‌فرض: 'active')
         * @param {string} [config.btnSelector]  - سلکتور دکمه‌های تب
         * @param {string} [config.dataAttr]     - نام data attribute (پیش‌فرض: 'tab')
         * @param {Function} [config.onBeforeLoad] - callback قبل از لود
         * @param {Function} [config.onAfterLoad]  - callback بعد از لود
         * @param {Function} [config.onError]      - callback هنگام خطا
         */
        constructor(config) {
            // اعتبارسنجی
            if (!config || !config.tabs || !config.containerId || !config.tabsNavId) {
                throw new Error('❌ TabManager: config ناقص است. tabs, containerId, tabsNavId الزامی هستند.');
            }

            // تنظیمات
            this.config = {
                tabs: config.tabs,
                labels: config.labels || {},
                containerId: config.containerId,
                tabsNavId: config.tabsNavId,
                cacheKey: config.cacheKey || null,
                urlParam: config.urlParam || 'tab',
                defaultTab: config.defaultTab || Object.keys(config.tabs)[0],
                initPrefix: config.initPrefix || 'init_',
                cleanupPrefix: config.cleanupPrefix || 'cleanup_',
                activeClass: config.activeClass || 'active',
                btnSelector: config.btnSelector || '.tab-btn',
                dataAttr: config.dataAttr || 'tab',
                onBeforeLoad: config.onBeforeLoad || null,
                onAfterLoad: config.onAfterLoad || null,
                onError: config.onError || null,
            };

            // State
            this.cache = {};                // { tabName: html }
            this.currentTab = null;
            this.currentInitTimer = null;
            this.isInitialized = false;
            this.loadingTab = null;         // تب در حال لود (برای cancel)

            // DOM refs (بعداً set میشن)
            this.container = null;
            this.tabsNav = null;

            // Bind
            this._handleTabClick = this._handleTabClick.bind(this);
        }

        // ========================================================
        // مقداردهی اولیه
        // ========================================================

        init() {
            if (this.isInitialized) {
                console.warn('⚠️ TabManager already initialized');
                return;
            }

            // پیدا کردن DOM
            this.container = document.getElementById(this.config.containerId);
            this.tabsNav = document.getElementById(this.config.tabsNavId);

            if (!this.container) {
                console.error(`❌ TabManager: container #${this.config.containerId} پیدا نشد`);
                return;
            }

            if (!this.tabsNav) {
                console.error(`❌ TabManager: tabsNav #${this.config.tabsNavId} پیدا نشد`);
                return;
            }

            // نصب listener روی تب‌ها
            this._setupTabListeners();

            // تعیین تب پیش‌فرض
            const initialTab = this._resolveInitialTab();

            // فعال‌سازی دکمه تب
            this._activateButton(initialTab);

            // لود تب
            this.load(initialTab);

            this.isInitialized = true;
            console.log(`✅ TabManager initialized (default: ${initialTab})`);
        }

        // ========================================================
        // Setup Tab Listeners
        // ========================================================

        _setupTabListeners() {
            const buttons = this.tabsNav.querySelectorAll(this.config.btnSelector);

            buttons.forEach(btn => {
                btn.addEventListener('click', this._handleTabClick);
            });

            console.log(`🔗 TabManager: ${buttons.length} تب ثبت شد`);
        }

        _handleTabClick(e) {
            e.preventDefault();

            const btn = e.currentTarget;
            const tabName = btn.dataset[this.config.dataAttr];

            if (!tabName) return;
            if (tabName === this.currentTab && this.cache[tabName]) return;

            this._activateButton(tabName);
            this.load(tabName);
        }

        _activateButton(tabName) {
            const buttons = this.tabsNav.querySelectorAll(this.config.btnSelector);
            buttons.forEach(btn => {
                const btnTab = btn.dataset[this.config.dataAttr];
                btn.classList.toggle(this.config.activeClass, btnTab === tabName);
            });
        }

        // ========================================================
        // تعیین تب اولیه
        // ========================================================

        _resolveInitialTab() {
            const { tabs, defaultTab, urlParam, cacheKey } = this.config;

            // ۱. از URL
            try {
                const params = new URLSearchParams(window.location.search);
                const urlTab = params.get(urlParam);
                if (urlTab && tabs[urlTab]) return urlTab;
            } catch (e) { /* ignore */ }

            // ۲. از localStorage
            if (cacheKey) {
                try {
                    const savedTab = localStorage.getItem(cacheKey);
                    if (savedTab && tabs[savedTab]) return savedTab;
                } catch (e) { /* ignore */ }
            }

            // ۳. پیش‌فرض
            return defaultTab;
        }

        // ========================================================
        // لود تب
        // ========================================================

        async load(tabName) {
            if (!this.container) return;

            // اگر تب اشتباه
            if (!this.config.tabs[tabName]) {
                this._showError(tabName, 'تب یافت نشد');
                return;
            }

            // اگر قبلاً لود شده و تب فعلی هنوز هست
            if (tabName === this.currentTab && this.cache[tabName]) {
                return;
            }

            // پاک کردن timer قبلی
            if (this.currentInitTimer) {
                clearTimeout(this.currentInitTimer);
                this.currentInitTimer = null;
            }

            // cleanup تب قبلی
            if (this.currentTab && this.currentTab !== tabName) {
                this._cleanupTab(this.currentTab);
            }

            // ثبت تب در حال لود
            const previousTab = this.currentTab;
            this.currentTab = tabName;
            this.loadingTab = tabName;

            // callback
            if (this.config.onBeforeLoad) {
                try { this.config.onBeforeLoad(tabName, previousTab); } catch (e) {}
            }

            // ===== اگر در کش هست =====
            if (this.cache[tabName]) {
                this.container.innerHTML = this.cache[tabName];
                this._executeScripts(tabName);
                this._updateURL(tabName);
                this.loadingTab = null;
                return;
            }

            // ===== نمایش لودینگ =====
            this._showSkeleton();

            // ===== fetch =====
            try {
                const res = await fetch(this.config.tabs[tabName]);
                if (!res.ok) throw new Error(`HTTP ${res.status}`);

                const html = await res.text();

                // اگر تب عوض شده، نادیده بگیر
                if (this.loadingTab !== tabName) {
                    console.debug(`⏭️ Tab "${tabName}" discarded (tab changed)`);
                    return;
                }

                this.cache[tabName] = html;
                this.container.innerHTML = html;
                this._executeScripts(tabName);
                this._updateURL(tabName);

                // callback
                if (this.config.onAfterLoad) {
                    try { this.config.onAfterLoad(tabName); } catch (e) {}
                }

                this.loadingTab = null;

            } catch (err) {
                console.error(`❌ TabManager: failed to load "${tabName}"`, err);
                this.loadingTab = null;
                this._showError(tabName, err.message);

                if (this.config.onError) {
                    try { this.config.onError(tabName, err); } catch (e) {}
                }
            }
        }

        // ========================================================
        // اجرای اسکریپت‌ها + init
        // ========================================================

        _executeScripts(tabName) {
            // اجرای اسکریپت‌های inline
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

            // اجرای init function
            const initFnName = `${this.config.initPrefix}${tabName}`;
            const initFn = window[initFnName];

            if (typeof initFn === 'function') {
                // تأخیر کوچک برای اطمینان از رندر
                this.currentInitTimer = setTimeout(() => {
                    // اگر تب هنوز همون تب باشه
                    if (this.currentTab === tabName) {
                        try {
                            initFn();
                            console.log(`✅ TabManager: init_${tabName}() اجرا شد`);
                        } catch (err) {
                            console.error(`❌ TabManager: init_${tabName}() خطا داد`, err);
                        }
                    }
                }, 50);
            }
        }

        // ========================================================
        // cleanup تب قبلی
        // ========================================================

        _cleanupTab(tabName) {
            const cleanupFnName = `${this.config.cleanupPrefix}${tabName}`;
            const cleanupFn = window[cleanupFnName];

            if (typeof cleanupFn === 'function') {
                try {
                    cleanupFn();
                    console.log(`🧹 TabManager: cleanup_${tabName}() اجرا شد`);
                } catch (err) {
                    console.warn(`⚠️ TabManager: cleanup_${tabName}() خطا داد`, err);
                }
            }
        }

        // ========================================================
        // Skeleton / Error
        // ========================================================

        _showSkeleton() {
            const label = this.config.labels[this.currentTab] || this.currentTab;
            this.container.innerHTML = `
                <div class="loading-container">
                    <div class="loading-spinner"></div>
                    <p class="loading-text">در حال بارگذاری ${this._escapeHtml(label)}...</p>
                </div>
            `;
        }

        _showError(tabName, message) {
            const label = this.config.labels[tabName] || tabName;
            this.container.innerHTML = `
                <div class="empty-state error">
                    <span class="empty-icon">⚠️</span>
                    <div class="empty-title">خطا در بارگذاری ${this._escapeHtml(label)}</div>
                    <div class="empty-message">${this._escapeHtml(message || '')}</div>
                    <button class="empty-action" onclick="window.__tabManager_${this.config.containerId}?.reload('${this._escapeAttr(tabName)}')">
                        <i class="fas fa-sync-alt"></i>
                        تلاش مجدد
                    </button>
                </div>
            `;
        }

        // ========================================================
        // URL
        // ========================================================

        _updateURL(tabName) {
            try {
                const url = new URL(window.location);
                url.searchParams.set(this.config.urlParam, tabName);
                window.history.replaceState(null, '', url.toString());
            } catch (e) { /* ignore */ }

            // ذخیره در localStorage
            if (this.config.cacheKey) {
                try {
                    localStorage.setItem(this.config.cacheKey, tabName);
                } catch (e) { /* ignore */ }
            }
        }

        // ========================================================
        // Public API
        // ========================================================

        /**
         * رفرش تب فعلی
         */
        refresh() {
            if (!this.currentTab) return;

            const tabToReload = this.currentTab;
            delete this.cache[tabToReload];

            // cleanup
            this._cleanupTab(tabToReload);

            // reset state
            this.currentTab = null;

            // reload
            this.load(tabToReload);

            console.log(`🔄 TabManager: refresh ${tabToReload}`);
        }

        /**
         * لود مجدد تب مشخص
         */
        reload(tabName) {
            if (!tabName) tabName = this.currentTab;
            if (!tabName) return;

            delete this.cache[tabName];
            this._cleanupTab(tabName);

            if (this.currentTab === tabName) {
                this.currentTab = null;
            }

            this._activateButton(tabName);
            this.load(tabName);
        }

        /**
         * رفتن به تب مشخص
         */
        goTo(tabName) {
            if (!this.config.tabs[tabName]) return;
            this._activateButton(tabName);
            this.load(tabName);
        }

        /**
         * پاک کردن کش
         */
        clearCache(tabName = null) {
            if (tabName) {
                delete this.cache[tabName];
            } else {
                this.cache = {};
            }
        }

        /**
         * وضعیت فعلی
         */
        getState() {
            return {
                currentTab: this.currentTab,
                isInitialized: this.isInitialized,
                cachedTabs: Object.keys(this.cache),
                tabs: Object.keys(this.config.tabs),
            };
        }

        /**
         * پاک‌سازی کامل
         */
        destroy() {
            // cleanup تب فعلی
            if (this.currentTab) {
                this._cleanupTab(this.currentTab);
            }

            // پاک timers
            if (this.currentInitTimer) {
                clearTimeout(this.currentInitTimer);
                this.currentInitTimer = null;
            }

            // حذف listeners
            if (this.tabsNav) {
                const buttons = this.tabsNav.querySelectorAll(this.config.btnSelector);
                buttons.forEach(btn => {
                    btn.removeEventListener('click', this._handleTabClick);
                });
            }

            this.cache = {};
            this.currentTab = null;
            this.isInitialized = false;

            console.log('🧹 TabManager destroyed');
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

        _escapeAttr(str) {
            if (!str) return '';
            return String(str).replace(/'/g, "\\'").replace(/"/g, '&quot;');
        }
    }

    // ============================================================
    // Expose to window
    // ============================================================

    window.TabManager = TabManager;

    console.log('✅ TabManager v1.0 loaded');
})();
