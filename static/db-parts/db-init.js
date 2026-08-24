// ============================================================
// db-init.js - مدیریت مرکزی تمام تب‌های دیتابیس
// ============================================================

// ============================================================
// PostgreSQL
// ============================================================

let pgTables = [];
let pgCurrentTable = '';

function init_postgresql() {
    console.log('🔄 PostgreSQL tab initialized');
    loadPostgresTables();
    
    document.getElementById('pgTableSelect')?.addEventListener('change', loadPostgresTableData);
    document.getElementById('pgSearchInput')?.addEventListener('keyup', function(e) {
        const search = this.value.toLowerCase();
        document.querySelectorAll('#pgTableBody tr').forEach(row => {
            const text = row.textContent.toLowerCase();
            row.style.display = text.includes(search) ? '' : 'none';
        });
    });
}

function loadPostgresTables() {
    const select = document.getElementById('pgTableSelect');
    const status = document.getElementById('pgStatus');
    if (!select || !status) return;
    
    select.innerHTML = '<option value="">در حال بارگذاری...</option>';

    fetch('/api/db/postgresql/tables')
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                pgTables = data.data;
                select.innerHTML = '<option value="">-- انتخاب جدول --</option>';
                let totalRows = 0;
                pgTables.forEach(table => {
                    const option = document.createElement('option');
                    option.value = table.table_name;
                    const rowCount = table.row_count || 0;
                    totalRows += rowCount;
                    option.textContent = `${table.table_name} (${rowCount.toLocaleString()} رکورد)`;
                    select.appendChild(option);
                });
                document.getElementById('pgTableCount').textContent = pgTables.length;
                document.getElementById('pgTotalRows').textContent = totalRows.toLocaleString();
                
                let totalSize = 0;
                pgTables.forEach(t => totalSize += (t.size_mb || 0));
                document.getElementById('pgTotalSize').textContent = totalSize > 0 ? totalSize.toFixed(1) + ' MB' : '-';
                
                status.textContent = '✅ متصل';
                status.className = 'db-status online';
            } else {
                status.textContent = '❌ خطا';
                status.className = 'db-status offline';
            }
        })
        .catch(() => {
            status.textContent = '❌ قطع';
            status.className = 'db-status offline';
        });
}

function loadPostgresTableData() {
    const select = document.getElementById('pgTableSelect');
    const tableName = select?.value;
    const tbody = document.getElementById('pgTableBody');
    const thead = document.getElementById('pgTableHead');
    const info = document.getElementById('pgRowInfo');
    const timeEl = document.getElementById('pgUpdateTime');

    if (!tableName || !tbody) {
        if (tbody) tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:#4a5a6a;">یک جدول را انتخاب کنید</td></tr>';
        if (thead) thead.innerHTML = '';
        if (info) info.textContent = 'یک جدول را انتخاب کنید';
        if (timeEl) timeEl.textContent = '';
        pgCurrentTable = '';
        return;
    }

    pgCurrentTable = tableName;
    tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:#4a5a6a;">در حال بارگذاری...</td></tr>';

    fetch(`/api/db/postgresql/table/${tableName}`)
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                const columns = data.data.columns || [];
                const rows = data.data.rows || [];

                let headerHtml = '<tr>';
                columns.forEach(col => {
                    headerHtml += `<th>${col.column_name}</th>`;
                });
                headerHtml += '</tr>';
                if (thead) thead.innerHTML = headerHtml;

                if (rows.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="' + columns.length + '" style="text-align:center;color:#4a5a6a;">هیچ رکوردی یافت نشد</td></tr>';
                } else {
                    let bodyHtml = '';
                    rows.forEach(row => {
                        bodyHtml += '<tr>';
                        columns.forEach(col => {
                            const value = row[col.column_name];
                            bodyHtml += `<td>${value !== null && value !== undefined ? value : '-'}</td>`;
                        });
                        bodyHtml += '</tr>';
                    });
                    tbody.innerHTML = bodyHtml;
                }

                if (info) info.textContent = `${rows.length} رکورد نمایش داده شده`;
                if (timeEl) timeEl.textContent = '🔄 ' + new Date().toLocaleTimeString('fa-IR');
            } else {
                tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:#ff4444;">❌ ' + data.error + '</td></tr>';
            }
        })
        .catch(err => {
            tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:#ff4444;">❌ خطا: ' + err.message + '</td></tr>';
        });
}

