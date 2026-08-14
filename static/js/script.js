// ============================================================
// اسکریپت‌های عمومی سیستم
// ============================================================

// Format numbers with commas
function numberWithCommas(x) {
    return x.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}

// Format date
function formatDate(dateString) {
    const date = new Date(dateString);
    return date.toLocaleString('fa-IR', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
    });
}

// Copy to clipboard
function copyToClipboard(text) {
    navigator.clipboard.writeText(text).then(() => {
        showToast('📋 کپی شد!');
    }).catch(() => {
        // Fallback
        const textarea = document.createElement('textarea');
        textarea.value = text;
        document.body.appendChild(textarea);
        textarea.select();
        document.execCommand('copy');
        document.body.removeChild(textarea);
        showToast('📋 کپی شد!');
    });
}

// Toast notification
function showToast(message) {
    const toast = document.createElement('div');
    toast.textContent = message;
    Object.assign(toast.style, {
        position: 'fixed',
        bottom: '20px',
        left: '50%',
        transform: 'translateX(-50%)',
        padding: '12px 24px',
        background: '#1a2a3a',
        color: '#e0e6ed',
        borderRadius: '10px',
        border: '1px solid #00d4ff',
        boxShadow: '0 4px 30px rgba(0,0,0,0.5)',
        zIndex: '9999',
        fontSize: '0.95rem',
        transition: 'all 0.3s ease'
    });
    document.body.appendChild(toast);
    setTimeout(() => {
        toast.style.opacity = '0';
        setTimeout(() => document.body.removeChild(toast), 300);
    }, 3000);
}

// Auto-refresh on visibility change
document.addEventListener('visibilitychange', function() {
    if (!document.hidden) {
        // Page became visible again
        const refreshBtn = document.querySelector('.btn-refresh');
        if (refreshBtn) refreshBtn.click();
    }
});

// Dark mode toggle (optional)
let darkMode = true;

// ============================================================
// اضافه کردن کلاس‌های اضافی به عناصر
// ============================================================

document.addEventListener('DOMContentLoaded', function() {
    // اضافه کردن کلاس btn-refresh به دکمه‌های بروزرسانی
    document.querySelectorAll('[onclick*="refresh"]').forEach(el => {
        el.classList.add('btn-refresh');
    });
    
    console.log('🚀 سیستم تشخیص الگوی بازاری بارگذاری شد');
});
