// js/alerts.js - منطق هشدارها

let currentFilter = 'all';

document.addEventListener('DOMContentLoaded', function() {
    loadAlerts();
    
    // فیلترها
    document.querySelectorAll('.alert-filters button').forEach(btn => {
        btn.addEventListener('click', function() {
            document.querySelectorAll('.alert-filters button').forEach(b => b.classList.remove('active'));
            this.classList.add('active');
            currentFilter = this.dataset.filter;
            loadAlerts();
        });
    });
    
    // بروزرسانی خودکار هر ۳۰ ثانیه
    setInterval(loadAlerts, 30000);
});

async function loadAlerts() {
    const container = document.getElementById('alertsList');
    
    try {
        let url = '/api/alerts?limit=50';
        if (currentFilter === 'resolved') url += '&resolved=true';
        else if (currentFilter === 'unresolved') url += '&resolved=false';
        
        const res = await fetch(url, { credentials: 'include' });
        const data = await res.json();
        
        if (data.success && data.data) {
            const alerts = data.data;
            document.getElementById('alertCount').textContent = alerts.length + ' هشدار';
            
            if (alerts.length === 0) {
                container.innerHTML = '<div class="no-alerts">✅ همه چیز خوب است! هشدار جدیدی وجود ندارد.</div>';
                return;
            }
            
            let html = '';
            alerts.forEach(alert => {
                const level = alert.level?.toLowerCase() || 'info';
                const isResolved = alert.resolved || false;
                const levelClass = isResolved ? 'resolved' : level;
                const icon = level === 'critical' ? '🚨' : level === 'warning' ? '⚠️' : 'ℹ️';
                const time = new Date(alert.timestamp).toLocaleString('fa-IR');
                
                html += `
                    <div class="alert-item ${levelClass}">
                        <span class="alert-icon">${icon}</span>
                        <div class="alert-content">
                            <div class="title">${alert.message || 'بدون پیام'}</div>
                            <div class="source">${alert.source || 'system'} • ${alert.level || 'info'}</div>
                        </div>
                        <span class="alert-time">${time}</span>
                        ${!isResolved ? `<button class="alert-action" onclick="resolveAlert(${alert.id})"><i class="fas fa-check-circle"></i></button>` : '<span style="color:var(--accent-green);font-size:0.7rem;">✅ حل شد</span>'}
                    </div>
                `;
            });
            container.innerHTML = html;
        } else {
            container.innerHTML = '<div class="no-alerts">❌ خطا در دریافت هشدارها</div>';
        }
    } catch (err) {
        container.innerHTML = '<div class="no-alerts">❌ خطا در ارتباط با سرور</div>';
    }
}

async function resolveAlert(id) {
    try {
        const res = await fetch(`/api/alerts/${id}/resolve`, {
            method: 'POST',
            credentials: 'include'
        });
        const data = await res.json();
        if (data.success) {
            showToast('✅ هشدار بسته شد', 'success');
            loadAlerts();
        } else {
            showToast('❌ خطا در بستن هشدار', 'error');
        }
    } catch (err) {
        showToast('❌ خطا', 'error');
    }
}
