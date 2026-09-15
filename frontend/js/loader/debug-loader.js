// ============================================================
// debug-loader.js — Debug Page Loader
// نسخه ۲.۰ — با TabManager مشترک + Debug Stats
// ============================================================

(function() {
    'use strict';

    // ============================================================
    // تنظیمات
    // ============================================================

    const DEBUG_TABS = {
        status: '/debug_tabs/status.html',
        logs: '/debug_tabs/logs.html',
        cli: '/debug_tabs/cli.html',
        system: '/debug_tabs/system.html',
        cache: '/debug_tabs/cache.html',
        processes: '/debug_tabs/processes.html',
        healing: '/debug_tabs/healing.html',
    };

    const DEBUG_LABELS = {
        status: 'وضعیت',
        logs: 'لاگ‌ها',
        cli: 'کنسول',
        system: 'سیستم',
        cache: 'کش',
        processes: 'پردازش‌ها',
        healing: 'خودترمیمی',
    };

    // ============================================================
    // State
    // ============================================================

    let tabManager = null;
    let statsInterval = null;

    // ============================================================
    // Init Tabs
    // ============================================================

    function initDebugTabs() {
        tabManager = new TabManager({
            tabs: DEBUG_TABS,
            labels: DEBUG_LABELS,
            containerId: 'tabContent',
            tabsNavId: 'debugTabs',
            cacheKey: 'debug_active_tab',
            defaultTab: 'status',
            urlParam: 'tab',
            initPrefix: 'init_',
            cleanupPrefix: 'cleanup_',
            activeClass: 'active',
            btnSelector: '.tab-btn',
        });

        tabManager.init();

        window.loadTab = (name) => tabManager.goTo(name);
        window.refreshCurrentTab = () => tabManager.refresh();
    }

    // ============================================================
    // Update Stats (Header)
    // ============================================================

    async function updateStats() {
        if (!window.api?.getAppStats) return;

        try {
            const res = await window.api.getAppStats();
            if (!res || !res.success || !res.data) return;

            const stats = res.data;
            const RAM_LIMIT_MB = 512;

            // ===== CPU =====
            const cpuEl = document.getElementById('debugCpu');
            if (cpuEl && stats.cpu) {
                const cpuPct = stats.cpu.percent || 0;
                cpuEl.textContent = cpuPct.toFixed(1) + '%';
                cpuEl.className = 'stat-value ' +
                    (cpuPct > 80 ? 'red' : cpuPct > 60 ? 'orange' : 'green');
            }

            // ===== RAM =====
            const ramEl = document.getElementById('debugRam');
            const ramBar = document.getElementById('debugRamBar');
            if (stats.ram) {
                const ramUsed = stats.ram.used_mb || 0;
                const ramPct = Math.min((ramUsed / RAM_LIMIT_MB) * 100, 100);

                if (ramEl) {
                    ramEl.textContent = ramUsed.toFixed(1) + ' MB (' + ramPct.toFixed(1) + '%)';
                    ramEl.className = 'stat-value ' +
                        (ramPct > 80 ? 'red' : ramPct > 60 ? 'orange' : 'green');
                }

                if (ramBar) {
                    ramBar.style.width = ramPct + '%';
                    ramBar.style.background = ramPct > 80
                        ? 'var(--color-red)'
                        : ramPct > 60
                            ? 'var(--color-orange)'
                            : 'var(--color-green)';
                }
            }

            // ===== Uptime =====
            const uptimeEl = document.getElementById('debugUptime');
            if (uptimeEl && stats.uptime) {
                uptimeEl.textContent = stats.uptime.app_formatted || '—';
            }

            // ===== Collections =====
            if (window.api.getMetrics) {
                const metrics = await window.api.getMetrics();
                if (metrics?.success && metrics.data) {
                    const collections = metrics.data.stats?.collections || 0;
                    const colEl = document.getElementById('debugCollections');
                    if (colEl) colEl.textContent = collections;
                }
            }

        } catch (err) {
            console.warn('⚠️ Debug stats update error:', err.message);
        }
    }

    function startStatsUpdate() {
        if (statsInterval) clearInterval(statsInterval);
        updateStats();
        statsInterval = setInterval(updateStats, 2000);
    }

    // ============================================================
    // Init
    // ============================================================

    function init() {
        console.log('🚀 Debug page initializing...');

        // Nav خودکار توسط core/index.js لود می‌شه

        initDebugTabs();
        startStatsUpdate();

        console.log('✅ Debug page ready');
    }

    // ============================================================
    // Cleanup
    // ============================================================

    function cleanup() {
        if (statsInterval) {
            clearInterval(statsInterval);
            statsInterval = null;
        }
        if (tabManager) {
            tabManager.destroy();
            tabManager = null;
        }

        console.log('🧹 Debug page cleaned up');
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

    console.log('✅ Debug loader v2.0 loaded');
})();
