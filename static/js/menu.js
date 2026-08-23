// ============================================================
// menu.js - مدیریت منو و نویگیشن
// ============================================================

function initMenu() {
    const menuToggle = document.getElementById('menuToggle');
    const flyoutMenu = document.getElementById('flyoutMenu');
    const flyoutOverlay = document.getElementById('flyoutOverlay');

    if (!menuToggle || !flyoutMenu || !flyoutOverlay) {
        console.warn('❌ المنت‌های منو پیدا نشد');
        return;
    }

    // جلوگیری از چندباره شدن
    if (window._menuInitialized) return;
    window._menuInitialized = true;

    function toggleMenu() {
        const isOpen = flyoutMenu.classList.toggle('open');
        flyoutOverlay.classList.toggle('open');
        menuToggle.classList.toggle('open');
        menuToggle.innerHTML = isOpen ? '<i class="fas fa-times"></i>' : '<i class="fas fa-bars"></i>';
    }

    menuToggle.addEventListener('click', toggleMenu);
    flyoutOverlay.addEventListener('click', toggleMenu);

    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape' && flyoutMenu.classList.contains('open')) {
            toggleMenu();
        }
    });

    // تنظیم کلاس active بر اساس مسیر فعلی
    const currentPath = window.location.pathname;
    const links = flyoutMenu.querySelectorAll('a');
    links.forEach(link => {
        link.classList.remove('active');
        if (link.getAttribute('href') === currentPath) {
            link.classList.add('active');
        }
    });

    // ⭐ اتصال دکمه خروج از منو (مشکل اصلی)
    const logoutLink = document.getElementById('logoutMenuBtn');
    if (logoutLink) {
        console.log('✅ Logout button found in menu, attaching event listener');
        // حذف event listenerهای قبلی
        const newLogoutLink = logoutLink.cloneNode(true);
        logoutLink.parentNode.replaceChild(newLogoutLink, logoutLink);
        
        newLogoutLink.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation();
            console.log('🚪 Logout button clicked from menu');
            
            if (!confirm('آیا از خروج از حساب کاربری اطمینان دارید؟')) {
                console.log('❌ User cancelled logout');
                return;
            }
            
            console.log('✅ User confirmed logout, sending request...');
            
            fetch('/logout', { 
                method: 'POST',
                credentials: 'include',
                headers: {
                    'Content-Type': 'application/json'
                }
            })
            .then(res => {
                console.log('📡 Response status:', res.status);
                return res.json();
            })
            .then(data => {
                console.log('📡 Response data:', data);
                window.location.href = '/login';
            })
            .catch(err => {
                console.error('❌ Logout error:', err);
                window.location.href = '/login';
            });
        });
    } else {
        console.warn('⚠️ Logout button not found in menu!');
    }

    console.log('✅ منو راه‌اندازی شد');
}

// ============================================================
// تابع کمکی برای خروج از منو (در صورت نیاز)
// ============================================================
function logoutFromMenu() {
    console.log('🚪 logoutFromMenu called');
    
    if (!confirm('آیا از خروج از حساب کاربری اطمینان دارید؟')) {
        console.log('❌ User cancelled logout');
        return;
    }
    
    console.log('✅ User confirmed logout, sending request...');
    
    fetch('/logout', { 
        method: 'POST',
        credentials: 'include',
        headers: {
            'Content-Type': 'application/json'
        }
    })
    .then(res => {
        console.log('📡 Response status:', res.status);
        return res.json();
    })
    .then(data => {
        console.log('📡 Response data:', data);
        window.location.href = '/login';
    })
    .catch(err => {
        console.error('❌ Logout error:', err);
        window.location.href = '/login';
    });
}
