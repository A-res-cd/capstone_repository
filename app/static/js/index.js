(function () {
function initApp() {
    const toggleBtn = document.getElementById("nav-toggle");
    const layout = document.querySelector(".layout");
    const backdrop = document.getElementById("nav-backdrop");
    const MOBILE_QUERY = "(max-width: 900px)";
    const isMobile = () => window.matchMedia(MOBILE_QUERY).matches;

    function closeMobileNav() {
        if (layout) layout.classList.remove("mobile-nav-open");
    }

    if (toggleBtn && layout && !toggleBtn.dataset.bound) {
        toggleBtn.dataset.bound = "true";
        toggleBtn.addEventListener("click", () => {
            if (isMobile()) {
                // Mobile: slide the drawer open/closed. This is a transient
                // UI state, not a saved preference, so it isn't persisted
                // via /toggle-nav the way the desktop collapsed state is.
                layout.classList.toggle("mobile-nav-open");
                return;
            }

            const collapsed = layout.classList.toggle("collapsed");

            // Persist the new state in the session so it survives page loads
            // and only changes back when the user clicks the burger menu again.
            const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content;
            fetch("/toggle-nav", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    ...(csrfToken ? { "X-CSRFToken": csrfToken } : {}),
                },
                body: JSON.stringify({ collapsed }),
            }).catch(() => {
                // Non-critical — the UI already reflects the new state either way.
            });
        });
    }

    // Tapping the dimmed backdrop closes the drawer
    if (backdrop && !backdrop.dataset.bound) {
        backdrop.dataset.bound = "true";
        backdrop.addEventListener("click", closeMobileNav);
    }

    // Picking a nav link closes the drawer instead of leaving it open
    // behind the newly-loaded page
    document.querySelectorAll(".nav-item").forEach((link) => {
        if (link.dataset.navBound) return;
        link.dataset.navBound = "true";
        link.addEventListener("click", () => {
            if (isMobile()) closeMobileNav();
        });
    });

    document.querySelectorAll(".flash-list li, .mu-flash-list li").forEach((item) => {
        if (item.dataset.flashBound) return;
        item.dataset.flashBound = "true";

        const close = document.createElement("button");
        close.type = "button";
        close.className = "flash-close";
        close.setAttribute("aria-label", "Dismiss message");
        close.textContent = "×";

        const dismiss = () => {
            item.classList.add("flash-dismiss");
            window.setTimeout(() => item.remove(), 180);
        };

        close.addEventListener("click", dismiss);
        item.appendChild(close);
        window.setTimeout(dismiss, 10000);
    });

    // If the window is resized/rotated past the breakpoint, drop the
    // mobile-only open state so it doesn't linger into desktop view
    if (!window.__capreResizeBound) {
        window.__capreResizeBound = true;
        window.addEventListener("resize", () => {
            if (!isMobile()) closeMobileNav();
        });
    }

    // ── Auto-submitting filter bars ──────────────────────────────────
    // Applies to every GET filter form on the site (Explore Archive,
    // Manage Users, admin Requests, and any future one) generically —
    // targets the shared .filter-input/.filter-select classes rather
    // than a specific form/page, so a new filter form works without
    // needing to touch this file. Debounced on text input so it isn't
    // submitting on every single keystroke; selects submit immediately
    // since picking one is already a deliberate, discrete action.
    const FILTER_DEBOUNCE_MS = 500;
    let filterDebounceTimer = null;

    document.querySelectorAll(".filter-input").forEach((input) => {
        if (input.dataset.filterBound) return;
        input.dataset.filterBound = "true";
        input.addEventListener("input", () => {
            clearTimeout(filterDebounceTimer);
            filterDebounceTimer = setTimeout(() => {
                const form = input.closest("form");
                if (form) (form.requestSubmit ? form.requestSubmit() : form.submit());
            }, FILTER_DEBOUNCE_MS);
        });

        // A GET-form submit is a full page reload, which drops focus —
        // if this input already has a value (i.e. it's what triggered
        // the reload), restore focus with the cursor at the end so
        // continued typing feels uninterrupted instead of needing a
        // re-click after every pause.
        if (input.value) {
            input.focus();
            const end = input.value.length;
            input.setSelectionRange(end, end);
        }
    });

    document.querySelectorAll(".filter-select").forEach((select) => {
        if (select.dataset.filterBound) return;
        select.dataset.filterBound = "true";
        select.addEventListener("change", () => {
            const form = select.closest("form");
            if (form) (form.requestSubmit ? form.requestSubmit() : form.submit());
        });
    });
}

if (!window.__caprePageShowBound) {
    window.__caprePageShowBound = true;
    window.addEventListener("pageshow", (event) => {
        if (event.persisted) window.location.reload();
    });
}

window.CAPRE = window.CAPRE || {};
window.CAPRE.initApp = initApp;
document.addEventListener("DOMContentLoaded", initApp);
})();