function exportPostgresCSV() {
    if (!pgCurrentTable) {
        showToast('⚠️ لطفاً ابتدا یک جدول را انتخاب کنید', 'warning');
        return;
    }
    const rows = document.querySelectorAll('#pgTableBody tr');
    let csv = '';
    rows.forEach(row => {
        const cells = row.querySelectorAll('td');
        const rowData = [];
        cells.forEach(cell => rowData.push(cell.textContent.trim()));
        csv += rowData.join(',') + '\n';
    });
    if (navigator.clipboard) {
        navigator.clipboard.writeText(csv).then(() => {
            showToast('📋 CSV کپی شد!', 'success');
        });
    }
}


// ============================================================
// Redis
// ============================================================

let redisKeys = [];
let selectedRedisKey = '';

function init_redis() {
    console.log('🔄 Redis tab initialized');
    loadRedisKeys();
    document.getElementById('redisSearchInput')?.addEventListener('keyup', function() {
        const search = this.value.toLowerCase();
        const filtered = redisKeys.filter(item => item.key.toLowerCase().includes(search));
        renderRedisKeys(filtered);
    });
    document.getElementById('redisTypeFilter')?.addEventListener('change', filterRedisKeys);
}

function loadRedisKeys() {
    const tbody = document.getElementById('redisTableBody');
    const status = document.getElementById('redisStatus');
    if (!tbody || !status) return;
    
    tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:#4a5a6a;">در حال بارگذاری...</td></tr>';

    fetch('/api/db/redis/keys')
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                redisKeys = data.data;
                document.getElementById('redisKeyCount').textContent = data.count;
                
                fetch('/health/database')
                    .then(r => r.json())
                    .then(h => {
                        if (h.success && h.data.redis) {
                            const stats = h.data.redis.stats || {};
                            document.getElementById('redisMemory').textContent = stats.memory || '-';
                            document.getElementById('redisClients').textContent = stats.clients || '-';
                        }
                    });
                
                renderRedisKeys(redisKeys);
                status.textContent = '✅ متصل';
                status.className = 'db-status online';
            } else {
                status.textContent = '❌ خطا';
                status.className = 'db-status offline';
            }
        })
        .catch(() => {
            status.textContent = '❌ قطع';
            status.className = 'db-status offline';
        });
}

function renderRedisKeys(keys) {
    const tbody = document.getElementById('redisTableBody');
    if (!tbody) return;
    
    if (keys.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:#4a5a6a;">هیچ کلیدی یافت نشد</td></tr>';
        return;
    }

    let html = '';
    keys.forEach(item => {
        const size = item.size > 1024 ? (item.size/1024).toFixed(1) + 'KB' : item.size + 'B';
        html += `
            <tr>
                <td style="font-family:'Courier New',monospace;font-size:0.75rem;max-width:150px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${item.key}">${item.key}</td>
                <td><span class="badge info">${item.type}</span></td>
                <td>${item.ttl}</td>
                <td>${size}</td>
                <td style="display:flex;gap:4px;flex-wrap:wrap;">
                    <button class="btn-refresh" onclick="viewRedisKey('${item.key}')" style="padding:2px 8px;font-size:0.6rem;" title="مشاهده">👁️</button>
                    <button class="btn-refresh" onclick="deleteRedisKeyConfirm('${item.key}')" style="padding:2px 8px;font-size:0.6rem;color:#ff4444;" title="حذف">🗑️</button>
                </td>
            </tr>
        `;
    });
    tbody.innerHTML = html;
}

function filterRedisKeys() {
    const type = document.getElementById('redisTypeFilter')?.value;
    const search = document.getElementById('redisSearchInput')?.value.toLowerCase() || '';
    let filtered = redisKeys;
    if (type && type !== 'all') {
        filtered = filtered.filter(item => item.type === type);
    }
    if (search) {
        filtered = filtered.filter(item => item.key.toLowerCase().includes(search));
    }
    renderRedisKeys(filtered);
}

