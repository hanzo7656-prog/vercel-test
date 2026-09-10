// ============================================================
// analyzer-loader.js - بارگذاری پویای تب‌های تحلیلگر
// نسخه ۲.۰ - رفع باگ‌ها + loading-overlay + cleanup
// ============================================================

// ============================================================
// ۱. تنظیمات
// ============================================================

const ANALYZER_TABS = {
    predict: '/analyzer_tabs/predict.html',
    indicators: '/analyzer_tabs/indicators.html',
    history: '/analyzer_tabs/history.html',
};

const TAB_LABELS = {
    predict: 'پیش‌بینی',
    indicators: 'شاخص‌ها',
    history: 'تاریخچه',
};

let tabCache = {};
let currentTab = null;
let currentTabInitTimer = null;
let clockInterval = null;
let isInitialized = false;

// ============================================================
// ۲. بارگذاری کامپوننت
// ============================================================

async function loadComponent(id, url) {
    const container = document.getElementById(id);
    if (!container) {
        console.warn(`⚠️ Container #${id} not found`);
        return false;
    }
    
    try {
        const res = await fetch(url);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const html = await res.text();
        container.innerHTML = html;
        
        // اجرای اسکریپت‌های داخل کامپوننت
        const scripts = container.querySelectorAll('script');
        scripts.forEach(old => {
            const ns = document.createElement('script');
            ns.textContent = old.textContent;
            old.parentNode.replaceChild(ns, old);
        });
        
        return true;
    } catch (err) {
        console.error(`❌ Failed to load ${url}:`, err);
        return false;
    }
}

// ============================================================
// ۳. بارگذاری تب
// ============================================================

async function loadAnalyzerTab(tabName) {
    // ✅ جلوگیری از load تکراری
    if (tabName === currentTab && tabCache[tabName]) {
        return;
    }
    
    // ✅ پاک کردن timer قبلی
    if (currentTabInitTimer) {
        clearTimeout(currentTabInitTimer);
        currentTabInitTimer = null;
    }
    
    // ✅ اجرای cleanup تب قبلی
    if (currentTab && currentTab !== tabName) {
        const cleanupFn = window[`cleanup_${currentTab}`];
        if (typeof cleanupFn === 'function') {
            try {
                cleanupFn();
                console.log(`🧹 Cleaned up: ${currentTab}`);
            } catch (err) {
                console.warn(`⚠️ Cleanup error for ${currentTab}:`, err);
            }
        }
    }
    
    // ✅ ثبت تب جدید
    const previousTab = currentTab;
    currentTab = tabName;
    
    const container = document.getElementById('analyzerTabContent');
    if (!container) {
        console.error('❌ Tab content container not found');
        return;
    }
    
    // ===== اگر در کش هست =====
    if (tabCache[tabName]) {
        container.innerHTML = tabCache[tabName];
        executeTabScripts(container, tabName);
        return;
    }
    
    // ===== نمایش لودینگ =====
    container.innerHTML = `
        <div class="analyzer-empty">
            <span class="empty-icon">⏳</span>
            <div class="empty-title">در حال بارگذاری ${TAB_LABELS[tabName] || tabName}...</div>
            <div class="empty-message">لطفاً کمی صبر کنید</div>
        </div>
    `;
    
    const url = ANALYZER_TABS[tabName];
    if (!url) {
        container.innerHTML = `
            <div class="analyzer-empty error">
                <span class="empty-icon">❌</span>
                <div class="empty-title">تب یافت نشد</div>
                <div class="empty-message">"${tabName}" وجود ندارد</div>
            </div>
        `;
        return;
    }
    
    // ===== fetch =====
    try {
        const res = await fetch(url);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        
        const html = await res.text();
        tabCache[tabName] = html;
        container.innerHTML = html;
        executeTabScripts(container, tabName);
        
        // ✅ بروزرسانی URL
        history.replaceState(null, '', `?tab=${tabName}`);
        
    } catch (err) {
        console.error(`❌ Failed to load tab "${tabName}":`, err);
        container.innerHTML = `
            <div class="analyzer-empty error">
                <span class="empty-icon">⚠️</span>
                <div class="empty-title">خطا در بارگذاری تب</div>
                <div class="empty-message">${err.message}</div>
                <button class="empty-action" onclick="loadAnalyzerTab('${tabName}')">
                    <i class="fas fa-sync-alt"></i>
                    تلاش مجدد
                </button>
            </div>
        `;
    }
}

// ============================================================
// ۴. اجرای اسکریپت‌های تب
// ============================================================

function executeTabScripts(container, tabName) {
    // اجرای اسکریپت‌های inline
    const scripts = container.querySelectorAll('script');
    scripts.forEach(oldScript => {
        const newScript = document.createElement('script');
        newScript.textContent = oldScript.textContent;
        oldScript.parentNode.replaceChild(newScript, oldScript);
    });
    
    // ✅ اجرای init با بررسی تب فعلی
    const initFn = window[`init_${tabName}`];
    if (typeof initFn === 'function') {
        currentTabInitTimer = setTimeout(() => {
            // ✅ فقط اگه تب هنوز همون تب باشه
            if (currentTab === tabName) {
                try {
                    initFn();
                    console.log(`✅ ${tabName} initialized`);
                } catch (err) {
                    console.error(`❌ Init error for ${tabName}:`, err);
                }
            }
        }, 100);
    }
}

