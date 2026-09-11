// ============================================================
// button-effects.js
// افکت‌های تعاملی دکمه‌ها - قابل استفاده در همه صفحات
// نسخه ۱.۰
// ============================================================

(function() {
    'use strict';
    
    // ============================================================
    // ۱. RIPPLE EFFECT
    // ============================================================
    
    /**
     * ایجاد افکت موج روی دکمه
     * استفاده: onclick="createRipple(event)"
     * یا: button-effects خودکار به همه دکمه‌های .btn-ripple اضافه می‌کنه
     */
    function createRipple(event) {
        const button = event.currentTarget || event.target.closest('.btn-ripple');
        if (!button) return;
        
        // حذف ripple قبلی
        const existingRipple = button.querySelector('.ripple-circle');
        if (existingRipple) {
            existingRipple.remove();
        }
        
        // محاسبه ابعاد
        const rect = button.getBoundingClientRect();
        const diameter = Math.max(rect.width, rect.height);
        const radius = diameter / 2;
        
        // موقعیت کلیک نسبت به دکمه
        let x, y;
        if (event.clientX && event.clientY) {
            x = event.clientX - rect.left - radius;
            y = event.clientY - rect.top - radius;
        } else {
            // اگه با کیبورد یا کلیک برنامه‌ای بود، از مرکز
            x = rect.width / 2 - radius;
            y = rect.height / 2 - radius;
        }
        
        // ساخت span
        const circle = document.createElement('span');
        circle.className = 'ripple-circle';
        circle.style.width = circle.style.height = `${diameter}px`;
        circle.style.left = `${x}px`;
        circle.style.top = `${y}px`;
        
        button.appendChild(circle);
        
        // حذف بعد از انیمیشن
        setTimeout(() => {
            if (circle.parentNode) {
                circle.remove();
            }
        }, 600);
    }
    
    // ============================================================
    // ۲. AUTO-ATTACH
    // ============================================================
    
    /**
     * به همه دکمه‌های .btn-ripple به صورت خودکار listener اضافه می‌کنه
     * لازم نیست onclick بنویسی
     */
    function attachRippleListeners(root = document) {
        const buttons = root.querySelectorAll('.btn-ripple:not([data-ripple-attached])');
        buttons.forEach(button => {
            button.setAttribute('data-ripple-attached', 'true');
            button.addEventListener('click', createRipple);
        });
    }
    
    // ============================================================
    // ۳. MAGNETIC EFFECT (اختیاری - برای دکمه‌های خاص)
    // ============================================================
    
    /**
     * دکمه به سمت موس کشیده میشه
     * استفاده: button-effects.makeMagnetic(button)
     */
    function makeMagnetic(button, strength = 0.3) {
        if (!button) return;
        
        button.style.transition = 'transform 0.3s cubic-bezier(0.22, 1, 0.36, 1)';
        
        button.addEventListener('mousemove', (e) => {
            const rect = button.getBoundingClientRect();
            const x = e.clientX - rect.left - rect.width / 2;
            const y = e.clientY - rect.top - rect.height / 2;
            
            button.style.transform = `translate(${x * strength}px, ${y * strength}px)`;
        });
        
        button.addEventListener('mouseleave', () => {
            button.style.transform = 'translate(0, 0)';
        });
    }
    
    // ============================================================
    // ۴. AUTO-INIT برای Magnetic
    // ============================================================
    
    function attachMagneticListeners(root = document) {
        const buttons = root.querySelectorAll('.btn-magnetic[data-magnetic-auto]:not([data-magnetic-attached])');
        buttons.forEach(button => {
            button.setAttribute('data-magnetic-attached', 'true');
            const strength = parseFloat(button.dataset.magneticStrength) || 0.3;
            makeMagnetic(button, strength);
        });
    }
    
    // ============================================================
    // ۵. AUTO-INIT در DOMContentLoaded
    // ============================================================
    
    function autoInit() {
        attachRippleListeners();
        attachMagneticListeners();
    }
    
    // اگه DOM آماده بود بلافاصله اجرا کن، وگرنه منتظر بمون
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', autoInit);
    } else {
        autoInit();
    }
    
    // ============================================================
    // ۶. MUTATION OBSERVER (برای محتوای داینامیک)
    // ============================================================
    
    /**
     * چون تب‌ها به صورت داینامیک لود میشن،
     * باید بعد از هر لود، دکمه‌های جدید رو شناسایی کنیم
     */
    const observer = new MutationObserver((mutations) => {
        let shouldUpdate = false;
        mutations.forEach(mutation => {
            if (mutation.addedNodes.length > 0) {
                shouldUpdate = true;
            }
        });
        
        if (shouldUpdate) {
            // با تأخیر کوچیک تا DOM کامل بشه
            setTimeout(() => {
                attachRippleListeners();
                attachMagneticListeners();
            }, 100);
        }
    });
    
    // شروع رصد تغییرات DOM
    if (document.body) {
        observer.observe(document.body, {
            childList: true,
            subtree: true
        });
    } else {
        document.addEventListener('DOMContentLoaded', () => {
            observer.observe(document.body, {
                childList: true,
                subtree: true
            });
        });
    }
    
    // ============================================================
    // ۷. EXPOSE API GLOBAL
    // ============================================================
    
    window.buttonEffects = {
        createRipple,
        makeMagnetic,
        attachRippleListeners,
        attachMagneticListeners,
        autoInit
    };
    
    // همچنین به صورت تابع سراسری برای onclick
    window.createRipple = createRipple;
    
    console.log('✅ Button Effects v1.0 loaded');
    
})();
