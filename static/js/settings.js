// ============================================================
// settings.js - منطق کامل صفحه تنظیمات
// ============================================================

// ============================================================
// حالت‌ها و متغیرها
// ============================================================

const SettingsState = {
    currentUser: null,
    currentRole: 'guest',
    uptimeStartTime: null,
    uptimeInterval: null,
    statsInterval: null,
    timestampInterval: null,  // ← جدید برای آپدیت ساعت
    isLoaded: false
};

// ============================================================
// راه‌اندازی اولیه
// ============================================================

document.addEventListener('DOMContentLoaded', function() {
    initializeSettings();
});

function initializeSettings() {
    loadNav();
    loadAllData();
    
    // بروزرسانی آمار هر ۳۰ ثانیه
    SettingsState.statsInterval = setInterval(() => {
        loadStats();
    }, 30000);
    
    // بروزرسانی ساعت هر ۱ ثانیه (مشکل ۱)
    SettingsState.timestampInterval = setInterval(() => {
        updateTimestamp();
    }, 1000);
}

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
            if (typeof fetchAndStartUptime === 'function') fetchAndStartUptime();
            loadUserInfo();
        })
        .catch(err => console.error('❌ خطا در بارگذاری منو:', err));
}

// ============================================================
// بارگذاری همه داده‌ها
// ============================================================

function loadAllData() {
    loadStats();
    loadSettings();
    loadUserInfo();
    updateTimestamp();
}

function updateTimestamp() {
    const el = document.getElementById('pageTimestamp');
    if (el) {
        el.textContent = '🔄 ' + new Date().toLocaleString('fa-IR');
    }
}

// ============================================================
// ۱. آمار سیستم
// ============================================================

function loadStats() {
    // ۱.۱. آمار عمومی
    fetch('/stats', { credentials: 'include' })
        .then(res => res.json())
        .then(data => {
            if (data.uptime) startUptime(data.uptime);
            updateElement('statRequests', data.api_stats?.total_requests || 0);
            updateElement('statCache', data.api_stats?.cache_size || 0);
        })
        .catch(err => console.error('Stats error:', err));
    
    // ۱.۲. اعتبار
    fetch('/credits', { credentials: 'include' })
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                const remaining = data.data?.remaining || 0;
                const el = document.getElementById('statCredits');
                if (el) {
                    el.textContent = remaining.toLocaleString();
                    el.className = 'stat-value ' + getCreditStatus(remaining);
                }
            } else {
                updateElement('statCredits', '❌');
            }
        })
        .catch(() => updateElement('statCredits', '❌'));
    
    // ۱.۳. وضعیت مدل
    fetch('/model/status', { credentials: 'include' })
        .then(res => res.json())
        .then(data => {
            const el = document.getElementById('statModel');
            if (!el) return;
            
            const modelExists = data?.model_exists || false;
            const isTraining = data?.is_training || false;
            const mode = data?.stats?.mode || 'DEMO';
            
            if (isTraining) {
                el.textContent = '⏳ در حال آموزش...';
                el.className = 'stat-value warning';
            } else if (modelExists && mode === 'BETA') {
                el.textContent = '✅ بتا';
                el.className = 'stat-value success';
            } else if (modelExists) {
                el.textContent = '⚠️ فعال';
                el.className = 'stat-value warning';
            } else {
                el.textContent = '📦 دمو';
                el.className = 'stat-value info';
            }
        })
        .catch(() => {
            const el = document.getElementById('statModel');
            if (el) {
                el.textContent = '❌';
                el.className = 'stat-value danger';
            }
        });
}

// ============================================================
// ۲. آپتایم زنده
// ============================================================

function startUptime(uptimeStr) {
    if (!uptimeStr) return;
    
    const totalSeconds = parseUptime(uptimeStr);
    SettingsState.uptimeStartTime = Date.now() - (totalSeconds * 1000);
    
    updateUptimeDisplay();
    
    if (SettingsState.uptimeInterval) {
        clearInterval(SettingsState.uptimeInterval);
    }
    SettingsState.uptimeInterval = setInterval(updateUptimeDisplay, 1000);
}