function viewRedisKey(key) {
    selectedRedisKey = key;
    const modal = document.getElementById('redisValueModal');
    const content = document.getElementById('redisModalContent');
    if (!modal || !content) return;
    
    modal.style.display = 'flex';
    content.textContent = 'در حال بارگذاری...';

    fetch(`/api/db/redis/key/${encodeURIComponent(key)}`)
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                const val = data.data.value;
                const formatted = typeof val === 'object' ? JSON.stringify(val, null, 2) : val;
                content.textContent = formatted;
            } else {
                content.textContent = '❌ ' + data.error;
            }
        })
        .catch(err => {
            content.textContent = '❌ ' + err.message;
        });
}

function closeRedisModal() {
    const modal = document.getElementById('redisValueModal');
    if (modal) modal.style.display = 'none';
}

function copyRedisValue() {
    const content = document.getElementById('redisModalContent');
    if (!content) return;
    const text = content.textContent;
    if (navigator.clipboard) {
        navigator.clipboard.writeText(text).then(() => {
            showToast('📋 کپی شد!', 'success');
        });
    } else {
        const textarea = document.createElement('textarea');
        textarea.value = text;
        document.body.appendChild(textarea);
        textarea.select();
        document.execCommand('copy');
        document.body.removeChild(textarea);
        showToast('📋 کپی شد!', 'success');
    }
}

function deleteRedisKeyConfirm(key) {
    if (!confirm(`آیا از حذف کلید "${key}" اطمینان دارید؟`)) return;
    fetch(`/api/db/redis/key/${encodeURIComponent(key)}`, { method: 'DELETE' })
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                showToast('🗑️ کلید حذف شد', 'success');
                loadRedisKeys();
            } else {
                showToast('❌ ' + data.error, 'error');
            }
        })
        .catch(() => {
            showToast('❌ خطا در حذف', 'error');
        });
}


// ============================================================
// SQLite
// ============================================================

let sqliteTables = [];
let sqliteCurrentTable = '';

function init_sqlite() {
    console.log('🔄 SQLite tab initialized');
    loadSqliteTables();
    document.getElementById('sqliteTableSelect')?.addEventListener('change', loadSqliteTableData);
    document.getElementById('sqliteSearchInput')?.addEventListener('keyup', function(e) {
        const search = this.value.toLowerCase();
        document.querySelectorAll('#sqliteTableBody tr').forEach(row => {
            const text = row.textContent.toLowerCase();
            row.style.display = text.includes(search) ? '' : 'none';
        });
    });
}

function loadSqliteTables() {
    const select = document.getElementById('sqliteTableSelect');
    const status = document.getElementById('sqliteStatus');
    if (!select || !status) return;
    
    select.innerHTML = '<option value="">در حال بارگذاری...</option>';

    fetch('/api/db/sqlite/tables')
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                sqliteTables = data.data;
                select.innerHTML = '<option value="">-- انتخاب جدول --</option>';
                let totalRows = 0;
                sqliteTables.forEach(table => {
                    const option = document.createElement('option');
                    option.value = table.table_name;
                    const rowCount = table.row_count || 0;
                    totalRows += rowCount;
                    option.textContent = `${table.table_name} (${rowCount.toLocaleString()} رکورد)`;
                    select.appendChild(option);
                });
                document.getElementById('sqliteTableCount').textContent = sqliteTables.length;
                document.getElementById('sqliteTotalRows').textContent = totalRows.toLocaleString();
                status.textContent = '✅ متصل';
                status.className = 'db-status online';
            } else {
                status.textContent = '❌ خطا';
                status.className = 'db-status offline';
            }
        })
        .catch(() => {
            status.textContent = '❌ قطع';
            status.className = 'db-status offline';
        });
}

