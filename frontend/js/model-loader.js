// ============================================================
// model-loader.js - بارگذاری پویای تب‌های مدل
// نسخه ۲.۰ - رفع باگ‌ها + loading-overlay + cleanup
// ============================================================

// ============================================================
// ۱. تنظیمات
// ============================================================

const MODEL_TABS = {
    dashboard: '/model_tabs/dashboard.html',
    info: '/model_tabs/info.html',
    training: '/model_tabs/training.html',
    schedule: '/model_tabs/schedule.html',
    history: '/model_tabs/history.html',
    features: '/model_tabs/features.html',
    tools: '/model_tabs/tools.html',
};

const MODEL_TAB_LABELS = {
    dashboard: 'داشبورد',
    info: 'اطلاعات مدل',
    training: 'آموزش',
    schedule: 'زمان‌بندی',
    history: 'تاریخچه',
    features: 'اهمیت ویژگی‌ها',
    tools: 'ابزارها',
};

let tabCache = {};
let currentTab = null;
let currentTabInitTimer = null;
let clockInterval = null;
let statusInterval = null;
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

async function loadModelTab(tabName) {
    // جلوگیری از load تکراری
    if (tabName === currentTab && tabCache[tabName]) {
        return;
    }
    
    // پاک کردن timer قبلی
    if (currentTabInitTimer) {
        clearTimeout(currentTabInitTimer);
        currentTabInitTimer = null;
    }
    
    // اجرای cleanup تب قبلی
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
    
    // ثبت تب جدید
    currentTab = tabName;
    
    const container = document.getElementById('modelTabContent');
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
        <div class="model-empty">
            <span class="empty-icon">⏳</span>
            <div class="empty-title">در حال بارگذاری ${MODEL_TAB_LABELS[tabName] || tabName}...</div>
            <div class="empty-message">لطفاً کمی صبر کنید</div>
        </div>
    `;
    
    const url = MODEL_TABS[tabName];
    if (!url) {
        container.innerHTML = `
            <div class="model-empty error">
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
        
        // بروزرسانی URL
        history.replaceState(null, '', `?tab=${tabName}`);
        
        // ذخیره تب فعال
        localStorage.setItem('modelActiveTab', tabName);
        
    } catch (err) {
        console.error(`❌ Failed to load tab "${tabName}":`, err);
        container.innerHTML = `
            <div class="model-empty error">
                <span class="empty-icon">⚠️</span>
                <div class="empty-title">خطا در بارگذاری تب</div>
                <div class="empty-message">${err.message}</div>
                <button class="empty-action" onclick="loadModelTab('${tabName}')">
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
    
    // اجرای init با بررسی تب فعلی
    const initFn = window[`init_${tabName}`];
    if (typeof initFn === 'function') {
        currentTabInitTimer = setTimeout(() => {
            // فقط اگه تب هنوز همون تب باشه
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
    
    // cleanup تب فعلی
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
    loadModelTab(tabToReload);
    
    // نمایش toast (اگه موجود باشه)
    if (typeof showToast === 'function') {
        showToast('🔄 بروزرسانی...', 'info');
    }
}

// ============================================================
// ۶. مقداردهی اولیه تب‌ها
// ============================================================

function initModelTabs() {
    const tabs = document.querySelectorAll('#modelTabs .model-tab-btn');
    
    tabs.forEach(btn => {
        btn.addEventListener('click', function() {
            const tabName = this.dataset.tab;
            if (tabName === currentTab) return;
            
            // بروزرسانی دکمه‌ها
            tabs.forEach(b => b.classList.remove('active'));
            this.classList.add('active');
            
            // بارگذاری تب
            loadModelTab(tabName);
        });
    });
    
    // ===== تب از URL یا localStorage =====
    const params = new URLSearchParams(window.location.search);
    const tabFromUrl = params.get('tab');
    const tabFromStorage = localStorage.getItem('modelActiveTab');
    
    let defaultTab = 'dashboard';
    if (tabFromUrl && MODEL_TABS[tabFromUrl]) {
        defaultTab = tabFromUrl;
    } else if (tabFromStorage && MODEL_TABS[tabFromStorage]) {
        defaultTab = tabFromStorage;
    }
    
    // فعال‌سازی دکمه تب
    const targetBtn = document.querySelector(`#modelTabs .model-tab-btn[data-tab="${defaultTab}"]`);
    if (targetBtn) {
        tabs.forEach(b => b.classList.remove('active'));
        targetBtn.classList.add('active');
    }
    
    // ===== بارگذاری تب =====
    loadModelTab(defaultTab);
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
// ۸. Model Status Badge
// ============================================================

async function updateModelBadge() {
    try {
        const data = await api.getModelStatus();
        const badge = document.getElementById('modelStatusBadge');
        if (!badge) return;
        
        if (data && data.success && data.data) {
            const loaded = data.data.loaded || false;
            const isTraining = data.data.is_training || false;
            const statusText = badge.querySelector('.status-text');
            
            if (isTraining) {
                badge.className = 'model-status-badge training';
                if (statusText) statusText.textContent = 'در حال آموزش';
            } else if (loaded) {
                badge.className = 'model-status-badge active';
                if (statusText) statusText.textContent = 'فعال';
            } else {
                badge.className = 'model-status-badge demo';
                if (statusText) statusText.textContent = 'دمو';
            }
        }
    } catch (err) {
        console.warn('Badge update error:', err.message);
    }
}

function startModelBadgeUpdate() {
    if (statusInterval) clearInterval(statusInterval);
    updateModelBadge();
    statusInterval = setInterval(updateModelBadge, 15000);
}

// ============================================================
// ۹. مقداردهی اولیه
// ============================================================

async function initializeModel() {
    if (isInitialized) return;
    isInitialized = true;
    
    console.log('🚀 Model page initializing...');
    
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
    
    // ===== ۴. شروع badge update =====
    startModelBadgeUpdate();
    
    // ===== ۵. init tabs =====
    initModelTabs();
    
    console.log('✅ Model page ready');
}

// ============================================================
// ۱۰. پاکسازی کلی
// ============================================================

function cleanupModel() {
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
    if (statusInterval) {
        clearInterval(statusInterval);
        statusInterval = null;
    }
    
    isInitialized = false;
    currentTab = null;
    tabCache = {};
    
    console.log('🧹 Model page cleaned up');
}

// ============================================================
// ۱۱. شروع
// ============================================================

document.addEventListener('DOMContentLoaded', initializeModel);

// ===== در دسترس قرار دادن برای onclick =====
window.loadModelTab = loadModelTab;
window.refreshCurrentTab = refreshCurrentTab;

// ===== cleanup هنگام بستن صفحه =====
window.addEventListener('beforeunload', cleanupModel);

console.log('✅ Model loader v2.0 loaded');
