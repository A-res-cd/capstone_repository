(function () {
    const CONTENT_SELECTOR = '#page-content';
    const CORE_SCRIPTS = ['theme.js', 'index.js', 'navigation.js'];
    const MOTION = {
        refresh: 360,
        leave: 220,
        enter: 300,
    };

    let activeRequest = null;
    let activeUrl = null;
    let transitionRunning = false;
    let pendingNavigation = null;

    function contentEl() {
        return document.querySelector(CONTENT_SELECTOR);
    }

    function prefersReducedMotion() {
        return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    }

    async function animateContent(element, keyframes, duration, easing) {
        if (!element || prefersReducedMotion()) return;

        const animation = element.animate(keyframes, {
            duration,
            easing,
            fill: 'both',
        });

        try {
            await animation.finished;
        } catch (error) {
            if (error.name !== 'AbortError') throw error;
        } finally {
            animation.cancel();
        }
    }

    function animateRefresh() {
        return animateContent(
            contentEl(),
            [
                { opacity: 0, transform: 'translateY(12px)' },
                { opacity: 1, transform: 'translateY(0)' },
            ],
            MOTION.refresh,
            'ease-out'
        );
    }

    function animateLeave(element) {
        return animateContent(
            element,
            [
                { opacity: 1, transform: 'translateY(0)' },
                { opacity: 0, transform: 'translateY(-8px)' },
            ],
            MOTION.leave,
            'ease-out'
        );
    }

    function animateEnter(element) {
        return animateContent(
            element,
            [
                { opacity: 0, transform: 'translateY(12px)' },
                { opacity: 1, transform: 'translateY(0)' },
            ],
            MOTION.enter,
            'ease-in'
        );
    }

    function toUrl(href) {
        return new URL(href, window.location.href);
    }

    function shouldHandleLink(link, event) {
        if (!link || event.defaultPrevented) return false;
        if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return false;
        if (link.target && link.target !== '_self') return false;
        if (link.hasAttribute('download') || link.hasAttribute('data-no-spa')) return false;

        const url = toUrl(link.href);
        if (url.origin !== window.location.origin) return false;
        if (url.pathname === '/logout') return false;
        if (url.pathname === window.location.pathname && url.search === window.location.search) return false;
        if (/\.(pdf|doc|docx|png|jpe?g|gif|zip)$/i.test(url.pathname)) return false;

        return true;
    }

    function hasMatchingShell(doc) {
        return Boolean(document.querySelector('.nav-container')) === Boolean(doc.querySelector('.nav-container'))
            && Boolean(document.querySelector('.header')) === Boolean(doc.querySelector('.header'));
    }

    function updateHead(doc) {
        const nextTitle = doc.querySelector('title');
        if (nextTitle) document.title = nextTitle.textContent;

        const nextToken = doc.querySelector('meta[name="csrf-token"]');
        const token = document.querySelector('meta[name="csrf-token"]');
        if (nextToken && token) token.content = nextToken.content;
    }

    async function prepareStylesheets(doc, url) {
        const nextLinks = Array.from(doc.querySelectorAll('link[rel~="stylesheet"]'));
        const desired = new Map(nextLinks.map((link) => [
            new URL(link.getAttribute('href'), url.href).href,
            link,
        ]));
        const currentLinks = Array.from(document.querySelectorAll('link[rel~="stylesheet"]'));
        const current = new Map(currentLinks.map((link) => [link.href, link]));
        const loads = [];

        desired.forEach((source, href) => {
            if (current.has(href)) return;

            const link = source.cloneNode(true);
            link.href = href;
            loads.push(new Promise((resolve) => {
                const timer = window.setTimeout(resolve, 3000);
                const finish = () => {
                    window.clearTimeout(timer);
                    resolve();
                };
                link.addEventListener('load', finish, { once: true });
                link.addEventListener('error', finish, { once: true });
            }));
            document.head.appendChild(link);
        });

        await Promise.all(loads);

        return () => {
            current.forEach((link, href) => {
                if (!desired.has(href)) link.remove();
            });
        };
    }

    function updateShell(doc, url) {
        const nextBreadcrumb = doc.querySelector('.header-breadcrumb');
        const breadcrumb = document.querySelector('.header-breadcrumb');
        if (nextBreadcrumb && breadcrumb) breadcrumb.innerHTML = nextBreadcrumb.innerHTML;

        document.querySelectorAll('.nav-item').forEach((link) => {
            if (link.classList.contains('logout')) return;
            link.classList.toggle('active', toUrl(link.href).pathname === url.pathname);
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
        if (!script.src || CORE_SCRIPTS.some((name) => script.src.includes(name))) {
            return Promise.resolve();
        }

        return withDOMContentLoadedShim(() => new Promise((resolve) => {
            const fresh = document.createElement('script');
            fresh.src = script.src;
            fresh.async = false;
            fresh.addEventListener('load', resolve, { once: true });
            fresh.addEventListener('error', resolve, { once: true });
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

    function focusContent(element) {
        element.setAttribute('tabindex', '-1');
        element.focus({ preventScroll: true });
    }

    async function swapPage(doc, url) {
        const current = contentEl();
        const next = doc.querySelector(CONTENT_SELECTOR);
        if (!current || !next) throw new Error('Missing page content');

        const removeOldStylesheets = await prepareStylesheets(doc, url);
        await animateLeave(current);

        removeOldStylesheets();
        updateHead(doc);
        updateShell(doc, url);
        current.innerHTML = next.innerHTML;
        current.scrollTop = 0;

        await animateEnter(current);
        await runPageScripts(doc);
        focusContent(current);
    }

    async function navigateTo(href, options = {}) {
        const url = toUrl(href);
        const current = contentEl();
        if (!current) {
            window.location.assign(url.href);
            return;
        }

        if (activeUrl === url.href) return;

        if (transitionRunning) {
            pendingNavigation = { href: url.href, options };
            return;
        }

        activeRequest?.abort();
        const controller = new AbortController();
        activeRequest = controller;
        activeUrl = url.href;
        current.setAttribute('aria-busy', 'true');

        let startedTransition = false;
        try {
            const response = await fetch(url.href, {
                credentials: 'same-origin',
                headers: { 'X-Requested-With': 'fetch' },
                signal: controller.signal,
            });

            if (!response.ok) throw new Error(`Navigation failed: ${response.status}`);
            if (response.redirected) {
                window.location.assign(response.url);
                return;
            }

            const html = await response.text();
            const doc = new DOMParser().parseFromString(html, 'text/html');
            if (!hasMatchingShell(doc)) {
                window.location.assign(url.href);
                return;
            }

            activeRequest = null;
            transitionRunning = true;
            startedTransition = true;
            await swapPage(doc, url);

            if (!options.replace) history.pushState({ url: url.href }, '', url.href);
        } catch (error) {
            if (error.name !== 'AbortError') {
                console.error(error);
                alert('Page failed to load. Please try again.');
            }
        } finally {
            if (activeRequest === controller) activeRequest = null;
            if (startedTransition) transitionRunning = false;

            if (!activeRequest && !transitionRunning) {
                current.removeAttribute('aria-busy');
                activeUrl = null;
                const pending = pendingNavigation;
                pendingNavigation = null;
                if (pending) navigateTo(pending.href, pending.options);
            }
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

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', animateRefresh, { once: true });
    } else {
        animateRefresh();
    }

    history.replaceState({ url: window.location.href }, '', window.location.href);
    window.CAPRE = window.CAPRE || {};
    window.CAPRE.navigateTo = navigateTo;
})();
