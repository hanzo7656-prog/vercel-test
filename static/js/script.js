// ============================================================
// توابع عمومی
// ============================================================

// نمایش نوتیفیکیشن
function showToast(message, type = 'info') {
    const colors = {
        info: '#00d4ff',
        success: '#00ff88',
        error: '#ff4444',
        warning: '#ffaa00'
    };
    
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
        border: `2px solid ${colors[type] || colors.info}`,
        boxShadow: '0 4px 30px rgba(0,0,0,0.5)',
        zIndex: '9999',
        fontSize: '0.95rem',
        transition: 'all 0.3s ease',
        maxWidth: '90%'
    });
    document.body.appendChild(toast);
    setTimeout(() => {
        toast.style.opacity = '0';
        setTimeout(() => document.body.removeChild(toast), 300);
    }, 3000);
}

// فرمت کردن عدد با کاما
function numberWithCommas(x) {
    if (!x) return '0';
    return x.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ',');
}

// فرمت کردن تاریخ
function formatDate(dateString) {
    if (!dateString) return '-';
    try {
        const date = new Date(dateString);
        return date.toLocaleString('fa-IR', {
            year: 'numeric',
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit'
        });
    } catch {
        return dateString;
    }
}

// کپی در کلیپ‌بورد
function copyToClipboard(text) {
    if (navigator.clipboard) {
        navigator.clipboard.writeText(text).then(() => {
            showToast('📋 کپی شد!', 'success');
        }).catch(() => fallbackCopy(text));
    } else {
        fallbackCopy(text);
    }
}

function fallbackCopy(text) {
    const textarea = document.createElement('textarea');
    textarea.value = text;
    document.body.appendChild(textarea);
    textarea.select();
    try {
        document.execCommand('copy');
        showToast('📋 کپی شد!', 'success');
    } catch {
        showToast('❌ کپی نشد!', 'error');
    }
    document.body.removeChild(textarea);
}

// دریافت وضعیت سیستم (برای استفاده در صفحات)
function getSystemStatus() {
    return fetch('/health')
        .then(res => res.json())
        .catch(() => ({ status: 'unknown', components: {} }));
}

// ============================================================
// توابع مخصوص داشبورد
// ============================================================

function loadDashboardData() {
    const container = document.getElementById('dashboardContent');
    if (!container) return;
    
    container.innerHTML = '<div class="loading"><div class="spinner"></div><p>در حال دریافت داده...</p></div>';
    
    fetch('/health')
        .then(res => res.json())
        .then(data => {
            const components = data.components || {};
            const memory = components.memory || { used_mb: 0, total_mb: 512, percent: 0 };
            const credits = components.credits || { remaining: 0, total: 0, used: 0, subscription: 'free' };
            
            container.innerHTML = `
                <div class="row">
                    <div class="card">
                        <div class="card-title">💻 وضعیت سیستم</div>
                        <table class="table">
                            <tr><td>وضعیت کلی</td><td><span class="badge ${data.status === 'ok' ? 'badge-success' : data.status === 'degraded' ? 'badge-warning' : 'badge-danger'}">${data.status || 'نامشخص'}</span></td></tr>
                            <tr><td>حافظه مصرفی</td><td>${memory.used_mb || 0}MB / ${memory.total_mb || 512}MB (${memory.percent || 0}%)</td></tr>
                            <tr><td>آپتایم</td><td id="uptimeDisplay">-</td></tr>
                        </table>
                    </div>
                    <div class="card">
                        <div class="card-title">💰 اعتبار API</div>
                        <table class="table">
                            <tr><td>کل اعتبار</td><td>${numberWithCommas(credits.total || 0)}</td></tr>
                            <tr><td>استفاده شده</td><td>${numberWithCommas(credits.used || 0)}</td></tr>
                            <tr><td>باقیمانده</td><td><span class="badge ${(credits.remaining || 0) > 1000 ? 'badge-success' : (credits.remaining || 0) > 100 ? 'badge-warning' : 'badge-danger'}">${numberWithCommas(credits.remaining || 0)}</span></td></tr>
                            <tr><td>پلن</td><td>${credits.subscription || 'free'}</td></tr>
                        </table>
                    </div>
                </div>
            `;
            
            // بروزرسانی آپتایم
            fetch('/stats')
                .then(res => res.json())
                .then(stats => {
                    const uptimeEl = document.getElementById('uptimeDisplay');
                    if (uptimeEl && stats.uptime) uptimeEl.textContent = stats.uptime;
                })
                .catch(() => {});
        })
        .catch(err => {
            container.innerHTML = `<div class="card"><div class="card-title">❌ خطا</div><p style="color:#ff4444;">${err.message}</p></div>`;
        });
}

// ============================================================
// اجرا هنگام بارگذاری صفحه
// ============================================================

document.addEventListener('DOMContentLoaded', function() {
    // هایلایت کردن منوی فعال
    const currentPath = window.location.pathname;
    document.querySelectorAll('.navbar-menu a').forEach(link => {
        const href = link.getAttribute('href');
        if (href === currentPath || (currentPath !== '/' && href === currentPath)) {
            link.classList.add('active');
        } else {
            link.classList.remove('active');
        }
    });
    
    // اگر صفحه داشبورد هست، داده‌ها رو بارگذاری کن
    if (document.getElementById('dashboardContent')) {
        loadDashboardData();
        // بروزرسانی هر ۳۰ ثانیه
        setInterval(loadDashboardData, 30000);
    }
    
    console.log('🚀 سیستم تشخیص الگوی بازاری بارگذاری شد');
});
