// js/database.js - منطق دیتابیس

const DB_TABS = {
    overview: '/components/tabs/db-overview.html',
    postgresql: '/components/tabs/db-postgresql.html',
    redis: '/components/tabs/db-redis.html',
    sqlite: '/components/tabs/db-sqlite.html',
    explorer: '/components/tabs/db-explorer.html',
    monitor: '/components/tabs/db-monitor.html'
};

let currentTab = 'overview';
const loadedTabs = new Set();

document.addEventListener('DOMContentLoaded', function() {
    // تب‌ها
    document.querySelectorAll('#dbTabs button').forEach(btn => {
        btn.addEventListener('click', function() {
            const tab = this.dataset.tab;
            switchTab(tab);
        });
    });
    
    // بارگذاری تب اول
    switchTab('overview');
});

function switchTab(tab) {
    if (currentTab === tab && loadedTabs.has(tab)) return;
    currentTab = tab;
    
    // به‌روزرسانی دکمه‌ها
    document.querySelectorAll('#dbTabs button').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.tab === tab);
    });
    
    const container = document.getElementById('dbContent');
    
    if (loadedTabs.has(tab)) {
        // اگر قبلاً بارگذاری شده، نمایش بده
        const content = document.getElementById('tabContent_' + tab);
        if (content) {
            container.innerHTML = content.innerHTML;
            return;
        }
    }
    
    // بارگذاری
    container.innerHTML = '<div class="loading">⏳ در حال بارگذاری...</div>';
    
    const url = DB_TABS[tab];
    if (!url) {
        container.innerHTML = '<p style="color:var(--accent-red);">❌ تب یافت نشد</p>';
        return;
    }
    
    fetch(url)
        .then(res => {
            if (!res.ok) throw new Error('Tab not found');
            return res.text();
        })
        .then(html => {
            loadedTabs.add(tab);
            const contentDiv = document.createElement('div');
            contentDiv.id = 'tabContent_' + tab;
            contentDiv.innerHTML = html;
            container.innerHTML = contentDiv.innerHTML;
            
            // اجرای اسکریپت‌های داخل تب
            const scripts = container.querySelectorAll('script');
            scripts.forEach(old => {
                const ns = document.createElement('script');
                ns.textContent = old.textContent;
                old.parentNode.replaceChild(ns, old);
            });
            
            // تابع init مخصوص هر تب
            const initFn = window['init_' + tab];
            if (typeof initFn === 'function') setTimeout(initFn, 100);
        })
        .catch(err => {
            container.innerHTML = `<p style="color:var(--accent-red);">❌ خطا: ${err.message}</p>`;
        });
}

// ============================================================
// توابع هر تب
// ============================================================

function init_overview() {
    fetch('/health/database', { credentials: 'include' })
        .then(res => res.json())
        .then(data => {
            const container = document.querySelector('#tabContent_overview .db-stats');
            if (!container) return;
            if (data.success && data.data) {
                let html = '<div class="db-stats-grid" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;">';
                Object.entries(data.data).forEach(([name, info]) => {
                    const status = info.connected ? '✅ متصل' : '❌ قطع';
                    html += `
                        <div style="background:var(--bg-primary);padding:14px 16px;border-radius:8px;border:1px solid var(--border-color);">
                            <div style="font-weight:600;">${name}</div>
                            <div style="font-size:0.85rem;color:${info.connected ? 'var(--accent-green)' : 'var(--accent-red)'};">${status}</div>
                            <div style="font-size:0.7rem;color:var(--text-secondary);">نسخه: ${info.version || 'unknown'}</div>
                        </div>
                    `;
                });
                html += '</div>';
                container.innerHTML = html;
            } else {
                container.innerHTML = '<p style="color:var(--accent-red);">❌ خطا در دریافت اطلاعات</p>';
            }
        })
        .catch(() => {
            const container = document.querySelector('#tabContent_overview .db-stats');
            if (container) container.innerHTML = '<p style="color:var(--accent-red);">❌ خطا در ارتباط با سرور</p>';
        });
}

function init_postgresql() {
    const tbody = document.querySelector('#pgTableBody');
    if (!tbody) return;
    tbody.innerHTML = '<tr><td colspan="3" style="text-align:center;color:var(--text-secondary);">در حال بارگذاری...</td></tr>';
    
    fetch('/api/db/tables', { credentials: 'include' })
        .then(res => res.json())
        .then(data => {
            if (data.success && data.data) {
                let html = '';
                data.data.forEach(table => {
                    html += `<tr>
                                <td><strong>${table.table_name}</strong></td>
                                <td>${(table.row_count || 0).toLocaleString()}</td>
                                <td>${(table.size_mb || 0).toFixed(2)}</td>
                            </tr>`;
                });
                tbody.innerHTML = html || '<tr><td colspan="3" style="text-align:center;color:var(--text-secondary);">📭 هیچ جدولی یافت نشد</td></tr>';
            } else {
                tbody.innerHTML = '<tr><td colspan="3" style="text-align:center;color:var(--accent-red);">❌ خطا</td></tr>';
            }
        })
        .catch(() => {
            tbody.innerHTML = '<tr><td colspan="3" style="text-align:center;color:var(--accent-red);">❌ خطا در ارتباط</td></tr>';
        });
}

