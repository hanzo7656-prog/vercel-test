// ============================================================
// utils.js - Utility Functions
// ============================================================

// ===== TOAST =====
function showToast(message, type = 'info', duration = 3000) {
    const container = document.getElementById('toastContainer') || (() => {
        const el = document.createElement('div');
        el.id = 'toastContainer';
        el.className = 'toast-container';
        document.body.appendChild(el);
        return el;
    })();
    
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
    
    // انیمیشن ورود
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

// ===== FORMATTERS =====
function formatCurrency(value, currency = '$') {
    if (value === undefined || value === null || isNaN(value)) return '—';
    return `${currency}${value.toLocaleString('en-US', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    })}`;
}

function formatNumber(value) {
    if (value === undefined || value === null || isNaN(value)) return '—';
    if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
    if (value >= 1_000) return `${(value / 1_000).toFixed(1)}K`;
    return value.toString();
}

function formatPercent(value) {
    if (value === undefined || value === null || isNaN(value)) return '—';
    const sign = value >= 0 ? '+' : '';
    return `${sign}${value.toFixed(2)}%`;
}

function formatDate(date, locale = 'fa-IR') {
    if (!date) return '—';
    try {
        const d = typeof date === 'string' ? new Date(date) : date;
        return d.toLocaleDateString(locale, {
            year: 'numeric',
            month: 'short',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit'
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

// ===== DOM HELPERS =====
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

// ===== LOADING =====
function showLoading(container, message = 'در حال بارگذاری...') {
    container.innerHTML = `
        <div class="loading-container">
            <div class="loading-spinner"></div>
            <p class="loading-text">${message}</p>
        </div>
    `;
}

function hideLoading(container) {
    container.innerHTML = '';
}

// ===== CLIPBOARD =====
async function copyToClipboard(text) {
    try {
        await navigator.clipboard.writeText(text);
        showToast('📋 کپی شد!', 'success');
    } catch {
        // Fallback
        const textarea = document.createElement('textarea');
        textarea.value = text;
        textarea.style.position = 'fixed';
        textarea.style.opacity = '0';
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

// ===== EXPORT =====
window.showToast = showToast;
window.formatCurrency = formatCurrency;
window.formatNumber = formatNumber;
window.formatPercent = formatPercent;
window.formatDate = formatDate;
window.formatDuration = formatDuration;
window.$ = $;
window.$$ = $$;
window.createElement = createElement;
window.showLoading = showLoading;
window.hideLoading = hideLoading;
window.copyToClipboard = copyToClipboard;

console.log('✅ Utils loaded');
