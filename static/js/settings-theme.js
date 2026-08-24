// ============================================================
// settings-theme.js - مدیریت تم، زبان و ترجمه
// ============================================================

// ============================================================
// تنظیمات پیش‌فرض
// ============================================================

const ThemeSettings = {
    themes: {
        dark: {
            name: '🌙 تیره',
            class: 'theme-dark',
            background: '#0a0e17',
            card: '#111d2b',
            text: '#e0e6ed',
            accent: '#00d4ff',
            border: '#1a2a3a',
            input: '#0a0e17'
        },
        light: {
            name: '☀️ روشن',
            class: 'theme-light',
            background: '#f0f2f5',
            card: '#ffffff',
            text: '#1a1a2e',
            accent: '#0066cc',
            border: '#d0d5dd',
            input: '#f8f9fa'
        },
        auto: {
            name: '🔄 خودکار',
            class: 'theme-auto',
            background: 'auto',
            card: 'auto',
            text: 'auto',
            accent: '#00d4ff',
            border: 'auto',
            input: 'auto'
        }
    },
    languages: {
        fa: {
            name: '🇮🇷 فارسی',
            dir: 'rtl',
            locale: 'fa-IR',
            file: 'fa.json'
        },
        en: {
            name: '🇬🇧 English',
            dir: 'ltr',
            locale: 'en-US',
            file: 'en.json'
        }
    },
    currentTheme: 'dark',
    currentLanguage: 'fa',
    translations: {}
};

// ============================================================
// بارگذاری تنظیمات ذخیره شده
// ============================================================

function loadThemeSettings() {
    try {
        const savedTheme = localStorage.getItem('theme_preference');
        if (savedTheme && ThemeSettings.themes[savedTheme]) {
            ThemeSettings.currentTheme = savedTheme;
        }
        
        const savedLang = localStorage.getItem('language_preference');
        if (savedLang && ThemeSettings.languages[savedLang]) {
            ThemeSettings.currentLanguage = savedLang;
        }
    } catch (e) {
        console.warn('⚠️ خطا در بارگذاری تنظیمات:', e);
    }
}

// ============================================================
// اعمال تم
// ============================================================

function applyTheme(theme) {
    const body = document.body;
    const root = document.documentElement;
    
    body.classList.remove('theme-dark', 'theme-light', 'theme-auto');
    
    if (theme === 'auto') {
        body.classList.add('theme-auto');
        const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
        applyThemeColors(prefersDark ? 'dark' : 'light');
    } else {
        body.classList.add(`theme-${theme}`);
        applyThemeColors(theme);
    }
    
    try {
        localStorage.setItem('theme_preference', theme);
    } catch (e) {}
    
    ThemeSettings.currentTheme = theme;
    updateThemeSelect(theme);
}

function applyThemeColors(theme) {
    const colors = ThemeSettings.themes[theme];
    if (!colors) return;
    
    const root = document.documentElement;
    root.style.setProperty('--bg-color', colors.background);
    root.style.setProperty('--card-color', colors.card);
    root.style.setProperty('--text-color', colors.text);
    root.style.setProperty('--accent-color', colors.accent);
    root.style.setProperty('--border-color', colors.border);
    root.style.setProperty('--input-bg', colors.input);
}

// ============================================================
// اعمال زبان
// ============================================================

function applyLanguage(lang) {
    const langData = ThemeSettings.languages[lang];
    if (!langData) return;
    
    document.documentElement.dir = langData.dir;
    document.documentElement.lang = lang;
    
    try {
        localStorage.setItem('language_preference', lang);
    } catch (e) {}
    
    ThemeSettings.currentLanguage = lang;
    updateLanguageSelect(lang);
    
    loadTranslations(lang);
}

// ============================================================
// بارگذاری ترجمه‌ها
// ============================================================

function loadTranslations(lang) {
    const langData = ThemeSettings.languages[lang];
    if (!langData) return;
    
    fetch(`/static/locales/${langData.file}`)
        .then(res => {
            if (!res.ok) throw new Error('File not found');
            return res.json();
        })
        .then(data => {
            ThemeSettings.translations = data;
            applyTranslations();
            console.log(`✅ ترجمه ${lang} بارگذاری شد`);
        })
        .catch(err => {
            console.warn('⚠️ خطا در بارگذاری ترجمه:', err);
            // Fallback: استفاده از متن‌های داخل HTML
        });
}

function applyTranslations() {
    const t = ThemeSettings.translations;
    if (!t || Object.keys(t).length === 0) return;
    
    // تمام المنت‌های دارای data-i18n
    document.querySelectorAll('[data-i18n]').forEach(el => {
        const key = el.getAttribute('data-i18n');
        if (t[key]) {
            el.textContent = t[key];
        }
    });
    
    // المنت‌های دارای placeholder
    document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
        const key = el.getAttribute('data-i18n-placeholder');
        if (t[key]) {
            el.placeholder = t[key];
        }
    });
    
    // المنت‌های دارای title
    document.querySelectorAll('[data-i18n-title]').forEach(el => {
        const key = el.getAttribute('data-i18n-title');
        if (t[key]) {
            el.title = t[key];
        }
    });
    
    // آپدیت المنت‌های select
    document.querySelectorAll('select[data-i18n-options]').forEach(select => {
        const key = select.getAttribute('data-i18n-options');
        if (t[key]) {
            // این برای موارد خاص استفاده میشه
        }
    });
}

// ============================================================
// به‌روزرسانی المنت‌های انتخاب
// ============================================================

function updateThemeSelect(theme) {
    const select = document.getElementById('themeSelect');
    if (select) select.value = theme;
}

function updateLanguageSelect(lang) {
    const select = document.getElementById('languageSelect');
    if (select) select.value = lang;
}

// ============================================================
// راه‌اندازی اولیه
// ============================================================

function initThemeAndLanguage() {
    loadThemeSettings();
    applyTheme(ThemeSettings.currentTheme);
    applyLanguage(ThemeSettings.currentLanguage);
    
    const themeSelect = document.getElementById('themeSelect');
    if (themeSelect) {
        themeSelect.addEventListener('change', function() {
            applyTheme(this.value);
        });
    }
    
    const langSelect = document.getElementById('languageSelect');
    if (langSelect) {
        langSelect.addEventListener('change', function() {
            applyLanguage(this.value);
        });
    }
}

// ============================================================
// تشخیص تغییر تم سیستم (برای حالت auto)
// ============================================================

if (window.matchMedia) {
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
    mediaQuery.addEventListener('change', function(e) {
        if (ThemeSettings.currentTheme === 'auto') {
            applyThemeColors(e.matches ? 'dark' : 'light');
        }
    });
}

// ============================================================
// اجرا بعد از بارگذاری DOM
// ============================================================

document.addEventListener('DOMContentLoaded', function() {
    initThemeAndLanguage();
});

console.log('✅ Theme & Language manager loaded');