function loadSqliteTableData() {
    const select = document.getElementById('sqliteTableSelect');
    const tableName = select?.value;
    const tbody = document.getElementById('sqliteTableBody');
    const thead = document.getElementById('sqliteTableHead');
    const info = document.getElementById('sqliteRowInfo');
    const timeEl = document.getElementById('sqliteUpdateTime');

    if (!tableName || !tbody) {
        if (tbody) tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:#4a5a6a;">یک جدول را انتخاب کنید</td></tr>';
        if (thead) thead.innerHTML = '';
        if (info) info.textContent = 'یک جدول را انتخاب کنید';
        if (timeEl) timeEl.textContent = '';
        sqliteCurrentTable = '';
        return;
    }

    sqliteCurrentTable = tableName;
    tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:#4a5a6a;">در حال بارگذاری...</td></tr>';

    fetch(`/api/db/sqlite/table/${tableName}`)
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                const columns = data.data.columns || [];
                const rows = data.data.rows || [];

                let headerHtml = '<tr>';
                columns.forEach(col => {
                    headerHtml += `<th>${col}</th>`;
                });
                headerHtml += '</tr>';
                if (thead) thead.innerHTML = headerHtml;

                if (rows.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="' + columns.length + '" style="text-align:center;color:#4a5a6a;">هیچ رکوردی یافت نشد</td></tr>';
                } else {
                    let bodyHtml = '';
                    rows.forEach(row => {
                        bodyHtml += '<tr>';
                        columns.forEach(col => {
                            const value = row[col];
                            bodyHtml += `<td>${value !== null && value !== undefined ? value : '-'}</td>`;
                        });
                        bodyHtml += '</tr>';
                    });
                    tbody.innerHTML = bodyHtml;
                }

                if (info) info.textContent = `${rows.length} رکورد نمایش داده شده`;
                if (timeEl) timeEl.textContent = '🔄 ' + new Date().toLocaleTimeString('fa-IR');
            } else {
                tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:#ff4444;">❌ ' + data.error + '</td></tr>';
            }
        })
        .catch(err => {
            tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:#ff4444;">❌ خطا: ' + err.message + '</td></tr>';
        });
}

function exportSqliteCSV() {
    if (!sqliteCurrentTable) {
        showToast('⚠️ لطفاً ابتدا یک جدول را انتخاب کنید', 'warning');
        return;
    }
    const rows = document.querySelectorAll('#sqliteTableBody tr');
    let csv = '';
    rows.forEach(row => {
        const cells = row.querySelectorAll('td');
        const rowData = [];
        cells.forEach(cell => rowData.push(cell.textContent.trim()));
        csv += rowData.join(',') + '\n';
    });
    if (navigator.clipboard) {
        navigator.clipboard.writeText(csv).then(() => {
            showToast('📋 CSV کپی شد!', 'success');
        });
    }
}


// ============================================================
// Explorer
// ============================================================

function init_explorer() {
    console.log('🔄 Explorer tab initialized');
    document.getElementById('explorerSearch')?.addEventListener('keydown', function(e) {
        if (e.key === 'Enter') searchExplorer();
    });
}

function searchExplorer() {
    const query = document.getElementById('explorerSearch')?.value.trim();
    const target = document.getElementById('explorerTarget')?.value || 'all';
    const limit = document.getElementById('explorerLimit')?.value || 25;
    const results = document.getElementById('explorerResults');

    if (!query) {
        if (results) results.innerHTML = '<p style="color:#7a8fa3;text-align:center;font-size:0.8rem;">🔍 لطفاً عبارت جستجو را وارد کنید</p>';
        return;
    }

    if (results) {
        results.innerHTML = '<div class="loading" style="padding:20px;"><div class="spinner" style="width:24px;height:24px;"></div><p style="color:#7a8fa3;font-size:0.8rem;">⏳ در حال جستجو...</p></div>';
    }

    fetch(`/api/db/search?q=${encodeURIComponent(query)}&target=${target}&limit=${limit}`)
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                renderSearchResults(data.data, query);
            } else {
                if (results) results.innerHTML = `<p style="color:#ff4444;text-align:center;">❌ ${data.error}</p>`;
            }
        })
        .catch(err => {
            if (results) results.innerHTML = `<p style="color:#ff4444;text-align:center;">❌ ${err.message}</p>`;
        });
}

