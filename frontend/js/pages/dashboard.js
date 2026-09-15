// ============================================================
// dashboard.js — Dashboard Page Script
// نسخه ۱.۰ — سیستم تحلیلگر
// ============================================================

(function() {
    'use strict';

    // ============================================================
    // State
    // ============================================================

    let autoUpdateInterval = null;
    let isReady = false;

    // ============================================================
    // ۱. Floating Particles
    // ============================================================

    function initParticles() {
        const container = document.getElementById('dashboardParticles');
        if (!container) return;

        const colors = ['', 'purple', 'pink', 'green'];
        const count = 25;

        for (let i = 0; i < count; i++) {
            const p = document.createElement('div');
            p.className = 'dashboard-particle ' +
                colors[Math.floor(Math.random() * colors.length)];

            const size = Math.random() * 8 + 3;
            const left = Math.random() * 100;
            const duration = Math.random() * 20 + 15;
            const delay = Math.random() * -30;
            const drift = (Math.random() - 0.5) * 200;

            p.style.width = size + 'px';
            p.style.height = size + 'px';
            p.style.left = left + '%';
            p.style.animationDuration = duration + 's';
            p.style.animationDelay = delay + 's';
            p.style.setProperty('--drift', drift + 'px');

            container.appendChild(p);
        }

        console.log(`✨ Created ${count} floating particles`);
    }

    // ============================================================
    // ۲. Count-Up Animation
    // ============================================================

    function animateCountUp(element, targetValue, options = {}) {
        if (!element) return;

        const {
            duration = 1500,
            decimals = 0,
            prefix = '',
            suffix = '',
            useComma = true,
        } = options;

        if (!targetValue || targetValue === 0 || isNaN(targetValue)) {
            element.textContent = prefix + '0' + suffix;
            return;
        }

        const startTime = performance.now();

        element.classList.add('counting');

        function update(currentTime) {
            const elapsed = currentTime - startTime;
            const progress = Math.min(elapsed / duration, 1);
            const eased = 1 - Math.pow(1 - progress, 4);
            const current = targetValue * eased;

            let display = current.toFixed(decimals);
            if (useComma) {
                display = Number(display).toLocaleString('en-US', {
                    minimumFractionDigits: decimals,
                    maximumFractionDigits: decimals,
                });
            }

            element.textContent = prefix + display + suffix;

            if (progress < 1) {
                requestAnimationFrame(update);
            } else {
                element.classList.remove('counting');
            }
        }

        requestAnimationFrame(update);
    }

    // ============================================================
    // ۳. Load User Info
    // ============================================================

    async function loadUserInfo() {
        if (!window.api?.getUserInfo) return;

        try {
            const data = await window.api.getUserInfo();
            if (data && data.success) {
                const nameEl = document.getElementById('userName');
                if (nameEl) {
                    nameEl.textContent = data.data?.username || 'کاربر';
                }
            }
        } catch (err) {
            console.warn('⚠️ User info error:', err.message);
        }
    }

    // ============================================================
    // ۴. Load Market Data
    // ============================================================

    async function loadMarketData() {
        const tasks = [];

        // ===== BTC =====
        tasks.push((async () => {
            try {
                const btc = await window.api.getCoinPrice('bitcoin');
                if (btc && btc.success && btc.data) {
                    const priceEl = document.getElementById('btcPrice');
                    const changeEl = document.getElementById('btcChange');

                    if (priceEl && btc.data.price) {
                        animateCountUp(priceEl, btc.data.price, {
                            duration: 1800,
                            decimals: 2,
                            prefix: '$',
                        });
                    }

                    if (changeEl && btc.data.change_24h !== undefined) {
                        const change = btc.data.change_24h;
                        changeEl.textContent = formatPercent(change);
                        changeEl.className = 'stat-change ' +
                            (change >= 0 ? 'up' : 'down');
                    }
                }
            } catch (e) {
                console.warn('BTC error:', e.message);
            }
        })());

        // ===== ETH =====
        tasks.push((async () => {
            try {
                const eth = await window.api.getCoinPrice('ethereum');
                if (eth && eth.success && eth.data) {
                    const priceEl = document.getElementById('ethPrice');
                    const changeEl = document.getElementById('ethChange');

                    if (priceEl && eth.data.price) {
                        animateCountUp(priceEl, eth.data.price, {
                            duration: 1800,
                            decimals: 2,
                            prefix: '$',
                        });
                    }

                    if (changeEl && eth.data.change_24h !== undefined) {
                        const change = eth.data.change_24h;
                        changeEl.textContent = formatPercent(change);
                        changeEl.className = 'stat-change ' +
                            (change >= 0 ? 'up' : 'down');
                    }
                }
            } catch (e) {
                console.warn('ETH error:', e.message);
            }
        })());

        // ===== Fear & Greed =====
        tasks.push((async () => {
            try {
                const fg = await window.api.getFearGreed();
                if (fg && fg.success && fg.data) {
                    const valEl = document.getElementById('fearGreedValue');
                    const labelEl = document.getElementById('fearGreedLabel');

                    if (valEl && fg.data.value) {
                        animateCountUp(valEl, fg.data.value, {
                            duration: 1500,
                            decimals: 0,
                            useComma: false,
                        });
                    }

                    if (labelEl) {
                        labelEl.textContent = fg.data.classification || '—';
                        const cls = fg.data.value <= 45 ? 'down' :
                            fg.data.value >= 55 ? 'up' : 'neutral';
                        labelEl.className = 'stat-change ' + cls;
                    }
                }
            } catch (e) {
                console.warn('FG error:', e.message);
            }
        })());

        // ===== Dominance =====
        tasks.push((async () => {
            try {
                const dom = await window.api.getBTCDominance();
                if (dom && dom.success && dom.data) {
                    const valEl = document.getElementById('btcDominance');
                    if (valEl && dom.data.value) {
                        animateCountUp(valEl, dom.data.value, {
                            duration: 1500,
                            decimals: 1,
                            suffix: '%',
                            useComma: false,
                        });
                    }
                }
            } catch (e) {
                console.warn('Dominance error:', e.message);
            }
        })());

        // ===== Predictions =====
        tasks.push((async () => {
            try {
                const pred = await window.api.getPredictionHistory(100);
                if (pred && pred.success && pred.data) {
                    const predictions = pred.data;
                    const buyCount = predictions.filter(p => p.signal_type === 'BUY').length;
                    const sellCount = predictions.filter(p => p.signal_type === 'SELL').length;

                    const buyEl = document.getElementById('buySignals');
                    const sellEl = document.getElementById('sellSignals');

                    if (buyEl) {
                        animateCountUp(buyEl, buyCount, {
                            duration: 1500,
                            useComma: false,
                        });
                    }
                    if (sellEl) {
                        animateCountUp(sellEl, sellCount, {
                            duration: 1500,
                            useComma: false,
                        });
                    }
                }
            } catch (e) {
                console.warn('Predictions error:', e.message);
            }
        })());

        // ===== Model Status =====
        tasks.push((async () => {
            try {
                const model = await window.api.getModelStatus();
                if (model && model.success && model.data) {
                    const el = document.getElementById('modelStatus');
                    if (el) {
                        el.textContent = model.data.loaded ? '✅ فعال' : '📦 دمو';
                    }
                }
            } catch (e) {
                console.warn('Model status error:', e.message);
            }
        })());

        // ===== System Status =====
        tasks.push((async () => {
            try {
                const metrics = await window.api.getMetrics();
                const dot = document.getElementById('statusDot');
                const text = document.getElementById('statusText');

                if (dot && text && metrics?.success) {
                    const apiStatus = metrics.data?.metrics?.api_status?.value || 'ok';
                    dot.className = 'status-indicator';

                    if (apiStatus === 'ok' || apiStatus === 'healthy') {
                        dot.classList.add('online');
                        text.textContent = 'سیستم پایدار';
                    } else if (apiStatus === 'degraded') {
                        dot.classList.add('warning');
                        text.textContent = 'عملکرد کاهش یافته';
                    } else {
                        dot.classList.add('online');
                        text.textContent = 'متصل';
                    }
                }
            } catch (e) {
                console.warn('Metrics error:', e.message);
            }
        })());

        await Promise.allSettled(tasks);
        console.log('✅ Market data loaded');
    }

    // ============================================================
    // ۵. Load Activities
    // ============================================================

    async function loadActivities() {
        const container = document.getElementById('activityList');
        if (!container) return;

        try {
            const [alertsRes, historyRes] = await Promise.allSettled([
                window.api.getAlerts({ limit: 8, resolved: false }),
                window.api.getModelHistory(5),
            ]);

            const items = [];

            // ===== Alerts =====
            if (alertsRes.status === 'fulfilled' &&
                alertsRes.value?.success &&
                alertsRes.value.data) {
                alertsRes.value.data.forEach(a => {
                    const levelMap = {
                        'CRITICAL': { icon: '🚨', cls: 'alert' },
                        'WARNING': { icon: '⚠️', cls: 'warning' },
                        'INFO': { icon: 'ℹ️', cls: 'info' },
                    };
                    const info = levelMap[a.level] || levelMap.INFO;

                    items.push({
                        icon: info.icon,
                        cls: info.cls,
                        text: a.message || 'رویداد جدید',
                        time: new Date(a.timestamp),
                    });
                });
            }

            // ===== Model History =====
            if (historyRes.status === 'fulfilled' &&
                historyRes.value?.success &&
                historyRes.value.data) {
                historyRes.value.data.slice(0, 3).forEach(h => {
                    const acc = ((h.accuracy || 0) * 100).toFixed(1);
                    items.push({
                        icon: '🧠',
                        cls: 'model',
                        text: `مدل <span class="highlight">${h.version || 'v1'}</span> با دقت ${acc}%`,
                        time: new Date(h.training_date || h.created_at || Date.now()),
                    });
                });
            }

            // مرتب‌سازی
            items.sort((a, b) => b.time - a.time);
            const display = items.slice(0, 10);

            // ===== Badge =====
            const badge = document.getElementById('alertBadge');
            if (badge && alertsRes.status === 'fulfilled' && alertsRes.value?.data) {
                const count = alertsRes.value.data.length;
                badge.textContent = count;
                badge.style.display = count > 0 ? 'inline-flex' : 'none';
            }

            // ===== Render =====
            if (display.length === 0) {
                container.innerHTML = `
                    <div class="empty-state">
                        <span class="empty-icon">📭</span>
                        <div class="empty-title">هیچ فعالیتی ثبت نشده</div>
                        <div class="empty-message">با تحلیل و آموزش مدل، فعالیت‌ها اینجا نمایش داده می‌شوند</div>
                    </div>
                `;
                return;
            }

            container.innerHTML = display.map((item, i) => `
                <div class="activity-item" style="animation-delay:${i * 0.04}s;">
                    <div class="a-icon ${item.cls}">${item.icon}</div>
                    <div class="a-text">${item.text}</div>
                    <div class="a-time">${formatTimeAgo(item.time) || '—'}</div>
                </div>
            `).join('');

        } catch (err) {
            console.error('❌ Activities error:', err);
            container.innerHTML = `
                <div class="empty-state error">
                    <span class="empty-icon">⚠️</span>
                    <div class="empty-title">خطا در بارگذاری</div>
                    <div class="empty-message">لطفاً صفحه را بروزرسانی کنید</div>
                </div>
            `;
        }
    }

    // ============================================================
    // ۶. Auto Update
    // ============================================================

    function startAutoUpdate() {
        if (autoUpdateInterval) clearInterval(autoUpdateInterval);

        autoUpdateInterval = setInterval(async () => {
            try {
                await loadMarketData();
                await loadActivities();
            } catch (e) {
                // silent
            }
        }, 30000);
    }

    // ============================================================
    // ۷. Refresh
    // ============================================================

    async function refreshDashboard() {
        console.log('🔄 Refreshing dashboard...');

        if (window.loadingSystem?.show) {
            window.loadingSystem.show({
                messages: ['بروزرسانی...', 'دریافت اطلاعات جدید|لطفاً صبر کنید'],
                duration: 2000,
            });
        }

        try {
            await Promise.allSettled([
                loadUserInfo(),
                loadMarketData(),
                loadActivities(),
            ]);

            if (typeof showToast === 'function') {
                showToast('✅ بروزرسانی شد', 'success');
            }
        } catch (err) {
            console.error('Refresh error:', err);
            if (typeof showToast === 'function') {
                showToast('❌ خطا در بروزرسانی', 'error');
            }
        } finally {
            if (window.loadingSystem?.hide) {
                window.loadingSystem.hide();
            }
        }
    }

    // ============================================================
    // ۸. Init
    // ============================================================

    async function init() {
        if (isReady) return;
        isReady = true;

        console.log('🚀 Dashboard initializing...');

        // ۱. ذرات شناور
        initParticles();

        // ۲. لود داده‌ها
        await Promise.allSettled([
            loadUserInfo(),
            loadMarketData(),
            loadActivities(),
        ]);

        // ۳. auto-update
        startAutoUpdate();

        console.log('✅ Dashboard ready');
    }

    // ============================================================
    // Expose
    // ============================================================

    window.refreshDashboard = refreshDashboard;
    window.loadMarketData = loadMarketData;
    window.loadActivities = loadActivities;

    // ============================================================
    // Start
    // ============================================================

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    // Cleanup
    window.addEventListener('beforeunload', () => {
        if (autoUpdateInterval) {
            clearInterval(autoUpdateInterval);
            autoUpdateInterval = null;
        }
    });

    console.log('✅ Dashboard script loaded');
})();
