// ============================================================
// settings.js - نسخه نهایی
// ============================================================

// ============================================================
// راه‌اندازی اولیه
// ============================================================

document.addEventListener('DOMContentLoaded', function() {
    console.log('🚀 Settings page loaded');
    loadNav();
    loadAllData();
    
    // ⭐ آپدیت ساعت هر ۱ ثانیه (مشکل ۲ حل شد)
    setInterval(updateTimestamp, 1000);
    
    // بروزرسانی آمار هر ۳۰ ثانیه
    setInterval(loadStats, 30000);
});

// ============================================================
// بارگذاری منو
// ============================================================

function loadNav() {
    const container = document.getElementById('navContainer');
    if (!container) return;
    
    fetch('/static/nav.html')
        .then(res => res.text())
        .then(html => {
            container.innerHTML = html;
            if (typeof initMenu === 'function') initMenu();
            loadUserInfo();
        })
        .catch(err => console.error('❌ خطا در بارگذاری منو:', err));
}

// ============================================================
// بارگذاری همه داده‌ها
// ============================================================

function loadAllData() {
    loadStats();
    loadUserInfo();
    updateTimestamp();
}

// ============================================================
// آپدیت تاریخ و ساعت (هر ثانیه)
// ============================================================

function updateTimestamp() {
    const el = document.getElementById('pageTimestamp');
    if (el) {
        el.textContent = '🔄 ' + new Date().toLocaleString('fa-IR');
    }
}

// ============================================================
// بارگذاری آمار
// ============================================================

function loadStats() {
    console.log('📊 Loading stats...');
    
    fetch('/stats', { credentials: 'include' })
        .then(res => res.json())
        .then(data => {
            console.log('📊 Stats data:', data);
            if (data.uptime) {
                const el = document.getElementById('statUptime');
                if (el) el.textContent = data.uptime;
            }
            const requests = document.getElementById('statRequests');
            if (requests) requests.textContent = data.api_stats?.total_requests || 0;
            const cache = document.getElementById('statCache');
            if (cache) cache.textContent = data.api_stats?.cache_size || 0;
        })
        .catch(err => console.error('Stats error:', err));
    
    fetch('/credits', { credentials: 'include' })
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                const el = document.getElementById('statCredits');
                if (el) el.textContent = data.data?.remaining || 0;
            }
        })
        .catch(() => {});
    
    fetch('/model/status', { credentials: 'include' })
        .then(res => res.json())
        .then(data => {
            const el = document.getElementById('statModel');
            if (!el) return;
            
            if (data?.is_training) {
                el.textContent = '⏳ در حال آموزش...';
            } else if (data?.model_exists) {
                el.textContent = '✅ فعال';
            } else {
                el.textContent = '📦 دمو';
            }
        })
        .catch(() => {});
}

// ============================================================
// بارگذاری اطلاعات کاربر
// ============================================================

function loadUserInfo() {
    console.log('👤 Loading user info...');
    const userInfo = document.getElementById('userInfo');
    if (!userInfo) return;
    
    userInfo.innerHTML = '<div style="text-align:center;padding:20px;color:#7a8fa3;">⏳ در حال بارگذاری...</div>';
    
    fetch('/api/user', { credentials: 'include' })
        .then(res => {
            if (res.status === 401) {
                window.location.href = '/login';
                return null;
            }
            return res.json();
        })
        .then(data => {
            console.log('👤 User data:', data);
            if (data && data.success) {
                renderUserInfo(data.data);
                updateUserDisplay(data.data);
            } else if (data && !data.success) {
                userInfo.innerHTML = `<div style="color:#ff4444;text-align:center;padding:20px;">❌ ${data.error}</div>`;
            }
        })
        .catch(err => {
            console.error('User info error:', err);
            userInfo.innerHTML = `<div style="color:#ff4444;text-align:center;padding:20px;">❌ خطا در ارتباط با سرور</div>`;
        });
}

// ============================================================
// نمایش اطلاعات کاربر (با چشم اصلاح شده)
// ============================================================

let passwordVisible = false;

