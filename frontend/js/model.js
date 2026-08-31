// js/model.js - منطق مدیریت مدل

const BASE_URL = '';

document.addEventListener('DOMContentLoaded', function() {
    loadModelStatus();
    loadHistory();
    
    document.getElementById('trainBtn').addEventListener('click', trainModel);
    document.getElementById('stopBtn').addEventListener('click', stopTraining);
    document.getElementById('exportBtn').addEventListener('click', exportModel);
    document.getElementById('scheduleBtn').addEventListener('click', toggleSchedule);
    
    // بروزرسانی خودکار هر ۱۰ ثانیه
    setInterval(loadModelStatus, 10000);
});

async function loadModelStatus() {
    try {
        const res = await fetch('/api/model?section=status', { credentials: 'include' });
        const data = await res.json();
        if (data.success && data.data) {
            const s = data.data;
            document.getElementById('statusLoaded').textContent = s.loaded ? '✅ فعال' : '📦 دمو';
            document.getElementById('statusLoaded').className = 'value ' + (s.loaded ? 'active' : 'inactive');
            document.getElementById('statusVersion').textContent = s.version || 'N/A';
            document.getElementById('statusAccuracy').textContent = s.last_score ? (s.last_score * 100).toFixed(1) + '%' : '—';
            document.getElementById('statusTrainings').textContent = s.total_trainings || 0;
            document.getElementById('statusTraining').textContent = s.is_training ? '⏳ در حال آموزش...' : '⏹️ غیرفعال';
            document.getElementById('statusTraining').className = 'value ' + (s.is_training ? 'active' : 'inactive');
        }
    } catch (err) {
        console.error('Model status error:', err);
    }
}

async function trainModel() {
    const btn = document.getElementById('trainBtn');
    btn.disabled = true;
    btn.textContent = '⏳ در حال آموزش...';
    
    try {
        const res = await fetch('/api/model', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({
                action: 'train',
                period: '1m',
                coins: ['bitcoin', 'ethereum']
            })
        });
        const data = await res.json();
        showToast(data.success ? '✅ آموزش شروع شد' : '❌ ' + data.message, data.success ? 'success' : 'error');
        if (data.success) {
            loadModelStatus();
            setTimeout(loadHistory, 3000);
        }
    } catch (err) {
        showToast('❌ خطا در شروع آموزش', 'error');
    }
    
    btn.disabled = false;
    btn.textContent = '🚀 آموزش دستی';
}

async function stopTraining() {
    try {
        const res = await fetch('/api/model/schedule', {
            method: 'DELETE',
            credentials: 'include'
        });
        const data = await res.json();
        showToast(data.success ? '✅ آموزش متوقف شد' : '❌ ' + data.message, data.success ? 'success' : 'error');
        loadModelStatus();
    } catch (err) {
        showToast('❌ خطا', 'error');
    }
}

async function exportModel() {
    try {
        window.open('/api/model/export', '_blank');
        showToast('📥 دانلود شروع شد', 'success');
    } catch (err) {
        showToast('❌ خطا در دانلود', 'error');
    }
}

async function toggleSchedule() {
    const btn = document.getElementById('scheduleBtn');
    const isActive = btn.textContent.includes('غیرفعال');
    
    try {
        const res = await fetch('/api/model/schedule', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({
                enabled: isActive,
                interval: 6,
                period: '1m',
                coins: ['bitcoin', 'ethereum']
            })
        });
        const data = await res.json();
        if (data.success) {
            btn.textContent = isActive ? '⏰ زمان‌بندی فعال' : '⏰ تنظیم زمان‌بندی';
            showToast(isActive ? '✅ زمان‌بندی فعال شد' : '⏹️ زمان‌بندی غیرفعال شد', 'success');
            loadModelStatus();
        } else {
            showToast('❌ ' + data.message, 'error');
        }
    } catch (err) {
        showToast('❌ خطا', 'error');
    }
}

async function loadHistory() {
    const tbody = document.getElementById('historyBody');
    try {
        const res = await fetch('/api/model?section=history', { credentials: 'include' });
        const data = await res.json();
        if (data.success && data.data && data.data.length > 0) {
            let html = '';
            data.data.forEach(item => {
                const isActive = item.is_active ? '✅ فعال' : '📦 غیرفعال';
                html += `<tr>
                            <td>${item.version || '—'}</td>
                            <td style="color:var(--accent-green);">${(item.accuracy * 100).toFixed(1)}%</td>
                            <td>${item.period || '—'}</td>
                            <td style="color:var(--text-secondary);">${new Date(item.training_date).toLocaleString('fa-IR')}</td>
                            <td>${isActive}</td>
                        </tr>`;
            });
            tbody.innerHTML = html;
        } else {
            tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:var(--text-secondary);">📭 هیچ نسخه‌ای یافت نشد</td></tr>';
        }
    } catch (err) {
        tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:var(--accent-red);">❌ خطا در دریافت تاریخچه</td></tr>';
    }
}
