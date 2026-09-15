// ============================================================
// settings_loader.js — Settings Page Loader
// نسخه ۲.۰ — با TabManager مشترک
// ============================================================

(function() {
    'use strict';

    // ============================================================
    // تنظیمات
    // ============================================================

    const SETTINGS_TABS = {
        scheduler: '/settings_tabs/scheduler.html',
        theme: '/settings_tabs/theme.html',
        cache: '/settings_tabs/cache.html',
        notifications: '/settings_tabs/notifications.html',
        dashboard: '/settings_tabs/dashboard.html',
        account: '/settings_tabs/account.html',
        system: '/settings_tabs/system.html',
    };

    const SETTINGS_LABELS = {
        scheduler: 'همگام‌سازی',
        theme: 'ظاهر',
        cache: 'کش',
        notifications: 'اعلان‌ها',
        dashboard: 'داشبورد',
        account: 'حساب کاربری',
        system: 'سیستم',
    };

    // ============================================================
    // State
    // ============================================================

    let tabManager = null;
    let clockInterval = null;

    // ============================================================
    // Init Tabs
    // ============================================================

    function initSettingsTabs() {
        tabManager = new TabManager({
            tabs: SETTINGS_TABS,
            labels: SETTINGS_LABELS,
            containerId: 'settingsTabContent',
            tabsNavId: 'settingsTabs',
            cacheKey: 'settings_active_tab',
            defaultTab: 'scheduler',
            urlParam: 'tab',
            initPrefix: 'init_settings_',
            cleanupPrefix: 'cleanup_settings_',
            activeClass: 'active',
            btnSelector: '.settings-tab-btn',
        });

        tabManager.init();

        window.refreshCurrentTab = () => tabManager.refresh();
        window.loadSettingsTab = (name) => tabManager.goTo(name);
    }

    // ============================================================
    // Clock
    // ============================================================

    function updateClock() {
        const el = document.getElementById('pageTimestamp');
        if (!el) return;

        const now = new Date();
        el.textContent = now.toLocaleTimeString('fa-IR', {
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
        });
    }

    function startClock() {
        if (clockInterval) clearInterval(clockInterval);
        updateClock();
        clockInterval = setInterval(updateClock, 1000);
    }

    // ============================================================
    // Init
    // ============================================================

    function init() {
        console.log('🚀 Settings page initializing...');

        // Nav خودکار توسط core/index.js لود می‌شه

        startClock();
        initSettingsTabs();

        console.log('✅ Settings page ready');
    }

    // ============================================================
    // Cleanup
    // ============================================================

    function cleanup() {
        if (clockInterval) {
            clearInterval(clockInterval);
            clockInterval = null;
        }
        if (tabManager) {
            tabManager.destroy();
            tabManager = null;
        }

        console.log('🧹 Settings page cleaned up');
    }

    // ============================================================
    // شروع
    // ============================================================

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    window.addEventListener('beforeunload', cleanup);

    console.log('✅ Settings loader v2.0 loaded');
})();