// ============================================================
// ۵. رفرش تب فعلی
// ============================================================

function refreshCurrentTab() {
    if (!currentTab) return;
    
    // پاک کردن کش برای رفرش کامل
    delete tabCache[currentTab];
    
    // ✅ cleanup تب فعلی
    const cleanupFn = window[`cleanup_${currentTab}`];
    if (typeof cleanupFn === 'function') {
        try {
            cleanupFn();
        } catch (err) {
            console.warn(`⚠️ Cleanup error:`, err);
        }
    }
    
    // ذخیره نام تب قبل از reset
    const tabToReload = currentTab;
    currentTab = null;
    
    // load مجدد
    loadAnalyzerTab(tabToReload);
    
    // نمایش toast (اگه موجود باشه)
    if (typeof showToast === 'function') {
        showToast('🔄 بروزرسانی...', 'info');
    }
}

// ============================================================
// ۶. مقداردهی اولیه تب‌ها
// ============================================================

function initAnalyzerTabs() {
    const tabs = document.querySelectorAll('#analyzerTabs .analyzer-tab-btn');
    
    tabs.forEach(btn => {
        btn.addEventListener('click', function() {
            const tabName = this.dataset.tab;
            if (tabName === currentTab) return;
            
            // بروزرسانی دکمه‌ها
            tabs.forEach(b => b.classList.remove('active'));
            this.classList.add('active');
            
            // بارگذاری تب
            loadAnalyzerTab(tabName);
        });
    });
    
    // ===== تب از URL =====
    const params = new URLSearchParams(window.location.search);
    const tabFromUrl = params.get('tab');
    const defaultTab = (tabFromUrl && ANALYZER_TABS[tabFromUrl]) ? tabFromUrl : 'predict';
    
    // فعال‌سازی دکمه تب
    const targetBtn = document.querySelector(`#analyzerTabs .analyzer-tab-btn[data-tab="${defaultTab}"]`);
    if (targetBtn) {
        tabs.forEach(b => b.classList.remove('active'));
        targetBtn.classList.add('active');
    }
    
    // ===== بارگذاری تب =====
    loadAnalyzerTab(defaultTab);
}

// ============================================================
// ۷. Clock (Timestamp)
// ============================================================

function updateClock() {
    const el = document.getElementById('pageTimestamp');
    if (!el) return;
    
    const now = new Date();
    el.textContent = now.toLocaleTimeString('fa-IR', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
    });
}

function startClock() {
    if (clockInterval) clearInterval(clockInterval);
    updateClock();
    clockInterval = setInterval(updateClock, 1000);
}

// ============================================================
// ۸. Page Status Badge
// ============================================================

function updatePageStatus(status, text) {
    const badge = document.getElementById('pageStatusBadge');
    if (!badge) return;
    
    badge.className = 'analyzer-status-badge ' + status;
    const textEl = badge.querySelector('.status-text');
    if (textEl) textEl.textContent = text;
}

// ============================================================
// ۹. مقداردهی اولیه
// ============================================================

async function initializeAnalyzer() {
    if (isInitialized) return;
    isInitialized = true;
    
    console.log('🚀 Analyzer initializing...');
    
    // ===== ۱. لود loading-overlay =====
    const overlayLoaded = await loadComponent(
        'loadingOverlayContainer',
        '/components/loading-overlay.html'
    );
    
    if (!overlayLoaded) {
        console.warn('⚠️ Loading overlay not loaded');
    }
    
    // ===== ۲. لود navigation =====
    const navLoaded = await loadComponent('navContainer', '/nav.html');
    if (!navLoaded) {
        console.warn('⚠️ Navigation not loaded');
    }
    
    // ===== ۳. شروع clock =====
    startClock();
    
    // ===== ۴. init tabs =====
    initAnalyzerTabs();
    
    // ===== ۵. وضعیت اولیه =====
    updatePageStatus('online', 'آماده');
    
    console.log('✅ Analyzer ready');
}

// ============================================================
// ۱۰. پاکسازی کلی
// ============================================================

function cleanupAnalyzer() {
    // cleanup تب فعلی
    if (currentTab) {
        const cleanupFn = window[`cleanup_${currentTab}`];
        if (typeof cleanupFn === 'function') {
            try {
                cleanupFn();
            } catch (err) {
                console.warn('Cleanup error:', err);
            }
        }
    }
    
    // پاک کردن timerها
    if (currentTabInitTimer) {
        clearTimeout(currentTabInitTimer);
        currentTabInitTimer = null;
    }
    if (clockInterval) {
        clearInterval(clockInterval);
        clockInterval = null;
    }
    
    isInitialized = false;
    currentTab = null;
    tabCache = {};
    
    console.log('🧹 Analyzer cleaned up');
}

// ============================================================
// ۱۱. شروع
// ============================================================

document.addEventListener('DOMContentLoaded', initializeAnalyzer);

// ===== در دسترس قرار دادن برای onclick =====
window.loadAnalyzerTab = loadAnalyzerTab;
window.refreshCurrentTab = refreshCurrentTab;
window.updatePageStatus = updatePageStatus;

// ===== cleanup هنگام بستن صفحه =====
window.addEventListener('beforeunload', cleanupAnalyzer);

console.log('✅ Analyzer loader v2.0 loaded');
