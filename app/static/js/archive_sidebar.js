document.addEventListener('DOMContentLoaded', () => {

    let selectedCapstoneId = document.getElementById('sidebar-card')?.dataset.capstoneId || null;
    const MOBILE_QUERY = '(max-width: 900px)';
    const isMobile = () => window.matchMedia(MOBILE_QUERY).matches;
    const sidebarEl = document.querySelector('.archive-sidebar');
    const sidebarSaveBtn = document.getElementById('sb-save-btn');
    const saveBaseUrl = sidebarSaveBtn?.dataset.baseUrl;

    const setSaveButton = (button, saved) => {
        if (!button) return;
        button.classList.toggle('is-saved', saved);
        button.setAttribute('aria-pressed', String(saved));
        button.setAttribute('aria-label', saved ? 'Remove from saved capstones' : 'Save capstone');
        const icon = button.querySelector('i');
        if (icon) icon.className = `bx ${saved ? 'bxs-bookmark' : 'bx-bookmark'}`;
        const label = button.querySelector('span');
        if (label) label.textContent = saved ? 'Saved' : 'Save';
    };

    const toggleSaved = async (capstoneId, button) => {
        if (!saveBaseUrl || !capstoneId) return;
        button.disabled = true;
        try {
            const response = await fetch(saveBaseUrl.slice(0, -1) + capstoneId, {
                method: 'POST',
                headers: {
                    'X-Requested-With': 'XMLHttpRequest',
                    'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content,
                },
            });
            const data = await response.json();
            if (!response.ok) throw new Error(data.error || 'Could not update saved capstone.');

            const card = document.querySelector(`.archive-card[data-id="${capstoneId}"]`);
            if (card) {
                card.dataset.saved = String(data.saved);
                setSaveButton(card.querySelector('.save-capstone-btn'), data.saved);
            }
            if (String(selectedCapstoneId) === String(capstoneId)) {
                setSaveButton(sidebarSaveBtn, data.saved);
            }

            if (!data.saved && document.querySelector('input[name="saved"]:checked')) {
                window.location.reload();
            }
        } catch (error) {
            window.alert(error.message);
        } finally {
            button.disabled = false;
        }
    };

    document.querySelectorAll('.archive-card').forEach(card => {
        card.addEventListener('click', () => {

            document.querySelectorAll('.archive-card').forEach(c => c.classList.remove('active'));
            card.classList.add('active');

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

            const id = card.dataset.id;
            selectedCapstoneId = id;
            const isApproved = card.dataset.approved === 'true';
            setSaveButton(sidebarSaveBtn, card.dataset.saved === 'true');

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

    document.querySelectorAll('.save-capstone-btn').forEach((button) => {
        button.addEventListener('click', (event) => {
            event.stopPropagation();
            toggleSaved(button.dataset.capstoneId, button);
        });
    });

    if (sidebarSaveBtn) {
        sidebarSaveBtn.addEventListener('click', () => {
            toggleSaved(selectedCapstoneId, sidebarSaveBtn);
        });
    }

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
