// ============================================================
// سیستم تشخیص الگوهای بازاری - توابع عمومی
// ============================================================

// ============================================================
// ۱. آپتایم زنده (بدون رفرش)
// ============================================================

let systemStartTime = null;

function fetchAndStartUptime() {
    const displayEl = document.getElementById('uptimeDisplay');
    if (!displayEl) return;
    
    fetch('/stats')
        .then(res => res.json())
        .then(data => {
            if (data.uptime) {
                const parts = data.uptime.split(':').map(Number);
                let totalSeconds = 0;
                if (parts.length === 3) {
                    totalSeconds = parts[0] * 3600 + parts[1] * 60 + parts[2];
                } else if (parts.length === 2) {
                    totalSeconds = parts[0] * 60 + parts[1];
                } else {
                    totalSeconds = parts[0] || 0;
                }
                
                systemStartTime = Date.now() - (totalSeconds * 1000);
                updateUptimeDisplay();
                setInterval(updateUptimeDisplay, 1000);
            }
        })
        .catch(() => {
            displayEl.textContent = '⚠️ نامشخص';
        });
}

function updateUptimeDisplay() {
    const displayEl = document.getElementById('uptimeDisplay');
    if (!displayEl || !systemStartTime) return;
    
    const elapsed = Math.floor((Date.now() - systemStartTime) / 1000);
    displayEl.textContent = formatDuration(elapsed);
}

function formatDuration(seconds) {
    if (seconds < 60) return `${seconds} ثانیه`;
    
    const days = Math.floor(seconds / 86400);
    seconds -= days * 86400;
    const hours = Math.floor(seconds / 3600);
    seconds -= hours * 3600;
    const minutes = Math.floor(seconds / 60);
    seconds -= minutes * 60;
    
    let parts = [];
    if (days > 0) parts.push(`${days} روز`);
    if (hours > 0 || days > 0) parts.push(`${hours} ساعت`);
    if (minutes > 0 || hours > 0 || days > 0) parts.push(`${minutes} دقیقه`);
    parts.push(`${seconds} ثانیه`);
    
    return parts.join(' ');
}

// ============================================================
// ۲. نمایش نوتیفیکیشن (Toast)
// ============================================================

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

// ============================================================
// ۳. ابزارهای کمکی
// ============================================================

// فرمت کردن عدد با کاما
function numberWithCommas(x) {
    if (!x && x !== 0) return '0';
    return x.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ',');
}

// فرمت کردن تاریخ به فارسی
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

// فرمت قیمت با نماد دلار
function formatPrice(price) {
    if (!price && price !== 0) return '-';
    if (price >= 1000) {
        return '$' + numberWithCommas(Math.round(price));
    }
    return '$' + price.toFixed(2);
}

// دریافت وضعیت سیستم
function getSystemStatus() {
    return fetch('/health')
        .then(res => res.json())
        .catch(() => ({ status: 'unknown', components: {} }));
}

// دریافت پارامترهای URL
function getUrlParams() {
    const params = new URLSearchParams(window.location.search);
    const result = {};
    for (const [key, value] of params) {
        result[key] = value;
    }
    return result;
}

// ============================================================
// ۴. کپی در کلیپ‌بورد
// ============================================================

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

// ============================================================
// ۵. مدیریت خطاها
// ============================================================

function handleApiError(error, fallbackMessage = 'خطا در ارتباط با سرور') {
    console.error('API Error:', error);
    showToast(`❌ ${fallbackMessage}`, 'error');
}

// ============================================================
// ۶. اعتبارسنجی فرم‌ها
// ============================================================

function validateForm(formId) {
    const form = document.getElementById(formId);
    if (!form) return true;
    
    const inputs = form.querySelectorAll('input[required], select[required]');
    let isValid = true;
    
    inputs.forEach(input => {
        if (!input.value || input.value.trim() === '') {
            input.style.borderColor = '#ff4444';
            isValid = false;
        } else {
            input.style.borderColor = '#1a2a3a';
        }
    });
    
    if (!isValid) {
        showToast('❌ لطفاً تمام فیلدهای ضروری را پر کنید', 'error');
    }
    
    return isValid;
}

// ============================================================
// ۷. توابع مخصوص داشبورد
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
                            <tr><td>آپتایم</td><td id="uptimeDisplay">۰ ثانیه</td></tr>
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
            
            // شروع آپتایم
            if (typeof fetchAndStartUptime === 'function') {
                fetchAndStartUptime();
            }
        })
        .catch(err => {
            container.innerHTML = `<div class="card"><div class="card-title">❌ خطا</div><p style="color:#ff4444;">${err.message}</p></div>`;
        });
}

// ============================================================
// ۸. بارگذاری خودکار برای همه صفحات
// ============================================================

