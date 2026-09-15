// ============================================================
// utils.js - Utility Functions v12.0
// با استفاده از dayjs, jalaliday, radash, Notyf, SweetAlert2
// ============================================================

(function() {
    'use strict';
    
    // ============================================================
    // Setup Libraries
    // ============================================================
    
    // Day.js Setup
    if (typeof dayjs !== 'undefined') {
        // Plugins
        if (typeof dayjs_plugin_utc !== 'undefined') {
            dayjs.extend(dayjs_plugin_utc);
        }
        if (typeof dayjs_plugin_relativeTime !== 'undefined') {
            dayjs.extend(dayjs_plugin_relativeTime);
        }
        // Jalali (jalaliday)
        if (typeof jalaliday !== 'undefined') {
            dayjs.extend(jalaliday);
        }
        dayjs.locale('fa');
    }
    
    // Notyf Setup (Toast)
    const notyf = (typeof Notyf !== 'undefined') ? new Notyf({
        duration: 3000,
        position: { x: 'center', y: 'bottom' },
        dismissible: true,
        ripple: true,
        types: [
            {
                type: 'success',
                background: 'var(--accent-green, #22d3ee)',
                icon: { className: 'fas fa-check-circle', tagName: 'i', color: 'white' },
            },
            {
                type: 'error',
                background: 'var(--accent-red, #ef4444)',
                icon: { className: 'fas fa-times-circle', tagName: 'i', color: 'white' },
                duration: 5000,
            },
            {
                type: 'warning',
                background: 'var(--accent-orange, #f59e0b)',
                icon: { className: 'fas fa-exclamation-triangle', tagName: 'i', color: 'white' },
            },
            {
                type: 'info',
                background: 'var(--accent-cyan, #00d4ff)',
                icon: { className: 'fas fa-info-circle', tagName: 'i', color: 'white' },
            },
        ],
    }) : null;
    
    // NProgress Setup
    if (typeof NProgress !== 'undefined') {
        NProgress.configure({
            showSpinner: false,
            trickleSpeed: 200,
            minimum: 0.1,
        });
    }
    
    // Radash Setup (fallback به دستی اگه نیست)
    const _ = (typeof radash !== 'undefined') ? radash : {};
    
    // ============================================================
    // Toast System
    // ============================================================
    
    /**
     * نمایش Toast
     * 
     * @param {string} message - پیام
     * @param {string} type - نوع (success, error, warning, info)
     * @param {number} duration - مدت زمان (ms)
     */
    function showToast(message, type = 'info', duration = 3000) {
        if (notyf) {
            const options = {};
            if (duration !== 3000) options.duration = duration;
            
            switch (type) {
                case 'success':
                    return notyf.success(message);
                case 'error':
                    return notyf.error(message);
                case 'warning':
                    return notyf.open({ type: 'warning', message });
                case 'info':
                default:
                    return notyf.open({ type: 'info', message });
            }
        } else {
            // Fallback: دستی
            console.warn(`[Toast ${type}] ${message}`);
            return null;
        }
    }
    
    // ============================================================
    // Confirm & Alert (SweetAlert2)
    // ============================================================
    
    /**
     * Confirm Dialog
     * 
     * @param {string} title - عنوان
     * @param {string} text - متن
     * @param {string} confirmText - متن دکمه تأیید
     * @param {string} cancelText - متن دکمه انصراف
     * @returns {Promise<boolean>}
     */
    async function confirm(title, text = '', confirmText = 'تأیید', cancelText = 'انصراف') {
        if (typeof Swal === 'undefined') {
            return window.confirm(`${title}\n${text}`);
        }
        
        const result = await Swal.fire({
            title,
            text,
            icon: 'question',
            showCancelButton: true,
            confirmButtonText: confirmText,
            cancelButtonText: cancelText,
            confirmButtonColor: 'var(--accent-cyan, #00d4ff)',
            cancelButtonColor: 'var(--accent-red, #ef4444)',
            reverseButtons: true,
            customClass: {
                popup: 'swal-rtl',
            },
        });
        
        return result.isConfirmed;
    }
    
    /**
     * Alert Dialog
     */
    async function alertDialog(title, text = '', type = 'info') {
        if (typeof Swal === 'undefined') {
            window.alert(`${title}\n${text}`);
            return;
        }
        
        const icons = {
            success: 'success',
            error: 'error',
            warning: 'warning',
            info: 'info',
            question: 'question',
        };
        
        await Swal.fire({
            title,
            text,
            icon: icons[type] || 'info',
            confirmButtonText: 'باشه',
            confirmButtonColor: 'var(--accent-cyan, #00d4ff)',
            customClass: {
                popup: 'swal-rtl',
            },
        });
    }
    
    /**
     * Prompt Dialog
     */
    async function promptDialog(title, inputPlaceholder = '', inputType = 'text', defaultValue = '') {
        if (typeof Swal === 'undefined') {
            return window.prompt(title, defaultValue);
        }
        
        const result = await Swal.fire({
            title,
            input: inputType,
            inputPlaceholder,
            inputValue: defaultValue,
            showCancelButton: true,
            confirmButtonText: 'تأیید',
            cancelButtonText: 'انصراف',
            confirmButtonColor: 'var(--accent-cyan, #00d4ff)',
            reverseButtons: true,
            customClass: {
                popup: 'swal-rtl',
            },
        });
        
        return result.isConfirmed ? result.value : null;
    }
    
    // ============================================================
    // Progress Bar (NProgress)
    // ============================================================
    
    const progress = {
        start() {
            if (typeof NProgress !== 'undefined') NProgress.start();
        },
        done() {
            if (typeof NProgress !== 'undefined') NProgress.done();
        },
        set(percent) {
            if (typeof NProgress !== 'undefined') NProgress.set(percent);
        },
        inc() {
            if (typeof NProgress !== 'undefined') NProgress.inc();
        },
    };
    
    // ============================================================
    // Date & Time (dayjs + jalaliday)
    // ============================================================
    
    /**
     * تبدیل به تاریخ شمسی
     * 
     * @param {Date|string} date 
     * @param {string} format - فرمت خروجی
     * @returns {string}
     */
    function toJalali(date, format = 'YYYY/MM/DD') {
        if (!date) return '—';
        if (typeof dayjs === 'undefined') {
            return new Date(date).toLocaleDateString('fa-IR');
        }
        try {
            return dayjs(date).calendar('jalali').format(format);
        } catch (e) {
            return dayjs(date).format(format);
        }
    }
    
    /**
     * تاریخ و ساعت شمسی
     */
    function toJalaliDateTime(date) {
        return toJalali(date, 'YYYY/MM/DD HH:mm:ss');
    }
    
    /**
     * تاریخ شمسی کوتاه
     */
    function toJalaliShort(date) {
        return toJalali(date, 'MM/DD');
    }
    
    /**
     * فرمت تاریخ کامل (fa-IR)
     */
    function formatDate(date, locale = 'fa-IR') {
        if (!date) return '—';
        try {
            const d = typeof date === 'string' ? new Date(date) : date;
            if (isNaN(d.getTime())) return '—';
            return d.toLocaleDateString(locale, {
                year: 'numeric',
                month: 'short',
                day: 'numeric',
                hour: '2-digit',
                minute: '2-digit',
                second: '2-digit',
            });
        } catch {
            return '—';
        }
    }
    
    /**
     * زمان نسبی (چند دقیقه پیش)
     */
    function formatTimeAgo(date) {
        if (!date) return '—';
        
        if (typeof dayjs !== 'undefined' && dayjs_plugin_relativeTime) {
            try {
                return dayjs(date).fromNow();
            } catch {
                // fallback
            }
        }
        
        // Fallback دستی
        try {
            const d = typeof date === 'string' ? new Date(date) : date;
            const now = new Date();
            const diff = Math.floor((now - d) / 1000);
            
            if (diff < 60) return `${diff} ثانیه پیش`;
            if (diff < 3600) return `${Math.floor(diff / 60)} دقیقه پیش`;
            if (diff < 86400) return `${Math.floor(diff / 3600)} ساعت پیش`;
            if (diff < 604800) return `${Math.floor(diff / 86400)} روز پیش`;
            return formatDate(date);
        } catch {
            return '—';
        }
    }
    
    /**
     * مدت زمان
     */
    function formatDuration(seconds) {
        if (!seconds || seconds < 0) return '0s';
        
        const days = Math.floor(seconds / 86400);
        const hours = Math.floor((seconds % 86400) / 3600);
        const minutes = Math.floor((seconds % 3600) / 60);
        const secs = Math.floor(seconds % 60);
        
        const parts = [];
        if (days > 0) parts.push(`${days}d`);
        if (hours > 0 || days > 0) parts.push(`${hours}h`);
        if (minutes > 0 || hours > 0 || days > 0) parts.push(`${minutes}m`);
        parts.push(`${secs}s`);
        
        return parts.join(' ');
    }
    
    // Date helpers (نسبی)
    const dateHelpers = {
        addDays(date, days) {
            if (typeof dayjs !== 'undefined') return dayjs(date).add(days, 'day').toDate();
            const d = new Date(date);
            d.setDate(d.getDate() + days);
            return d;
        },
        addHours(date, hours) {
            if (typeof dayjs !== 'undefined') return dayjs(date).add(hours, 'hour').toDate();
            const d = new Date(date);
            d.setHours(d.getHours() + hours);
            return d;
        },
        startOfDay(date) {
            if (typeof dayjs !== 'undefined') return dayjs(date).startOf('day').toDate();
            const d = new Date(date);
            d.setHours(0, 0, 0, 0);
            return d;
        },
        endOfDay(date) {
            if (typeof dayjs !== 'undefined') return dayjs(date).endOf('day').toDate();
            const d = new Date(date);
            d.setHours(23, 59, 59, 999);
            return d;
        },
        isToday(date) {
            if (typeof dayjs !== 'undefined') return dayjs(date).isSame(dayjs(), 'day');
            const d = new Date(date);
            const today = new Date();
            return d.toDateString() === today.toDateString();
        },
        isYesterday(date) {
            const yesterday = this.addDays(new Date(), -1);
            return this.isToday(yesterday) && new Date(date).toDateString() === yesterday.toDateString();
        },
    };
    
    // ============================================================
    // Formatters
    // ============================================================
    
    function formatCurrency(value, currency = '$') {
        if (value === undefined || value === null || isNaN(value)) return '—';
        return `${currency}${Number(value).toLocaleString('en-US', {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
        })}`;
    }
    
    function formatNumber(value) {
        if (value === undefined || value === null || isNaN(value)) return '—';
        const num = Number(value);
        if (num >= 1_000_000_000) return `${(num / 1_000_000_000).toFixed(1)}B`;
        if (num >= 1_000_000) return `${(num / 1_000_000).toFixed(1)}M`;
        if (num >= 1_000) return `${(num / 1_000).toFixed(1)}K`;
        return num.toString();
    }
    
    function formatPercent(value) {
        if (value === undefined || value === null || isNaN(value)) return '—';
        const sign = value >= 0 ? '+' : '';
        return `${sign}${Number(value).toFixed(2)}%`;
    }
    
    function formatFileSize(bytes) {
        if (!bytes || bytes === 0) return '0 B';
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return `${(bytes / Math.pow(k, i)).toFixed(1)} ${sizes[i]}`;
    }
    
    function truncateText(text, maxLength = 50) {
        if (!text) return '—';
        if (text.length <= maxLength) return text;
        return text.slice(0, maxLength) + '...';
    }
    
    function getStatusColor(percent, thresholds = { warning: 60, danger: 80 }) {
        if (percent >= thresholds.danger) return 'red';
        if (percent >= thresholds.warning) return 'orange';
        return 'green';
    }
    
    function getStatusText(percent, thresholds = { warning: 60, danger: 80 }) {
        if (percent >= thresholds.danger) return '🚨 بحرانی';
        if (percent >= thresholds.warning) return '⚠️ هشدار';
        return '✅ سالم';
    }
    
    // ============================================================
    // DOM Helpers
    // ============================================================
    
    function $(selector, context = document) {
        return context.querySelector(selector);
    }
    
    function $$(selector, context = document) {
        return context.querySelectorAll(selector);
    }
    
    function createElement(tag, className = '', attributes = {}, children = []) {
        const el = document.createElement(tag);
        if (className) el.className = className;
        
        Object.entries(attributes).forEach(([key, value]) => {
            el.setAttribute(key, value);
        });
        
        children.forEach(child => {
            if (typeof child === 'string') {
                el.appendChild(document.createTextNode(child));
            } else if (child instanceof HTMLElement) {
                el.appendChild(child);
            }
        });
        
        return el;
    }
    
    function showLoading(container, message = 'در حال بارگذاری...') {
        if (!container) return;
        container.innerHTML = `
            <div class="loading-container">
                <div class="loading-spinner"></div>
                <p class="loading-text">${message}</p>
            </div>
        `;
    }
    
    function hideLoading(container) {
        if (!container) return;
        container.innerHTML = '';
    }
    
    function renderTable(data, columns, container, options = {}) {
        const { clickable = false, onRowClick = null } = options;
        
        let html = `<table class="table-modern"><thead><tr>`;
        columns.forEach(col => {
            html += `<th>${col.label || col.key}</th>`;
        });
        html += `</tr></thead><tbody>`;
        
        if (!data || data.length === 0) {
            html += `<tr><td colspan="${columns.length}" style="text-align:center;color:var(--text-muted);">📭 هیچ داده‌ای یافت نشد</td></tr>`;
        } else {
            data.forEach((row, index) => {
                html += `<tr${clickable ? ' style="cursor:pointer;"' : ''}`;
                if (clickable && onRowClick) {
                    html += ` onclick="(${onRowClick.toString()})(${index})"`;
                }
                html += `>`;
                columns.forEach(col => {
                    const value = row[col.key];
                    html += `<td>${col.format ? col.format(value) : (value !== undefined && value !== null ? value : '—')}</td>`;
                });
                html += `</tr>`;
            });
        }
        
        html += `</tbody></table>`;
        container.innerHTML = html;
    }
    
    // ============================================================
    // Clipboard
    // ============================================================
    
    async function copyToClipboard(text) {
        if (!text) {
            showToast('❌ چیزی برای کپی وجود ندارد', 'error');
            return;
        }
        
        try {
            await navigator.clipboard.writeText(text);
            showToast('📋 کپی شد!', 'success', 1500);
        } catch {
            const textarea = document.createElement('textarea');
            textarea.value = text;
            textarea.style.cssText = 'position:fixed;opacity:0;pointer-events:none;';
            document.body.appendChild(textarea);
            textarea.select();
            try {
                document.execCommand('copy');
                showToast('📋 کپی شد!', 'success', 1500);
            } catch {
                showToast('❌ خطا در کپی', 'error');
            }
            document.body.removeChild(textarea);
        }
    }
    
    function copyObjectToClipboard(obj) {
        try {
            const json = JSON.stringify(obj, null, 2);
            copyToClipboard(json);
        } catch (err) {
            showToast('❌ خطا در کپی', 'error');
        }
    }
    
    // ============================================================
    // Download
    // ============================================================
    
    function downloadFile(content, filename, mimeType = 'application/octet-stream') {
        const blob = new Blob([content], { type: mimeType });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        showToast('📥 دانلود شروع شد', 'success', 1500);
    }
    
    function downloadCSV(data, filename = 'data.csv') {
        if (!Array.isArray(data) || data.length === 0) {
            showToast('⚠️ داده‌ای برای دانلود نیست', 'warning');
            return;
        }
        
        const headers = Object.keys(data[0]);
        const csv = [
            headers.join(','),
            ...data.map(row => 
                headers.map(h => {
                    const val = row[h] ?? '';
                    const str = String(val);
                    if (str.includes(',') || str.includes('"') || str.includes('\n')) {
                        return `"${str.replace(/"/g, '""')}"`;
                    }
                    return str;
                }).join(',')
            ),
        ].join('\n');
        
        downloadFile('\ufeff' + csv, filename, 'text/csv;charset=utf-8;');
    }
    
    function downloadJSON(data, filename = 'data.json') {
        const json = JSON.stringify(data, null, 2);
        downloadFile(json, filename, 'application/json');
    }
    
    // ============================================================
    // Function Helpers
    // ============================================================
    
    function debounce(fn, delay = 300) {
        let timer = null;
        return function(...args) {
            clearTimeout(timer);
            timer = setTimeout(() => fn.apply(this, args), delay);
        };
    }
    
    function throttle(fn, limit = 300) {
        let inThrottle = false;
        return function(...args) {
            if (!inThrottle) {
                fn.apply(this, args);
                inThrottle = true;
                setTimeout(() => inThrottle = false, limit);
            }
        };
    }
    
    // ============================================================
    // Storage Helpers (با TTL)
    // ============================================================
    
    const storage = {
        set(key, value) {
            try {
                localStorage.setItem(key, JSON.stringify(value));
                return true;
            } catch {
                return false;
            }
        },
        
        get(key, defaultValue = null) {
            try {
                const item = localStorage.getItem(key);
                return item ? JSON.parse(item) : defaultValue;
            } catch {
                return defaultValue;
            }
        },
        
        setWithTTL(key, value, ttlSeconds) {
            try {
                const data = {
                    value,
                    expires: Date.now() + (ttlSeconds * 1000),
                };
                localStorage.setItem(key, JSON.stringify(data));
                return true;
            } catch {
                return false;
            }
        },
        
        getWithTTL(key, defaultValue = null) {
            try {
                const item = localStorage.getItem(key);
                if (!item) return defaultValue;
                
                const data = JSON.parse(item);
                if (data.expires && Date.now() > data.expires) {
                    localStorage.removeItem(key);
                    return defaultValue;
                }
                return data.value;
            } catch {
                return defaultValue;
            }
        },
        
        remove(key) {
            try {
                localStorage.removeItem(key);
                return true;
            } catch {
                return false;
            }
        },
        
        clear() {
            try {
                localStorage.clear();
                return true;
            } catch {
                return false;
            }
        },
        
        has(key) {
            return localStorage.getItem(key) !== null;
        },
    };
    
    // ============================================================
    // Business Helpers
    // ============================================================
    
    function getTripleScoreCoins(coins, limit = 5) {
        if (!coins || coins.length === 0) return [];
        
        const scored = coins.map(coin => {
            const rankScore = (100 - Math.min(coin.rank || 999, 100)) * 0.4;
            const change = Math.min(Math.max(coin.priceChange1d || 0, -20), 20);
            const changeScore = (change + 20) / 40 * 35;
            const volume = Math.min((coin.volume || 0) / 1e9, 10);
            const volumeScore = (volume / 10) * 25;
            
            return {
                ...coin,
                score: rankScore + changeScore + volumeScore,
            };
        });
        
        return scored
            .sort((a, b) => b.score - a.score)
            .slice(0, limit)
            .map(c => c.id);
    }
    
    function saveUserCoinSelection(coins) {
        if (coins && coins.length > 0) {
            storage.set('selectedTrainCoins', coins);
        }
    }
    
    function loadUserCoinSelection() {
        const saved = storage.get('selectedTrainCoins');
        if (Array.isArray(saved) && saved.length > 0) {
            return saved;
        }
        return null;
    }
    
    async function getSmartDefaultCoins(allCoins) {
        // ۱. اولویت با ارزهای مدل فعلی
        try {
            const status = await api.getModelStatus();
            if (status.success && status.data?.coins?.length > 0) {
                const modelCoins = status.data.coins;
                const validCoins = modelCoins.filter(id => 
                    allCoins.some(c => c.id === id)
                );
                if (validCoins.length > 0) {
                    return validCoins;
                }
            }
        } catch (e) {}
        
        // ۲. دومین اولویت: انتخاب‌های قبلی کاربر
        const userHistory = loadUserCoinSelection();
        if (userHistory && userHistory.length > 0) {
            const validCoins = userHistory.filter(id => 
                allCoins.some(c => c.id === id)
            );
            if (validCoins.length > 0) {
                return validCoins;
            }
        }
        
        // ۳. پیش‌فرض هوشمند
        return getTripleScoreCoins(allCoins, 5);
    }
    
    // ============================================================
    // String Helpers (از radash اگه هست)
    // ============================================================
    
    const stringHelpers = {
        capitalize(str) {
            if (!str) return '';
            if (typeof _.capitalize === 'function') return _.capitalize(str);
            return str.charAt(0).toUpperCase() + str.slice(1);
        },
        
        camelCase(str) {
            if (!str) return '';
            if (typeof _.camel === 'function') return _.camel(str);
            return str.replace(/-([a-z])/g, (g) => g[1].toUpperCase());
        },
        
        snakeCase(str) {
            if (!str) return '';
            if (typeof _.snake === 'function') return _.snake(str);
            return str.replace(/[A-Z]/g, (letter) => `_${letter.toLowerCase()}`);
        },
        
        slugify(str) {
            if (!str) return '';
            if (typeof _.slug === 'function') return _.slug(str);
            return str
                .toLowerCase()
                .replace(/[^a-z0-9\u0600-\u06FF]+/g, '-')
                .replace(/^-+|-+$/g, '');
        },
        
        escapeHtml(str) {
            if (!str) return '';
            return String(str)
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#39;');
        },
        
        mask(str, visibleStart = 4, visibleEnd = 4) {
            if (!str) return '';
            if (str.length <= visibleStart + visibleEnd) return str;
            const start = str.slice(0, visibleStart);
            const end = str.slice(-visibleEnd);
            const middle = '*'.repeat(Math.max(0, str.length - visibleStart - visibleEnd));
            return `${start}${middle}${end}`;
        },
    };
    
    // ============================================================
    // Array Helpers (از radash اگه هست)
    // ============================================================
    
    const arrayHelpers = {
        unique(arr) {
            if (!arr) return [];
            if (typeof _.unique === 'function') return _.unique(arr);
            return [...new Set(arr)];
        },
        
        uniqueBy(arr, key) {
            if (!arr) return [];
            if (typeof _.unique === 'function' && key) {
                return _.unique(arr, (item) => item[key]);
            }
            const seen = new Set();
            return arr.filter(item => {
                const k = item[key];
                if (seen.has(k)) return false;
                seen.add(k);
                return true;
            });
        },
        
        groupBy(arr, key) {
            if (!arr) return {};
            if (typeof _.group === 'function') {
                return _.group(arr, (item) => item[key]);
            }
            return arr.reduce((acc, item) => {
                const k = item[key];
                if (!acc[k]) acc[k] = [];
                acc[k].push(item);
                return acc;
            }, {});
        },
        
        chunk(arr, size) {
            if (!arr) return [];
            if (typeof _.chunk === 'function') return _.chunk(arr, size);
            const result = [];
            for (let i = 0; i < arr.length; i += size) {
                result.push(arr.slice(i, i + size));
            }
            return result;
        },
        
        sortBy(arr, key, order = 'asc') {
            if (!arr) return [];
            const sorted = [...arr].sort((a, b) => {
                const va = a[key];
                const vb = b[key];
                if (va < vb) return order === 'asc' ? -1 : 1;
                if (va > vb) return order === 'asc' ? 1 : -1;
                return 0;
            });
            return sorted;
        },
        
        sumBy(arr, key) {
            if (!arr) return 0;
            return arr.reduce((sum, item) => sum + (Number(item[key]) || 0), 0);
        },
        
        avgBy(arr, key) {
            if (!arr || arr.length === 0) return 0;
            return this.sumBy(arr, key) / arr.length;
        },
    };
    
    // ============================================================
    // Object Helpers (از radash اگه هست)
    // ============================================================
    
    const objectHelpers = {
        pick(obj, keys) {
            if (!obj) return {};
            if (typeof _.pick === 'function') return _.pick(obj, keys);
            const result = {};
            keys.forEach(key => {
                if (key in obj) result[key] = obj[key];
            });
            return result;
        },
        
        omit(obj, keys) {
            if (!obj) return {};
            if (typeof _.omit === 'function') return _.omit(obj, keys);
            const result = { ...obj };
            keys.forEach(key => delete result[key]);
            return result;
        },
        
        merge(target, source) {
            if (typeof _.merge === 'function') return _.merge(target, source);
            return { ...target, ...source };
        },
        
        deepClone(obj) {
            if (!obj) return obj;
            if (typeof _.clone === 'function') return _.clone(obj);
            try {
                return JSON.parse(JSON.stringify(obj));
            } catch {
                return obj;
            }
        },
        
        isEmpty(obj) {
            if (typeof _.isEmpty === 'function') return _.isEmpty(obj);
            if (!obj) return true;
            if (Array.isArray(obj)) return obj.length === 0;
            if (typeof obj === 'object') return Object.keys(obj).length === 0;
            return false;
        },
        
        deepGet(obj, path, defaultValue = null) {
            if (!obj || !path) return defaultValue;
            if (typeof _.get === 'function') return _.get(obj, path, defaultValue);
            const keys = path.split('.');
            let result = obj;
            for (const key of keys) {
                if (result === undefined || result === null) return defaultValue;
                result = result[key];
            }
            return result ?? defaultValue;
        },
    };
    
    // ============================================================
    // URL Helpers
    // ============================================================
    
    const urlHelpers = {
        buildQuery(params) {
            if (!params) return '';
            const query = new URLSearchParams();
            Object.entries(params).forEach(([key, value]) => {
                if (value !== undefined && value !== null && value !== '') {
                    query.append(key, value);
                }
            });
            const str = query.toString();
            return str ? `?${str}` : '';
        },
        
        parseQuery(queryString) {
            const params = {};
            const search = queryString.startsWith('?') ? queryString.slice(1) : queryString;
            new URLSearchParams(search).forEach((value, key) => {
                params[key] = value;
            });
            return params;
        },
        
        getQueryParam(name) {
            return new URLSearchParams(window.location.search).get(name);
        },
    };
    
    // ============================================================
    // Export to Window
    // ============================================================
    
    window.showToast = showToast;
    window.confirm = confirm;
    window.alertDialog = alertDialog;
    window.promptDialog = promptDialog;
    window.progress = progress;
    
    window.toJalali = toJalali;
    window.toJalaliDateTime = toJalaliDateTime;
    window.toJalaliShort = toJalaliShort;
    window.formatDate = formatDate;
    window.formatTimeAgo = formatTimeAgo;
    window.formatDuration = formatDuration;
    window.dateHelpers = dateHelpers;
    
    window.formatCurrency = formatCurrency;
    window.formatNumber = formatNumber;
    window.formatPercent = formatPercent;
    window.formatFileSize = formatFileSize;
    window.truncateText = truncateText;
    window.getStatusColor = getStatusColor;
    window.getStatusText = getStatusText;
    
    window.$ = $;
    window.$$ = $$;
    window.createElement = createElement;
    window.showLoading = showLoading;
    window.hideLoading = hideLoading;
    window.renderTable = renderTable;
    
    window.copyToClipboard = copyToClipboard;
    window.copyObjectToClipboard = copyObjectToClipboard;
    
    window.downloadFile = downloadFile;
    window.downloadCSV = downloadCSV;
    window.downloadJSON = downloadJSON;
    
    window.debounce = debounce;
    window.throttle = throttle;
    
    window.storage = storage;
    
    window.getTripleScoreCoins = getTripleScoreCoins;
    window.saveUserCoinSelection = saveUserCoinSelection;
    window.loadUserCoinSelection = loadUserCoinSelection;
    window.getSmartDefaultCoins = getSmartDefaultCoins;
    
    window.str = stringHelpers;
    window.arr = arrayHelpers;
    window.obj = objectHelpers;
    window.url = urlHelpers;
    
    // Alias برای دسترسی
    window.notyf = notyf;
    window.swal = (typeof Swal !== 'undefined') ? Swal : null;
    window.dayjs = (typeof dayjs !== 'undefined') ? dayjs : null;
    window._ = _;
    
    console.log('✅ Utils v12.0 loaded (with libraries)');
})();
