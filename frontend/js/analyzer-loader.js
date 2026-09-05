// ============================================================
// analyzer-loader.js - بارگذاری پویای تب‌های تحلیلگر
// ============================================================

const ANALYZER_TABS = {
    predict: '/analyzer_tabs/predict.html',
    chart: '/analyzer_tabs/chart.html',
    indicators: '/analyzer_tabs/indicators.html',
    history: '/analyzer_tabs/history.html',
};

let tabCache = {};
let currentTab = 'predict';
let refreshInterval = null;

// ============================================================
// بارگذاری تب
// ============================================================
function loadAnalyzerTab(tabName) {
    const container = document.getElementById('analyzerTabContent');
    currentTab = tabName;
    
    // اگر قبلاً بارگذاری شده
    if (tabCache[tabName]) {
        container.innerHTML = tabCache[tabName];
        executeTabScripts(container);
        updateTabBadge(tabName);
        return;
    }
    
    // نمایش لودینگ
    container.innerHTML = `
        <div class="loading-container">
            <div class="loading-spinner"></div>
            <p class="loading-text">در حال بارگذاری ${getTabLabel(tabName)}...</p>
        </div>
    `;
    
    const url = ANALYZER_TABS[tabName];
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
            updateTabBadge(tabName);
            
            // بروزرسانی URL
            history.replaceState(null, '', `?tab=${tabName}`);
        })
        .catch(err => {
            console.error(`❌ Failed to load tab "${tabName}":`, err);
            container.innerHTML = `
                <div class="error-msg">
                    <span class="icon">⚠️</span>
                    <p>خطا در بارگذاری تب</p>
                    <p style="font-size:0.7rem;color:var(--text-muted);margin-top:4px;">${err.message}</p>
                    <button onclick="loadAnalyzerTab('${tabName}')" style="margin-top:12px;padding:6px 16px;background:var(--accent-cyan);color:#000;border:none;border-radius:4px;cursor:pointer;">
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
        setTimeout(initFn, 150);
    }
}

// ============================================================
// بروزرسانی Badge تب (برای هشدارها)
// ============================================================
function updateTabBadge(tabName) {
    // می‌تواند برای نمایش تعداد هشدارها یا پیش‌بینی‌های جدید استفاده شود
    const badge = document.querySelector(`#analyzerTabs .tab-btn[data-tab="${tabName}"] .badge`);
    if (badge) {
        // مثال: دریافت تعداد از API
        // api.getAlerts({ limit: 1 }).then(data => {
        //     badge.textContent = data.count || 0;
        // });
    }
}

// ============================================================
// دریافت نام تب
// ============================================================
function getTabLabel(tabName) {
    const labels = {
        predict: 'پیش‌بینی',
        chart: 'نمودار',
        indicators: 'شاخص‌ها',
        history: 'تاریخچه'
    };
    return labels[tabName] || tabName;
}

// ============================================================
// رفرش تب فعلی
// ============================================================
function refreshCurrentTab() {
    if (currentTab) {
        // پاک کردن کش برای رفرش کامل
        delete tabCache[currentTab];
        loadAnalyzerTab(currentTab);
    }
}

// ============================================================
// مقداردهی اولیه تب‌ها
// ============================================================
function initAnalyzerTabs() {
    const tabs = document.querySelectorAll('#analyzerTabs .tab-btn');
    
    tabs.forEach(btn => {
        btn.addEventListener('click', function() {
            // بروزرسانی دکمه‌ها
            tabs.forEach(b => b.classList.remove('active'));
            this.classList.add('active');
            
            // بارگذاری تب
            const tabName = this.dataset.tab;
            loadAnalyzerTab(tabName);
        });
    });
    
    // بارگذاری تب از URL
    const params = new URLSearchParams(window.location.search);
    const tabFromUrl = params.get('tab');
    const defaultTab = tabFromUrl && ANALYZER_TABS[tabFromUrl] ? tabFromUrl : 'predict';
    
    // فعال‌سازی تب مربوطه
    const targetBtn = document.querySelector(`#analyzerTabs .tab-btn[data-tab="${defaultTab}"]`);
    if (targetBtn) {
        tabs.forEach(b => b.classList.remove('active'));
        targetBtn.classList.add('active');
    }
    
    loadAnalyzerTab(defaultTab);
    
    // بروزرسانی خودکار هر ۳۰ ثانیه (برای قیمت‌ها)
    if (refreshInterval) {
        clearInterval(refreshInterval);
    }
    refreshInterval = setInterval(() => {
        // فقط اگر تب predict فعال باشد
        if (currentTab === 'predict') {
            const container = document.getElementById('analyzerTabContent');
            const initFn = window['init_predict'];
            if (typeof initFn === 'function') {
                // بروزرسانی قیمت‌ها بدون رفرش کامل
                const wsUpdateFn = window['updatePricesFromWebSocket'];
                if (typeof wsUpdateFn === 'function') {
                    wsUpdateFn();
                }
            }
        }
    }, 10000);
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
    console.log('🚀 Analyzer page initializing...');
    loadNav();
    initAnalyzerTabs();
    
    // بروزرسانی تایم‌استمپ
    document.getElementById('pageTimestamp').textContent = 
        new Date().toLocaleTimeString('fa-IR');
    setInterval(() => {
        document.getElementById('pageTimestamp').textContent = 
            new Date().toLocaleTimeString('fa-IR');
    }, 30000);
    
    console.log('🚀 Analyzer page ready');
});

console.log('✅ Analyzer loader loaded');