function init_redis() {
    const container = document.querySelector('#tabContent_redis');
    if (!container) return;
    container.innerHTML = `
        <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;margin-bottom:16px;">
            <div style="background:var(--bg-primary);padding:14px;border-radius:8px;text-align:center;">
                <div style="font-size:0.7rem;color:var(--text-secondary);">🔑 کلیدها</div>
                <div style="font-size:1.3rem;font-weight:700;color:var(--accent-cyan);" id="redisCount">—</div>
            </div>
            <div style="background:var(--bg-primary);padding:14px;border-radius:8px;text-align:center;">
                <div style="font-size:0.7rem;color:var(--text-secondary);">💾 حافظه</div>
                <div style="font-size:1.3rem;font-weight:700;color:var(--accent-green);" id="redisMemory">—</div>
            </div>
        </div>
        <p style="color:var(--text-secondary);text-align:center;padding:10px;">📋 اطلاعات Redis در حال بارگذاری...</p>
    `;
    
    // TODO: پیاده‌سازی کامل Redis
}

function init_sqlite() {
    const container = document.querySelector('#tabContent_sqlite');
    if (container) {
        container.innerHTML = `
            <p style="color:var(--text-secondary);text-align:center;padding:20px;">
                📄 اطلاعات SQLite در حال بارگذاری...
            </p>
        `;
    }
}

function init_explorer() {
    const container = document.querySelector('#tabContent_explorer');
    if (!container) return;
    container.innerHTML = `
        <div class="db-search">
            <input type="text" id="explorerSearch" placeholder="جستجو در دیتابیس..." onkeypress="if(event.key==='Enter') searchExplorer()">
            <button onclick="searchExplorer()">🔍 جستجو</button>
        </div>
        <div id="explorerResults" style="color:var(--text-secondary);text-align:center;padding:20px;">
            عبارت مورد نظر را وارد کنید
        </div>
    `;
}

function searchExplorer() {
    const q = document.getElementById('explorerSearch').value.trim();
    const results = document.getElementById('explorerResults');
    if (!q) {
        results.innerHTML = 'عبارت مورد نظر را وارد کنید';
        return;
    }
    results.innerHTML = '⏳ در حال جستجو...';
    
    fetch(`/api/db/search?q=${encodeURIComponent(q)}`, { credentials: 'include' })
        .then(res => res.json())
        .then(data => {
            if (data.success && data.data) {
                let html = '';
                data.data.forEach(item => {
                    html += `
                        <div style="padding:10px 14px;border-bottom:1px solid rgba(255,255,255,0.03);display:flex;justify-content:space-between;flex-wrap:wrap;gap:8px;">
                            <div><strong style="color:var(--accent-cyan);">${item.table}</strong> • ${item.count} نتیجه</div>
                            <div style="font-size:0.7rem;color:var(--text-secondary);">${item.rows.length} رکورد</div>
                        </div>
                    `;
                });
                results.innerHTML = html || '🔍 نتیجه‌ای یافت نشد';
            } else {
                results.innerHTML = '❌ خطا در جستجو';
            }
        })
        .catch(() => {
            results.innerHTML = '❌ خطا در ارتباط با سرور';
        });
}

function init_monitor() {
    const container = document.querySelector('#tabContent_monitor');
    if (!container) return;
    container.innerHTML = `
        <p style="color:var(--text-secondary);text-align:center;padding:20px;">
            📈 مانیتورینگ دیتابیس در حال بارگذاری...
        </p>
        <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-top:12px;">
            <div style="background:var(--bg-primary);padding:14px;border-radius:8px;text-align:center;">
                <div style="font-size:0.7rem;color:var(--text-secondary);">🟢 متصل</div>
                <div style="font-size:1.3rem;font-weight:700;color:var(--accent-green);" id="monOnline">—</div>
            </div>
            <div style="background:var(--bg-primary);padding:14px;border-radius:8px;text-align:center;">
                <div style="font-size:0.7rem;color:var(--text-secondary);">🔴 قطع</div>
                <div style="font-size:1.3rem;font-weight:700;color:var(--accent-red);" id="monOffline">—</div>
            </div>
            <div style="background:var(--bg-primary);padding:14px;border-radius:8px;text-align:center;">
                <div style="font-size:0.7rem;color:var(--text-secondary);">📊 کل</div>
                <div style="font-size:1.3rem;font-weight:700;color:var(--accent-cyan);" id="monTotal">—</div>
            </div>
        </div>
    `;
    
    fetch('/health/database', { credentials: 'include' })
        .then(res => res.json())
        .then(data => {
            if (data.success && data.data) {
                const entries = Object.entries(data.data);
                let online = 0, offline = 0;
                entries.forEach(([_, info]) => {
                    if (info.connected) online++;
                    else offline++;
                });
                document.getElementById('monOnline').textContent = online;
                document.getElementById('monOffline').textContent = offline;
                document.getElementById('monTotal').textContent = entries.length;
            }
        })
        .catch(() => {});
}