function renderSearchResults(results, query) {
    const container = document.getElementById('explorerResults');
    if (!container) return;
    
    if (!results || results.length === 0) {
        container.innerHTML = `
            <div style="text-align:center;padding:30px 0;color:#4a5a6a;">
                <i class="fas fa-search" style="font-size:2rem;opacity:0.2;"></i>
                <p style="margin-top:8px;">🔍 نتیجه‌ای برای "<strong>${query}</strong>" یافت نشد</p>
            </div>
        `;
        return;
    }

    let html = `<div style="font-size:0.75rem;color:#7a8fa3;margin-bottom:8px;">${results.length} نتیجه برای "<strong>${query}</strong>"</div>`;
    results.forEach(item => {
        const dbColors = {
            'postgresql': '#3366ff',
            'redis': '#ff4444',
            'sqlite': '#00ff88'
        };
        const color = dbColors[item.database?.toLowerCase()] || '#00d4ff';

        html += `
            <div class="db-card" style="margin-bottom:8px;padding:12px;border-left:3px solid ${color};">
                <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;">
                    <span style="color:${color};font-weight:600;font-size:0.85rem;">
                        <i class="fas ${item.database === 'Redis' ? 'fa-bolt' : item.database === 'PostgreSQL' ? 'fa-database' : 'fa-file'}"></i>
                        ${item.database}
                    </span>
                    <span class="badge info">${item.type}</span>
                </div>
                <div style="font-family:'Courier New',monospace;font-size:0.7rem;color:#e0e6ed;margin-top:4px;word-break:break-all;max-height:80px;overflow-y:auto;background:#0a0e17;padding:6px;border-radius:4px;">
                    ${item.content}
                </div>
                <div style="font-size:0.55rem;color:#4a5a6a;margin-top:4px;">
                    ${item.table || item.key || ''}
                </div>
            </div>
        `;
    });
    container.innerHTML = html;
}

function clearExplorer() {
    const search = document.getElementById('explorerSearch');
    const results = document.getElementById('explorerResults');
    if (search) search.value = '';
    if (results) {
        results.innerHTML = `
            <div style="text-align:center;padding:30px 0;color:#4a5a6a;">
                <i class="fas fa-search" style="font-size:3rem;opacity:0.2;"></i>
                <p style="margin-top:8px;font-size:0.85rem;">برای شروع جستجو، عبارت را وارد کنید</p>
            </div>
        `;
    }
}


// ============================================================
// Monitor
// ============================================================

function init_monitor() {
    console.log('🔄 Monitor tab initialized');
    loadMonitor();
    setInterval(loadMonitor, 30000);
}

function loadMonitor() {
    const container = document.getElementById('monitorContent');
    const timeEl = document.getElementById('monitorTime');
    if (!container) return;
    
    container.innerHTML = '<div class="loading"><div class="spinner"></div><p style="color:#7a8fa3;font-size:0.8rem;">در حال بارگذاری...</p></div>';

    fetch('/health/database')
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                renderMonitor(data.data);
                if (timeEl) timeEl.textContent = '🔄 ' + new Date().toLocaleTimeString('fa-IR');
            } else {
                container.innerHTML = '<p style="color:#ff4444;text-align:center;">❌ خطا در دریافت اطلاعات</p>';
            }
        })
        .catch(err => {
            container.innerHTML = `<p style="color:#ff4444;text-align:center;">❌ ${err.message}</p>`;
        });
}

function renderMonitor(dbData) {
    const container = document.getElementById('monitorContent');
    if (!container) return;
    
    let html = '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px;">';

    const dbIcons = {
        'redis': { icon: 'fa-bolt', color: '#ff4444' },
        'postgresql': { icon: 'fa-database', color: '#3366ff' },
        'sqlite': { icon: 'fa-file', color: '#00ff88' }
    };

    for (const [name, info] of Object.entries(dbData)) {
        const isConnected = info.connected && info.ping;
        const style = dbIcons[name] || { icon: 'fa-server', color: '#00d4ff' };
        const stats = info.stats || {};

        html += `
            <div class="db-card" style="margin-bottom:0;padding:14px;border-left:4px solid ${style.color};">
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
                    <div style="display:flex;align-items:center;gap:8px;">
                        <i class="fas ${style.icon}" style="color:${style.color};"></i>
                        <span style="font-weight:600;color:#e0e6ed;">${name}</span>
                    </div>
                    <span style="color:${isConnected ? '#00ff88' : '#ff4444'};font-size:0.7rem;display:flex;align-items:center;gap:4px;">
                        ${isConnected ? '✅' : '❌'}
                        ${isConnected ? 'متصل' : 'قطع'}
                    </span>
                </div>
                <div style="font-size:0.7rem;color:#7a8fa3;">
                    ${Object.entries(stats).map(([key, value]) => `
                        <div style="display:flex;justify-content:space-between;padding:3px 0;border-bottom:1px solid #0d1624;">
                            <span>${key}</span>
                            <span style="color:#e0e6ed;font-family:'Courier New',monospace;">${value}</span>
                        </div>
                    `).join('')}
                    ${Object.keys(stats).length === 0 ? '<p style="color:#4a5a6a;text-align:center;font-size:0.6rem;">هیچ آماری موجود نیست</p>' : ''}
                </div>
                <div style="margin-top:6px;font-size:0.5rem;color:#4a5a6a;">
                    ${info.version ? 'نسخه: ' + info.version : ''}
                </div>
            </div>
        `;
    }

    html += '</div>';
    container.innerHTML = html;
}


