document.addEventListener("DOMContentLoaded", function () {
    const toggleBtn = document.getElementById("nav-toggle");
    const layout = document.querySelector(".layout");
    const navLogo = document.querySelector('.logo');

    if (toggleBtn) {
        toggleBtn.addEventListener("click", () => {
            const collapsed = layout.classList.toggle("collapsed");

            // Sizing/transition is handled entirely by CSS (.layout.collapsed .logo).
            // JS only needs to swap the actual image asset.
            navLogo.src = collapsed
                ? "static/images/capre-logo-collapsed.png"
                : "static/images/capre-logo.png";

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
});