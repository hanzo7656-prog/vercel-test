// ============================================================
// menu.js - مدیریت منو
// ============================================================

function initMenu() {
    const menuToggle = document.getElementById('menuToggle');
    const flyoutMenu = document.getElementById('flyoutMenu');
    const flyoutOverlay = document.getElementById('flyoutOverlay');

    if (!menuToggle || !flyoutMenu || !flyoutOverlay) {
        console.warn('❌ المنت‌های منو پیدا نشد');
        return;
    }

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

    // تنظیم active
    const currentPath = window.location.pathname;
    document.querySelectorAll('.flyout-menu a').forEach(link => {
        link.classList.remove('active');
        if (link.getAttribute('href') === currentPath) {
            link.classList.add('active');
        }
    });

    // ============================================================
    // دکمه خروج از منو - با همون مکانیک ساده
    // ============================================================
    const logoutBtn = document.getElementById('logoutMenuBtn');
    if (logoutBtn) {
        // حذف event listener قبلی
        const newBtn = logoutBtn.cloneNode(true);
        logoutBtn.parentNode.replaceChild(newBtn, logoutBtn);
        
        newBtn.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation();
            console.log('🚪 Logout from menu');
            
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
        });
    }

    console.log('✅ منو راه‌اندازی شد');
}