function renderUserInfo(user) {
    const container = document.getElementById('userInfo');
    if (!container) return;
    
    const roleMap = {
        'admin': '👑 ادمین',
        'vip': '⭐ VIP',
        'guest': '👤 مهمان'
    };
    
    container.innerHTML = `
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px 24px;">
            <div class="form-group">
                <label>👤 نام کاربری</label>
                <input type="text" class="form-control" value="${user.username || '-'}" readonly>
            </div>
            <div class="form-group">
                <label>🔑 رمز عبور</label>
                <div style="display:flex;gap:8px;align-items:center;">
                    <input type="password" class="form-control" value="${user.password_display || '••••••••'}" readonly id="passwordDisplay" style="flex:1;">
                    <!-- ⭐ دکمه چشم با onclick مستقیم (مشکل ۳ حل شد) -->
                    <button class="btn btn-xs btn-outline" onclick="togglePasswordVisibility()" style="white-space:nowrap;padding:6px 12px;">
                        <i class="fas fa-eye" id="passwordEye"></i>
                    </button>
                </div>
            </div>
            <div class="form-group">
                <label>📧 ایمیل</label>
                <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;">
                    <span id="userEmailDisplay" style="color:#e0e6ed;padding:10px 14px;background:#0a0e17;border-radius:10px;flex:1;min-width:150px;">${user.recovery_email || '-'}</span>
                    <input type="email" id="userEmailInput" class="form-control" style="display:none;flex:1;min-width:150px;" placeholder="ایمیل جدید" value="${user.recovery_email || ''}">
                    <button class="btn btn-xs btn-outline" onclick="toggleEmailEdit(true)">
                        <i class="fas fa-edit"></i>
                    </button>
                    <button class="btn btn-xs btn-success" id="saveEmailBtn" style="display:none;" onclick="updateUserEmail()">
                        <i class="fas fa-save"></i> ذخیره
                    </button>
                </div>
            </div>
            <div class="form-group">
                <label>📋 نقش</label>
                <input type="text" class="form-control" value="${roleMap[user.role] || 'مهمان'}" readonly>
            </div>
            <div class="form-group">
                <label>📊 وضعیت</label>
                <input type="text" class="form-control" value="${user.active ? '✅ فعال' : '❌ غیرفعال'}" readonly>
            </div>
            <div class="form-group" style="justify-content:flex-end;">
                <button class="btn btn-danger btn-sm" onclick="logoutUser()">
                    <i class="fas fa-sign-out-alt"></i> خروج
                </button>
            </div>
        </div>
    `;
    
    // ریست کردن وضعیت چشم
    passwordVisible = false;
    const eye = document.getElementById('passwordEye');
    if (eye) {
        eye.className = 'fas fa-eye';
    }
}

// ============================================================
// چشم رمز عبور (مشکل ۳ حل شد - با onclick مستقیم)
// ============================================================

function togglePasswordVisibility() {
    console.log('🔑 Toggle password called');
    const input = document.getElementById('passwordDisplay');
    const eye = document.getElementById('passwordEye');
    
    if (!input || !eye) {
        console.warn('⚠️ Elements not found!');
        return;
    }
    
    if (passwordVisible) {
        input.type = 'password';
        eye.className = 'fas fa-eye';
        passwordVisible = false;
        console.log('🔒 Password hidden');
    } else {
        input.type = 'text';
        eye.className = 'fas fa-eye-slash';
        passwordVisible = true;
        console.log('🔓 Password shown');
    }
}

// ============================================================
// ویرایش ایمیل
// ============================================================

function toggleEmailEdit(enable) {
    const input = document.getElementById('userEmailInput');
    const display = document.getElementById('userEmailDisplay');
    const editBtn = document.querySelector('.btn-outline[onclick*="toggleEmailEdit"]');
    const saveBtn = document.getElementById('saveEmailBtn');
    
    if (enable) {
        input.style.display = 'block';
        display.style.display = 'none';
        if (editBtn) editBtn.style.display = 'none';
        if (saveBtn) saveBtn.style.display = 'inline-flex';
        input.focus();
    } else {
        input.style.display = 'none';
        display.style.display = 'block';
        if (editBtn) editBtn.style.display = 'inline-flex';
        if (saveBtn) saveBtn.style.display = 'none';
    }
}

function updateUserEmail() {
    const emailInput = document.getElementById('userEmailInput');
    if (!emailInput) return;
    
    const newEmail = emailInput.value.trim();
    if (!newEmail || !newEmail.includes('@')) {
        alert('❌ ایمیل نامعتبر است');
        return;
    }
    
    fetch('/api/user/email', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ email: newEmail })
    })
    .then(res => res.json())
    .then(data => {
        if (data.success) {
            alert('✅ ایمیل به‌روزرسانی شد');
            document.getElementById('userEmailDisplay').textContent = newEmail;
            toggleEmailEdit(false);
        } else {
            alert('❌ ' + data.error);
        }
    })
    .catch(() => alert('❌ خطا در ارتباط با سرور'));
}

// ============================================================
// خروج از حساب (فقط از اینجا)
// ============================================================

function logoutUser() {
    console.log('🚪 Logout from settings');
    if (!confirm('آیا از خروج از حساب کاربری اطمینان دارید؟')) return;
    
    fetch('/logout', { 
        method: 'POST',
        credentials: 'include'
    })
    .then(() => {
        window.location.href = '/login';
    })
    .catch(() => {
        window.location.href = '/login';
    });
}

// ============================================================
// نمایش نام کاربری در منو
// ============================================================

function updateUserDisplay(user) {
    const display = document.getElementById('userDisplay');
    const badge = document.getElementById('userRoleBadge');
    
    if (display) {
        const roleMap = { 'admin': '👑 ادمین', 'vip': '⭐ VIP', 'guest': '👤 مهمان' };
        display.textContent = roleMap[user.role] || user.username;
    }
    
    if (badge) {
        const roleMap = { 'admin': '👑 ادمین', 'vip': '⭐ VIP', 'guest': '👤 مهمان' };
        badge.textContent = roleMap[user.role] || '👤 مهمان';
    }
}