// ============================================================
// Overview
// ============================================================

function init_overview() {
    console.log('🔄 Overview tab initialized');
    loadOverview();
}

function loadOverview() {
    const container = document.getElementById('overviewCards');
    if (!container) return;
    
    container.innerHTML = '<div class="loading"><div class="spinner"></div><p style="color:#7a8fa3;font-size:0.8rem;">در حال دریافت...</p></div>';

    fetch('/health/database')
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                renderOverview(data.data);
            } else {
                container.innerHTML = `<div class="db-card"><p style="color:#ff4444;text-align:center;">❌ خطا در دریافت اطلاعات</p></div>`;
            }
        })
        .catch(err => {
            container.innerHTML = `<div class="db-card"><p style="color:#ff4444;text-align:center;">❌ خطا: ${err.message}</p></div>`;
        });
}

function renderOverview(dbData) {
    const container = document.getElementById('overviewCards');
    if (!container) return;
    
    const dbNames = Object.keys(dbData);
    let online = 0, offline = 0;

    for (const name of dbNames) {
        if (dbData[name].connected && dbData[name].ping) online++;
        else offline++;
    }

    document.getElementById('ovTotal').textContent = dbNames.length;
    document.getElementById('ovOnline').textContent = online;
    document.getElementById('ovOffline').textContent = offline;

    const dbStyles = {
        'redis': { icon: 'fa-bolt', class: 'redis', label: 'کش و داده‌های سریع' },
        'postgresql': { icon: 'fa-database', class: 'postgresql', label: 'داده‌های اصلی و ماندگار' },
        'sqlite': { icon: 'fa-file', class: 'sqlite', label: 'بک‌آپ و گزارش‌ها' }
    };

    let html = '';
    for (const name of dbNames) {
        const info = dbData[name];
        const style = dbStyles[name] || dbStyles['postgresql'];
        const isConnected = info.connected && info.ping;
        const stats = info.stats || {};

        html += `
            <div class="db-card ${style.class}">
                <div class="db-header">
                    <div class="db-info">
                        <span class="db-icon"><i class="fas ${style.icon}"></i></span>
                        <span class="db-name">${name}</span>
                        <span class="db-description">${style.label}</span>
                    </div>
                    <span class="db-status ${isConnected ? 'online' : 'offline'}">
                        ${isConnected ? '✅ متصل' : '❌ قطع'}
                    </span>
                </div>
                <div class="db-body">
                    <div class="db-field">
                        <label>📡 آدرس</label>
                        <div class="db-value">${info.host || info.url || 'تنظیم نشده'}</div>
                    </div>
                    <div class="db-field">
                        <label>📊 وضعیت</label>
                        <div class="db-value">${info.enabled ? '✅ فعال' : '⛔ غیرفعال'}</div>
                    </div>
                </div>
                <div class="db-stats">
                    ${Object.entries(stats).map(([key, value]) => `
                        <span class="stat-item">
                            <i class="fas fa-chart-simple"></i>
                            ${key}: <span class="stat-value">${value}</span>
                        </span>
                    `).join('')}
                </div>
            </div>
        `;
    }

    html += `
        <div style="text-align:center;margin-top:12px;">
            <button class="btn-refresh" onclick="loadOverview()" style="padding:8px 20px;">
                <i class="fas fa-sync-alt"></i> بروزرسانی
            </button>
        </div>
    `;

    container.innerHTML = html;
}
