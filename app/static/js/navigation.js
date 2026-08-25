(function () {
    const CONTENT_SELECTOR = '#page-content';
    const TRANSITION_MS = 170;
    const CORE_SCRIPTS = ['theme.js', 'index.js', 'spa_navigation.js'];
    let isNavigating = false;

    function contentEl() {
        return document.querySelector(CONTENT_SELECTOR);
    }

    function prefersReducedMotion() {
        return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    }

    function wait(ms) {
        return new Promise((resolve) => window.setTimeout(resolve, ms));
    }

    function nextPaint() {
        return new Promise((resolve) => {
            window.requestAnimationFrame(() => window.requestAnimationFrame(resolve));
        });
    }

    function sameOriginUrl(href) {
        return new URL(href, window.location.href);
    }

    function shouldHandleLink(link, event) {
        if (!link || event.defaultPrevented) return false;
        if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return false;
        if (link.target && link.target !== '_self') return false;
        if (link.hasAttribute('download')) return false;

        const url = sameOriginUrl(link.href);
        if (url.origin !== window.location.origin) return false;
        if (url.pathname === window.location.pathname && url.search === window.location.search) return false;
        if (url.pathname === '/logout') return false;
        if (['/', '/signin', '/signup', '/forgot_password', '/verify_otp', '/reset_password'].includes(url.pathname)) return false;
        if (url.pathname.startsWith('/repository/view/') || url.pathname.startsWith('/repository/pdf/') || url.pathname.startsWith('/manuscript/view/')) return false;
        if (/\.(pdf|doc|docx|png|jpe?g|gif|zip)$/i.test(url.pathname)) return false;

        return true;
    }

    function updateHead(doc) {
        const nextTitle = doc.querySelector('title');
        if (nextTitle) document.title = nextTitle.textContent;

        const nextToken = doc.querySelector('meta[name="csrf-token"]');
        const token = document.querySelector('meta[name="csrf-token"]');
        if (nextToken && token) token.content = nextToken.content;

        const stylesheetLoads = [];
        doc.querySelectorAll('link[rel="stylesheet"]').forEach((link) => {
            if (!link.href || document.querySelector(`link[rel="stylesheet"][href="${link.href}"]`)) return;
            const fresh = link.cloneNode(true);
            stylesheetLoads.push(new Promise((resolve) => {
                fresh.onload = resolve;
                fresh.onerror = resolve;
            }));
            document.head.appendChild(fresh);
        });

        return Promise.all(stylesheetLoads);
    }

    function updateShell(doc, url) {
        const nextBreadcrumb = doc.querySelector('.header-breadcrumb');
        const breadcrumb = document.querySelector('.header-breadcrumb');
        if (nextBreadcrumb && breadcrumb) breadcrumb.innerHTML = nextBreadcrumb.innerHTML;

        document.querySelectorAll('.nav-item').forEach((link) => {
            if (link.classList.contains('logout')) return;
            const linkUrl = sameOriginUrl(link.href);
            link.classList.toggle('active', linkUrl.pathname === url.pathname);
        });
    }

    function withDOMContentLoadedShim(run) {
        const originalAddEventListener = document.addEventListener.bind(document);
        document.addEventListener = function (type, listener, options) {
            if (type === 'DOMContentLoaded' && typeof listener === 'function') {
                window.setTimeout(() => listener.call(document, new Event('DOMContentLoaded')), 0);
                return;
            }
            return originalAddEventListener(type, listener, options);
        };

        return Promise.resolve()
            .then(run)
            .finally(() => {
                document.addEventListener = originalAddEventListener;
            });
    }

    function runInlineScript(script) {
        return withDOMContentLoadedShim(() => {
            new Function(script.textContent)();
        });
    }

    function runExternalScript(script) {
        const src = script.src;
        if (!src || CORE_SCRIPTS.some((name) => src.includes(name))) return Promise.resolve();

        return withDOMContentLoadedShim(() => new Promise((resolve) => {
            const fresh = document.createElement('script');
            fresh.src = src;
            fresh.async = false;
            fresh.onload = resolve;
            fresh.onerror = resolve;
            document.body.appendChild(fresh);
        }));
    }

    async function runPageScripts(doc) {
        const scripts = Array.from(doc.body.querySelectorAll('script'));
        for (const script of scripts) {
            try {
                if (script.src) {
                    await runExternalScript(script);
                } else {
                    await runInlineScript(script);
                }
            } catch (error) {
                console.error(error);
            }
        }
        window.CAPRE?.initApp?.();
    }

    async function swapContent(doc, url) {
        const current = contentEl();
        const next = doc.querySelector(CONTENT_SELECTOR);
        if (!current || !next) throw new Error('Missing page content');

        await updateHead(doc);
        updateShell(doc, url);

        const useMotion = !prefersReducedMotion();
        if (useMotion) {
            current.classList.add('page-content--leaving');
            await wait(TRANSITION_MS);
        }

        current.classList.remove('page-content--leaving');
        if (useMotion) current.classList.add('page-content--entering');
        current.innerHTML = next.innerHTML;
        current.scrollTop = 0;

        if (useMotion) {
            await nextPaint();
            current.classList.remove('page-content--entering');
        }

        await runPageScripts(doc);
    }

    async function navigateTo(href, options = {}) {
        if (isNavigating) return;
        const url = sameOriginUrl(href);
        const current = contentEl();
        if (!current) {
            window.location.href = url.href;
            return;
        }

        isNavigating = true;
        document.body.classList.add('spa-navigating');

        try {
            const response = await fetch(url.href, {
                headers: { 'X-Requested-With': 'fetch' },
                credentials: 'same-origin',
            });
            if (!response.ok) throw new Error(`Navigation failed: ${response.status}`);
            if (response.redirected) {
                window.location.href = response.url;
                return;
            }

            const html = await response.text();
            const doc = new DOMParser().parseFromString(html, 'text/html');
            if (document.querySelector('.nav-container') && !doc.querySelector('.nav-container')) {
                window.location.href = url.href;
                return;
            }
            await swapContent(doc, url);

            if (!options.replace) history.pushState({ url: url.href }, '', url.href);
        } catch (error) {
            console.error(error);
            current.classList.remove('page-content--leaving', 'page-content--entering');
            alert('Page failed to load. Please try again.');
        } finally {
            document.body.classList.remove('spa-navigating');
            isNavigating = false;
        }
    }

    document.addEventListener('click', (event) => {
        const link = event.target.closest('a[href]');
        if (!shouldHandleLink(link, event)) return;

        event.preventDefault();
        navigateTo(link.href);
    });

    window.addEventListener('popstate', () => {
        navigateTo(window.location.href, { replace: true });
    });

    history.replaceState({ url: window.location.href }, '', window.location.href);
    window.CAPRE = window.CAPRE || {};
    window.CAPRE.navigateTo = navigateTo;
})();
