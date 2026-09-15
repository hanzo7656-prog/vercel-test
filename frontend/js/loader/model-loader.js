// ============================================================
// model-loader.js — Model Page Loader
// نسخه ۲.۰ — با TabManager مشترک
// ============================================================

(function() {
    'use strict';

    // ============================================================
    // تنظیمات
    // ============================================================

    const MODEL_TABS = {
        dashboard: '/model_tabs/dashboard.html',
        info: '/model_tabs/info.html',
        training: '/model_tabs/training.html',
        schedule: '/model_tabs/schedule.html',
        history: '/model_tabs/history.html',
        features: '/model_tabs/features.html',
        tools: '/model_tabs/tools.html',
    };

    const MODEL_LABELS = {
        dashboard: 'داشبورد',
        info: 'اطلاعات مدل',
        training: 'آموزش',
        schedule: 'زمان‌بندی',
        history: 'تاریخچه',
        features: 'اهمیت ویژگی‌ها',
        tools: 'ابزارها',
    };

    // ============================================================
    // State
    // ============================================================

    let tabManager = null;
    let clockInterval = null;
    let badgeInterval = null;

    // ============================================================
    // Init Tabs
    // ============================================================

    function initModelTabs() {
        tabManager = new TabManager({
            tabs: MODEL_TABS,
            labels: MODEL_LABELS,
            containerId: 'modelTabContent',
            tabsNavId: 'modelTabs',
            cacheKey: 'model_active_tab',
            defaultTab: 'dashboard',
            urlParam: 'tab',
            initPrefix: 'init_',
            cleanupPrefix: 'cleanup_',
            activeClass: 'active',
            btnSelector: '.model-tab-btn',
        });

        tabManager.init();

        window.refreshCurrentTab = () => tabManager.refresh();
        window.loadModelTab = (name) => tabManager.goTo(name);
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
    // Model Status Badge
    // ============================================================

    async function updateModelBadge() {
        if (!window.api?.getModelStatus) return;

        try {
            const data = await window.api.getModelStatus();
            const badge = document.getElementById('modelStatusBadge');
            if (!badge) return;

            if (data && data.success && data.data) {
                const loaded = data.data.loaded || false;
                const isTraining = data.data.is_training || false;
                const statusText = badge.querySelector('.status-text');

                if (isTraining) {
                    badge.className = 'status-badge training';
                    if (statusText) statusText.textContent = 'در حال آموزش';
                } else if (loaded) {
                    badge.className = 'status-badge active';
                    if (statusText) statusText.textContent = 'فعال';
                } else {
                    badge.className = 'status-badge demo';
                    if (statusText) statusText.textContent = 'دمو';
                }
            }
        } catch (err) {
            console.warn('⚠️ Model badge update error:', err.message);
        }
    }

    function startModelBadgeUpdate() {
        if (badgeInterval) clearInterval(badgeInterval);
        updateModelBadge();
        badgeInterval = setInterval(updateModelBadge, 15000);
    }

    // ============================================================
    // Init
    // ============================================================

    function init() {
        console.log('🚀 Model page initializing...');

        // Nav خودکار توسط core/index.js لود می‌شه

        startClock();
        startModelBadgeUpdate();
        initModelTabs();

        console.log('✅ Model page ready');
    }

    // ============================================================
    // Cleanup
    // ============================================================

    function cleanup() {
        if (clockInterval) {
            clearInterval(clockInterval);
            clockInterval = null;
        }
        if (badgeInterval) {
            clearInterval(badgeInterval);
            badgeInterval = null;
        }
        if (tabManager) {
            tabManager.destroy();
            tabManager = null;
        }

        console.log('🧹 Model page cleaned up');
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

    console.log('✅ Model loader v2.0 loaded');
})();
