// ============================================================
// database.js — Database Page Script
// نسخه ۳.۰ — ارتقا کامل:
//   - loadingSystem v5 (inline + modal)
//   - Smart caching
//   - Debounced search
//   - Auto-refresh فقط تب فعال
//   - Keyboard shortcuts
//   - Retry logic
//   - Last updated timestamp
// ============================================================

(function() {
    'use strict';

    // ============================================================
    // State
    // ============================================================

    const state = {
        // Data
        pgData: [],
        redisData: [],
        archiveData: [],

        // Filters
        filters: {
            pg: { search: '', size: 'all' },
            redis: { search: '', type: 'all' },
            archive: { search: '' },
        },

        // Intervals
        monitorInterval: null,
        activeTabRefreshInterval: null,

        // Migration
        isMigrationRunning: false,

        // Retry config
        maxRetries: 2,
        retryDelay: 800,

        // Debounce
        searchDebounceTimers: {},

        // Last updated
        lastUpdated: {
            overview: null,
            postgresql: null,
            redis: null,
            archive: null,
            monitor: null,
        },

        // Cache (TTL: 30s)
        cache: new Map(),
        cacheTTL: 30000,

        // Active tab
        activeTab: 'overview',
    };

    // ============================================================
    // Helpers
    // ============================================================

    function escapeHtml(str) {
        if (!str) return '';
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function escapeAttr(str) {
        if (!str) return '';
        return String(str).replace(/'/g, "\\'").replace(/"/g, '&quot;');
    }

    function setText(id, value) {
        const el = document.getElementById(id);
        if (el) el.textContent = value ?? '—';
    }

    function escapeCsv(value) {
        const str = String(value ?? '');
        if (str.includes(',') || str.includes('"') || str.includes('\n')) {
            return '"' + str.replace(/"/g, '""') + '"';
        }
        return str;
    }

    function downloadCSV(content, filename) {
        const blob = new Blob(['\ufeff' + content], { type: 'text/csv;charset=utf-8;' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        a.click();
        URL.revokeObjectURL(url);
        if (typeof showToast === 'function') showToast('📥 دانلود شد', 'success');
    }

    function debounce(fn, delay = 300) {
        let timer = null;
        return function(...args) {
            clearTimeout(timer);
            timer = setTimeout(() => fn.apply(this, args), delay);
        };
    }

    function toPersian(num) {
        return String(num).replace(/\d/g, d => '۰۱۲۳۴۵۶۷۸۹'[d]);
    }

    // ============================================================
    // Cache Helper
    // ============================================================

    function getCache(key) {
        const item = state.cache.get(key);
        if (!item) return null;
        if (Date.now() > item.expires) {
            state.cache.delete(key);
            return null;
        }
        return item.value;
    }

    function setCache(key, value, ttl = state.cacheTTL) {
        state.cache.set(key, {
            value,
            expires: Date.now() + ttl,
        });
    }

    function clearCache(pattern = null) {
        if (!pattern) {
            state.cache.clear();
            return;
        }
        for (const key of state.cache.keys()) {
            if (key.includes(pattern)) {
                state.cache.delete(key);
            }
        }
    }

    // ============================================================
    // Retry Logic
    // ============================================================

    async function withRetry(fn, retries = state.maxRetries) {
        let lastError = null;

        for (let attempt = 1; attempt <= retries + 1; attempt++) {
            try {
                return await fn();
            } catch (err) {
                lastError = err;
                console.warn(`⚠️ Attempt ${attempt} failed:`, err.message);

                if (attempt <= retries) {
                    await new Promise(r => setTimeout(r, state.retryDelay));
                }
            }
        }

        throw lastError;
    }

    // ============================================================
    // Inline Loading for Tabs
    // ============================================================

    function showTabLoading(tabId) {
        const container = document.getElementById(tabId);
        if (!container) return;

        if (window.loadingSystem?.showInline) {
            window.loadingSystem.showInline(container, { color: '#00d4ff' });
        }
    }

    function hideTabLoading() {
        if (window.loadingSystem?.hideInline) {
            window.loadingSystem.hideInline();
        }
    }

    // ============================================================
    // ۱. Load Overview
    // ============================================================

    async function loadOverview(force = false) {
        const container = document.getElementById('overviewContent');
        if (!container) return;

        // چک cache
        if (!force) {
            const cached = getCache('overview');
            if (cached) {
                renderOverview(cached);
                return;
            }
        }

        showTabLoading('overviewContent');

        try {
            const [data, dbListRes] = await withRetry(async () => {
                return await Promise.all([
                    window.api.getHealthSummary(),
                    window.api.getDBList(),
                ]);
            });

            if (!data?.success || !data.data) {
                throw new Error('خطا در دریافت وضعیت دیتابیس‌ها');
            }

            const result = {
                summary: data.data,
                dbList: dbListRes?.data || [],
            };

            // Cache کن
            setCache('overview', result, 15000);

            renderOverview(result);

            // Last updated
            state.lastUpdated.overview = new Date();

        } catch (err) {
            console.error('❌ Overview error:', err);
            renderOverviewError(err.message);
        } finally {
            hideTabLoading();
        }
    }

    function renderOverview(result) {
        const container = document.getElementById('overviewContent');
        if (!container) return;

        const summary = result.summary;
        const details = summary.details || {};
        const dbList = result.dbList;

        // شمارش
        let online = 0;
        let offline = 0;
        const entries = Object.entries(details);

        entries.forEach(([_, info]) => {
            if (info?.connected) online++;
            else offline++;
        });

        // آپدیت stats
        setText('dbTotal', entries.length || dbList.length);
        setText('dbOnline', online);
        setText('dbOffline', offline);

        // PostgreSQL tables count
        if (state.pgData.length > 0) {
            setText('dbTables', state.pgData.length);
        } else {
            window.api.getPostgreSQLTables('primary').then(tables => {
                if (tables?.success && tables.data) {
                    setText('dbTables', tables.data.length);
                }
            }).catch(() => {});
        }

        // Render
        const icons = {
            postgresql: '🐘',
            postgres: '🐘',
            redis: '⚡',
            archive: '📦',
            sqlite: '📄',
            primary: '🗄️',
            backup: '💾',
            analytics: '📊',
            logs: '📝',
        };

        const dbNames = Object.keys(details).length > 0
            ? Object.keys(details)
            : dbList.map(d => d.name || d);

        if (dbNames.length === 0) {
            container.innerHTML = `
                <div class="db-empty">
                    <span class="empty-icon">📭</span>
                    <div class="empty-title">هیچ دیتابیسی یافت نشد</div>
                    <div class="empty-message">اطلاعات دیتابیس در دسترس نیست</div>
                </div>
            `;
            return;
        }

        container.innerHTML = `
            <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:14px;">
                ${dbNames.map(name => {
                    const info = details[name] || {};
                    const isConnected = info.connected === true || info.status === 'online';
                    const icon = icons[info.type] || icons[name] || '📦';
                    const version = info.version || '—';

                    return `
                        <div style="background:var(--bg-input);padding:16px 18px;border-radius:var(--radius-sm);border:1px solid ${isConnected ? 'var(--border-color)' : 'rgba(239, 68, 68, 0.3)'};transition:var(--transition);">
                            <div style="display:flex;justify-content:space-between;align-items:center;">
                                <div style="display:flex;align-items:center;gap:10px;">
                                    <span style="font-size:1.6rem;">${icon}</span>
                                    <div>
                                        <div style="font-weight:600;font-size:0.95rem;color:var(--text-primary);">${escapeHtml(name)}</div>
                                        <div style="font-size:0.65rem;color:var(--text-muted);font-family:var(--font-mono);">
                                            ${escapeHtml(info.type || 'unknown')} • ${escapeHtml(version)}
                                        </div>
                                    </div>
                                </div>
                                <div style="text-align:center;">
                                    <div style="font-size:1.3rem;font-weight:700;color:${isConnected ? 'var(--color-green)' : 'var(--color-red)'};">
                                        ${isConnected ? '🟢' : '🔴'}
                                    </div>
                                    <div style="font-size:0.55rem;color:${isConnected ? 'var(--color-green)' : 'var(--color-red)'};font-weight:600;text-transform:uppercase;">
                                        ${isConnected ? 'متصل' : 'قطع'}
                                    </div>
                                </div>
                            </div>
                            ${info.last_check ? `
                                <div style="margin-top:10px;padding-top:8px;border-top:1px solid var(--border-color);font-size:0.7rem;color:var(--text-muted);display:flex;gap:12px;flex-wrap:wrap;">
                                    <span>🕐 آخرین بررسی: ${formatTimeAgo(info.last_check) || '—'}</span>
                                    ${info.ping_ms !== undefined ? `<span>⚡ ${info.ping_ms}ms</span>` : ''}
                                </div>
                            ` : ''}
                        </div>
                    `;
                }).join('')}
            </div>
        `;
    }

    function renderOverviewError(message) {
        const container = document.getElementById('overviewContent');
        if (!container) return;

        container.innerHTML = `
            <div class="db-empty">
                <span class="empty-icon" style="color:var(--color-red);">⚠️</span>
                <div class="empty-title" style="color:var(--color-red);">خطا در بارگذاری</div>
                <div class="empty-message">${escapeHtml(message)}</div>
                <button class="btn btn-primary btn-sm" style="margin-top:16px;" onclick="DatabasePage.loadOverview(true)">
                    <i class="fas fa-sync-alt"></i>
                    <span>تلاش مجدد</span>
                </button>
            </div>
        `;
    }

    // ============================================================
    // ۲. Load PostgreSQL
    // ============================================================

    async function loadPostgreSQL(force = false) {
        const tbody = document.getElementById('pgTableBody');
        if (!tbody) return;

        if (!force) {
            const cached = getCache('postgresql');
            if (cached) {
                state.pgData = cached;
                renderPGTable(applyPGFilters(cached));
                return;
            }
        }

        showTabLoading('tab-postgresql');

        try {
            const data = await withRetry(() =>
                window.api.getPostgreSQLTables('primary')
            );

            if (!data?.success || !data.data) {
                throw new Error(data?.error || 'خطا در دریافت جدول‌ها');
            }

            state.pgData = data.data;

            setCache('postgresql', state.pgData, 20000);

            // Stats
            setText('pgTableCount', state.pgData.length);

            let totalSize = 0;
            let totalRows = 0;
            state.pgData.forEach(t => {
                totalSize += t.size_mb || 0;
                totalRows += t.row_count || 0;
            });

            setText('pgSize', totalSize.toFixed(1) + ' MB');
            setText('pgRows', totalRows.toLocaleString('en-US'));
            setText('dbTables', state.pgData.length);

            renderPGTable(applyPGFilters(state.pgData));

            state.lastUpdated.postgresql = new Date();

        } catch (err) {
            console.error('❌ PostgreSQL error:', err);
            renderPGError(err.message);
        } finally {
            hideTabLoading();
        }
    }

    function applyPGFilters(data) {
        const { search, size } = state.filters.pg;

        let filtered = data.filter(t =>
            (t.table_name || '').toLowerCase().includes(search.toLowerCase())
        );

        if (size === 'large') {
            filtered = filtered.filter(t => (t.size_mb || 0) > 10);
        } else if (size === 'medium') {
            filtered = filtered.filter(t => (t.size_mb || 0) >= 1 && (t.size_mb || 0) <= 10);
        } else if (size === 'small') {
            filtered = filtered.filter(t => (t.size_mb || 0) < 1);
        }

        return filtered;
    }

    function renderPGTable(data) {
        const tbody = document.getElementById('pgTableBody');
        if (!tbody) return;

        if (!data || data.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="6" style="padding:0;">
                        <div class="db-empty">
                            <span class="empty-icon">📭</span>
                            <div class="empty-title">هیچ جدولی یافت نشد</div>
                            <div class="empty-message">${state.filters.pg.search ? 'فیلتر را تغییر دهید' : ''}</div>
                        </div>
                    </td>
                </tr>
            `;
            return;
        }

        const maxSize = Math.max(...data.map(t => t.size_mb || 0), 1);

        tbody.innerHTML = data.map((t, i) => {
            const sizePercent = Math.min(((t.size_mb || 0) / maxSize) * 100, 100);

            return `
                <tr style="animation: slideUp 0.3s var(--ease-out) backwards; animation-delay:${Math.min(i * 0.02, 0.3)}s;">
                    <td style="color:var(--text-muted);font-size:0.65rem;font-family:var(--font-mono);">${i + 1}</td>
                    <td><strong>${escapeHtml(t.table_name || '—')}</strong></td>
                    <td style="font-family:var(--font-mono);">${(t.row_count || 0).toLocaleString('en-US')}</td>
                    <td style="font-family:var(--font-mono);">${(t.size_mb || 0).toFixed(2)}</td>
                    <td>
                        <div class="size-bar-wrapper">
                            <span class="size-text">${Math.round(sizePercent)}%</span>
                            <div class="size-bar-track">
                                <div class="size-bar" style="width:${sizePercent}%;"></div>
                            </div>
                        </div>
                    </td>
                    <td>
                        <div class="row-actions">
                            <button class="btn-icon purple" onclick="DatabasePage.viewPGTable('${escapeAttr(t.table_name)}')" title="مشاهده">
                                <i class="fas fa-eye"></i>
                            </button>
                            <button class="btn-icon" onclick="DatabasePage.copyPGMeta('${escapeAttr(t.table_name)}')" title="کپی اطلاعات">
                                <i class="fas fa-copy"></i>
                            </button>
                        </div>
                    </td>
                </tr>
            `;
        }).join('');
    }

    function renderPGError(message) {
        const tbody = document.getElementById('pgTableBody');
        if (!tbody) return;

        tbody.innerHTML = `
            <tr>
                <td colspan="6" style="padding:0;">
                    <div class="db-empty">
                        <span class="empty-icon" style="color:var(--color-red);">⚠️</span>
                        <div class="empty-title" style="color:var(--color-red);">خطا در بارگذاری</div>
                        <div class="empty-message">${escapeHtml(message)}</div>
                        <button class="btn btn-primary btn-sm" style="margin-top:16px;" onclick="DatabasePage.refreshPostgreSQL(true)">
                            <i class="fas fa-sync-alt"></i>
                            <span>تلاش مجدد</span>
                        </button>
                    </div>
                </td>
            </tr>
        `;
    }

    // ============================================================
    // ۳. Load Redis
    // ============================================================

    async function loadRedis(force = false) {
        const tbody = document.getElementById('redisTableBody');
        if (!tbody) return;

        if (!force) {
            const cached = getCache('redis');
            if (cached) {
                state.redisData = cached.data;
                renderRedisStats(cached.stats);
                renderRedisTable(applyRedisFilters(cached.data));
                return;
            }
        }

        showTabLoading('tab-redis');

        try {
            const data = await withRetry(() =>
                window.api.getRedisKeys({ limit: 200 })
            );

            if (!data?.success) {
                throw new Error(data?.error || 'خطا در دریافت کلیدها');
            }

            state.redisData = data.data || [];

            const stats = data.stats || {};
            setCache('redis', { data: state.redisData, stats }, 15000);

            renderRedisStats(stats);
            renderRedisTable(applyRedisFilters(state.redisData));

            state.lastUpdated.redis = new Date();

        } catch (err) {
            console.error('❌ Redis error:', err);
            renderRedisError(err.message);
        } finally {
            hideTabLoading();
        }
    }

    function renderRedisStats(stats) {
        setText('redisKeyCount', stats.total_keys || state.redisData.length);
        setText('redisMemory', stats.memory || '—');
        setText('redisClients', stats.clients || '—');
    }

    function applyRedisFilters(data) {
        const { search, type } = state.filters.redis;

        let filtered = data.filter(k =>
            (k.key || '').toLowerCase().includes(search.toLowerCase())
        );

        if (type !== 'all') {
            filtered = filtered.filter(k => k.type === type);
        }

        return filtered;
    }

    function renderRedisTable(data) {
        const tbody = document.getElementById('redisTableBody');
        if (!tbody) return;

        if (!data || data.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="6" style="padding:0;">
                        <div class="db-empty">
                            <span class="empty-icon">🔑</span>
                            <div class="empty-title">هیچ کلیدی یافت نشد</div>
                            <div class="empty-message">Redis خالی است یا فیلتر نتیجه‌ای ندارد</div>
                        </div>
                    </td>
                </tr>
            `;
            return;
        }

        const typeClasses = {
            string: 'string',
            hash: 'hash',
            list: 'list',
            set: 'set',
            zset: 'zset',
        };

        tbody.innerHTML = data.slice(0, 100).map((k, i) => {
            const preview = k.value
                ? (typeof k.value === 'object'
                    ? JSON.stringify(k.value).slice(0, 40)
                    : String(k.value).slice(0, 40))
                : '—';

            return `
                <tr style="animation: slideUp 0.3s var(--ease-out) backwards; animation-delay:${Math.min(i * 0.015, 0.3)}s;">
                    <td style="color:var(--text-muted);font-size:0.65rem;font-family:var(--font-mono);">${i + 1}</td>
                    <td style="font-family:var(--font-mono);font-size:0.7rem;">${escapeHtml(k.key || '—')}</td>
                    <td><span class="badge-type ${typeClasses[k.type] || 'string'}">${escapeHtml(k.type || '—')}</span></td>
                    <td style="font-family:var(--font-mono);font-size:0.7rem;">${k.ttl || '—'}</td>
                    <td style="font-size:0.65rem;color:var(--text-secondary);max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">
                        ${escapeHtml(preview)}
                    </td>
                    <td>
                        <div class="row-actions">
                            <button class="btn-icon purple" onclick="DatabasePage.viewRedisKey('${escapeAttr(k.key)}')" title="مشاهده">
                                <i class="fas fa-eye"></i>
                            </button>
                            <button class="btn-icon" onclick="DatabasePage.copyRedisKey('${escapeAttr(k.key)}')" title="کپی">
                                <i class="fas fa-copy"></i>
                            </button>
                            <button class="btn-icon danger" onclick="DatabasePage.deleteRedisKey('${escapeAttr(k.key)}')" title="حذف">
                                <i class="fas fa-trash"></i>
                            </button>
                        </div>
                    </td>
                </tr>
            `;
        }).join('');
    }

    function renderRedisError(message) {
        const tbody = document.getElementById('redisTableBody');
        if (!tbody) return;

        tbody.innerHTML = `
            <tr>
                <td colspan="6" style="padding:0;">
                    <div class="db-empty">
                        <span class="empty-icon" style="color:var(--color-red);">⚠️</span>
                        <div class="empty-title" style="color:var(--color-red);">خطا در بارگذاری</div>
                        <div class="empty-message">${escapeHtml(message)}</div>
                        <button class="btn btn-primary btn-sm" style="margin-top:16px;" onclick="DatabasePage.refreshRedis(true)">
                            <i class="fas fa-sync-alt"></i>
                            <span>تلاش مجدد</span>
                        </button>
                    </div>
                </td>
            </tr>
        `;
    }

    // ============================================================
    // ۴. Load Archive
    // ============================================================

    async function loadArchive(force = false) {
        const tbody = document.getElementById('archiveTableBody');
        if (!tbody) return;

        if (!force) {
            const cached = getCache('archive');
            if (cached) {
                state.archiveData = cached;
                renderArchiveTable(applyArchiveFilters(cached));
                return;
            }
        }

        showTabLoading('tab-archive');

        try {
            const data = await withRetry(() =>
                window.api.getArchiveTables()
            );

            if (!data?.success) {
                throw new Error(data?.error || 'خطا در دریافت جدول‌ها');
            }

            state.archiveData = data.data || [];
            setCache('archive', state.archiveData, 20000);

            // Stats
            setText('archiveTableCount', state.archiveData.length);

            let totalSize = 0;
            let totalRows = 0;
            state.archiveData.forEach(t => {
                totalSize += t.size_mb || 0;
                totalRows += t.row_count || 0;
            });

            setText('archiveSize', totalSize.toFixed(1) + ' MB');
            setText('archiveRows', totalRows.toLocaleString('en-US'));

            renderArchiveTable(applyArchiveFilters(state.archiveData));

            state.lastUpdated.archive = new Date();

        } catch (err) {
            console.error('❌ Archive error:', err);
            renderArchiveError(err.message);
        } finally {
            hideTabLoading();
        }
    }

    function applyArchiveFilters(data) {
        const { search } = state.filters.archive;
        return data.filter(t =>
            (t.table_name || '').toLowerCase().includes(search.toLowerCase())
        );
    }

    function renderArchiveTable(data) {
        const tbody = document.getElementById('archiveTableBody');
        if (!tbody) return;

        if (!data || data.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="5" style="padding:0;">
                        <div class="db-empty">
                            <span class="empty-icon">📦</span>
                            <div class="empty-title">هیچ جدولی یافت نشد</div>
                            <div class="empty-message">Archive خالی است</div>
                        </div>
                    </td>
                </tr>
            `;
            return;
        }

        const maxSize = Math.max(...data.map(t => t.size_mb || 0), 1);

        tbody.innerHTML = data.map((t, i) => {
            const size = (t.size_mb || 0).toFixed(2);
            const sizePercent = Math.min(((t.size_mb || 0) / maxSize) * 100, 100);

            return `
                <tr style="animation: slideUp 0.3s var(--ease-out) backwards; animation-delay:${Math.min(i * 0.02, 0.3)}s;">
                    <td style="color:var(--text-muted);font-size:0.65rem;font-family:var(--font-mono);">${i + 1}</td>
                    <td><strong>${escapeHtml(t.table_name || '—')}</strong></td>
                    <td style="font-family:var(--font-mono);">${(t.row_count || 0).toLocaleString('en-US')}</td>
                    <td style="font-family:var(--font-mono);">${size} MB</td>
                    <td>
                        <div class="row-actions">
                            <button class="btn-icon purple" onclick="DatabasePage.viewArchiveTable('${escapeAttr(t.table_name)}')" title="مشاهده">
                                <i class="fas fa-eye"></i>
                            </button>
                            <button class="btn-icon" onclick="DatabasePage.copyArchiveMeta('${escapeAttr(t.table_name)}')" title="کپی">
                                <i class="fas fa-copy"></i>
                            </button>
                        </div>
                    </td>
                </tr>
            `;
        }).join('');
    }

    function renderArchiveError(message) {
        const tbody = document.getElementById('archiveTableBody');
        if (!tbody) return;

        tbody.innerHTML = `
            <tr>
                <td colspan="5" style="padding:0;">
                    <div class="db-empty">
                        <span class="empty-icon" style="color:var(--color-red);">⚠️</span>
                        <div class="empty-title" style="color:var(--color-red);">خطا در بارگذاری</div>
                        <div class="empty-message">${escapeHtml(message)}</div>
                        <button class="btn btn-primary btn-sm" style="margin-top:16px;" onclick="DatabasePage.refreshArchive(true)">
                            <i class="fas fa-sync-alt"></i>
                            <span>تلاش مجدد</span>
                        </button>
                    </div>
                </td>
            </tr>
        `;
    }

    // ============================================================
    // ۵. Load Monitor
    // ============================================================

    async function loadMonitor() {
        const container = document.getElementById('monitorContent');
        if (!container) return;

        try {
            const [healthRes, redisStatsRes, pgStatsRes, archiveStatsRes] = await Promise.allSettled([
                window.api.getHealthSummary(),
                window.api.getRedisStats(),
                window.api.getPostgreSQLStats('primary'),
                window.api.getArchiveStats(),
            ]);

            const health = healthRes.status === 'fulfilled' ? healthRes.value?.data : null;
            const redisStats = redisStatsRes.status === 'fulfilled' ? redisStatsRes.value?.data : null;
            const pgStats = pgStatsRes.status === 'fulfilled' ? pgStatsRes.value?.data : null;
            const archiveStats = archiveStatsRes.status === 'fulfilled' ? archiveStatsRes.value?.data : null;

            const details = health?.details || {};
            const dbNames = Object.keys(details);

            let connected = 0;
            let disconnected = 0;
            dbNames.forEach(name => {
                if (details[name]?.connected) connected++;
                else disconnected++;
            });

            const total = dbNames.length;
            const avgHealth = total > 0
                ? Math.round(
                    dbNames.reduce((sum, name) => {
                        const isConn = details[name]?.connected;
                        return sum + (isConn ? 100 : 0);
                    }, 0) / total
                )
                : 0;

            let html = `
                <div class="monitor-grid">
                    <div class="monitor-card">
                        <div class="m-value green">${connected}</div>
                        <div class="m-label">🟢 متصل</div>
                    </div>
                    <div class="monitor-card">
                        <div class="m-value red">${disconnected}</div>
                        <div class="m-label">🔴 قطع</div>
                    </div>
                    <div class="monitor-card">
                        <div class="m-value cyan">${total}</div>
                        <div class="m-label">📊 کل</div>
                    </div>
                    <div class="monitor-card">
                        <div class="m-value ${avgHealth > 70 ? 'green' : avgHealth > 40 ? 'orange' : 'red'}">
                            ${avgHealth}
                        </div>
                        <div class="m-label">💚 سلامت</div>
                    </div>
                </div>
            `;

            html += `<div class="monitor-status-list">`;

            const icons = {
                postgresql: '🐘',
                postgres: '🐘',
                redis: '⚡',
                archive: '📦',
                primary: '🗄️',
                backup: '💾',
                analytics: '📊',
                logs: '📝',
            };

            dbNames.forEach(name => {
                const info = details[name] || {};
                const isConnected = info.connected === true;
                const health = isConnected ? 100 : 0;
                const healthColor = isConnected ? 'var(--color-green)' : 'var(--color-red)';
                const icon = icons[info.type] || icons[name] || '📦';

                html += `
                    <div class="monitor-status-item">
                        <div class="name">
                            <span class="icon">${icon}</span>
                            <span>${escapeHtml(name)}</span>
                            <span class="version">${escapeHtml(info.version || '')}</span>
                        </div>
                        <div class="status-group">
                            <div class="health-bar">
                                <div class="fill" style="width:${health}%;background:${healthColor};"></div>
                            </div>
                            <span class="health-text" style="color:${healthColor};">${health}%</span>
                            <span class="ping-text">${isConnected ? (info.ping_ms || 0) + 'ms' : '—'}</span>
                        </div>
                    </div>
                `;
            });

            html += `</div>`;

            html += `
                <div class="monitor-charts">
                    <div class="monitor-chart-wrapper">
                        <canvas id="monitorHealthChart"></canvas>
                    </div>
                    <div class="monitor-chart-wrapper">
                        <canvas id="monitorSizeChart"></canvas>
                    </div>
                </div>
            `;

            container.innerHTML = html;

            renderMonitorCharts(dbNames, details, redisStats, pgStats, archiveStats);

            state.lastUpdated.monitor = new Date();

        } catch (err) {
            console.error('❌ Monitor error:', err);
            container.innerHTML = `
                <div class="db-empty">
                    <span class="empty-icon" style="color:var(--color-red);">⚠️</span>
                    <div class="empty-title" style="color:var(--color-red);">خطا در مانیتورینگ</div>
                    <div class="empty-message">${escapeHtml(err.message)}</div>
                </div>
            `;
        }
    }

    function renderMonitorCharts(dbNames, details, redisStats, pgStats, archiveStats) {
        if (typeof Chart === 'undefined') return;

        const textColor = getComputedStyle(document.documentElement)
            .getPropertyValue('--text-secondary').trim() || '#94a3b8';

        const ctx1 = document.getElementById('monitorHealthChart');
        if (ctx1) {
            const healthData = dbNames.map(name => details[name]?.connected ? 100 : 0);

            if (window._monitorHealthChart) {
                window._monitorHealthChart.destroy();
            }

            window._monitorHealthChart = new Chart(ctx1, {
                type: 'bar',
                data: {
                    labels: dbNames,
                    datasets: [{
                        label: 'سلامت (%)',
                        data: healthData,
                        backgroundColor: healthData.map(v =>
                            v > 70 ? 'rgba(34, 211, 238, 0.7)' :
                            v > 40 ? 'rgba(245, 158, 11, 0.7)' :
                            'rgba(239, 68, 68, 0.7)'
                        ),
                        borderColor: healthData.map(v =>
                            v > 70 ? '#22d3ee' :
                            v > 40 ? '#f59e0b' :
                            '#ef4444'
                        ),
                        borderWidth: 1.5,
                        borderRadius: 6,
                    }],
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { display: false },
                        title: {
                            display: true,
                            text: 'سلامت دیتابیس‌ها',
                            color: textColor,
                            font: { size: 11, family: 'inherit' },
                        },
                    },
                    scales: {
                        y: {
                            min: 0,
                            max: 100,
                            ticks: {
                                color: textColor,
                                font: { size: 9 },
                                callback: v => v + '%',
                            },
                            grid: { color: 'rgba(255, 255, 255, 0.05)' },
                        },
                        x: {
                            ticks: { color: textColor, font: { size: 9 } },
                            grid: { display: false },
                        },
                    },
                },
            });
        }

        const ctx2 = document.getElementById('monitorSizeChart');
        if (ctx2) {
            const sizeData = [
                pgStats?.size_mb || 0,
                redisStats?.memory_mb || redisStats?.used_memory_mb || 0,
                archiveStats?.size_mb || 0,
            ];
            const sizeLabels = ['PostgreSQL', 'Redis', 'Archive'];

            if (window._monitorSizeChart) {
                window._monitorSizeChart.destroy();
            }

            window._monitorSizeChart = new Chart(ctx2, {
                type: 'doughnut',
                data: {
                    labels: sizeLabels,
                    datasets: [{
                        data: sizeData,
                        backgroundColor: [
                            'rgba(0, 212, 255, 0.7)',
                            'rgba(239, 68, 68, 0.7)',
                            'rgba(139, 92, 246, 0.7)',
                        ],
                        borderColor: ['#00d4ff', '#ef4444', '#8b5cf6'],
                        borderWidth: 2,
                    }],
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: {
                            position: 'bottom',
                            labels: {
                                color: textColor,
                                font: { size: 10 },
                                padding: 12,
                                usePointStyle: true,
                            },
                        },
                        title: {
                            display: true,
                            text: 'حجم دیتابیس‌ها (MB)',
                            color: textColor,
                            font: { size: 11, family: 'inherit' },
                        },
                    },
                    cutout: '60%',
                },
            });
        }
    }

    // ============================================================
    // ۶. Tabs
    // ============================================================

    function initTabs() {
        const tabs = document.querySelectorAll('#dbTabs .tab-btn');
        const contents = document.querySelectorAll('.tab-content');

        tabs.forEach(btn => {
            btn.addEventListener('click', () => {
                const tabName = btn.dataset.tab;
                state.activeTab = tabName;

                tabs.forEach(b => b.classList.remove('active'));
                btn.classList.add('active');

                contents.forEach(c => c.classList.remove('active'));
                const target = document.getElementById(`tab-${tabName}`);
                if (target) target.classList.add('active');

                // لود محتوای تب
                const loaders = {
                    overview: loadOverview,
                    postgresql: loadPostgreSQL,
                    redis: loadRedis,
                    archive: loadArchive,
                    monitor: loadMonitor,
                };

                if (loaders[tabName]) {
                    try { loaders[tabName](); } catch (e) { console.error(e); }
                }
            });
        });
    }

    // ============================================================
    // ۷. Debounced Filters
    // ============================================================

    const debouncedPGFilter = debounce(() => {
        renderPGTable(applyPGFilters(state.pgData));
    }, 300);

    const debouncedRedisFilter = debounce(() => {
        renderRedisTable(applyRedisFilters(state.redisData));
    }, 300);

    const debouncedArchiveFilter = debounce(() => {
        renderArchiveTable(applyArchiveFilters(state.archiveData));
    }, 300);

    function onPGSearchChange() {
        state.filters.pg.search = document.getElementById('pgSearch')?.value || '';
        debouncedPGFilter();
    }

    function onPGFilterChange() {
        state.filters.pg.size = document.getElementById('pgFilter')?.value || 'all';
        renderPGTable(applyPGFilters(state.pgData));
    }

    function onRedisSearchChange() {
        state.filters.redis.search = document.getElementById('redisSearch')?.value || '';
        debouncedRedisFilter();
    }

    function onRedisTypeChange() {
        state.filters.redis.type = document.getElementById('redisTypeFilter')?.value || 'all';
        renderRedisTable(applyRedisFilters(state.redisData));
    }

    function onArchiveSearchChange() {
        state.filters.archive.search = document.getElementById('archiveSearch')?.value || '';
        debouncedArchiveFilter();
    }

    // ============================================================
    // ۸. PostgreSQL Actions
    // ============================================================

    async function viewPGTable(tableName) {
        if (!tableName) return;

        if (window.loadingSystem?.showModal) {
            window.loadingSystem.showModal({
                messages: [`در حال دریافت ${tableName}...`],
                duration: 3000,
                showProgress: false,
                color: '#00d4ff',
            });
        }

        try {
            const data = await withRetry(() =>
                window.api.getPostgreSQLTableData('primary', tableName, { limit: 20 })
            );

            if (window.loadingSystem?.hideModal) {
                window.loadingSystem.hideModal();
            }

            if (!data?.success || !data.data) {
                if (typeof showToast === 'function') showToast('❌ خطا در دریافت داده‌ها', 'error');
                return;
            }

            const rows = data.data.rows || [];
            const columns = data.data.columns || [];

            if (rows.length === 0) {
                if (typeof showToast === 'function') showToast(`📭 جدول ${tableName} خالی است`, 'info');
                return;
            }

            let msg = `📋 جدول: ${tableName}\n📊 ${rows.length} رکورد\n\n`;
            msg += columns.join(' | ') + '\n';
            msg += '─'.repeat(50) + '\n';

            rows.slice(0, 10).forEach(row => {
                msg += columns.map(c => String(row[c] || '').slice(0, 20)).join(' | ') + '\n';
            });

            if (rows.length > 10) {
                msg += `\n... و ${rows.length - 10} رکورد دیگر`;
            }

            alert(msg);

        } catch (err) {
            if (window.loadingSystem?.hideModal) window.loadingSystem.hideModal();
            if (typeof showToast === 'function') showToast('❌ ' + err.message, 'error');
        }
    }

    function copyPGMeta(tableName) {
        const t = state.pgData.find(x => x.table_name === tableName);
        if (!t) return;

        const text = `نام جدول: ${t.table_name}\nرکوردها: ${t.row_count || 0}\nحجم: ${(t.size_mb || 0).toFixed(2)} MB`;

        if (typeof copyToClipboard === 'function') {
            copyToClipboard(text);
        } else {
            navigator.clipboard.writeText(text).then(() => {
                if (typeof showToast === 'function') showToast('📋 کپی شد', 'success');
            });
        }
    }

    function copyPGTable() {
        if (state.pgData.length === 0) {
            if (typeof showToast === 'function') showToast('⚠️ داده‌ای نیست', 'warning');
            return;
        }

        const header = 'نام جدول\tرکوردها\tحجم (MB)\n' +
            state.pgData.map(t =>
                `${t.table_name}\t${t.row_count || 0}\t${(t.size_mb || 0).toFixed(2)}`
            ).join('\n');

        if (typeof copyToClipboard === 'function') {
            copyToClipboard(header);
        }
    }

    function exportPGTable() {
        if (state.pgData.length === 0) {
            if (typeof showToast === 'function') showToast('⚠️ داده‌ای نیست', 'warning');
            return;
        }

        const headers = ['نام جدول', 'رکوردها', 'حجم (MB)'];
        const rows = state.pgData.map(t => [
            t.table_name,
            t.row_count || 0,
            (t.size_mb || 0).toFixed(2),
        ]);

        const csv = [headers, ...rows]
            .map(r => r.map(escapeCsv).join(','))
            .join('\n');

        downloadCSV(csv, `postgresql_tables_${new Date().toISOString().slice(0, 10)}.csv`);
    }

    // ============================================================
    // ۹. Redis Actions
    // ============================================================

    async function viewRedisKey(key) {
        if (!key) return;

        if (window.loadingSystem?.showModal) {
            window.loadingSystem.showModal({
                messages: [`در حال دریافت ${key}...`],
                duration: 2000,
                showProgress: false,
                color: '#ef4444',
            });
        }

        try {
            const data = await withRetry(() => window.api.getRedisKey(key));

            if (window.loadingSystem?.hideModal) window.loadingSystem.hideModal();

            if (data?.success && data.data) {
                const value = data.data.value;
                let display = value;

                if (typeof value === 'object') {
                    display = JSON.stringify(value, null, 2);
                }

                alert(`📋 کلید: ${key}\n\n📦 مقدار:\n${display}`);
            } else {
                if (typeof showToast === 'function') showToast('❌ خطا در دریافت مقدار', 'error');
            }
        } catch (err) {
            if (window.loadingSystem?.hideModal) window.loadingSystem.hideModal();
            if (typeof showToast === 'function') showToast('❌ ' + err.message, 'error');
        }
    }

    function copyRedisKey(key) {
        if (typeof copyToClipboard === 'function') {
            copyToClipboard(key);
        } else {
            navigator.clipboard.writeText(key).then(() => {
                if (typeof showToast === 'function') showToast('📋 کپی شد', 'success');
            });
        }
    }

    async function deleteRedisKey(key) {
        if (!confirm(`⚠️ آیا از حذف کلید "${key}" اطمینان دارید؟`)) return;

        try {
            const data = await withRetry(() => window.api.deleteRedisKey(key));

            if (data?.success) {
                if (typeof showToast === 'function') showToast('🗑️ حذف شد', 'success');
                clearCache('redis');
                loadRedis(true);
            } else {
                if (typeof showToast === 'function') showToast('❌ خطا در حذف', 'error');
            }
        } catch (err) {
            if (typeof showToast === 'function') showToast('❌ ' + err.message, 'error');
        }
    }

    function copyRedisKeys() {
        if (state.redisData.length === 0) {
            if (typeof showToast === 'function') showToast('⚠️ داده‌ای نیست', 'warning');
            return;
        }

        const header = 'کلید\tنوع\tTTL\n' +
            state.redisData.map(k => `${k.key}\t${k.type}\t${k.ttl}`).join('\n');

        if (typeof copyToClipboard === 'function') {
            copyToClipboard(header);
        }
    }

    function exportRedisKeys() {
        if (state.redisData.length === 0) {
            if (typeof showToast === 'function') showToast('⚠️ داده‌ای نیست', 'warning');
            return;
        }

        const json = JSON.stringify(state.redisData, null, 2);
        const blob = new Blob([json], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `redis_keys_${new Date().toISOString().slice(0, 10)}.json`;
        a.click();
        URL.revokeObjectURL(url);
        if (typeof showToast === 'function') showToast('📥 دانلود شد', 'success');
    }

    async function clearRedis() {
        if (!confirm('⚠️ پاک کردن همه کلیدهای Redis؟')) return;

        if (window.loadingSystem?.showModal) {
            window.loadingSystem.showModal({
                messages: ['در حال پاک‌سازی Redis...|لطفاً صبر کنید'],
                duration: 3000,
                showProgress: true,
                color: '#ef4444',
            });
        }

        try {
            const data = await withRetry(() => window.api.clearRedis(true));

            if (window.loadingSystem?.hideModal) window.loadingSystem.hideModal();

            if (data?.success) {
                if (typeof showToast === 'function') showToast('🗑️ Redis پاک شد', 'success');
                clearCache('redis');
                loadRedis(true);
            } else {
                if (typeof showToast === 'function') showToast('❌ خطا', 'error');
            }
        } catch (err) {
            if (window.loadingSystem?.hideModal) window.loadingSystem.hideModal();
            if (typeof showToast === 'function') showToast('❌ ' + err.message, 'error');
        }
    }

    // ============================================================
    // ۱۰. Archive Actions
    // ============================================================

    async function viewArchiveTable(tableName) {
        if (!tableName) return;

        if (window.loadingSystem?.showModal) {
            window.loadingSystem.showModal({
                messages: [`در حال دریافت ${tableName}...`],
                duration: 3000,
                showProgress: false,
                color: '#8b5cf6',
            });
        }

        try {
            const data = await withRetry(() =>
                window.api.getArchiveTableData(tableName, { limit: 20 })
            );

            if (window.loadingSystem?.hideModal) window.loadingSystem.hideModal();

            if (!data?.success || !data.data) {
                if (typeof showToast === 'function') showToast('❌ خطا در دریافت داده‌ها', 'error');
                return;
            }

            const rows = data.data.rows || [];
            const columns = data.data.columns || [];

            if (rows.length === 0) {
                if (typeof showToast === 'function') showToast(`📭 جدول ${tableName} خالی است`, 'info');
                return;
            }

            let msg = `📦 Archive: ${tableName}\n📊 ${rows.length} رکورد\n\n`;
            msg += columns.join(' | ') + '\n';
            msg += '─'.repeat(50) + '\n';

            rows.slice(0, 10).forEach(row => {
                msg += columns.map(c => String(row[c] || '').slice(0, 20)).join(' | ') + '\n';
            });

            if (rows.length > 10) {
                msg += `\n... و ${rows.length - 10} رکورد دیگر`;
            }

            alert(msg);

        } catch (err) {
            if (window.loadingSystem?.hideModal) window.loadingSystem.hideModal();
            if (typeof showToast === 'function') showToast('❌ ' + err.message, 'error');
        }
    }

    function copyArchiveMeta(tableName) {
        const t = state.archiveData.find(x => x.table_name === tableName);
        if (!t) return;

        const text = `نام جدول: ${t.table_name}\nرکوردها: ${t.row_count || 0}\nحجم: ${(t.size_mb || 0).toFixed(2)} MB`;

        if (typeof copyToClipboard === 'function') {
            copyToClipboard(text);
        }
    }

    function copyArchiveTable() {
        if (state.archiveData.length === 0) return;

        const header = 'نام جدول\tرکوردها\n' +
            state.archiveData.map(t => `${t.table_name}\t${t.row_count || 0}`).join('\n');

        if (typeof copyToClipboard === 'function') {
            copyToClipboard(header);
        }
    }

    function exportArchiveTable() {
        if (state.archiveData.length === 0) {
            if (typeof showToast === 'function') showToast('⚠️ داده‌ای نیست', 'warning');
            return;
        }

        const headers = ['نام جدول', 'رکوردها', 'حجم (MB)'];
        const rows = state.archiveData.map(t => [
            t.table_name,
            t.row_count || 0,
            (t.size_mb || 0).toFixed(2),
        ]);

        const csv = [headers, ...rows]
            .map(r => r.map(escapeCsv).join(','))
            .join('\n');

        downloadCSV(csv, `archive_tables_${new Date().toISOString().slice(0, 10)}.csv`);
    }

    // ============================================================
    // ۱۱. Migration (با Modal Loading پیشرفته)
    // ============================================================

    async function runMigration() {
        if (state.isMigrationRunning) return;
        state.isMigrationRunning = true;

        const btn = document.getElementById('migrationBtn');
        const modal = document.getElementById('migrationModal');
        const closeBtn = document.getElementById('migrationCloseBtn');
        const errorEl = document.getElementById('migrationError');
        const outputEl = document.getElementById('migrationOutput');
        const spinner = document.getElementById('migrationSpinner');
        const titleEl = document.getElementById('migrationTitle');
        const subtitleEl = document.getElementById('migrationSubtitle');

        const steps = [1, 2, 3, 4, 5].map(i => document.getElementById(`step${i}`));

        // Reset
        if (btn) {
            btn.disabled = true;
            btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> در حال اجرا...';
        }
        if (errorEl) errorEl.classList.remove('show');
        if (outputEl) {
            outputEl.classList.remove('show');
            outputEl.textContent = '';
        }
        if (closeBtn) closeBtn.classList.remove('show');
        if (modal) modal.classList.add('active');
        if (spinner) spinner.style.display = 'block';
        if (titleEl) titleEl.textContent = 'در حال بروزرسانی دیتابیس...';
        if (subtitleEl) subtitleEl.textContent = 'لطفاً صبر کنید';

        steps.forEach((step) => {
            if (!step) return;
            step.className = '';
            const icon = step.querySelector('.icon');
            const statusIcon = step.querySelector('.status-icon');
            if (icon) icon.textContent = '⏳';
            if (statusIcon) statusIcon.textContent = '';
        });

        function updateStep(index, status) {
            const step = steps[index];
            if (!step) return;
            step.className = status;

            const icon = step.querySelector('.icon');
            const statusIcon = step.querySelector('.status-icon');

            if (status === 'active') {
                if (icon) icon.textContent = '🔄';
                if (statusIcon) statusIcon.textContent = '...';
            } else if (status === 'done') {
                if (icon) icon.textContent = '✅';
                if (statusIcon) statusIcon.textContent = '✔️';
            } else if (status === 'error') {
                if (icon) icon.textContent = '❌';
                if (statusIcon) statusIcon.textContent = '✖️';
            } else {
                if (icon) icon.textContent = '⏳';
                if (statusIcon) statusIcon.textContent = '';
            }
        }

        function sleep(ms) {
            return new Promise(resolve => setTimeout(resolve, ms));
        }

        try {
            updateStep(0, 'active');
            await sleep(1200);
            updateStep(0, 'done');

            updateStep(1, 'active');
            await sleep(1500);
            updateStep(1, 'done');

            updateStep(2, 'active');
            await sleep(1500);
            updateStep(2, 'done');

            updateStep(3, 'active');

            const response = await fetch('/api/db/migrate', {
                method: 'POST',
                credentials: 'include',
                headers: { 'Content-Type': 'application/json' },
            });

            const data = await response.json();

            if (data.success) {
                updateStep(3, 'done');
                if (outputEl && data.output) {
                    outputEl.textContent = data.output;
                    outputEl.classList.add('show');
                }
            } else {
                updateStep(3, 'error');
                throw new Error(data.error || data.output || 'خطا در migration');
            }

            updateStep(4, 'active');
            await sleep(1200);
            updateStep(4, 'done');

            // Success
            if (titleEl) titleEl.textContent = '✅ مهاجرت با موفقیت انجام شد!';
            if (subtitleEl) subtitleEl.textContent = 'همه جدول‌ها با موفقیت ایجاد یا به‌روز شدند.';
            if (spinner) spinner.style.display = 'none';
            if (closeBtn) closeBtn.classList.add('show');

            const statusEl = document.getElementById('migrationStatus');
            if (statusEl) {
                statusEl.innerHTML = '<span style="color:var(--color-green);">✅ دیتابیس به‌روز است</span>';
            }

            const lastRunEl = document.getElementById('migrationLastRun');
            if (lastRunEl) {
                lastRunEl.textContent = 'آخرین بروزرسانی: ' + new Date().toLocaleString('fa-IR');
            }

            // پاک کردن cache
            clearCache();

            setTimeout(() => {
                loadOverview(true);
                loadPostgreSQL(true);
                loadRedis(true);
                loadArchive(true);
            }, 500);

        } catch (error) {
            if (titleEl) titleEl.textContent = '❌ خطا در اجرای مهاجرت!';
            if (subtitleEl) subtitleEl.textContent = 'مشکلی در فرآیند رخ داده است.';
            if (spinner) spinner.style.display = 'none';
            if (errorEl) {
                errorEl.textContent = error.message || 'خطای ناشناخته';
                errorEl.classList.add('show');
            }
            if (closeBtn) closeBtn.classList.add('show');
        }

        state.isMigrationRunning = false;
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = '<i class="fas fa-play"></i> اجرای بروزرسانی';
        }
    }

    function closeMigrationModal() {
        const modal = document.getElementById('migrationModal');
        if (modal) modal.classList.remove('active');

        const closeBtn = document.getElementById('migrationCloseBtn');
        if (closeBtn) closeBtn.classList.remove('show');

        const spinner = document.getElementById('migrationSpinner');
        if (spinner) spinner.style.display = 'block';

        const errorEl = document.getElementById('migrationError');
        if (errorEl) errorEl.classList.remove('show');

        const outputEl = document.getElementById('migrationOutput');
        if (outputEl) outputEl.classList.remove('show');
    }

    // ============================================================
    // ۱۲. Auto Update Monitor (فقط تب فعال)
    // ============================================================

    function startActiveTabRefresh() {
        if (state.activeTabRefreshInterval) {
            clearInterval(state.activeTabRefreshInterval);
        }

        state.activeTabRefreshInterval = setInterval(() => {
            if (document.visibilityState !== 'visible') return;

            // فقط تب فعال
            switch (state.activeTab) {
                case 'overview':
                    loadOverview(true);
                    break;
                case 'postgresql':
                    loadPostgreSQL(true);
                    break;
                case 'redis':
                    loadRedis(true);
                    break;
                case 'archive':
                    loadArchive(true);
                    break;
                case 'monitor':
                    loadMonitor();
                    break;
            }
        }, 30000); // هر 30s
    }

    // ============================================================
    // ۱۳. Keyboard Shortcuts
    // ============================================================

    function initKeyboardShortcuts() {
        document.addEventListener('keydown', (e) => {
            // Ctrl+R / Cmd+R → refresh tab فعال
            if ((e.ctrlKey || e.metaKey) && e.key === 'r') {
                e.preventDefault();

                switch (state.activeTab) {
                    case 'overview':
                        loadOverview(true);
                        break;
                    case 'postgresql':
                        loadPostgreSQL(true);
                        break;
                    case 'redis':
                        loadRedis(true);
                        break;
                    case 'archive':
                        loadArchive(true);
                        break;
                    case 'monitor':
                        loadMonitor();
                        break;
                }

                if (typeof showToast === 'function') {
                    showToast('🔄 بروزرسانی تب فعال', 'info', 1500);
                }
            }

            // Escape → بستن modal migration
            if (e.key === 'Escape') {
                const modal = document.getElementById('migrationModal');
                if (modal?.classList.contains('active') && !state.isMigrationRunning) {
                    closeMigrationModal();
                }
            }
        });
    }

    // ============================================================
    // ۱۴. Init
    // ============================================================

    async function init() {
        console.log('🚀 Database page initializing...');

        initTabs();
        initKeyboardShortcuts();

        await Promise.allSettled([
            loadOverview(),
            loadPostgreSQL(),
            loadRedis(),
            loadArchive(),
        ]);

        startActiveTabRefresh();

        console.log('✅ Database page ready');
    }

    // ============================================================
    // ۱۵. Expose Actions
    // ============================================================

    window.DatabasePage = {
        // Loaders (force refresh)
        loadOverview: (force) => loadOverview(force !== false),
        loadPostgreSQL: (force) => loadPostgreSQL(force !== false),
        loadRedis: (force) => loadRedis(force !== false),
        loadArchive: (force) => loadArchive(force !== false),
        loadMonitor,

        // Alias refresh
        refreshPostgreSQL: (force) => loadPostgreSQL(force !== false),
        refreshRedis: (force) => loadRedis(force !== false),
        refreshArchive: (force) => loadArchive(force !== false),
        refreshMonitor: loadMonitor,

        // Filters
        onPGSearchChange,
        onPGFilterChange,
        onRedisSearchChange,
        onRedisTypeChange,
        onArchiveSearchChange,

        // PostgreSQL
        viewPGTable,
        copyPGMeta,
        copyPGTable,
        exportPGTable,

        // Redis
        viewRedisKey,
        copyRedisKey,
        deleteRedisKey,
        copyRedisKeys,
        exportRedisKeys,
        clearRedis,

        // Archive
        viewArchiveTable,
        copyArchiveMeta,
        copyArchiveTable,
        exportArchiveTable,

        // Migration
        runMigration,
        closeMigrationModal,

        // Utils
        clearCache,
    };

    // ============================================================
    // Start
    // ============================================================

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    window.addEventListener('beforeunload', () => {
        if (state.monitorInterval) clearInterval(state.monitorInterval);
        if (state.activeTabRefreshInterval) clearInterval(state.activeTabRefreshInterval);
        clearCache();
    });

    console.log('✅ Database script v3.0 loaded (with enhancements)');
})();
