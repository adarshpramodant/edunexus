// ── EduNexus Theme and Session Management Script ──

(function() {
    // Immediate execution to prevent flash of dark theme
    const theme = localStorage.getItem('theme') || 'dark';
    if (theme === 'light') {
        document.documentElement.classList.add('light-theme');
        document.addEventListener('DOMContentLoaded', () => {
            if (document.body) {
                document.body.classList.add('light-theme');
            }
        });
    }

    window.toggleTheme = function() {
        const docClass = document.documentElement.classList;
        const bodyClass = document.body ? document.body.classList : null;
        
        const isLight = docClass.toggle('light-theme');
        if (bodyClass) {
            bodyClass.toggle('light-theme', isLight);
        }
        
        localStorage.setItem('theme', isLight ? 'light' : 'dark');
        updateThemeBtnIcon();
    };

    window.updateThemeBtnIcon = function() {
        const btn = document.getElementById('theme-toggle-btn');
        if (!btn) return;
        const isLight = document.documentElement.classList.contains('light-theme');
        btn.innerHTML = isLight ? '<i class="fas fa-sun"></i> Light Mode' : '<i class="fas fa-moon"></i> Dark Mode';
    };

    window.applySavedTheme = function() {
        const theme = localStorage.getItem('theme') || 'dark';
        const isLight = theme === 'light';
        document.documentElement.classList.toggle('light-theme', isLight);
        if (document.body) {
            document.body.classList.toggle('light-theme', isLight);
        }
        updateThemeBtnIcon();
    };

    // Global Logout Function - shared across all pages
    window.logout = function() {
        localStorage.clear();
        window.location.href = 'login.html';
    };

    // Global Sidebar Drawer Toggle
    window.toggleSidebar = function() {
        const sidebar = document.querySelector('.sidebar');
        const backdrop = document.getElementById('sidebar-backdrop');
        if (sidebar && backdrop) {
            sidebar.classList.toggle('open');
            backdrop.classList.toggle('active');
        }
    };

    document.addEventListener('DOMContentLoaded', applySavedTheme);
})();
