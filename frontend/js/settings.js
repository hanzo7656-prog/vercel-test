// js/settings.js - منطق تنظیمات

document.addEventListener('DOMContentLoaded', function() {
    loadUserInfo();
    loadScheduleStatus();
    
    // تغییر تم
    document.getElementById('themeSelect').addEventListener('change', function() {
        const theme = this.value;
        document.body.className = theme;
        localStorage.setItem('theme', theme);
    });
    
    // بارگذاری تم ذخیره شده
    const savedTheme = localStorage.getItem('theme') || 'dark';
    document.getElementById('themeSelect').value = savedTheme;
    document.body.className = savedTheme;
});

async function loadUserInfo() {
    try {
        const res = await fetch('/api/user', { credentials: 'include' });
        const data = await res.json();
        if (data.success) {
            document.getElementById('settingsUsername').textContent = data.data.username || '—';
            document.getElementById('settingsRole').textContent = data.data.role || 'guest';
        }
    } catch (err) {
        console.error('User info error:', err);
    }
}

async function loadScheduleStatus() {
    try {
        const res = await fetch('/api/model/schedule', { credentials: 'include' });
        const data = await res.json();
        if (data.success && data.data) {
            const isRunning = data.data.is_running || false;
            const toggle = document.getElementById('scheduleToggle');
            const status = document.getElementById('scheduleStatus');
            if (isRunning) {
                toggle.classList.add('active');
                status.textContent = 'فعال (هر ' + (data.data.interval_hours || 6) + ' ساعت)';
            } else {
                toggle.classList.remove('active');
                status.textContent = 'غیرفعال';
            }
        }
    } catch (err) {
        console.error('Schedule status error:', err);
    }
}

async function toggleAutoTrain() {
    const toggle = document.getElementById('scheduleToggle');
    const status = document.getElementById('scheduleStatus');
    const isActive = toggle.classList.contains('active');
    
    try {
        const res = await fetch('/api/model/schedule', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({
                enabled: !isActive,
                interval: 6,
                period: document.getElementById('defaultPeriod').value,
                coins: ['bitcoin', 'ethereum']
            })
        });
        const data = await res.json();
        if (data.success) {
            if (!isActive) {
                toggle.classList.add('active');
                status.textContent = 'فعال (هر ۶ ساعت)';
                showToast('✅ آموزش خودکار فعال شد', 'success');
            } else {
                toggle.classList.remove('active');
                status.textContent = 'غیرفعال';
                showToast('⏹️ آموزش خودکار غیرفعال شد', 'success');
            }
        } else {
            showToast('❌ ' + data.message, 'error');
        }
    } catch (err) {
        showToast('❌ خطا', 'error');
    }
}

function changePassword() {
    const newPass = prompt('رمز عبور جدید را وارد کنید (حداقل ۶ کاراکتر):');
    if (!newPass || newPass.length < 6) {
        if (newPass) showToast('❌ رمز عبور باید حداقل ۶ کاراکتر باشد', 'error');
        return;
    }
    
    // TODO: پیاده‌سازی تغییر رمز
    showToast('🔧 این قابلیت در حال توسعه است', 'info');
}

function logout() {
    if (!confirm('آیا از خروج از حساب کاربری اطمینان دارید؟')) return;
    fetch('/logout', { method: 'POST', credentials: 'include' })
        .then(() => window.location.href = '/');
}
