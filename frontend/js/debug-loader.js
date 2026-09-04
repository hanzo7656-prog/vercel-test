// ============================================================
// debug-loader.js - بارگذاری پویای تب‌های دیباگ
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

let loadedTabs = {};
let currentTab = 'status';
let tabCache = {};

// ============================================================
// بارگذاری تب
// ============================================================
function loadTab(tabName) {
    const container = document.getElementById('tabContent');
    currentTab = tabName;
    
    // اگر قبلاً بارگذاری شده
    if (tabCache[tabName]) {
        container.innerHTML = tabCache[tabName];
        // اجرای اسکریپت‌های داخل تب
        executeTabScripts(container);
        return;
    }
    
    // نمایش لودینگ
    container.innerHTML = `
        <div class="loading-container">
            <div class="loading-spinner"></div>
            <p class="loading-text">در حال بارگذاری ${getTabLabel(tabName)}...</p>
        </div>
    `;
    
    const url = DEBUG_TABS[tabName];
    if (!url) {
        container.innerHTML = `
            <div class="error-msg">
                <span class="icon">❌</span>
                <p>تب "${tabName}" یافت نشد</p>
            </div>
        `;
        return;
    }
    
    fetch(url)
        .then(res => {
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            return res.text();
        })
        .then(html => {
            tabCache[tabName] = html;
            container.innerHTML = html;
            executeTabScripts(container);
            
            // بروزرسانی Badge (برای کش)
            if (tabName === 'cache') {
                document.getElementById('cacheBadge').style.display = 'none';
            }
        })
        .catch(err => {
            console.error(`❌ Failed to load tab "${tabName}":`, err);
            container.innerHTML = `
                <div class="error-msg">
                    <span class="icon">⚠️</span>
                    <p>خطا در بارگذاری تب</p>
                    <p style="font-size:0.7rem;color:var(--text-muted);margin-top:4px;">${err.message}</p>
                    <button onclick="loadTab('${tabName}')" style="margin-top:12px;padding:6px 16px;background:var(--accent-cyan);color:#000;border:none;border-radius:4px;cursor:pointer;">
                        🔄 تلاش مجدد
                    </button>
                </div>
            `;
        });
}

// ============================================================
// اجرای اسکریپت‌های داخل تب
// ============================================================
function executeTabScripts(container) {
    const scripts = container.querySelectorAll('script');
    scripts.forEach(oldScript => {
        const newScript = document.createElement('script');
        newScript.textContent = oldScript.textContent;
        oldScript.parentNode.replaceChild(newScript, oldScript);
    });
    
    // فراخوانی تابع init مخصوص تب (اگر وجود داشته باشد)
    const initFn = window[`init_${currentTab}`];
    if (typeof initFn === 'function') {
        setTimeout(initFn, 100);
    }
}

// ============================================================
// دریافت نام تب
// ============================================================
function getTabLabel(tabName) {
    const labels = {
        status: 'وضعیت',
        logs: 'لاگ‌ها',
        cli: 'کنسول',
        system: 'سیستم',
        cache: 'کش',
        processes: 'پردازش‌ها',
        healing: 'خودترمیمی'
    };
    return labels[tabName] || tabName;
}

// ============================================================
// مقداردهی اولیه تب‌ها
// ============================================================
function initTabs() {
    const tabs = document.querySelectorAll('#debugTabs .tab-btn');
    
    tabs.forEach(btn => {
        btn.addEventListener('click', function() {
            // بروزرسانی دکمه‌ها
            tabs.forEach(b => b.classList.remove('active'));
            this.classList.add('active');
            
            // بارگذاری تب
            const tabName = this.dataset.tab;
            loadTab(tabName);
        });
    });
    
    // بارگذاری تب پیش‌فرض
    const activeTab = document.querySelector('#debugTabs .tab-btn.active');
    if (activeTab) {
        loadTab(activeTab.dataset.tab);
    } else {
        loadTab('status');
    }
}

// ============================================================
// بروزرسانی آمار (بالای صفحه)
// ============================================================
async function updateStats() {
    try {
        const res = await fetch('/api/app/stats', { credentials: 'include' });
        const data = await res.json();
        if (data.success && data.data) {
            const stats = data.data;
            const RAM_LIMIT_MB = 512;
            
            // CPU
            const cpuEl = document.getElementById('debugCpu');
            if (cpuEl) {
                cpuEl.textContent = stats.cpu.percent + '%';
                const pct = stats.cpu.percent;
                cpuEl.className = 'stat-value ' + (pct > 80 ? 'red' : pct > 60 ? 'orange' : 'green');
            }
            
            // RAM
            const ramEl = document.getElementById('debugRam');
            const ramBar = document.getElementById('debugRamBar');
            const ramUsed = stats.ram.used_mb;
            const ramPercent = Math.min((ramUsed / RAM_LIMIT_MB) * 100, 100);
            if (ramEl) {
                ramEl.textContent = ramUsed.toFixed(1) + ' MB (' + ramPercent.toFixed(1) + '%)';
                const pct = ramPercent;
                ramEl.className = 'stat-value ' + (pct > 80 ? 'red' : pct > 60 ? 'orange' : 'green');
            }
            if (ramBar) {
                ramBar.style.width = ramPercent + '%';
                ramBar.style.background = ramPercent > 80 ? 'var(--accent-red)' :
                                          ramPercent > 60 ? 'var(--accent-orange)' :
                                          'var(--accent-green)';
            }
            
            // Uptime
            const uptimeEl = document.getElementById('debugUptime');
            if (uptimeEl && stats.uptime) {
                uptimeEl.textContent = stats.uptime.app_formatted || '—';
            }
            
            // Collections
            const metrics = await api.getMetrics();
            if (metrics.success && metrics.data) {
                const collections = metrics.data.stats?.collections || 0;
                document.getElementById('debugCollections').textContent = collections;
            }
        }
    } catch (err) {
        console.error('Failed to update stats:', err);
    }
}

// ============================================================
// بارگذاری نویگیشن
// ============================================================
async function loadNav() {
    const container = document.getElementById('navContainer');
    if (!container) return;
    try {
        const res = await fetch('/nav.html');
        if (!res.ok) throw new Error('nav.html not found');
        const html = await res.text();
        container.innerHTML = html;
        const scripts = container.querySelectorAll('script');
        scripts.forEach(old => {
            const ns = document.createElement('script');
            ns.textContent = old.textContent;
            old.parentNode.replaceChild(ns, old);
        });
    } catch (err) {
        console.error('❌ Nav error:', err);
    }
}

// ============================================================
// مقداردهی اولیه
// ============================================================
document.addEventListener('DOMContentLoaded', function() {
    console.log('🚀 Debug page initializing...');
    
    loadNav();
    initTabs();
    updateStats();
    
    // بروزرسانی آمار هر ۱ ثانیه
    setInterval(updateStats, 1000);
    
    console.log('🚀 Debug page ready');
});
