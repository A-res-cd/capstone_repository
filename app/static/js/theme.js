/* app/static/js/theme.js
 *
 * Light/dark theme toggle. The actual "no flash of wrong theme"
 * application happens via an inline <script> in base.html's <head>
 * (runs before CSS paints); this file only wires up the header
 * button once the DOM is ready and keeps localStorage in sync.
 */
(function () {
    const STORAGE_KEY = 'capre-theme';

    function applyTheme(theme) {
        if (theme === 'dark') {
            document.documentElement.setAttribute('data-theme', 'dark');
        } else {
            document.documentElement.removeAttribute('data-theme');
        }
    }

    function currentTheme() {
        return document.documentElement.getAttribute('data-theme') === 'dark' ? 'dark' : 'light';
    }

    document.addEventListener('DOMContentLoaded', () => {
        const toggle = document.getElementById('theme-toggle');
        if (!toggle) return;

        toggle.addEventListener('click', () => {
            const next = currentTheme() === 'dark' ? 'light' : 'dark';
            applyTheme(next);
            try {
                localStorage.setItem(STORAGE_KEY, next);
            } catch (e) {
                /* localStorage unavailable (private mode, etc.) — theme
                   still applies for this page load, just won't persist */
            }
        });
    });
})();
