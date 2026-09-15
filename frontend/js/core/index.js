// ============================================================
// index.js — Core Bootstrap
// نسخه ۱.۰ — سیستم تحلیلگر
// لود خودکار هسته‌های اصلی + setup اولیه
// ============================================================

(function() {
    'use strict';

    // ============================================================
    // Auto-init
    // ============================================================

    async function bootstrap() {
        // ۱. ThemeManager خودش در constructor کار می‌کنه
        // ۲. NavManager باید در هر صفحه setup بشه

        // اگه navContainer هست، NavManager رو بساز
        if (document.getElementById('navContainer')) {
            if (!window.navManager) {
                window.navManager = new window.NavManager();
                await window.navManager.load();
            }
        }

        console.log('✅ Core bootstrap complete');
    }

    // اجرا بعد از DOMContentLoaded
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', bootstrap);
    } else {
        bootstrap();
    }

    // ============================================================
    // Cleanup هنگام بستن
    // ============================================================

    window.addEventListener('beforeunload', () => {
        if (window.navManager?.destroy) {
            try { window.navManager.destroy(); } catch (e) {}
        }
    });

    console.log('✅ Core index loaded');
})();
