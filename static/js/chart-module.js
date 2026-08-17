// ============================================================
// ماژول نمودار - نسخه کامل با ابزارک‌های واقعی
// ============================================================

const ChartModule = (function() {
    'use strict';

    // ============================================================
    // STATE
    // ============================================================
    let chartInstance = null;
    let currentData = [];
    let currentCoin = 'bitcoin';
    let currentPeriod = '24h';
    let isLogScale = false;
    let showMA = false;
    let autoUpdateInterval = null;
    let isFullscreen = false;

    // ============================================================
    // DOM REFS
    // ============================================================
    const DOM = {
        container: null,
        canvas: null,
        priceDisplay: null,
        changeDisplay: null,
        highDisplay: null,
        lowDisplay: null,
        maToggle: null,
        logToggle: null,
        fullscreenBtn: null,
        zoomInBtn: null,
        zoomOutBtn: null,
        resetBtn: null,
        downloadBtn: null,
        loading: null,
        error: null,
        coinSelect: null,
        periodSelect: null,
        refreshBtn: null,
    };

    // ============================================================
    // PRIVATE METHODS
    // ============================================================

    function getCoinName(id) {
        const names = {
            bitcoin: 'بیت‌کوین (BTC)',
            ethereum: 'اتریوم (ETH)',
            solana: 'سولانا (SOL)',
            ripple: 'ریپل (XRP)',
            cardano: 'کاردانو (ADA)',
            dogecoin: 'داوج‌کوین (DOGE)',
            polkadot: 'پولکادات (DOT)',
            chainlink: 'چین‌لینک (LINK)',
            avalanche: 'آوالانچ (AVAX)',
            polygon: 'پالیگان (MATIC)',
        };
        return names[id] || id;
    }

    function formatPrice(value) {
        if (value >= 1000) return '$' + Math.round(value).toLocaleString();
        if (value >= 1) return '$' + value.toFixed(2);
        return '$' + value.toFixed(4);
    }

    function calculateMA(data, window) {
        if (data.length < window) return [];
        const ma = [];
        for (let i = 0; i < data.length; i++) {
            if (i < window - 1) {
                ma.push(null);
            } else {
                const sum = data.slice(i - window + 1, i + 1).reduce((a, b) => a + b, 0);
                ma.push(sum / window);
            }
        }
        return ma;
    }

    // ============================================================
    // AUTO UPDATE (هر ۱۰ ثانیه)
    // ============================================================
    function startAutoUpdate() {
        if (autoUpdateInterval) clearInterval(autoUpdateInterval);
        autoUpdateInterval = setInterval(() => {
            updatePriceOnly();
        }, 10000);
    }

    function stopAutoUpdate() {
        if (autoUpdateInterval) {
            clearInterval(autoUpdateInterval);
            autoUpdateInterval = null;
        }
    }

    function updatePriceOnly() {
        // فقط قیمت لحظه‌ای رو میگیریم بدون رندر مجدد نمودار
        fetch(`/test-api?type=coin&coin=${currentCoin}`)
            .then(res => res.json())
            .then(data => {
                if (data.success && data.data) {
                    const coin = data.data;
                    const price = coin.price || 0;
                    const change = coin.priceChange1d || 0;

                    // به‌روزرسانی قیمت
                    if (DOM.priceDisplay) {
                        DOM.priceDisplay.textContent = formatPrice(price);
                    }
                    if (DOM.changeDisplay) {
                        const sign = change >= 0 ? '▲' : '▼';
                        DOM.changeDisplay.textContent = `${sign} ${Math.abs(change).toFixed(2)}%`;
                        DOM.changeDisplay.style.color = change >= 0 ? '#00ff88' : '#ff4444';
                    }
                }
            })
            .catch(() => {});
    }

    // ============================================================
    // CREATE CHART
    // ============================================================
    function createChart(data, coin, period) {
        if (!DOM.canvas) return;

        // Destroy existing chart
        if (chartInstance) {
            chartInstance.destroy();
            chartInstance = null;
        }

        // پاک کردن خطا
        if (DOM.error) DOM.error.style.display = 'none';

        if (!data || data.length === 0) {
            showError('داده‌ای برای نمایش وجود ندارد');
            return;
        }

        currentData = data;
        currentCoin = coin;
        currentPeriod = period;

        const ctx = DOM.canvas.getContext('2d');

        // Extract data
        const timestamps = data.map(p => new Date(p[0] * 1000));
        const prices = data.map(p => p[1]);

        // Calculate price change
        const firstPrice = prices[0];
        const lastPrice = prices[prices.length - 1];
        const change = lastPrice - firstPrice;
        const changePercent = firstPrice !== 0 ? (change / firstPrice) * 100 : 0;

        // Update price display
        if (DOM.priceDisplay) {
            DOM.priceDisplay.textContent = formatPrice(lastPrice);
            DOM.priceDisplay.style.color = change >= 0 ? '#00ff88' : '#ff4444';
        }
        if (DOM.changeDisplay) {
            const sign = change >= 0 ? '▲' : '▼';
            DOM.changeDisplay.textContent = `${sign} ${Math.abs(changePercent).toFixed(2)}%`;
            DOM.changeDisplay.style.color = change >= 0 ? '#00ff88' : '#ff4444';
        }

        // High/Low
        const high = Math.max(...prices);
        const low = Math.min(...prices);
        if (DOM.highDisplay) DOM.highDisplay.textContent = formatPrice(high);
        if (DOM.lowDisplay) DOM.lowDisplay.textContent = formatPrice(low);

        // Gradient
        const gradient = ctx.createLinearGradient(0, 0, 0, DOM.canvas.parentElement?.clientHeight || 300);
        gradient.addColorStop(0, 'rgba(0, 212, 255, 0.7)');
        gradient.addColorStop(0.4, 'rgba(0, 212, 255, 0.25)');
        gradient.addColorStop(1, 'rgba(0, 212, 255, 0.0)');

        // Datasets
        const datasets = [{
            label: 'قیمت (USD)',
            data: prices,
            borderColor: '#00d4ff',
            backgroundColor: gradient,
            borderWidth: 2.5,
            pointRadius: 0,
            pointHoverRadius: 6,
            pointBackgroundColor: '#00d4ff',
            pointBorderColor: '#00d4ff',
            tension: 0.3,
            fill: true,
            yAxisID: 'y',
        }];

        // Moving Average
        if (showMA) {
            const ma20 = calculateMA(prices, 20);
            datasets.push({
                label: 'MA ۲۰',
                data: ma20,
                borderColor: '#ffaa00',
                borderWidth: 1.5,
                borderDash: [5, 5],
                pointRadius: 0,
                fill: false,
                tension: 0.3,
                yAxisID: 'y',
            });
        }

        // Chart config
        const config = {
            type: 'line',
            data: {
                labels: timestamps,
                datasets: datasets,
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: {
                    intersect: false,
                    mode: 'index',
                },
                plugins: {
                    legend: {
                        labels: {
                            color: '#a0b4c8',
                            font: { family: 'Vazir', size: 11 },
                            boxWidth: 12,
                            padding: 12,
                        }
                    },
                    tooltip: {
                        backgroundColor: 'rgba(13, 22, 36, 0.9)',
                        titleColor: '#e0e6ed',
                        bodyColor: '#00d4ff',
                        borderColor: '#1a2a3a',
                        borderWidth: 1,
                        padding: 12,
                        cornerRadius: 8,
                        titleFont: { family: 'Vazir' },
                        bodyFont: { family: 'Vazir' },
                        callbacks: {
                            label: function(context) {
                                return formatPrice(context.parsed.y);
                            },
                            afterLabel: function(context) {
                                const idx = context.dataIndex;
                                const date = new Date(currentData[idx][0] * 1000);
                                return date.toLocaleString('fa-IR', {
                                    hour: '2-digit',
                                    minute: '2-digit',
                                    day: '2-digit',
                                    month: '2-digit',
                                    year: 'numeric'
                                });
                            }
                        }
                    },
                    zoom: {
                        pan: {
                            enabled: true,
                            mode: 'x',
                        },
                        zoom: {
                            wheel: {
                                enabled: true,
                                speed: 0.05,
                            },
                            pinch: {
                                enabled: true,
                            },
                            mode: 'x',
                        },
                        limits: {
                            x: { minRange: 5 },
                        },
                    },
                },
                scales: {
                    x: {
                        type: 'time',
                        time: {
                            unit: getTimeUnit(period),
                            displayFormats: {
                                hour: 'HH:mm',
                                day: 'MMM DD',
                                week: 'MMM DD',
                                month: 'MMM YYYY',
                            },
                        },
                        grid: { color: 'rgba(255,255,255,0.04)' },
                        ticks: {
                            color: '#7a8fa3',
                            font: { family: 'Vazir', size: 10 },
                            maxTicksLimit: 12,
                        },
                    },
                    y: {
                        type: isLogScale ? 'logarithmic' : 'linear',
                        grid: { color: 'rgba(255,255,255,0.04)' },
                        ticks: {
                            color: '#7a8fa3',
                            font: { family: 'Vazir', size: 10 },
                            callback: function(value) {
                                return formatPrice(value);
                            }
                        },
                    },
                },
                animation: {
                    duration: 800,
                    easing: 'easeOutQuart',
                },
            },
        };

        chartInstance = new Chart(DOM.canvas, config);
        hideLoading();

        // شروع آپدیت خودکار
        startAutoUpdate();
    }

    function getTimeUnit(period) {
        const map = {
            '24h': 'hour',
            '1w': 'day',
            '1m': 'day',
            '3m': 'week',
        };
        return map[period] || 'day';
    }

    // ============================================================
    // LOAD DATA
    // ============================================================
    function loadData(coin, period) {
        showLoading();
        if (DOM.error) DOM.error.style.display = 'none';

        fetch(`/test-api?type=chart&coin=${coin}&period=${period}`)
            .then(res => res.json())
            .then(data => {
                if (data.success && data.count > 0) {
                    const chartData = data.sample || data.data || [];
                    if (chartData.length === 0) {
                        showError('داده‌ای برای این بازه وجود ندارد');
                        return;
                    }
                    createChart(chartData, coin, period);
                } else {
                    showError(data.error || 'خطا در دریافت داده');
                }
            })
            .catch(err => {
                showError('خطا در ارتباط با سرور');
                console.error('Chart error:', err);
            });
    }

    // ============================================================
    // UI HELPERS
    // ============================================================
    function showLoading() {
        if (DOM.loading) DOM.loading.style.display = 'flex';
        if (DOM.canvas) DOM.canvas.style.display = 'none';
    }

    function hideLoading() {
        if (DOM.loading) DOM.loading.style.display = 'none';
        if (DOM.canvas) DOM.canvas.style.display = 'block';
    }

    function showError(message) {
        hideLoading();
        if (DOM.error) {
            DOM.error.textContent = '❌ ' + message;
            DOM.error.style.display = 'block';
        }
    }

    // ============================================================
    // TOGGLE FUNCTIONS
    // ============================================================
    function toggleMA() {
        showMA = !showMA;
        if (DOM.maToggle) {
            DOM.maToggle.classList.toggle('active');
        }
        if (currentData.length > 0) {
            createChart(currentData, currentCoin, currentPeriod);
        }
    }

    function toggleLogScale() {
        isLogScale = !isLogScale;
        if (DOM.logToggle) {
            DOM.logToggle.classList.toggle('active');
        }
        if (chartInstance) {
            chartInstance.options.scales.y.type = isLogScale ? 'logarithmic' : 'linear';
            chartInstance.update();
        }
    }

    // ============================================================
    // FULLSCREEN
    // ============================================================
    function toggleFullscreen() {
        const container = DOM.container;
        if (!container) return;

        if (!document.fullscreenElement) {
            container.requestFullscreen().catch(err => {
                // Fallback برای مرورگرهای مختلف
                if (container.webkitRequestFullscreen) {
                    container.webkitRequestFullscreen();
                }
            });
            if (DOM.fullscreenBtn) DOM.fullscreenBtn.textContent = '⛶ خروج';
        } else {
            if (document.exitFullscreen) {
                document.exitFullscreen();
            } else if (document.webkitExitFullscreen) {
                document.webkitExitFullscreen();
            }
            if (DOM.fullscreenBtn) DOM.fullscreenBtn.textContent = '⛶';
        }
    }

    // ============================================================
    // ZOOM
    // ============================================================
    function zoomIn() {
        if (chartInstance) {
            const currentZoom = chartInstance.options.plugins.zoom.zoom?.x || 1;
            chartInstance.zoom(1.2);
        }
    }

    function zoomOut() {
        if (chartInstance) {
            chartInstance.zoom(0.8);
        }
    }

    function resetZoom() {
        if (chartInstance) {
            chartInstance.resetZoom();
        }
    }

    // ============================================================
    // DOWNLOAD PNG
    // ============================================================
    function downloadPNG() {
        if (!DOM.canvas) return;
        const link = document.createElement('a');
        link.download = `chart_${currentCoin}_${currentPeriod}.png`;
        link.href = DOM.canvas.toDataURL('image/png');
        link.click();
    }

    // ============================================================
    // PUBLIC API
    // ============================================================
    return {
        init: function(containerId, options = {}) {
            const container = document.getElementById(containerId);
            if (!container) {
                console.error('Chart container not found:', containerId);
                return;
            }

            DOM.container = container;
            DOM.canvas = container.querySelector('#chartCanvas');
            DOM.priceDisplay = container.querySelector('#chartPrice');
            DOM.changeDisplay = container.querySelector('#chartChange');
            DOM.highDisplay = container.querySelector('#chartHigh');
            DOM.lowDisplay = container.querySelector('#chartLow');
            DOM.maToggle = container.querySelector('#maToggle');
            DOM.logToggle = container.querySelector('#logToggle');
            DOM.fullscreenBtn = container.querySelector('#fullscreenBtn');
            DOM.zoomInBtn = container.querySelector('#zoomInBtn');
            DOM.zoomOutBtn = container.querySelector('#zoomOutBtn');
            DOM.resetBtn = container.querySelector('#resetZoom');
            DOM.downloadBtn = container.querySelector('#downloadBtn');
            DOM.loading = container.querySelector('#chartLoading');
            DOM.error = container.querySelector('#chartError');
            DOM.coinSelect = container.querySelector('#chartCoin');
            DOM.periodSelect = container.querySelector('#chartPeriod');
            DOM.refreshBtn = container.querySelector('#chartRefresh');

            // Set initial values
            if (DOM.coinSelect) {
                DOM.coinSelect.value = options.coin || 'bitcoin';
                currentCoin = DOM.coinSelect.value;
            }
            if (DOM.periodSelect) {
                DOM.periodSelect.value = options.period || '24h';
                currentPeriod = DOM.periodSelect.value;
            }

            // Bind events
            if (DOM.coinSelect) {
                DOM.coinSelect.addEventListener('change', function() {
                    currentCoin = this.value;
                    // توقف آپدیت خودکار قبل از بارگذاری جدید
                    stopAutoUpdate();
                    loadData(currentCoin, currentPeriod);
                });
            }

            if (DOM.periodSelect) {
                DOM.periodSelect.addEventListener('change', function() {
                    currentPeriod = this.value;
                    stopAutoUpdate();
                    loadData(currentCoin, currentPeriod);
                });
            }

            if (DOM.refreshBtn) {
                DOM.refreshBtn.addEventListener('click', function() {
                    stopAutoUpdate();
                    loadData(currentCoin, currentPeriod);
                });
            }

            if (DOM.maToggle) {
                DOM.maToggle.addEventListener('click', toggleMA);
            }

            if (DOM.logToggle) {
                DOM.logToggle.addEventListener('click', toggleLogScale);
            }

            if (DOM.fullscreenBtn) {
                DOM.fullscreenBtn.addEventListener('click', toggleFullscreen);
            }

            if (DOM.zoomInBtn) {
                DOM.zoomInBtn.addEventListener('click', zoomIn);
            }

            if (DOM.zoomOutBtn) {
                DOM.zoomOutBtn.addEventListener('click', zoomOut);
            }

            if (DOM.resetBtn) {
                DOM.resetBtn.addEventListener('click', resetZoom);
            }

            if (DOM.downloadBtn) {
                DOM.downloadBtn.addEventListener('click', downloadPNG);
            }

            // Fullscreen change event
            document.addEventListener('fullscreenchange', function() {
                if (DOM.fullscreenBtn) {
                    DOM.fullscreenBtn.textContent = document.fullscreenElement ? '⛶ خروج' : '⛶';
                }
            });

            // Initial load
            loadData(currentCoin, currentPeriod);
        },

        refresh: function() {
            stopAutoUpdate();
            loadData(currentCoin, currentPeriod);
        },

        destroy: function() {
            stopAutoUpdate();
            if (chartInstance) {
                chartInstance.destroy();
                chartInstance = null;
            }
        },
    };
})();
