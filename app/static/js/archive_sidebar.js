document.addEventListener('DOMContentLoaded', () => {

    let selectedCapstoneId = document.getElementById('sidebar-card')?.dataset.capstoneId || null;

    document.querySelectorAll('.archive-card').forEach(card => {
        card.addEventListener('click', () => {

            document.querySelectorAll('.archive-card').forEach(c => c.classList.remove('active'));
            card.classList.add('active');

            document.getElementById('sb-title').textContent = card.dataset.title;
            document.getElementById('sb-program').textContent = card.dataset.program;
            document.getElementById('sb-spec').textContent = card.dataset.spec;
            document.getElementById('sb-year').textContent = card.dataset.year;
            document.getElementById('sb-term').textContent = card.dataset.semester;
            document.getElementById('sb-citations').textContent = card.dataset.citations;

            const tagsContainer = document.getElementById('sb-keywords-tags');
            if (tagsContainer) {
                tagsContainer.innerHTML = '';
                (card.dataset.keywords || '').split(',').forEach((kw) => {
                    const trimmed = kw.trim();
                    if (!trimmed) return;
                    const tag = document.createElement('span');
                    tag.className = 'sidebar-tag';
                    tag.textContent = trimmed;
                    tagsContainer.appendChild(tag);
                });
            }

            const id = card.dataset.id;
            selectedCapstoneId = id;
            const isApproved = card.dataset.approved === 'true';

            const abstractLink = document.getElementById('sb-abstract-link');
            if (abstractLink) {
                abstractLink.href = abstractLink.dataset.baseUrl.slice(0, -1) + id;
                abstractLink.style.display = isApproved ? 'none' : '';
            }

            const fullviewLink = document.getElementById('sb-fullview-link');
            if (fullviewLink) {
                fullviewLink.href = fullviewLink.dataset.baseUrl.slice(0, -1) + id;
                fullviewLink.style.display = isApproved ? '' : 'none';
            }

            const requestLink = document.getElementById('sb-request-link');
            if (requestLink) {
                requestLink.href = requestLink.dataset.baseUrl.slice(0, -1) + id;
                requestLink.style.display = isApproved ? 'none' : '';
            }
        });
    });

    const citeBtn = document.getElementById('sb-cite-btn');
    const overlay = document.getElementById('cite-modal-overlay');
    const modalText = document.getElementById('cite-modal-text');
    const closeBtn = document.getElementById('cite-modal-close');
    const copyBtn = document.getElementById('cite-modal-copy');
    const copiedMsg = document.getElementById('cite-modal-copied');

    if (citeBtn) {
        citeBtn.addEventListener('click', async () => {
            if (!selectedCapstoneId) return;

            citeBtn.disabled = true;
            citeBtn.textContent = 'Citing…';

            try {
                const res = await fetch(`/cite/${selectedCapstoneId}`, {
                    method: 'POST',
                    headers: { 'X-Requested-With': 'XMLHttpRequest', 
                        'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content},
                });

                const data = await res.json();

                if (!res.ok) {
                    modalText.textContent = data.error || 'Something went wrong.';
                } else {
                    modalText.textContent = data.citation;

                    const sbCitations = document.getElementById('sb-citations');
                    if (sbCitations) sbCitations.textContent = data.citation_count;

                    const selectedCard = document.querySelector(`.archive-card[data-id="${selectedCapstoneId}"]`);
                    if (selectedCard) selectedCard.dataset.citations = data.citation_count;
                }

                copiedMsg.style.display = 'none';
                overlay.style.display = 'flex';

            } catch (err) {
                modalText.textContent = 'Network error. Please try again.';
                overlay.style.display = 'flex';
            } finally {
                citeBtn.disabled = false;
                citeBtn.textContent = 'Cite';
            }
        });
    }

    if (closeBtn) {
        closeBtn.addEventListener('click', () => {
            overlay.style.display = 'none';
        });
    }

    if (overlay) {
        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) overlay.style.display = 'none';
        });
    }

    if (copyBtn) {
        copyBtn.addEventListener('click', async () => {
            try {
                await navigator.clipboard.writeText(modalText.textContent);
                copiedMsg.style.display = 'block';
            } catch (err) {
                copiedMsg.textContent = 'Could not copy — please select and copy manually.';
                copiedMsg.style.display = 'block';
            }
        });
    }

    if (overlay) overlay.style.display = 'none';
});