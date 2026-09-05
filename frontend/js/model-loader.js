// ============================================================
// model-loader.js - بارگذاری پویای تب‌های مدل
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

let tabCache = {};
let currentTab = 'dashboard';

// ===== بارگذاری تب =====
function loadModelTab(tabName) {
    const container = document.getElementById('modelTabContent');
    currentTab = tabName;
    
    if (tabCache[tabName]) {
        container.innerHTML = tabCache[tabName];
        executeTabScripts(container);
        return;
    }
    
    container.innerHTML = `
        <div class="loading-container">
            <div class="loading-spinner"></div>
            <p class="loading-text">در حال بارگذاری ${getTabLabel(tabName)}...</p>
        </div>
    `;
    
    const url = MODEL_TABS[tabName];
    if (!url) {
        container.innerHTML = `<div class="error-msg"><span class="icon">❌</span><p>تب "${tabName}" یافت نشد</p></div>`;
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
        })
        .catch(err => {
            console.error(`Failed to load tab "${tabName}":`, err);
            container.innerHTML = `
                <div class="error-msg">
                    <span class="icon">⚠️</span>
                    <p>خطا در بارگذاری تب</p>
                    <button onclick="loadModelTab('${tabName}')">🔄 تلاش مجدد</button>
                </div>
            `;
        });
}

function executeTabScripts(container) {
    const scripts = container.querySelectorAll('script');
    scripts.forEach(oldScript => {
        const newScript = document.createElement('script');
        newScript.textContent = oldScript.textContent;
        oldScript.parentNode.replaceChild(newScript, oldScript);
    });
    
    const initFn = window[`init_${currentTab}`];
    if (typeof initFn === 'function') {
        setTimeout(initFn, 150);
    }
}

function getTabLabel(tabName) {
    const labels = {
        dashboard: 'داشبورد',
        info: 'اطلاعات مدل',
        training: 'آموزش',
        schedule: 'زمان‌بندی',
        history: 'تاریخچه',
        features: 'اهمیت ویژگی‌ها',
        tools: 'ابزارها'
    };
    return labels[tabName] || tabName;
}

// ===== مقداردهی اولیه تب‌ها =====
function initModelTabs() {
    const tabs = document.querySelectorAll('#modelTabs .tab-btn');
    
    tabs.forEach(btn => {
        btn.addEventListener('click', function() {
            tabs.forEach(b => b.classList.remove('active'));
            this.classList.add('active');
            const tabName = this.dataset.tab;
            loadModelTab(tabName);
            
            // بروزرسانی URL
            history.replaceState(null, '', `?tab=${tabName}`);
        });
    });
    
    // بارگذاری تب از URL
    const params = new URLSearchParams(window.location.search);
    const tabFromUrl = params.get('tab');
    const defaultTab = tabFromUrl && MODEL_TABS[tabFromUrl] ? tabFromUrl : 'dashboard';
    
    document.querySelector(`#modelTabs .tab-btn[data-tab="${defaultTab}"]`)?.classList.add('active');
    loadModelTab(defaultTab);
    
    // بارگذاری نویگیشن
    loadNav();
}

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

// ===== دریافت وضعیت مدل برای Badge =====
async function updateModelBadge() {
    try {
        const data = await api.getModelStatus();
        if (data.success && data.data) {
            const badge = document.getElementById('modelStatusBadge');
            const loaded = data.data.loaded || false;
            const isTraining = data.data.is_training || false;
            
            if (isTraining) {
                badge.textContent = '⏳ در حال آموزش';
                badge.className = 'badge badge-orange';
            } else if (loaded) {
                badge.textContent = '✅ فعال';
                badge.className = 'badge badge-green';
            } else {
                badge.textContent = '📦 دمو';
                badge.className = 'badge badge-orange';
            }
        }
    } catch (err) {
        console.error('Badge update error:', err);
    }
}

// ===== مقداردهی اولیه =====
document.addEventListener('DOMContentLoaded', function() {
    initModelTabs();
    updateModelBadge();
    setInterval(updateModelBadge, 15000);
});
