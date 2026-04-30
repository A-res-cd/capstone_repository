document.addEventListener("DOMContentLoaded", function () {
    const toggleBtn = document.getElementById("nav-toggle");
    const layout = document.querySelector(".layout");

    if (toggleBtn) {
        toggleBtn.addEventListener("click", () => {
            layout.classList.toggle("collapsed");
        });
    }
});