function parseUptime(uptimeStr) {
    const parts = uptimeStr.split(':').map(Number);
    if (parts.length === 3) {
        return parts[0] * 3600 + parts[1] * 60 + parts[2];
    } else if (parts.length === 2) {
        return parts[0] * 60 + parts[1];
    }
    return parts[0] || 0;
}

function updateUptimeDisplay() {
    const el = document.getElementById('statUptime');
    if (!el || !SettingsState.uptimeStartTime) return;
    
    const elapsed = Math.floor((Date.now() - SettingsState.uptimeStartTime) / 1000);
    el.textContent = formatDuration(elapsed);
}

function formatDuration(seconds) {
    if (seconds < 60) return `${seconds}ثانیه`;
    
    const days = Math.floor(seconds / 86400);
    seconds -= days * 86400;
    const hours = Math.floor(seconds / 3600);
    seconds -= hours * 3600;
    const minutes = Math.floor(seconds / 60);
    seconds -= minutes * 60;
    
    const parts = [];
    if (days > 0) parts.push(`${days}روز`);
    if (hours > 0 || days > 0) parts.push(`${hours}ساعت`);
    if (minutes > 0 || hours > 0 || days > 0) parts.push(`${minutes}دقیقه`);
    parts.push(`${seconds}ثانیه`);
    
    return parts.join(' ');
}

// ============================================================
// ۳. اطلاعات کاربر
// ============================================================

function loadUserInfo() {
    const userInfo = document.getElementById('userInfo');
    if (!userInfo) return;
    
    showLoading(userInfo);
    
    fetch('/api/user', { credentials: 'include' })
        .then(res => {
            if (res.status === 401) {
                window.location.href = '/login';
                return null;
            }
            return res.json();
        })
        .then(data => {
            if (data && data.success) {
                SettingsState.currentUser = data.data;
                SettingsState.currentRole = data.data.role || 'guest';
                
                updateUserDisplay(data.data);
                renderUserInfo(data.data);
                
                if (data.data.role === 'admin') {
                    showUsersManagement();
                    loadUsers();
                }
                
                if (data.data.recovered) {
                    showToast('⚠️ شما با ایمیل بازیابی وارد شده‌اید. لطفاً رمز عبور و نام کاربری خود را در همین صفحه مشاهده کنید.', 'recovered');
                }
            } else if (data && !data.success) {
                showError(userInfo, data.error || 'خطا در دریافت اطلاعات کاربر');
            }
        })
        .catch(() => {
            showError(userInfo, 'خطا در ارتباط با سرور');
        });
}

function updateUserDisplay(user) {
    const display = document.getElementById('userDisplay');
    const badge = document.getElementById('userRoleBadge');
    
    if (display) {
        const roleMap = { 'admin': '👑 ادمین', 'vip': '⭐ VIP', 'guest': '👤 مهمان' };
        display.textContent = roleMap[user.role] || user.username;
    }
    
    if (badge) {
        const roleMap = { 'admin': '👑 ادمین (مدیر کل)', 'vip': '⭐ VIP', 'guest': '👤 مهمان' };
        badge.textContent = roleMap[user.role] || '👤 مهمان';
        badge.className = 'badge' + (user.role === 'admin' ? ' admin' : '');
    }
}

// ============================================================
// ۴. رندر اطلاعات کاربر (با چشم اصلاح شده)
// ============================================================

