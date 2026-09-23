(function () {
    const reader = document.querySelector('[data-manuscript-reader]');
    if (!reader) return;

    let canvas = null;
    let slots = [];
    let scrollTimer = null;
    const stage = reader.querySelector('[data-reader-stage]');
    const status = reader.querySelector('[data-reader-status]');
    const retry = reader.querySelector('[data-retry]');
    const previous = reader.querySelector('[data-previous]');
    const next = reader.querySelector('[data-next]');
    const input = reader.querySelector('#manuscript-page');
    const zoom = reader.querySelector('#manuscript-zoom');
    const view = reader.querySelector('#manuscript-view');
    const events = new AbortController();
    let pending = null;
    let pageCount = 0;
    let pageNumber = 1;
    let loading = true;
    let zoomFactor = 1;
    let pdfjsPromise = null;
    let pdfTask = null;
    let renderTask = null;
    let pan = null;

    function loadPdfJs() {
        if (!pdfjsPromise) {
            pdfjsPromise = import(reader.dataset.pdfjsUrl).then(pdfjs => {
                pdfjs.GlobalWorkerOptions.workerSrc = reader.dataset.workerUrl;
                return pdfjs;
            }).catch(error => { pdfjsPromise = null; throw error; });
        }
        return pdfjsPromise;
    }

    function clearPage() {
        renderTask?.cancel();
        renderTask = null;
        pdfTask?.destroy().catch(() => {});
        pdfTask = null;
        pan = null;
        stage.classList.remove('is-panning');
        slots.forEach(slot => {
            const page = slot.querySelector('canvas');
            page.hidden = true;
            page.width = page.height = 0;
        });
    }

    function controls() {
        previous.disabled = loading || !pageCount || pageNumber <= 1;
        next.disabled = loading || !pageCount || pageNumber >= pageCount;
        input.disabled = loading || !pageCount;
        view.disabled = loading || !pageCount;
        stage.setAttribute('aria-busy', String(loading));
    }

    function resize() {
        slots.forEach((slot, index) => {
            slot.hidden = view.value === 'single' && index + 1 !== pageNumber;
            slot.style.width = `${Math.max(120, stage.clientWidth - 18) * zoomFactor}px`;
        });
    }

    function setZoom(value, anchor) {
        if (!canvas) return;
        const slot = canvas.parentElement;
        const before = slot.getBoundingClientRect();
        const bounds = stage.getBoundingClientRect();
        const x = anchor?.x ?? bounds.left + stage.clientWidth / 2;
        const y = anchor?.y ?? bounds.top + stage.clientHeight / 2;
        const relativeX = before.width ? (x - before.left) / before.width : 0;
        const relativeY = before.height ? (y - before.top) / before.height : 0;
        zoomFactor = Math.max(.5, Math.min(3, value));
        const preset = Array.from(zoom.options).find(option => Number(option.value) === zoomFactor);
        if (preset) {
            zoom.value = preset.value;
        } else {
            const custom = zoom.querySelector('[data-custom-zoom]');
            custom.value = String(zoomFactor);
            custom.textContent = `${Math.round(zoomFactor * 100)}%`;
            custom.hidden = false;
            zoom.value = custom.value;
        }
        resize();
        if (!canvas.hidden) {
            const after = slot.getBoundingClientRect();
            stage.scrollLeft += after.left + relativeX * after.width - x;
            stage.scrollTop += after.top + relativeY * after.height - y;
        }
    }

    function errorMessage(response) {
        if (response.status === 401 || response.redirected) return 'Your session ended. Sign in again to continue.';
        if (response.status === 403) return 'You no longer have access to this manuscript.';
        if (response.status === 404) return 'This manuscript or page is no longer available.';
        if (response.status === 415) return 'A PDF copy is needed for viewing. Please contact the administrator.';
        return 'This manuscript could not be displayed. Please retry or contact the administrator.';
    }

    async function loadPage(number, background = false) {
        pending?.abort();
        const request = new AbortController();
        pending = request;
        loading = true;
        renderTask?.cancel();
        renderTask = null;
        pdfTask?.destroy().catch(() => {});
        pdfTask = null;
        retry.hidden = true;
        status.textContent = 'Loading manuscript…';
        controls();
        const options = { credentials: 'same-origin', cache: 'no-store', signal: request.signal };
        try {
            // Recheck metadata on each navigation, including after file replacement.
            const metadata = await fetch(reader.dataset.pagesUrl, options);
            if (!metadata.ok || metadata.redirected) throw new Error(errorMessage(metadata));
            const data = await metadata.json();
            if (!Number.isInteger(data.page_count) || data.page_count < 1) throw new Error('No pages are available.');
            pageCount = data.page_count;
            number = Math.max(1, Math.min(number, pageCount));
            if (slots.length !== pageCount) {
                clearPage();
                slots = Array.from({ length: pageCount }, (_, index) => {
                    const slot = document.createElement('div');
                    slot.className = 'manuscript-reader__page';
                    slot.style.aspectRatio = '8.5 / 11';
                    const page = document.createElement('canvas');
                    page.dataset.readerPage = String(index + 1);
                    page.setAttribute('role', 'img');
                    page.setAttribute('aria-label', `Manuscript page ${index + 1} of ${pageCount}`);
                    page.hidden = true;
                    slot.append(page);
                    return slot;
                });
                stage.replaceChildren(...slots);
                resize();
            }
            canvas = slots[number - 1].querySelector('canvas');
            const response = await fetch(`${reader.dataset.pagesUrl}/${number}?format=pdf`, options);
            if (!response.ok || response.redirected) throw new Error(errorMessage(response));
            if (!response.headers.get('Content-Type')?.startsWith('application/pdf')) {
                throw new Error('This manuscript could not be displayed. Please retry.');
            }
            const [pdfjs, dataBuffer] = await Promise.all([loadPdfJs(), response.arrayBuffer()]);
            if (request.signal.aborted || !reader.isConnected) return;
            // Only a newly generated watermarked image page is passed to PDF.js.
            pdfTask = pdfjs.getDocument({
                data: new Uint8Array(dataBuffer), isEvalSupported: false, useWasm: false,
            });
            const pdfDocument = await pdfTask.promise;
            const pdfPage = await pdfDocument.getPage(1);
            if (request.signal.aborted || !reader.isConnected) return;
            const original = pdfPage.getViewport({ scale: 1 });
            const viewport = pdfPage.getViewport({ scale: 1800 / Math.max(original.width, original.height) });
            slots[number - 1].style.aspectRatio = `${original.width} / ${original.height}`;
            canvas.width = Math.ceil(viewport.width);
            canvas.height = Math.ceil(viewport.height);
            renderTask = pdfPage.render({ canvas, viewport });
            await renderTask.promise;
            if (request.signal.aborted || !reader.isConnected) return;
            renderTask = null;
            if (!background) pageNumber = number;
            if (input.options.length !== pageCount) {
                input.replaceChildren(...Array.from({ length: pageCount }, (_, index) =>
                    new Option(String(index + 1), String(index + 1))));
            }
            input.value = String(pageNumber);
            reader.querySelector('[data-page-count]').textContent = `of ${pageCount}`;
            canvas.setAttribute('aria-label', `Manuscript page ${number} of ${pageCount}`);
            resize();
            canvas.hidden = false;
            // Keep only nearby raster pages in memory for long manuscripts.
            slots.forEach((slot, index) => {
                if (Math.abs(index + 1 - number) <= 2) return;
                const page = slot.querySelector('canvas');
                page.hidden = true;
                page.width = page.height = 0;
            });
            pdfTask?.destroy().catch(() => {});
            pdfTask = null;
            canvas = slots[pageNumber - 1].querySelector('canvas');
            status.textContent = `Page ${pageNumber} of ${pageCount}`;
        } catch (error) {
            if (request.signal.aborted) return;
            clearPage();
            status.textContent = error.message || 'Unable to load this page. Please retry.';
            retry.hidden = false;
        } finally {
            if (!request.signal.aborted) {
                loading = false;
                controls();
                stage.dispatchEvent(new Event('scroll'));
            }
        }
    }

    function jumpToPage(number) {
        number = Math.max(1, Math.min(number, pageCount || 1));
        pageNumber = number;
        resize();
        const slot = slots[number - 1];
        if (slot) stage.scrollTop += slot.getBoundingClientRect().top - stage.getBoundingClientRect().top - 9;
        loadPage(number);
    }

    const listen = (target, name, handler) => target.addEventListener(name, handler, { signal: events.signal });
    listen(previous, 'click', () => jumpToPage(pageNumber - 1));
    listen(next, 'click', () => jumpToPage(pageNumber + 1));
    listen(retry, 'click', () => loadPage(pageNumber));
    listen(zoom, 'change', () => setZoom(Number(zoom.value)));
    listen(view, 'change', () => jumpToPage(pageNumber));
    stage.addEventListener('wheel', event => {
        if (!event.ctrlKey || loading || !canvas || canvas.hidden || event.shiftKey || !event.deltaY) return;
        event.preventDefault();
        const unit = event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? stage.clientHeight : 1;
        const delta = Math.max(-100, Math.min(100, event.deltaY * unit));
        setZoom(zoomFactor * Math.exp(-delta * .0015), { x: event.clientX, y: event.clientY });
    }, { passive: false, signal: events.signal });
    listen(stage, 'pointerdown', event => {
        if (!canvas || canvas.hidden || event.button !== 0 || event.pointerType !== 'mouse') return;
        event.preventDefault();
        stage.focus({ preventScroll: true });
        pan = { x: event.clientX, y: event.clientY, left: stage.scrollLeft, top: stage.scrollTop };
        stage.setPointerCapture(event.pointerId);
        stage.classList.add('is-panning');
    });
    listen(stage, 'pointermove', event => {
        if (!pan) return;
        stage.scrollLeft = pan.left + pan.x - event.clientX;
        stage.scrollTop = pan.top + pan.y - event.clientY;
    });
    const stopPan = () => { pan = null; stage.classList.remove('is-panning'); };
    listen(stage, 'pointerup', stopPan);
    listen(stage, 'pointercancel', stopPan);
    listen(stage, 'lostpointercapture', stopPan);
    listen(stage, 'keydown', event => {
        if (!canvas || canvas.hidden || !['+', '=', '-', '0'].includes(event.key)) return;
        event.preventDefault();
        setZoom(event.key === '0' ? 1 : zoomFactor * (event.key === '-' ? .9 : 1.1));
    });
    listen(input, 'change', () => jumpToPage(Number(input.value)));
    listen(stage, 'scroll', () => {
        clearTimeout(scrollTimer);
        scrollTimer = setTimeout(() => {
            if (view.value === 'single' || document.hidden || !retry.hidden || !slots.length) return;
            const top = stage.getBoundingClientRect().top + Math.min(100, stage.clientHeight / 4);
            const index = slots.findIndex(slot => slot.getBoundingClientRect().bottom > top);
            if (index < 0) return;
            const number = index + 1;
            if (loading) return;
            if (slots[index].querySelector('canvas').hidden) loadPage(number);
            else {
                pageNumber = number;
                canvas = slots[index].querySelector('canvas');
                input.value = String(number);
                status.textContent = `Page ${number} of ${pageCount}`;
                controls();
                const bounds = stage.getBoundingClientRect();
                const missing = slots.findIndex(slot => {
                    const rect = slot.getBoundingClientRect();
                    return rect.bottom > bounds.top && rect.top < bounds.bottom && slot.querySelector('canvas').hidden;
                });
                if (missing >= 0) loadPage(missing + 1, true);
            }
        }, 100);
    });
    listen(document, 'visibilitychange' , () => {
        if (document.hidden) {
            pending?.abort();
            clearPage();
        } else if (reader.isConnected) {
            loadPage(pageNumber);
        }
    });
    listen(window, 'pagehide', () => { pending?.abort(); clearPage(); });
    listen(window, 'pageshow', event => { if (event.persisted) loadPage(pageNumber); });
    const resizeObserver = new ResizeObserver(resize);
    resizeObserver.observe(stage);
    // Dispose when the application's SPA navigation replaces the reader.
    const observer = new MutationObserver(() => {
        if (reader.isConnected) return;
        pending?.abort();
        clearPage();
        clearTimeout(scrollTimer);
        events.abort();
        resizeObserver.disconnect();
        observer.disconnect();
    });
    observer.observe(document.getElementById('page-content'), { childList: true });
    loadPage(1);
})();
