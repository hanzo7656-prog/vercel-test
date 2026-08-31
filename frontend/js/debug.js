// js/debug.js - منطق دیباگ

const DEBUG_TABS = {
    status: '/components/tabs/debug-status.html',
    logs: '/components/tabs/debug-logs.html',
    cli: '/components/tabs/debug-cli.html',
    system: '/components/tabs/debug-system.html',
    cache: '/components/tabs/debug-cache.html'
};

let currentDebugTab = 'status';
const loadedDebugTabs = new Set();

document.addEventListener('DOMContentLoaded', function() {
    document.querySelectorAll('#debugTabs button').forEach(btn => {
        btn.addEventListener('click', function() {
            const tab = this.dataset.tab;
            switchDebugTab(tab);
        });
    });
    switchDebugTab('status');
});

function switchDebugTab(tab) {
    if (currentDebugTab === tab && loadedDebugTabs.has(tab)) return;
    currentDebugTab = tab;
    
    document.querySelectorAll('#debugTabs button').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.tab === tab);
    });
    
    const container = document.getElementById('debugContent');
    
    if (loadedDebugTabs.has(tab)) {
        const content = document.getElementById('debugTabContent_' + tab);
        if (content) {
            container.innerHTML = content.innerHTML;
            return;
        }
    }
    
    container.innerHTML = '<div class="loading">⏳ در حال بارگذاری...</div>';
    
    const url = DEBUG_TABS[tab];
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
            loadedDebugTabs.add(tab);
            const contentDiv = document.createElement('div');
            contentDiv.id = 'debugTabContent_' + tab;
            contentDiv.innerHTML = html;
            container.innerHTML = contentDiv.innerHTML;
            
            const scripts = container.querySelectorAll('script');
            scripts.forEach(old => {
                const ns = document.createElement('script');
                ns.textContent = old.textContent;
                old.parentNode.replaceChild(ns, old);
            });
            
            const initFn = window['init_debug_' + tab];
            if (typeof initFn === 'function') setTimeout(initFn, 100);
        })
        .catch(err => {
            container.innerHTML = `<p style="color:var(--accent-red);">❌ خطا: ${err.message}</p>`;
        });
}

// ============================================================
// توابع هر تب
// ============================================================

function init_debug_status() {
    fetch('/api/metrics', { credentials: 'include' })
        .then(res => res.json())
        .then(data => {
            const container = document.querySelector('#debugTabContent_status');
            if (!container) return;
            
            if (data.success && data.data) {
                const m = data.data.metrics || {};
                const cpu = m.cpu?.value || 0;
                const ram = m.ram?.value || 0;
                const uptime = m.uptime?.value || '0s';
                const api = m.api_status?.value || 'unknown';
                const credits = m.api_credits?.value || 0;
                
                container.innerHTML = `
                    <div class="system-grid">
                        <div class="system-item">
                            <div class="label">💻 CPU</div>
                            <div class="value ${cpu > 80 ? 'red' : cpu > 60 ? 'orange' : 'green'}">${cpu}%</div>
                        </div>
                        <div class="system-item">
                            <div class="label">💾 RAM</div>
                            <div class="value ${ram > 80 ? 'red' : ram > 60 ? 'orange' : 'green'}">${ram}%</div>
                        </div>
                        <div class="system-item">
                            <div class="label">⏱️ آپتایم</div>
                            <div class="value">${uptime}</div>
                        </div>
                        <div class="system-item">
                            <div class="label">🔌 API</div>
                            <div class="value ${api === 'ok' ? 'green' : api === 'degraded' ? 'orange' : 'red'}">${api === 'ok' ? '✅ سالم' : api === 'degraded' ? '⚠️ ضعیف' : '❌ قطع'}</div>
                        </div>
                        <div class="system-item">
                            <div class="label">💰 اعتبار</div>
                            <div class="value">${credits.toLocaleString()}</div>
                        </div>
                        <div class="system-item">
                            <div class="label">📊 جمع‌آوری‌ها</div>
                            <div class="value">${data.data.stats?.collections || 0}</div>
                        </div>
                    </div>
                    <div style="margin-top:12px;font-size:0.7rem;color:var(--text-secondary);">
                        آخرین بروزرسانی: ${new Date(data.data.timestamp).toLocaleString('fa-IR')}
                    </div>
                `;
            } else {
                container.innerHTML = '<p style="color:var(--accent-red);">❌ خطا در دریافت متریک‌ها</p>';
            }
        })
        .catch(() => {
            const container = document.querySelector('#debugTabContent_status');
            if (container) container.innerHTML = '<p style="color:var(--accent-red);">❌ خطا در ارتباط با سرور</p>';
        });
}

