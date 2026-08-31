// js/analyzer.js - منطق تحلیلگر

const BASE_URL = '';

document.addEventListener('DOMContentLoaded', function() {
    const predictBtn = document.getElementById('predictBtn');
    const coinSelect = document.getElementById('coinSelect');
    const periodSelect = document.getElementById('periodSelect');
    
    // بارگذاری تاریخچه
    loadHistory();
    
    // پیش‌بینی
    predictBtn.addEventListener('click', async function() {
        const coin = coinSelect.value;
        const period = periodSelect.value;
        
        const resultContainer = document.getElementById('resultContainer');
        resultContainer.innerHTML = '<div class="result-card"><p style="text-align:center;color:var(--text-secondary);">⏳ در حال پیش‌بینی...</p></div>';
        
        try {
            const res = await fetch(`/api/predict?coin=${coin}&period=${period}`, {
                credentials: 'include'
            });
            const data = await res.json();
            
            if (data.success && data.data) {
                renderPrediction(data.data);
            } else {
                resultContainer.innerHTML = `<div class="result-card"><p style="color:var(--accent-red);">❌ ${data.error || 'خطا در پیش‌بینی'}</p></div>`;
            }
        } catch (err) {
            resultContainer.innerHTML = `<div class="result-card"><p style="color:var(--accent-red);">❌ خطا در ارتباط با سرور</p></div>`;
        }
    });
});

function renderPrediction(data) {
    const container = document.getElementById('resultContainer');
    const signalClass = data.signal_type?.toLowerCase() || 'neutral';
    const signalEmoji = signalClass === 'buy' ? '🟢' : signalClass === 'sell' ? '🔴' : '🟡';
    
    container.innerHTML = `
        <div class="result-card">
            <div class="signal ${signalClass}">${signalEmoji} ${data.signal || 'خنثی'}</div>
            <div class="result-grid">
                <div class="result-item">
                    <div class="label">💰 قیمت</div>
                    <div class="value">$${data.current_price?.toLocaleString() || '—'}</div>
                </div>
                <div class="result-item">
                    <div class="label">🎯 اطمینان</div>
                    <div class="value">${data.confidence || '—'}</div>
                </div>
                <div class="result-item">
                    <div class="label">🧠 مدل</div>
                    <div class="value">${data.model_mode || 'DEMO'}</div>
                </div>
                <div class="result-item">
                    <div class="label">🪙 ارز</div>
                    <div class="value">${data.coin_name || data.coin}</div>
                </div>
                <div class="result-item">
                    <div class="label">⏱️ زمان</div>
                    <div class="value">${new Date(data.timestamp).toLocaleTimeString('fa-IR')}</div>
                </div>
                <div class="result-item">
                    <div class="label">📊 امتیاز</div>
                    <div class="value">${(data.prediction_score * 100).toFixed(1)}%</div>
                </div>
            </div>
        </div>
    `;
}

async function loadHistory() {
    const container = document.getElementById('historyContainer');
    try {
        const res = await fetch('/api/model?section=history', { credentials: 'include' });
        const data = await res.json();
        if (data.success && data.data && data.data.length > 0) {
            let html = '<table style="width:100%;border-collapse:collapse;font-size:0.85rem;">';
            html += `<tr style="border-bottom:1px solid var(--border-color);">
                        <th style="text-align:right;padding:8px;">نسخه</th>
                        <th style="text-align:right;padding:8px;">دقت</th>
                        <th style="text-align:right;padding:8px;">تاریخ</th>
                    </tr>`;
            data.data.slice(0, 10).forEach(item => {
                html += `<tr style="border-bottom:1px solid rgba(255,255,255,0.03);">
                            <td style="padding:8px;">${item.version || '—'}</td>
                            <td style="padding:8px;color:var(--accent-green);">${(item.accuracy * 100).toFixed(1)}%</td>
                            <td style="padding:8px;color:var(--text-secondary);">${new Date(item.training_date).toLocaleDateString('fa-IR')}</td>
                        </tr>`;
            });
            html += '</table>';
            container.innerHTML = html;
        } else {
            container.innerHTML = '<p style="color:var(--text-secondary);text-align:center;padding:10px;">📭 هیچ پیش‌بینی ذخیره‌ای یافت نشد</p>';
        }
    } catch (err) {
        container.innerHTML = '<p style="color:var(--accent-red);text-align:center;">❌ خطا در دریافت تاریخچه</p>';
    }
}
