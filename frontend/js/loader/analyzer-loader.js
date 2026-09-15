// ============================================================
// analyzer-loader.js — Analyzer Page Loader
// نسخه ۲.۰ — با TabManager مشترک
// ============================================================

(function() {
    'use strict';

    // ============================================================
    // تنظیمات تب‌ها
    // ============================================================

    const ANALYZER_TABS = {
        predict: '/analyzer_tabs/predict.html',
        indicators: '/analyzer_tabs/indicators.html',
        history: '/analyzer_tabs/history.html',
    };

    const ANALYZER_LABELS = {
        predict: 'پیش‌بینی',
        indicators: 'شاخص‌ها',
        history: 'تاریخچه',
    };

    // ============================================================
    // ایجاد TabManager
    // ============================================================

    let tabManager = null;
    let clockInterval = null;

    function initAnalyzerTabs() {
        tabManager = new TabManager({
            tabs: ANALYZER_TABS,
            labels: ANALYZER_LABELS,
            containerId: 'analyzerTabContent',
            tabsNavId: 'analyzerTabs',
            cacheKey: 'analyzer_active_tab',
            defaultTab: 'predict',
            urlParam: 'tab',
            initPrefix: 'init_',
            cleanupPrefix: 'cleanup_',
            activeClass: 'active',
            btnSelector: '.analyzer-tab-btn',
        });

        tabManager.init();

        // Expose برای refresh از HTML
        window.refreshCurrentTab = () => tabManager.refresh();
        window.loadAnalyzerTab = (name) => tabManager.goTo(name);
    }

    // ============================================================
    // Clock (Timestamp)
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
    // Page Status Badge
    // ============================================================

    function updatePageStatus(status, text) {
        const badge = document.getElementById('pageStatusBadge');
        if (!badge) return;
        badge.className = 'status-badge ' + status;
        const textEl = badge.querySelector('.status-text');
        if (textEl) textEl.textContent = text;
    }

    window.updatePageStatus = updatePageStatus;

    // ============================================================
    // Init
    // ============================================================

    function init() {
        console.log('🚀 Analyzer page initializing...');

        // Nav خودکار توسط core/index.js لود می‌شه

        startClock();
        initAnalyzerTabs();
        updatePageStatus('online', 'آماده');

        console.log('✅ Analyzer page ready');
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

        console.log('🧹 Analyzer page cleaned up');
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

    console.log('✅ Analyzer loader v2.0 loaded');
})();