function init_debug_logs() {
    const container = document.querySelector('#debugTabContent_logs');
    if (!container) return;
    container.innerHTML = `
        <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px;">
            <button onclick="loadLogs()" style="padding:4px 16px;border:1px solid var(--border-color);border-radius:6px;background:transparent;color:var(--text-secondary);cursor:pointer;">🔄 بروزرسانی</button>
            <button onclick="clearLogs()" style="padding:4px 16px;border:1px solid var(--border-color);border-radius:6px;background:transparent;color:var(--accent-red);cursor:pointer;">🗑️ پاک کردن</button>
        </div>
        <div class="debug-output" id="logsOutput">⏳ در حال بارگذاری...</div>
    `;
    loadLogs();
}

function loadLogs() {
    const output = document.getElementById('logsOutput');
    fetch('/api/debug?section=logs&limit=50', { credentials: 'include' })
        .then(res => res.json())
        .then(data => {
            if (data.success && data.data) {
                output.innerHTML = data.data.length > 0 
                    ? data.data.map(line => `<div>${line}</div>`).join('') 
                    : '<span style="color:var(--text-secondary);">📭 هیچ لاگی ثبت نشده است</span>';
            } else {
                output.innerHTML = '<span class="error">❌ خطا در دریافت لاگ‌ها</span>';
            }
        })
        .catch(() => {
            output.innerHTML = '<span class="error">❌ خطا در ارتباط با سرور</span>';
        });
}

function clearLogs() {
    if (!confirm('آیا از پاک کردن لاگ‌ها اطمینان دارید؟')) return;
    fetch('/api/debug', {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ target: 'logs' })
    })
    .then(res => res.json())
    .then(data => {
        if (data.success) {
            showToast('🗑️ لاگ‌ها پاک شدند', 'success');
            loadLogs();
        } else {
            showToast('❌ ' + data.error, 'error');
        }
    })
    .catch(() => showToast('❌ خطا', 'error'));
}

function init_debug_cli() {
    const container = document.querySelector('#debugTabContent_cli');
    if (!container) return;
    container.innerHTML = `
        <div class="debug-output" id="cliOutput" style="min-height:200px;">
            <span style="color:var(--accent-green);">$</span> کنسول آماده است. دستورات پایتون را وارد کنید.
        </div>
        <div class="cli-input">
            <textarea id="cliInput" rows="3" placeholder="مثال: print('Hello World')&#10;یا: import os; os.listdir('.')"></textarea>
            <button onclick="executeCommand()"><i class="fas fa-play"></i> اجرا</button>
            <button class="danger" onclick="clearCliOutput()"><i class="fas fa-eraser"></i> پاک</button>
        </div>
    `;
}

function executeCommand() {
    const input = document.getElementById('cliInput');
    const output = document.getElementById('cliOutput');
    const cmd = input.value.trim();
    if (!cmd) return;
    
    output.innerHTML += `\n<span style="color:var(--accent-cyan);">>>> </span>${cmd}\n`;
    input.value = '';
    
    fetch('/api/debug/exec', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ command: cmd })
    })
    .then(res => res.json())
    .then(data => {
        if (data.success) {
            output.innerHTML += `<span style="color:var(--accent-green);">✅ </span>${data.result || 'انجام شد'}\n`;
        } else {
            output.innerHTML += `<span class="error">❌ </span>${data.error || 'خطا'}\n`;
        }
        output.scrollTop = output.scrollHeight;
    })
    .catch(err => {
        output.innerHTML += `<span class="error">❌ </span>${err.message}\n`;
    });
}

function clearCliOutput() {
    const output = document.getElementById('cliOutput');
    output.innerHTML = '<span style="color:var(--accent-green);">$</span> خروجی کنسول پاک شد';
}
