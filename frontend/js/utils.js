// ============================================================
// utils.js - Utility Functions v10.0
// ============================================================

// ============================================================
// TOAST SYSTEM
// ============================================================

function showToast(message, type = 'info', duration = 3000) {
    let container = document.getElementById('toastContainer');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toastContainer';
        container.className = 'toast-container';
        document.body.appendChild(container);
    }

    const colors = {
        info: 'var(--accent-cyan)',
        success: 'var(--accent-green)',
        error: 'var(--accent-red)',
        warning: 'var(--accent-orange)'
    };

    const icons = {
        info: 'ℹ️',
        success: '✅',
        error: '❌',
        warning: '⚠️'
    };

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerHTML = `
        <span class="toast-icon">${icons[type] || 'ℹ️'}</span>
        <span class="toast-message">${message}</span>
    `;
    toast.style.borderColor = colors[type] || colors.info;

    container.appendChild(toast);

    requestAnimationFrame(() => {
        toast.style.opacity = '1';
        toast.style.transform = 'translateY(0)';
    });

    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateY(-20px)';
        setTimeout(() => {
            if (toast.parentNode) toast.parentNode.removeChild(toast);
        }, 300);
    }, duration);
}

// ============================================================
// FORMATTERS
// ============================================================

function formatCurrency(value, currency = '$') {
    if (value === undefined || value === null || isNaN(value)) return '—';
    return `${currency}${Number(value).toLocaleString('en-US', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
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
            second: '2-digit'
        });
    } catch {
        return '—';
    }
}

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

function formatTimeAgo(date) {
    if (!date) return '—';
    try {
        const d = typeof date === 'string' ? new Date(date) : date;
        const now = new Date();
        const diff = Math.floor((now - d) / 1000);
        
        if (diff < 60) return `${diff} ثانیه پیش`;
        if (diff < 3600) return `${Math.floor(diff / 60)} دقیقه پیش`;
        if (diff < 86400) return `${Math.floor(diff / 3600)} ساعت پیش`;
        if (diff < 604800) return `${Math.floor(diff / 86400)} روز پیش`;
        if (diff < 2592000) return `${Math.floor(diff / 604800)} هفته پیش`;
        return formatDate(date);
    } catch {
        return '—';
    }
}

// ===== جدید: فرمت کردن حجم فایل =====
function formatFileSize(bytes) {
    if (!bytes || bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return `${(bytes / Math.pow(k, i)).toFixed(1)} ${sizes[i]}`;
}

// ===== جدید: فرمت کردن زمان به صورت نسبی =====
function formatRelativeTime(date) {
    if (!date) return '—';
    try {
        const d = typeof date === 'string' ? new Date(date) : date;
        const now = new Date();
        const diff = Math.floor((now - d) / 1000);
        
        if (diff < 60) return `${Math.floor(diff)} ثانیه پیش`;
        if (diff < 3600) return `${Math.floor(diff / 60)} دقیقه پیش`;
        if (diff < 86400) return `${Math.floor(diff / 3600)} ساعت پیش`;
        if (diff < 604800) return `${Math.floor(diff / 86400)} روز پیش`;
        if (diff < 2592000) return `${Math.floor(diff / 604800)} هفته پیش`;
        return formatDate(date);
    } catch {
        return '—';
    }
}

// ===== جدید: برش متن با نشانگر =====
function truncateText(text, maxLength = 50) {
    if (!text) return '—';
    if (text.length <= maxLength) return text;
    return text.slice(0, maxLength) + '...';
}

// ===== جدید: دریافت وضعیت رنگ بر اساس درصد =====
function getStatusColor(percent, thresholds = { warning: 60, danger: 80 }) {
    if (percent >= thresholds.danger) return 'red';
    if (percent >= thresholds.warning) return 'orange';
    return 'green';
}

// ===== جدید: دریافت وضعیت متن بر اساس درصد =====
function getStatusText(percent, thresholds = { warning: 60, danger: 80 }) {
    if (percent >= thresholds.danger) return '🚨 بحرانی';
    if (percent >= thresholds.warning) return '⚠️ هشدار';
    return '✅ سالم';
}

// ============================================================
// DOM HELPERS
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

// ============================================================
// LOADING
// ============================================================

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

// ============================================================
// CLIPBOARD
// ============================================================

async function copyToClipboard(text) {
    if (!text) {
        showToast('❌ چیزی برای کپی وجود ندارد', 'error');
        return;
    }
    
    try {
        await navigator.clipboard.writeText(text);
        showToast('📋 کپی شد!', 'success');
    } catch {
        const textarea = document.createElement('textarea');
        textarea.value = text;
        textarea.style.cssText = 'position:fixed;opacity:0;pointer-events:none;';
        document.body.appendChild(textarea);
        textarea.select();
        try {
            document.execCommand('copy');
            showToast('📋 کپی شد!', 'success');
        } catch {
            showToast('❌ خطا در کپی', 'error');
        }
        document.body.removeChild(textarea);
    }
}

// ===== جدید: کپی کردن شیء به صورت JSON =====
function copyObjectToClipboard(obj) {
    try {
        const json = JSON.stringify(obj, null, 2);
        copyToClipboard(json);
    } catch (err) {
        showToast('❌ خطا در کپی', 'error');
    }
}

// ============================================================
// TABLE HELPERS
// ============================================================

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
// utils.js - اضافه کردن تابع پیش‌فرض هوشمند
// ============================================================

/**
 * محاسبه امتیاز ترکیبی ۳ گانه برای هر ارز
 * @param {Array} coins - لیست ارزها
 * @param {number} limit - تعداد ارزهای مورد نظر
 * @returns {Array} - لیست ID ارزهای برتر
 */
function getTripleScoreCoins(coins, limit = 5) {
    if (!coins || coins.length === 0) return [];
    
    const scored = coins.map(coin => {
        // ۱. امتیاز رتبه (۴۰٪)
        const rankScore = (100 - Math.min(coin.rank || 999, 100)) * 0.4;
        
        // ۲. امتیاز تغییرات (۳۵٪) - محدود به بازه -۲۰ تا +۲۰
        const change = Math.min(Math.max(coin.priceChange1d || 0, -20), 20);
        const changeScore = (change + 20) / 40 * 35;
        
        // ۳. امتیاز حجم (۲۵٪) - محدود به ۱۰ میلیارد
        const volume = Math.min((coin.volume || 0) / 1e9, 10);
        const volumeScore = (volume / 10) * 25;
        
        return {
            ...coin,
            score: rankScore + changeScore + volumeScore
        };
    });
    
    return scored
        .sort((a, b) => b.score - a.score)
        .slice(0, limit)
        .map(c => c.id);
}

// ===== ذخیره و بازیابی انتخاب‌های کاربر =====
function saveUserCoinSelection(coins) {
    if (coins && coins.length > 0) {
        localStorage.setItem('selectedTrainCoins', JSON.stringify(coins));
    }
}

function loadUserCoinSelection() {
    const saved = localStorage.getItem('selectedTrainCoins');
    if (saved) {
        try {
            const parsed = JSON.parse(saved);
            if (Array.isArray(parsed) && parsed.length > 0) {
                return parsed;
            }
        } catch (e) {}
    }
    return null;
}

// ===== دریافت پیش‌فرض هوشمند (با در نظر گرفتن مدل فعلی) =====
async function getSmartDefaultCoins(allCoins) {
    // ۱. اولویت با ارزهای مدل فعلی
    try {
        const status = await api.getModelStatus();
        if (status.success && status.data?.coins?.length > 0) {
            const modelCoins = status.data.coins;
            // بررسی وجود ارزها در لیست فعلی
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
    
    // ۳. پیش‌فرض هوشمند: ترکیبی ۳ گانه
    return getTripleScoreCoins(allCoins, 5);
}
// ============================================================
// EXPORT
// ============================================================

window.showToast = showToast;
window.formatCurrency = formatCurrency;
window.formatNumber = formatNumber;
window.formatPercent = formatPercent;
window.formatDate = formatDate;
window.formatDuration = formatDuration;
window.formatTimeAgo = formatTimeAgo;
window.formatFileSize = formatFileSize;
window.formatRelativeTime = formatRelativeTime;
window.truncateText = truncateText;
window.copyToClipboard = copyToClipboard;
window.copyObjectToClipboard = copyObjectToClipboard;
window.getStatusColor = getStatusColor;
window.getStatusText = getStatusText;
window.$ = $;
window.$$ = $$;
window.createElement = createElement;
window.showLoading = showLoading;
window.hideLoading = hideLoading;
window.renderTable = renderTable;

console.log('✅ Utils v10.0 loaded');
