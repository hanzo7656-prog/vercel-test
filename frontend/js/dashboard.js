// js/dashboard.js

const BASE_URL = '';

async function fetchMetrics() {
    try {
        const res = await fetch('/api/metrics');
        const data = await res.json();
        if (data.success && data.data) {
            updateStats(data.data.metrics);
        }
    } catch (err) {
        console.error('Metrics error:', err);
    }
}

function updateStats(metrics) {
    const grid = document.getElementById('statsGrid');
    if (!grid) return;
    
    // قیمت‌ها (از CoinStats API)
    const btc = metrics.btc_price || {};
    const eth = metrics.eth_price || {};
    const fear = metrics.fear_greed || {};
    const credits = metrics.api_credits || {};
    
    grid.innerHTML = `
        <div class="stat-card">
            <div class="stat-icon">₿</div>
            <div class="stat-value cyan">${formatCurrency(btc.value)}</div>
            <div class="stat-label">بیت‌کوین</div>
            <div class="stat-change ${btc.change_24h >= 0 ? 'up' : 'down'}">
                ${btc.change_24h >= 0 ? '+' : ''}${(btc.change_24h || 0).toFixed(2)}%
            </div>
        </div>
        <div class="stat-card">
            <div class="stat-icon">⟠</div>
            <div class="stat-value purple">${formatCurrency(eth.value)}</div>
            <div class="stat-label">اتریوم</div>
            <div class="stat-change ${eth.change_24h >= 0 ? 'up' : 'down'}">
                ${eth.change_24h >= 0 ? '+' : ''}${(eth.change_24h || 0).toFixed(2)}%
            </div>
        </div>
        <div class="stat-card">
            <div class="stat-icon">😨</div>
            <div class="stat-value orange">${fear.value || 50}</div>
            <div class="stat-label">ترس و طمع</div>
            <div class="stat-change">${fear.classification || 'Neutral'}</div>
        </div>
        <div class="stat-card">
            <div class="stat-icon">💰</div>
            <div class="stat-value green">${formatNumber(credits.value)}</div>
            <div class="stat-label">اعتبار API</div>
        </div>
    `;
}

// بارگذاری اولیه
document.addEventListener('DOMContentLoaded', function() {
    fetchMetrics();
    // بروزرسانی هر ۱۰ ثانیه
    setInterval(fetchMetrics, 10000);
});
