// static/js/script.js
// ============================================================
// اسکریپت‌های عمومی - نسخه ۲.۰
// ============================================================

(function() {
    'use strict';

    // ============================================================
    // ۱. Toast Notification
    // ============================================================
    
    function showToast(message, type = 'info') {
        const container = document.getElementById('toastContainer');
        if (!container) {
            // اگر container وجود نداشت، بساز
            const newContainer = document.createElement('div');
            newContainer.id = 'toastContainer';
            newContainer.style.cssText = `
                position: fixed;
                bottom: 20px;
                left: 50%;
                transform: translateX(-50%);
                z-index: 9999;
                display: flex;
                flex-direction: column;
                gap: 6px;
                align-items: center;
                pointer-events: none;
                width: 90%;
                max-width: 400px;
            `;
            document.body.appendChild(newContainer);
            return showToast(message, type);
        }

        const colors = {
            info: '#00d4ff',
            success: '#00ff88',
            error: '#ff4444',
            warning: '#ffaa00'
        };

        const toast = document.createElement('div');
        toast.className = 'toast ' + type;
        toast.textContent = message;
        toast.style.cssText = `
            padding: 10px 20px;
            background: rgba(8, 12, 24, 0.95);
            backdrop-filter: blur(20px);
            border: 2px solid ${colors[type] || colors.info};
            border-radius: 10px;
            color: #e8eef7;
            font-size: 0.85rem;
            box-shadow: 0 8px 40px rgba(0, 0, 0, 0.5);
            pointer-events: all;
            animation: toastIn 0.35s ease;
            text-align: center;
            width: 100%;
        `;

        // اضافه کردن انیمیشن
        const style = document.createElement('style');
        style.textContent = `
            @keyframes toastIn {
                from { opacity: 0; transform: translateY(20px) scale(0.95); }
                to { opacity: 1; transform: translateY(0) scale(1); }
            }
            .toast { transition: all 0.3s ease; }
        `;
        document.head.appendChild(style);

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
        if (status === 'ok' || status === 'healthy' || status === 'online' || status === 'success') {
            return 'success';
        }
        if (status === 'degraded' || status === 'warning' || status === 'partial') {
            return 'warning';
        }
        return 'error';
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
    // ۴. Export Functions
    // ============================================================

    window.showToast = showToast;
    window.formatNumber = formatNumber;
    window.formatDate = formatDate;
    window.getStatusColor = getStatusColor;
    window.copyToClipboard = copyToClipboard;

})();
