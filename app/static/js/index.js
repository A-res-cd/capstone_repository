document.addEventListener("DOMContentLoaded", function () {
    const toggleBtn = document.getElementById("nav-toggle");
    const layout = document.querySelector(".layout");
    const backdrop = document.getElementById("nav-backdrop");
    const MOBILE_QUERY = "(max-width: 900px)";
    const isMobile = () => window.matchMedia(MOBILE_QUERY).matches;

    function closeMobileNav() {
        if (layout) layout.classList.remove("mobile-nav-open");
    }

    if (toggleBtn && layout) {
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
    if (backdrop) {
        backdrop.addEventListener("click", closeMobileNav);
    }

    // Picking a nav link closes the drawer instead of leaving it open
    // behind the newly-loaded page
    document.querySelectorAll(".nav-item").forEach((link) => {
        link.addEventListener("click", () => {
            if (isMobile()) closeMobileNav();
        });
    });

    // If the window is resized/rotated past the breakpoint, drop the
    // mobile-only open state so it doesn't linger into desktop view
    window.addEventListener("resize", () => {
        if (!isMobile()) closeMobileNav();
    });
});