function renderUserInfo(user) {
    const container = document.getElementById('userInfo');
    if (!container) return;
    
    const roleMap = {
        'admin': '👑 ادمین (مدیر کل)',
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
                    <button class="btn btn-xs btn-outline" id="togglePasswordBtn" onclick="togglePasswordVisibility()" style="white-space:nowrap;">
                        <i class="fas fa-eye" id="passwordEye"></i>
                    </button>
                </div>
            </div>
            <div class="form-group">
                <label>📧 ایمیل</label>
                <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;">
                    <span id="userEmailDisplay" style="color:#e0e6ed;padding:10px 14px;background:#0a0e17;border-radius:10px;flex:1;min-width:150px;">${user.recovery_email || '-'}</span>
                    <input type="email" id="userEmailInput" class="form-control" style="display:none;flex:1;min-width:150px;" placeholder="ایمیل جدید را وارد کنید" value="${user.recovery_email || ''}">
                    <button class="btn btn-xs btn-outline" id="editEmailBtn" onclick="toggleEmailEdit(true)" title="ویرایش ایمیل">
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
                    <i class="fas fa-sign-out-alt"></i> خروج از حساب
                </button>
            </div>
        </div>
    `;
    
    // اتصال مجدد دکمه چشم (مشکل ۲)
    const toggleBtn = document.getElementById('togglePasswordBtn');
    if (toggleBtn) {
        toggleBtn.onclick = togglePasswordVisibility;
    }
}

// ============================================================
// ۵. مدیریت کاربران (فقط ادمین)
// ============================================================

function showUsersManagement() {
    const el = document.getElementById('usersManagement');
    if (el) el.style.display = 'block';
}

function loadUsers() {
    const tbody = document.getElementById('usersTableBody');
    if (!tbody) return;
    
    tbody.innerHTML = `<tr><td colspan="5" style="text-align:center;color:#4a5a6a;">در حال بارگذاری...</td></tr>`;
    
    fetch('/api/users', { credentials: 'include' })
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                renderUsers(data.data);
            } else {
                tbody.innerHTML = `<tr><td colspan="5" style="text-align:center;color:#ff4444;">❌ ${data.error}</td></tr>`;
            }
        })
        .catch(() => {
            tbody.innerHTML = `<tr><td colspan="5" style="text-align:center;color:#ff4444;">❌ خطا در دریافت کاربران</td></tr>`;
        });
}

function renderUsers(users) {
    const tbody = document.getElementById('usersTableBody');
    if (!tbody) return;
    
    if (!users || users.length === 0) {
        tbody.innerHTML = `<tr><td colspan="5" style="text-align:center;color:#4a5a6a;">هیچ کاربری یافت نشد</td></tr>`;
        return;
    }
    
    const roleMap = {
        'admin': '<span class="badge-role admin">👑 ادمین</span>',
        'vip': '<span class="badge-role vip">⭐ VIP</span>',
        'guest': '<span class="badge-role guest">👤 مهمان</span>'
    };
    
    let html = '';
    users.forEach(user => {
        const isAdmin = user.username === 'admin';
        const statusBadge = user.active 
            ? '<span class="badge-status active">✅ فعال</span>' 
            : '<span class="badge-status inactive">⛔ غیرفعال</span>';
        
        html += `
            <tr>
                <td>${user.username}</td>
                <td>${roleMap[user.role] || '👤 مهمان'}</td>
                <td>${statusBadge}</td>
                <td>${user.recovery_email || '-'}</td>
                <td>
                    ${isAdmin ? '<span style="color:#4a5a6a;font-size:0.7rem;">غیرقابل تغییر</span>' : `
                        <button class="btn btn-xs btn-primary" onclick="toggleUserStatus('${user.username}')" title="تغییر وضعیت">
                            <i class="fas fa-power-off"></i>
                        </button>
                        <button class="btn btn-xs btn-warning" onclick="changeUserRole('${user.username}')" title="تغییر نقش">
                            <i class="fas fa-user-tag"></i>
                        </button>
                    `}
                </td>
            </tr>
        `;
    });
    
    tbody.innerHTML = html;
}

// ============================================================
// ۶. تنظیمات
// ============================================================

function loadSettings() {
    // این تابع در نسخه فعلی فقط نمایشی است
}

// ============================================================
// ۷. چشم رمز عبور (اصلاح شده - مشکل ۲)
// ============================================================

let passwordVisible = false;

function togglePasswordVisibility() {
    console.log('🔑 togglePasswordVisibility called'); // دیباگ
    const input = document.getElementById('passwordDisplay');
    const eye = document.getElementById('passwordEye');
    
    console.log('Input:', input, 'Eye:', eye); // دیباگ
    
    if (!input || !eye) {
        console.warn('⚠️ Element not found!');
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
// ۸. مدیریت ایمیل
// ============================================================

function toggleEmailEdit(enable) {
    const input = document.getElementById('userEmailInput');
    const display = document.getElementById('userEmailDisplay');
    const editBtn = document.getElementById('editEmailBtn');
    const saveBtn = document.getElementById('saveEmailBtn');
    
    if (enable) {
        input.style.display = 'block';
        display.style.display = 'none';
        editBtn.style.display = 'none';
        saveBtn.style.display = 'inline-flex';
        input.focus();
    } else {
        input.style.display = 'none';
        display.style.display = 'block';
        editBtn.style.display = 'inline-flex';
        saveBtn.style.display = 'none';
    }
}

function updateUserEmail() {
    const emailInput = document.getElementById('userEmailInput');
    if (!emailInput) return;
    
    const newEmail = emailInput.value.trim();
    if (!newEmail) {
        showToast('❌ لطفاً ایمیل را وارد کنید', 'error');
        return;
    }
    
    if (!newEmail.includes('@') || !newEmail.includes('.')) {
        showToast('❌ ایمیل نامعتبر است', 'error');
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
            showToast('✅ ایمیل با موفقیت به‌روزرسانی شد', 'success');
            const displayEl = document.getElementById('userEmailDisplay');
            if (displayEl) displayEl.textContent = newEmail;
            toggleEmailEdit(false);
        } else {
            showToast('❌ ' + data.error, 'error');
        }
    })
    .catch(() => {
        showToast('❌ خطا در ارتباط با سرور', 'error');
    });
}

// ============================================================
// ۹. خروج از حساب (صفحه تنظیمات)
// ============================================================

function logoutUser() {
    if (!confirm('آیا از خروج از حساب کاربری اطمینان دارید؟')) return;
    
    fetch('/logout', { 
        method: 'POST',
        credentials: 'include'
    })
    .then(res => res.json())
    .then(() => {
        window.location.href = '/login';
    })
    .catch(() => {
        window.location.href = '/login';
    });
}

// ============================================================
// ۱۰. توابع کمکی
// ============================================================

function updateElement(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
}

function getCreditStatus(remaining) {
    if (remaining < 100) return 'danger';
    if (remaining < 500) return 'warning';
    return 'success';
}

function showLoading(container) {
    container.innerHTML = `
        <div class="loading" style="padding:20px;">
            <div class="spinner" style="width:30px;height:30px;"></div>
            <p style="color:#7a8fa3;font-size:0.85rem;">در حال بارگذاری...</p>
        </div>
    `;
}

function showError(container, message) {
    container.innerHTML = `
        <div style="color:#ff4444;text-align:center;padding:20px;">
            ❌ ${message}
        </div>
    `;
}

// ============================================================
// ۱۱. Toast
// ============================================================

function showToast(message, type = 'info') {
    const container = document.getElementById('toastContainer');
    if (!container) return;
    
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
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
// ۱۲. مدیریت کاربران (عملیات)
// ============================================================

function toggleUserStatus(username) {
    if (!confirm(`آیا از تغییر وضعیت کاربر ${username} اطمینان دارید؟`)) return;
    
    fetch(`/api/users/${username}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ active: false })
    })
    .then(res => res.json())
    .then(data => {
        if (data.success) {
            showToast(`✅ وضعیت کاربر ${username} تغییر کرد`, 'success');
            loadUsers();
        } else {
            showToast(`❌ ${data.error}`, 'error');
        }
    })
    .catch(() => {
        showToast('❌ خطا در تغییر وضعیت کاربر', 'error');
    });
}

function changeUserRole(username) {
    const newRole = prompt(`نقش جدید برای کاربر ${username} را وارد کنید:`, 'vip');
    if (!newRole) return;
    
    if (!['admin', 'vip', 'guest'].includes(newRole)) {
        showToast('❌ نقش نامعتبر است. گزینه‌ها: admin, vip, guest', 'error');
        return;
    }
    
    fetch(`/api/users/${username}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ role: newRole })
    })
    .then(res => res.json())
    .then(data => {
        if (data.success) {
            showToast(`✅ نقش کاربر ${username} به ${newRole} تغییر کرد`, 'success');
            loadUsers();
        } else {
            showToast(`❌ ${data.error}`, 'error');
        }
    })
    .catch(() => {
        showToast('❌ خطا در تغییر نقش کاربر', 'error');
    });
}
