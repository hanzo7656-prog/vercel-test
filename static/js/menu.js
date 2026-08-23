// ============================================================
// menu.js - مدیریت منو (بدون دکمه خروج)
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

    console.log('✅ منو راه‌اندازی شد (بدون دکمه خروج)');
}
