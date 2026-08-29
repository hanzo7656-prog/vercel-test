// static/js/menu.js
// ============================================================
// مدیریت منوی اصلی - نسخه ۳.۰
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
            menuToggle.classList.toggle('open', isOpen);
        });

        // بستن با کلیک روی overlay
        flyoutOverlay.addEventListener('click', function() {
            closeMenu();
        });

        // بستن با کلیک روی لینک‌ها
        flyoutMenu.querySelectorAll('.menu-item').forEach(function(link) {
            link.addEventListener('click', function() {
                closeMenu();
                flyoutMenu.querySelectorAll('.menu-item').forEach(function(el) {
                    el.classList.remove('active');
                });
                this.classList.add('active');
            });
        });

        // بستن با کلید ESC
        document.addEventListener('keydown', function(e) {
            if (e.key === 'Escape' && flyoutMenu.classList.contains('open')) {
                closeMenu();
            }
        });

        // بستن با کلیک خارج
        document.addEventListener('click', function(e) {
            if (flyoutMenu.classList.contains('open')) {
                if (!flyoutMenu.contains(e.target) && !menuToggle.contains(e.target)) {
                    closeMenu();
                }
            }
        });

        // علامت‌گذاری صفحه فعلی
        const currentPath = window.location.pathname;
        flyoutMenu.querySelectorAll('.menu-item').forEach(function(item) {
            const href = item.getAttribute('href');
            if (href && currentPath.startsWith(href) && href !== '/') {
                item.classList.add('active');
            } else if (href === '/' && currentPath === '/') {
                item.classList.add('active');
            }
        });
    }

    function closeMenu() {
        const flyoutMenu = document.getElementById('flyoutMenu');
        const flyoutOverlay = document.getElementById('flyoutOverlay');
        const menuToggle = document.getElementById('menuToggle');
        
        if (flyoutMenu) flyoutMenu.classList.remove('open');
        if (flyoutOverlay) flyoutOverlay.classList.remove('open');
        if (menuToggle) {
            menuToggle.innerHTML = '<i class="fas fa-bars"></i>';
            menuToggle.classList.remove('open');
        }
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
        const el = document.getElementById('uptimeText');
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
                        dot.className = 'status-dot';
                        if (api === 'ok') {
                            dot.classList.remove('warning', 'error');
                            text.textContent = 'پایدار';
                        } else if (api === 'degraded') {
                            dot.classList.add('warning');
                            text.textContent = 'ضعیف';
                        } else {
                            dot.classList.add('error');
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
                    const display = document.getElementById('userName');
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
    // ۵. خروج
    // ============================================================
    
    window.logoutUser = function() {
        if (!confirm('آیا از خروج از حساب کاربری اطمینان دارید؟')) return;
        fetch('/logout', { method: 'POST', credentials: 'include' })
            .then(function() { window.location.href = '/login'; })
            .catch(function() { window.location.href = '/login'; });
    };

    // ============================================================
    // ۶. اجرا
    // ============================================================
    
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function() {
            initMenu();
            loadUserDisplay();
            updateStatusDot();
            setInterval(updateStatusDot, 10000);
            fetchAndStartUptime();
        });
    } else {
        initMenu();
        loadUserDisplay();
        updateStatusDot();
        setInterval(updateStatusDot, 10000);
        fetchAndStartUptime();
    }

    // صادر کردن توابع
    window.initMenu = initMenu;
    window.fetchAndStartUptime = fetchAndStartUptime;
    window.updateStatusDot = updateStatusDot;
    window.loadUserDisplay = loadUserDisplay;

})();
