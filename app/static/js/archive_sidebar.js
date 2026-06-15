document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.archive-card').forEach(card => {
        card.addEventListener('click', () => {

            document.querySelectorAll('.archive-card').forEach(c => c.classList.remove('active'));
            card.classList.add('active');

            document.getElementById('sb-title').textContent = card.dataset.title;
            document.getElementById('sb-program').textContent = card.dataset.program;
            document.getElementById('sb-spec').textContent = card.dataset.spec;
            document.getElementById('sb-keywords').textContent = card.dataset.keywords;
            document.getElementById('sb-year').textContent = card.dataset.year;
            document.getElementById('sb-term').textContent = `${card.dataset.semester} – ${card.dataset.term}`;
            document.getElementById('sb-citations').textContent = card.dataset.citations;

            const id = card.dataset.id;

            const abstractLink = document.getElementById('sb-abstract-link');
            if (abstractLink){
                abstractLink.href = abstractLink.dataset.baseUrl.slice(0, -1) + id;
            }

            const requestLink = document.getElementById('sb-request-link');
            if (requestLink){
                requestLink.href = requestLink.dataset.baseUrl.slice(0, -1) + id;
            }
        })

    });
});