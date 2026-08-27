// static/js/settings-theme.js
// ============================================================
// مدیریت تم - نسخه ۲.۰ (قبلاً در settings.html ادغام شده)
// ============================================================

(function() {
    'use strict';

    // ============================================================
    // ۱. بارگذاری تم ذخیره شده
    // ============================================================
    
    function loadTheme() {
        const savedTheme = localStorage.getItem('theme') || 'dark';
        const select = document.getElementById('themeSelect');
        if (select) {
            select.value = savedTheme;
            applyTheme(savedTheme);
        }
        return savedTheme;
    }

    // ============================================================
    // ۲. اعمال تم
    // ============================================================
    
    function applyTheme(theme) {
        // ذخیره در localStorage
        localStorage.setItem('theme', theme);
        
        // اعمال به body
        document.body.className = '';
        if (theme === 'light') {
            document.body.classList.add('theme-light');
        } else if (theme === 'auto') {
            document.body.classList.add('theme-auto');
            // بررسی سیستم
            if (window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches) {
                document.body.classList.add('theme-light');
            }
        }
        // dark حالت پیش‌فرض است
    }

    // ============================================================
    // ۳. گوش دادن به تغییرات سیستم (برای حالت auto)
    // ============================================================
    
    function listenToSystemTheme() {
        if (window.matchMedia) {
            const mediaQuery = window.matchMedia('(prefers-color-scheme: light)');
            mediaQuery.addEventListener('change', function(e) {
                const theme = document.getElementById('themeSelect')?.value;
                if (theme === 'auto') {
                    applyTheme('auto');
                }
            });
        }
    }

    // ============================================================
    // ۴. اجرا
    // ============================================================
    
    document.addEventListener('DOMContentLoaded', function() {
        loadTheme();
        listenToSystemTheme();

        // گوش دادن به تغییرات select
        const select = document.getElementById('themeSelect');
        if (select) {
            select.addEventListener('change', function() {
                applyTheme(this.value);
                showToast('✅ تم تغییر کرد', 'success');
            });
        }
    });

    // صادر کردن توابع
    window.applyTheme = applyTheme;
    window.loadTheme = loadTheme;

})();
