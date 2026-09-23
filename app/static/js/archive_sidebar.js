document.addEventListener('DOMContentLoaded', () => {

    let selectedCapstoneId = null;
    const MOBILE_QUERY = '(max-width: 900px)';
    const isMobile = () => window.matchMedia(MOBILE_QUERY).matches;
    const sidebarEl = document.querySelector('.archive-sidebar');
    const sidebarCard = document.getElementById('sidebar-card');
    const sidebarEmpty = document.getElementById('sidebar-empty');
    const requestLink = document.getElementById('sb-request-link');
    const requestDialog = document.getElementById('manuscript-request-dialog');
    const requestForm = document.getElementById('manuscript-request-form');

    if (requestLink && requestDialog && requestForm) {
        requestLink.addEventListener('click', (event) => {
            event.preventDefault();
            requestForm.reset();
            requestForm.action = requestLink.dataset.submitUrl;
            document.getElementById('manuscript-request-project').textContent =
                document.getElementById('sb-title').textContent;
            requestDialog.showModal();
        });
        requestDialog.querySelectorAll('[data-request-close]').forEach((button) => {
            button.addEventListener('click', () => requestDialog.close());
        });
    }

    document.querySelectorAll('.archive-card').forEach(card => {
        card.addEventListener('click', () => {
            const id = card.dataset.id;

            if (String(selectedCapstoneId) === String(id)) {
                card.classList.remove('active');
                selectedCapstoneId = null;
                sidebarCard.hidden = true;
                sidebarEmpty.hidden = false;
                sidebarEl?.classList.remove('archive-sidebar--mobile-open');
                document.body.classList.remove('archive-mobile-detail-open');
                return;
            }

            document.querySelectorAll('.archive-card').forEach(c => c.classList.remove('active'));
            card.classList.add('active');
            sidebarCard.hidden = false;
            sidebarEmpty.hidden = true;

            document.getElementById('sb-title').textContent = card.dataset.title;
            document.getElementById('sb-program').textContent = card.dataset.program;
            document.getElementById('sb-spec').textContent = card.dataset.spec;
            document.getElementById('sb-year').textContent = card.dataset.year;
            document.getElementById('sb-term').textContent = card.dataset.semester;

            const tagsContainer = document.getElementById('sb-keywords-tags');
            if (tagsContainer) {
                tagsContainer.replaceChildren();
                (card.dataset.keywords || '').split(',').forEach((kw) => {
                    const trimmed = kw.trim();
                    if (!trimmed) return;
                    const tag = document.createElement('span');
                    tag.className = 'sidebar-tag';
                    tag.textContent = trimmed;
                    tagsContainer.appendChild(tag);
                });
            }

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

            if (requestLink) {
                requestLink.href = requestLink.dataset.baseUrl.slice(0, -1) + id;
                requestLink.dataset.submitUrl = requestLink.dataset.submitBaseUrl.slice(0, -1) + id;
                requestLink.style.display = isApproved ? 'none' : '';
            }

            // On mobile, the sidebar becomes a full-screen overlay instead
            // of an inline block sitting below the list — tapping a card
            // opens it immediately (details + abstract/request buttons all
            // visible right away, no extra scrolling/tapping needed to
            // reach them), with a close button to get back to the list.
            if (isMobile() && sidebarEl) {
                sidebarEl.classList.add('archive-sidebar--mobile-open');
                document.body.classList.add('archive-mobile-detail-open');
            }
        });
    });

    const sidebarCloseBtn = document.getElementById('sidebar-close-btn');
    if (sidebarCloseBtn && sidebarEl) {
        sidebarCloseBtn.addEventListener('click', () => {
            sidebarEl.classList.remove('archive-sidebar--mobile-open');
            document.body.classList.remove('archive-mobile-detail-open');
        });
    }

    // Dropping back to desktop width should clear the mobile-only overlay
    // state so it doesn't linger if the window is resized/rotated.
    window.addEventListener('resize', () => {
        if (!isMobile() && sidebarEl) {
            sidebarEl.classList.remove('archive-sidebar--mobile-open');
            document.body.classList.remove('archive-mobile-detail-open');
        }
    });

    const citeBtn = document.getElementById('sb-cite-btn');
    const overlay = document.getElementById('cite-modal-overlay');
    const modalText = document.getElementById('cite-modal-text');
    const modalHeading = document.getElementById('cite-modal-heading');
    const formatSelect = document.getElementById('cite-format');
    const closeBtn = document.getElementById('cite-modal-close');
    const copyBtn = document.getElementById('cite-modal-copy');
    const downloadLink = document.getElementById('cite-modal-download');
    const copiedMsg = document.getElementById('cite-modal-copied');

    const citationLabels = {
        apa: { heading: 'APA 7 Citation', extension: 'txt' },
        bibtex: { heading: 'BibTeX Citation', extension: 'bib' },
        ris: { heading: 'RIS Citation', extension: 'ris' },
    };

    if (citeBtn) {
        citeBtn.addEventListener('click', async () => {
            if (!selectedCapstoneId) return;

            const citeLabel = citeBtn.querySelector('span');
            citeBtn.disabled = true;
            if (citeLabel) citeLabel.textContent = 'Citing…';

            try {
                const format = formatSelect?.value || 'apa';
                const res = await fetch(`/cite/${selectedCapstoneId}?format=${encodeURIComponent(format)}`, {
                    headers: { 'X-Requested-With': 'XMLHttpRequest' },
                });

                const data = await res.json();

                if (!res.ok) {
                    modalText.textContent = data.error || 'Something went wrong.';
                } else {
                    modalText.textContent = data.citation;
                    const formatMeta = citationLabels[data.format] || citationLabels.apa;
                    if (modalHeading) modalHeading.textContent = formatMeta.heading;
                    if (downloadLink) {
                        downloadLink.href = `/cite/${selectedCapstoneId}?format=${encodeURIComponent(data.format)}&download=1`;
                        downloadLink.querySelector('span').textContent = `Download .${formatMeta.extension}`;
                    }
                }

                copiedMsg.style.display = 'none';
                overlay.style.display = 'flex';

            } catch (err) {
                modalText.textContent = 'Network error. Please try again.';
                overlay.style.display = 'flex';
            } finally {
                citeBtn.disabled = false;
                if (citeLabel) citeLabel.textContent = 'Cite';
            }
        });
    }

    if (formatSelect && citeBtn) {
        formatSelect.addEventListener('change', () => citeBtn.click());
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
