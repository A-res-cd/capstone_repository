document.addEventListener("DOMContentLoaded", function () {
    const toggleBtn = document.getElementById("nav-toggle");
    const layout = document.querySelector(".layout");

    if (toggleBtn) {
        toggleBtn.addEventListener("click", () => {
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
});