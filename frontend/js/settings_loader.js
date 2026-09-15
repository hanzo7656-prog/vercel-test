// ============================================================
// settings_loader.js - بارگذاری پویای تب‌های تنظیمات
// نسخه ۱.۰ - الگو گرفته از model-loader.js
// ============================================================

// ============================================================
// ۱. تنظیمات
// ============================================================

const SETTINGS_TABS = {
    scheduler: '/settings_tabs/scheduler.html',
    theme: '/settings_tabs/theme.html',
    cache: '/settings_tabs/cache.html',
    notifications: '/settings_tabs/notifications.html',
    dashboard: '/settings_tabs/dashboard.html',
    account: '/settings_tabs/account.html',
    system: '/settings_tabs/system.html',
};

const SETTINGS_TAB_LABELS = {
    scheduler: 'همگام‌سازی',
    theme: 'ظاهر',
    cache: 'کش',
    notifications: 'اعلان‌ها',
    dashboard: 'داشبورد',
    account: 'حساب کاربری',
    system: 'سیستم',
};

let settingsTabCache = {};
let currentSettingsTab = null;
let currentTabInitTimer = null;
let clockInterval = null;
let isSettingsInitialized = false;

// ============================================================
// ۲. بارگذاری کامپوننت
// ============================================================

async function loadSettingsComponent(id, url) {
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

async function loadSettingsTab(tabName) {
    // جلوگیری از load تکراری
    if (tabName === currentSettingsTab && settingsTabCache[tabName]) {
        return;
    }
    
    // پاک کردن timer قبلی
    if (currentTabInitTimer) {
        clearTimeout(currentTabInitTimer);
        currentTabInitTimer = null;
    }
    
    // اجرای cleanup تب قبلی
    if (currentSettingsTab && currentSettingsTab !== tabName) {
        const cleanupFn = window[`cleanup_settings_${currentSettingsTab}`];
        if (typeof cleanupFn === 'function') {
            try {
                cleanupFn();
                console.log(`🧹 Cleaned up: ${currentSettingsTab}`);
            } catch (err) {
                console.warn(`⚠️ Cleanup error for ${currentSettingsTab}:`, err);
            }
        }
    }
    
    // ثبت تب جدید
    currentSettingsTab = tabName;
    
    const container = document.getElementById('settingsTabContent');
    if (!container) {
        console.error('❌ Tab content container not found');
        return;
    }
    
    // ===== اگر در کش هست =====
    if (settingsTabCache[tabName]) {
        container.innerHTML = settingsTabCache[tabName];
        executeTabScripts(container, tabName);
        return;
    }
    
    // ===== نمایش اسکلتون =====
    container.innerHTML = `
        <div class="settings-tab-content">
            <div class="settings-group">
                <div class="settings-skeleton skeleton-md"></div>
                <div class="settings-skeleton skeleton-sm" style="width: 60%;"></div>
                <div class="settings-skeleton skeleton-lg"></div>
            </div>
            <div class="settings-group">
                <div class="settings-skeleton skeleton-sm" style="width: 40%;"></div>
                <div class="settings-skeleton skeleton-lg"></div>
            </div>
        </div>
    `;
    
    const url = SETTINGS_TABS[tabName];
    if (!url) {
        container.innerHTML = `
            <div class="settings-empty">
                <p>❌ تب "${tabName}" وجود ندارد</p>
            </div>
        `;
        return;
    }
    
    // ===== fetch =====
    try {
        const res = await fetch(url);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        
        const html = await res.text();
        settingsTabCache[tabName] = html;
        container.innerHTML = html;
        executeTabScripts(container, tabName);
        
        // بروزرسانی URL
        history.replaceState(null, '', `?tab=${tabName}`);
        
        // ذخیره تب فعال
        localStorage.setItem('settingsActiveTab', tabName);
        
    } catch (err) {
        console.error(`❌ Failed to load tab "${tabName}":`, err);
        container.innerHTML = `
            <div class="settings-empty">
                <p style="color: var(--accent-red);">⚠️ خطا در بارگذاری تب</p>
                <p style="font-size: 0.8rem; color: var(--text-muted);">${err.message}</p>
                <button class="settings-btn settings-btn-primary" onclick="loadSettingsTab('${tabName}')" style="margin-top: 16px;">
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
    const initFn = window[`init_settings_${tabName}`];
    if (typeof initFn === 'function') {
        currentTabInitTimer = setTimeout(() => {
            if (currentSettingsTab === tabName) {
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
    if (!currentSettingsTab) return;
    
    // پاک کردن کش برای رفرش کامل
    delete settingsTabCache[currentSettingsTab];
    
    // cleanup تب فعلی
    const cleanupFn = window[`cleanup_settings_${currentSettingsTab}`];
    if (typeof cleanupFn === 'function') {
        try {
            cleanupFn();
        } catch (err) {
            console.warn(`⚠️ Cleanup error:`, err);
        }
    }
    
    // ذخیره نام تب قبل از reset
    const tabToReload = currentSettingsTab;
    currentSettingsTab = null;
    
    // load مجدد
    loadSettingsTab(tabToReload);
    
    // نمایش toast
    if (typeof showToast === 'function') {
        showToast('🔄 بروزرسانی...', 'info', 1500);
    }
}

// ============================================================
// ۶. مقداردهی اولیه تب‌ها
// ============================================================

function initSettingsTabs() {
    const tabs = document.querySelectorAll('#settingsTabs .settings-tab-btn');
    
    tabs.forEach(btn => {
        btn.addEventListener('click', function() {
            const tabName = this.dataset.tab;
            if (tabName === currentSettingsTab) return;
            
            // بروزرسانی دکمه‌ها
            tabs.forEach(b => b.classList.remove('active'));
            this.classList.add('active');
            
            // بارگذاری تب
            loadSettingsTab(tabName);
        });
    });
    
    // ===== تب از URL یا localStorage =====
    const params = new URLSearchParams(window.location.search);
    const tabFromUrl = params.get('tab');
    const tabFromStorage = localStorage.getItem('settingsActiveTab');
    
    let defaultTab = 'scheduler';
    if (tabFromUrl && SETTINGS_TABS[tabFromUrl]) {
        defaultTab = tabFromUrl;
    } else if (tabFromStorage && SETTINGS_TABS[tabFromStorage]) {
        defaultTab = tabFromStorage;
    }
    
    // فعال‌سازی دکمه تب
    const targetBtn = document.querySelector(`#settingsTabs .settings-tab-btn[data-tab="${defaultTab}"]`);
    if (targetBtn) {
        tabs.forEach(b => b.classList.remove('active'));
        targetBtn.classList.add('active');
    }
    
    // ===== بارگذاری تب =====
    loadSettingsTab(defaultTab);
}

// ============================================================
// ۷. Clock (Timestamp)
// ============================================================

function updateSettingsClock() {
    const el = document.getElementById('pageTimestamp');
    if (!el) return;
    
    const now = new Date();
    el.textContent = now.toLocaleTimeString('fa-IR', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
    });
}

function startSettingsClock() {
    if (clockInterval) clearInterval(clockInterval);
    updateSettingsClock();
    clockInterval = setInterval(updateSettingsClock, 1000);
}

// ============================================================
// ۸. مقداردهی اولیه صفحه
// ============================================================

async function initializeSettings() {
    if (isSettingsInitialized) return;
    isSettingsInitialized = true;
    
    console.log('🚀 Settings page initializing...');
    
    // ===== ۱. لود loading-overlay =====
    const overlayLoaded = await loadSettingsComponent(
        'loadingOverlayContainer',
        '/components/loading-overlay.html'
    );
    
    if (!overlayLoaded) {
        console.warn('⚠️ Loading overlay not loaded');
    }
    
    // ===== ۲. لود navigation =====
    const navLoaded = await loadSettingsComponent('navContainer', '/nav.html');
    if (!navLoaded) {
        console.warn('⚠️ Navigation not loaded');
    }
    
    // ===== ۳. شروع clock =====
    startSettingsClock();
    
    // ===== ۴. init tabs =====
    initSettingsTabs();
    
    console.log('✅ Settings page ready');
}

// ============================================================
// ۹. پاکسازی کلی
// ============================================================

function cleanupSettings() {
    // cleanup تب فعلی
    if (currentSettingsTab) {
        const cleanupFn = window[`cleanup_settings_${currentSettingsTab}`];
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
    
    isSettingsInitialized = false;
    currentSettingsTab = null;
    settingsTabCache = {};
    
    console.log('🧹 Settings page cleaned up');
}

// ============================================================
// ۱۰. شروع
// ============================================================

document.addEventListener('DOMContentLoaded', initializeSettings);

// ===== در دسترس قرار دادن برای onclick =====
window.loadSettingsTab = loadSettingsTab;
window.refreshCurrentTab = refreshCurrentTab;

// ===== cleanup هنگام بستن صفحه =====
window.addEventListener('beforeunload', cleanupSettings);

console.log('✅ Settings loader v1.0 loaded');
