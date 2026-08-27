// static/js/menu.js
// ============================================================
// مدیریت منوی اصلی - نسخه ۲.۰
// ============================================================

(function() {
    'use strict';

    // ============================================================
    // ۱. منوی همبرگری
    // ============================================================
    
    function initMenu() {
        const menuToggle = document.getElementById('menuToggle');
        const flyoutMenu = document.getElementById('flyoutMenu');
        const flyoutOverlay = document.getElementById('flyoutOverlay');

        if (!menuToggle || !flyoutMenu || !flyoutOverlay) {
            console.warn('⚠️ Menu elements not found');
            return;
        }

        // باز/بستن منو
        menuToggle.addEventListener('click', function(e) {
            e.stopPropagation();
            const isOpen = flyoutMenu.classList.toggle('open');
            flyoutOverlay.classList.toggle('open');
            menuToggle.innerHTML = isOpen ? '<i class="fas fa-times"></i>' : '<i class="fas fa-bars"></i>';
        });

        // بستن با کلیک روی overlay
        flyoutOverlay.addEventListener('click', function() {
            flyoutMenu.classList.remove('open');
            flyoutOverlay.classList.remove('open');
            menuToggle.innerHTML = '<i class="fas fa-bars"></i>';
        });

        // بستن با کلیک روی لینک‌ها
        flyoutMenu.querySelectorAll('a').forEach(function(link) {
            link.addEventListener('click', function() {
                flyoutMenu.classList.remove('open');
                flyoutOverlay.classList.remove('open');
                menuToggle.innerHTML = '<i class="fas fa-bars"></i>';
            });
        });

        // بستن با کلید ESC
        document.addEventListener('keydown', function(e) {
            if (e.key === 'Escape' && flyoutMenu.classList.contains('open')) {
                flyoutMenu.classList.remove('open');
                flyoutOverlay.classList.remove('open');
                menuToggle.innerHTML = '<i class="fas fa-bars"></i>';
            }
        });

        console.log('✅ Menu initialized');
    }

    // ============================================================
    // ۲. آپتایم
    // ============================================================

    let uptimeStartTime = null;
    let uptimeInterval = null;

    function fetchAndStartUptime() {
        fetch('/stats', { credentials: 'include' })
            .then(function(res) { return res.json(); })
            .then(function(data) {
                if (data.uptime) {
                    startUptime(data.uptime);
                }
            })
            .catch(function() {});
    }

    function startUptime(uptimeStr) {
        if (!uptimeStr) return;
        
        // تبدیل "1h 23m" یا "1h23m" یا "1h 23m 45s" به ثانیه
        let totalSeconds = 0;
        const parts = uptimeStr.match(/(\d+)\s*(h|m|s)/g);
        if (parts) {
            parts.forEach(function(part) {
                const num = parseInt(part);
                const unit = part.slice(-1);
                if (unit === 'h') totalSeconds += num * 3600;
                else if (unit === 'm') totalSeconds += num * 60;
                else if (unit === 's') totalSeconds += num;
            });
        } else {
            // fallback
            const parts2 = uptimeStr.split(':').map(Number);
            if (parts2.length === 3) totalSeconds = parts2[0] * 3600 + parts2[1] * 60 + parts2[2];
            else if (parts2.length === 2) totalSeconds = parts2[0] * 60 + parts2[1];
            else totalSeconds = parts2[0] || 0;
        }

        uptimeStartTime = Date.now() - (totalSeconds * 1000);
        updateUptimeDisplay();
        
        if (uptimeInterval) clearInterval(uptimeInterval);
        uptimeInterval = setInterval(updateUptimeDisplay, 1000);
    }

    function updateUptimeDisplay() {
        const el = document.getElementById('uptimeDisplay');
        if (!el || !uptimeStartTime) return;
        
        const elapsed = Math.floor((Date.now() - uptimeStartTime) / 1000);
        el.textContent = formatDuration(elapsed);
    }

    function formatDuration(seconds) {
        if (seconds < 60) return seconds + 's';
        
        const days = Math.floor(seconds / 86400);
        seconds -= days * 86400;
        const hours = Math.floor(seconds / 3600);
        seconds -= hours * 3600;
        const minutes = Math.floor(seconds / 60);
        seconds -= minutes * 60;
        
        let parts = [];
        if (days > 0) parts.push(days + 'd');
        if (hours > 0 || days > 0) parts.push(hours + 'h');
        if (minutes > 0 || hours > 0 || days > 0) parts.push(minutes + 'm');
        parts.push(seconds + 's');
        
        return parts.join(' ');
    }

    // ============================================================
    // ۳. وضعیت آنلاین/آفلاین
    // ============================================================

    function updateStatusDot() {
        fetch('/api/metrics', { credentials: 'include' })
            .then(function(res) { return res.json(); })
            .then(function(data) {
                if (data.success) {
                    const metrics = data.data.metrics || {};
                    const api = metrics.api_status?.value || 'unknown';
                    const dot = document.getElementById('statusDot');
                    const text = document.getElementById('statusText');
                    
                    if (dot && text) {
                        if (api === 'ok') {
                            dot.style.background = '#00ff88';
                            text.textContent = 'پایدار';
                        } else if (api === 'degraded') {
                            dot.style.background = '#ff8800';
                            text.textContent = 'ضعیف';
                        } else {
                            dot.style.background = '#ff4444';
                            text.textContent = 'قطع';
                        }
                    }
                }
            })
            .catch(function() {});
    }

    // ============================================================
    // ۴. نمایش کاربر
    // ============================================================

    function loadUserDisplay() {
        fetch('/api/user', { credentials: 'include' })
            .then(function(res) { return res.json(); })
            .then(function(data) {
                if (data.success) {
                    const display = document.getElementById('userDisplay');
                    if (display) {
                        const roleMap = { 
                            'admin': '👑 ادمین', 
                            'vip': '⭐ VIP', 
                            'guest': '👤 مهمان' 
                        };
                        display.textContent = roleMap[data.data.role] || data.data.username;
                    }
                }
            })
            .catch(function() {});
    }

    // ============================================================
    // ۵. اجرا
    // ============================================================

    // اجرا بعد از لود کامل DOM
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function() {
            initMenu();
            loadUserDisplay();
            updateStatusDot();
            setInterval(updateStatusDot, 10000);
        });
    } else {
        initMenu();
        loadUserDisplay();
        updateStatusDot();
        setInterval(updateStatusDot, 10000);
    }

    // صادر کردن توابع برای استفاده در صفحات دیگر
    window.initMenu = initMenu;
    window.fetchAndStartUptime = fetchAndStartUptime;
    window.updateStatusDot = updateStatusDot;
    window.loadUserDisplay = loadUserDisplay;

})();
