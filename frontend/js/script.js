// js/script.js - توابع عمومی

// بارگذاری منو در همه صفحات
function loadNav() {
    const container = document.getElementById('navContainer');
    if (!container) return;
    
    fetch('/nav.html')
        .then(res => res.text())
        .then(html => {
            container.innerHTML = html;
            // اجرای اسکریپت‌های داخل nav.html
            const scripts = container.querySelectorAll('script');
            scripts.forEach(old => {
                const ns = document.createElement('script');
                ns.textContent = old.textContent;
                old.parentNode.replaceChild(ns, old);
            });
        })
        .catch(err => console.error('❌ Nav error:', err));
}

// Toast notification
function showToast(message, type = 'info') {
    const colors = {
        info: '#00d4ff',
        success: '#00ff88',
        error: '#ff4444',
        warning: '#ff8800'
    };
    
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    toast.style.cssText = `
        position: fixed; bottom: 20px; left: 50%; transform: translateX(-50%);
        padding: 10px 24px; background: #0d1624; border: 2px solid ${colors[type] || colors.info};
        border-radius: 10px; color: #e8eef7; font-size: 0.85rem;
        z-index: 9999; box-shadow: 0 8px 40px rgba(0,0,0,0.5);
        animation: slideUp 0.3s ease;
    `;
    document.body.appendChild(toast);
    setTimeout(() => {
        toast.style.opacity = '0';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

// Format number
function formatNumber(num) {
    if (!num) return '—';
    if (num >= 1e6) return (num / 1e6).toFixed(1) + 'M';
    if (num >= 1e3) return (num / 1e3).toFixed(1) + 'K';
    return num.toLocaleString();
}

// Format currency
function formatCurrency(num) {
    if (!num) return '$—';
    return '$' + num.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

// اجرا بعد از لود DOM
document.addEventListener('DOMContentLoaded', loadNav);
