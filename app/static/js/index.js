document.addEventListener("DOMContentLoaded", function () {
    const toggleBtn = document.getElementById("nav-toggle");
    const layout = document.querySelector(".layout");
    const navLogo = document.querySelector('.logo');

    if (toggleBtn) {
        toggleBtn.addEventListener("click", () => {
            layout.classList.toggle("collapsed");
            navLogo.src = layout.classList.contains("collapsed")
                ? "static/images/capre-logo-collapsed.png"
                : "static/images/capre-logo.png";
            navLogo.style.width = layout.classList.contains("collapsed") ? "100px" : "140px";
            navLogo.style.height = layout.classList.contains("collapsed") ? "45px" : "45px";
        });
    }
});