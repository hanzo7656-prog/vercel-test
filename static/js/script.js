// static/js/script.js
// ============================================================
// اسکریپت‌های عمومی - نسخه ۳.۰
// ============================================================

(function() {
    'use strict';

    // ============================================================
    // ۱. Toast Notification
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
    // ۲. Utility Functions
    // ============================================================
    
    function formatNumber(num) {
        if (num === undefined || num === null) return '—';
        if (num >= 1000000) return (num / 1000000).toFixed(1) + 'M';
        if (num >= 1000) return (num / 1000).toFixed(1) + 'K';
        return num.toString();
    }

    function formatCurrency(num, currency = '$') {
        if (num === undefined || num === null) return '—';
        return currency + num.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }

    function formatDate(dateStr) {
        if (!dateStr) return '—';
        try {
            const d = new Date(dateStr);
            return d.toLocaleDateString('fa-IR') + ' ' + d.toLocaleTimeString('fa-IR', { hour: '2-digit', minute: '2-digit' });
        } catch {
            return dateStr;
        }
    }

    function getStatusColor(status) {
        const map = {
            'ok': 'success',
            'healthy': 'success',
            'online': 'success',
            'success': 'success',
            'degraded': 'warning',
            'warning': 'warning',
            'partial': 'warning',
            'error': 'error',
            'offline': 'error',
            'unhealthy': 'error'
        };
        return map[status] || 'info';
    }

    function getStatusEmoji(status) {
        const map = {
            'ok': '✅',
            'healthy': '✅',
            'online': '✅',
            'success': '✅',
            'degraded': '⚠️',
            'warning': '⚠️',
            'partial': '⚠️',
            'error': '❌',
            'offline': '❌',
            'unhealthy': '❌'
        };
        return map[status] || 'ℹ️';
    }

    // ============================================================
    // ۳. Copy to Clipboard
    // ============================================================
    
    function copyToClipboard(text) {
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
    // ۴. Fetch with Retry
    // ============================================================
    
    async function fetchWithRetry(url, options = {}, retries = 3, delay = 1000) {
        for (let i = 0; i < retries; i++) {
            try {
                const response = await fetch(url, options);
                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}: ${response.statusText}`);
                }
                return await response.json();
            } catch (error) {
                if (i === retries - 1) throw error;
                await new Promise(resolve => setTimeout(resolve, delay * (i + 1)));
            }
        }
    }

    // ============================================================
    // ۵. Export Functions
    // ============================================================

    window.showToast = showToast;
    window.formatNumber = formatNumber;
    window.formatCurrency = formatCurrency;
    window.formatDate = formatDate;
    window.getStatusColor = getStatusColor;
    window.getStatusEmoji = getStatusEmoji;
    window.copyToClipboard = copyToClipboard;
    window.fetchWithRetry = fetchWithRetry;

})();