document.addEventListener('DOMContentLoaded', function() {
    // ۱. هایلایت کردن منوی فعال
    const currentPath = window.location.pathname;
    document.querySelectorAll('.navbar-menu a').forEach(link => {
        const href = link.getAttribute('href');
        if (href === currentPath || (currentPath !== '/' && href === currentPath)) {
            link.classList.add('active');
        } else {
            link.classList.remove('active');
        }
    });
    
    // ۲. شروع آپتایم (اگر المنت وجود داشته باشه)
    if (document.getElementById('uptimeDisplay')) {
        fetchAndStartUptime();
    }
    
    // ۳. اگر صفحه داشبورد هست، داده‌ها رو بارگذاری کن
    if (document.getElementById('dashboardContent')) {
        loadDashboardData();
        // بروزرسانی هر ۳۰ ثانیه
        setInterval(loadDashboardData, 30000);
    }
    
    // ۴. انیمیشن کارت‌ها (Fade-in)
    const cards = document.querySelectorAll('.card');
    cards.forEach((card, index) => {
        card.style.opacity = '0';
        card.style.transform = 'translateY(20px)';
        card.style.transition = 'all 0.5s ease';
        setTimeout(() => {
            card.style.opacity = '1';
            card.style.transform = 'translateY(0)';
        }, 100 + index * 50);
    });
    
    // ۵. دکمه‌های بروزرسانی
    document.querySelectorAll('.btn-refresh, [onclick*="refresh"]').forEach(btn => {
        btn.addEventListener('click', function(e) {
            const loader = document.createElement('span');
            loader.className = 'spinner-small';
            loader.style.cssText = 'display:inline-block;width:16px;height:16px;border:2px solid #1a2a3a;border-top:2px solid #00d4ff;border-radius:50%;animation:spin 1s linear infinite;margin-right:8px;';
            this.prepend(loader);
            setTimeout(() => loader.remove(), 1000);
        });
    });
    
    console.log('🚀 سیستم تشخیص الگوی بازاری بارگذاری شد');
    console.log(`📅 زمان: ${new Date().toLocaleString('fa-IR')}`);
});

// ============================================================
// ۹. اسپینر کوچک برای لودینگ‌های داخلی
// ============================================================

// اضافه کردن استایل اسپینر کوچک
const style = document.createElement('style');
style.textContent = `
    .spinner-small {
        display: inline-block;
        width: 16px;
        height: 16px;
        border: 2px solid #1a2a3a;
        border-top: 2px solid #00d4ff;
        border-radius: 50%;
        animation: spin 1s linear infinite;
        margin-right: 8px;
        vertical-align: middle;
    }
`;
document.head.appendChild(style);

// ============================================================
// ۱۰. توابع مخصوص صفحه پیش‌بینی (برای نمودار)
// ============================================================

function createAreaChart(canvasId, data, label = 'قیمت (USD)') {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return null;
    
    // بررسی وجود Chart.js
    if (typeof Chart === 'undefined') {
        console.warn('Chart.js loaded!');
        return null;
    }
    
    const ctx = canvas.getContext('2d');
    
    // ایجاد گرادیان محو شونده
    const gradient = ctx.createLinearGradient(0, 0, 0, canvas.parentElement.clientHeight || 300);
    gradient.addColorStop(0, 'rgba(0, 212, 255, 0.7)');
    gradient.addColorStop(0.4, 'rgba(0, 212, 255, 0.3)');
    gradient.addColorStop(1, 'rgba(0, 212, 255, 0.0)');
    
    // استخراج داده‌ها
    const labels = data.map(d => {
        const ts = d[0] || d.timestamp;
        if (typeof ts === 'number') {
            return new Date(ts * 1000).toLocaleTimeString('fa-IR', { hour: '2-digit', minute: '2-digit' });
        }
        return '-';
    });
    
    const prices = data.map(d => d[1] || d.price || 0);
    
    return new Chart(canvas, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: label,
                data: prices,
                borderColor: '#00d4ff',
                backgroundColor: gradient,
                borderWidth: 2,
                pointRadius: 0,
                pointHoverRadius: 5,
                pointBackgroundColor: '#00d4ff',
                pointBorderColor: '#00d4ff',
                tension: 0.3,
                fill: true,
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    labels: {
                        color: '#a0b4c8',
                        font: { family: 'Vazir' }
                    }
                },
                tooltip: {
                    backgroundColor: '#0d1624',
                    titleColor: '#e0e6ed',
                    bodyColor: '#00d4ff',
                    borderColor: '#1a2a3a',
                    borderWidth: 1,
                    callbacks: {
                        label: function(context) {
                            return '$' + context.parsed.y.toFixed(2);
                        }
                    }
                }
            },
            scales: {
                x: {
                    grid: { color: 'rgba(255,255,255,0.05)' },
                    ticks: { color: '#7a8fa3', font: { family: 'Vazir' }, maxTicksLimit: 10 }
                },
                y: {
                    grid: { color: 'rgba(255,255,255,0.05)' },
                    ticks: { 
                        color: '#7a8fa3', 
                        font: { family: 'Vazir' }, 
                        callback: value => '$' + value.toFixed(0) 
                    }
                }
            },
            interaction: {
                intersect: false,
                mode: 'index'
            },
            animation: {
                duration: 2000,
                easing: 'easeOutQuart'
            }
        }
    });
}
