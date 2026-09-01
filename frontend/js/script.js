// static/js/script.js - توابع عمومی - نسخه ۳.۰

// ============================================================
// TOAST
// ============================================================
function showToast(message, type = 'info') {
    const container = document.getElementById('toastContainer');
    if (!container) {
        const newContainer = document.createElement('div');
        newContainer.id = 'toastContainer';
        newContainer.className = 'toast-container';
        document.body.appendChild(newContainer);
        return showToast(message, type);
    }

    const colors = {
        info: '#00d4ff',
        success: '#00ff88',
        error: '#ff4444',
        warning: '#ff8800'
    };

    const toast = document.createElement('div');
    toast.className = 'toast ' + type;
    toast.textContent = message;
    toast.style.borderColor = colors[type] || colors.info;

    container.appendChild(toast);

    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateY(-10px)';
        setTimeout(() => {
            if (toast.parentNode) toast.parentNode.removeChild(toast);
        }, 300);
    }, 3000);
}

// ============================================================
// FORMATTERS
// ============================================================
function formatNumber(num) {
    if (num === undefined || num === null) return '—';
    if (num >= 1_000_000) return (num / 1_000_000).toFixed(1) + 'M';
    if (num >= 1_000) return (num / 1_000).toFixed(1) + 'K';
    return num.toString();
}

function formatCurrency(num, currency = '$') {
    if (num === undefined || num === null) return '—';
    return currency + num.toLocaleString('en-US', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    });
}

function formatDate(dateStr) {
    if (!dateStr) return '—';
    try {
        const d = new Date(dateStr);
        return d.toLocaleDateString('fa-IR') + ' ' +
            d.toLocaleTimeString('fa-IR', { hour: '2-digit', minute: '2-digit' });
    } catch {
        return dateStr;
    }
}

function formatDuration(seconds) {
    if (seconds < 60) return seconds + 's';
    const days = Math.floor(seconds / 86400);
    seconds -= days * 86400;
    const hours = Math.floor(seconds / 3600);
    seconds -= hours * 3600;
    const minutes = Math.floor(seconds / 60);
    seconds -= minutes * 60;

    let parts = [];
    if (days > 0) parts.push(days + 'd');
    if (hours > 0 || days > 0) parts.push(hours + 'h');
    if (minutes > 0 || hours > 0 || days > 0) parts.push(minutes + 'm');
    parts.push(seconds + 's');
    return parts.join(' ');
}

// ============================================================
// CLIPBOARD
// ============================================================
function copyToClipboard(text) {
    if (!text) { showToast('❌ چیزی برای کپی وجود ندارد', 'error'); return; }

    if (navigator.clipboard) {
        navigator.clipboard.writeText(text)
            .then(() => showToast('📋 کپی شد!', 'success'))
            .catch(() => fallbackCopy(text));
    } else {
        fallbackCopy(text);
    }
}

function fallbackCopy(text) {
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

// ============================================================
// EXPORT
// ============================================================
window.showToast = showToast;
window.formatNumber = formatNumber;
window.formatCurrency = formatCurrency;
window.formatDate = formatDate;
window.formatDuration = formatDuration;
window.copyToClipboard = copyToClipboard;

console.log('✅ Script v3.0 loaded');
