// ── EduNexus Theme Management Script ──

(function() {
    // Immediate execution to prevent flash of dark theme
    const theme = localStorage.getItem('theme') || 'dark';
    if (theme === 'light') {
        document.documentElement.classList.add('light-theme');
        document.addEventListener('DOMContentLoaded', () => {
            document.body.classList.add('light-theme');
        });
    }

    window.toggleTheme = function() {
        const docClass = document.documentElement.classList;
        const bodyClass = document.body.classList;
        
        const isLight = docClass.toggle('light-theme');
        bodyClass.toggle('light-theme', isLight);
        
        localStorage.setItem('theme', isLight ? 'light' : 'dark');
        updateThemeBtnIcon();
    };

    window.updateThemeBtnIcon = function() {
        const btn = document.getElementById('theme-toggle-btn');
        if (!btn) return;
        const isLight = document.documentElement.classList.contains('light-theme');
        btn.innerHTML = isLight ? '<i class="fas fa-sun"></i> Light' : '<i class="fas fa-moon"></i> Dark';
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

    document.addEventListener('DOMContentLoaded', applySavedTheme);
})();
