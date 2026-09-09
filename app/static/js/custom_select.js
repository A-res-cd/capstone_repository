/* Shared single-select styling; data-custom-select="search" forces filtering.
   The native select owns submission/validation. After programmatic updates,
   call CAPRE.syncSelect(select) or dispatch change. Multiple/listbox selects,
   data-native-select opt-outs, and older browsers stay native. */
(function () {
    if (window.CAPRE_CUSTOM_SELECTS || !HTMLElement.prototype.showPopover) return;
    window.CAPRE_CUSTOM_SELECTS = true;

    const controls = new Map();
    let active = null;
    let sequence = 0;
    const selector = 'select:not([multiple]):not([data-native-select])';
    const normalize = (text) => text.trim().toLocaleLowerCase();
    const disabled = (option) => option.disabled || option.parentElement.disabled;

    function element(tag, className, text) {
        const node = document.createElement(tag);
        node.className = className;
        if (text !== undefined) node.textContent = text;
        return node;
    }

    function enhance(select) {
        if (controls.has(select) || select.size > 1) return;
        const id = `capre-select-${++sequence}`;
        const root = element('div', 'custom-select');
        const input = element('input', 'custom-select__input');
        const list = element('div', 'custom-select__list');
        const hint = element('span', 'custom-select__sr');
        const status = element('span', 'custom-select__sr');
        const error = element('span', 'custom-select__error');
        const nativeEvents = new AbortController();
        const originalTabindex = select.getAttribute('tabindex');
        const originalAriaHidden = select.getAttribute('aria-hidden');
        let items = [];
        let highlighted = null;
        let typeahead = '';
        let typedAt = 0;
        let searchable = false;

        input.type = 'text';
        input.id = `${id}-input`;
        input.autocomplete = 'off';
        input.spellcheck = false;
        input.setAttribute('role', 'combobox');
        input.setAttribute('aria-haspopup', 'listbox');
        input.setAttribute('aria-expanded', 'false');
        input.setAttribute('aria-controls', id);
        const originalLabels = Array.from(select.labels || [], (label) => [label, label.getAttribute('for')]);
        const labels = originalLabels.map(([label], index) => {
            if (!label.id) label.id = `${id}-label-${index}`;
            label.htmlFor = input.id;
            return label.id;
        });
        // Compact filter bars use a span caption instead of a label element.
        const caption = select.closest('.filter-group')?.querySelector(':scope > span');
        if (!labels.length && caption) {
            if (!caption.id) caption.id = `${id}-caption`;
            labels.push(caption.id);
        }
        const labelledBy = select.getAttribute('aria-labelledby') || labels.join(' ');
        for (const node of [input, list]) {
            if (labelledBy) node.setAttribute('aria-labelledby', labelledBy);
            else node.setAttribute('aria-label', select.getAttribute('aria-label') || select.name || 'Choose an option');
        }
        hint.id = `${id}-hint`;
        error.id = `${id}-error`;
        error.hidden = true;
        error.setAttribute('role', 'alert');
        status.setAttribute('role', 'status');
        input.setAttribute('aria-describedby', [select.getAttribute('aria-describedby'), hint.id, error.id].filter(Boolean).join(' '));
        list.id = id;
        list.setAttribute('role', 'listbox');
        list.setAttribute('popover', 'manual');

        select.before(root);
        root.append(select, input, list, hint, status, error);
        select.classList.add('custom-select__native');
        select.tabIndex = -1;
        select.setAttribute('aria-hidden', 'true');

        function setHighlight(item) {
            highlighted?.node.removeAttribute('data-active');
            highlighted = item || null;
            if (highlighted) {
                highlighted.node.setAttribute('data-active', '');
                input.setAttribute('aria-activedescendant', highlighted.node.id);
                highlighted.node.scrollIntoView({ block: 'nearest' });
            } else input.removeAttribute('aria-activedescendant');
        }

        function render(query = '') {
            const fragment = document.createDocumentFragment();
            const groups = new Map();
            items = [];
            for (const option of select.options) {
                if (option.hidden || option.parentElement.hidden || !normalize(option.label).includes(normalize(query))) continue;
                let parent = fragment;
                if (option.parentElement.tagName === 'OPTGROUP') {
                    const group = option.parentElement;
                    if (!groups.has(group)) {
                        const section = element('div', 'custom-select__group');
                        section.setAttribute('role', 'group');
                        section.setAttribute('aria-label', group.label);
                        section.append(element('div', 'custom-select__group-label', group.label));
                        groups.set(group, section);
                        fragment.append(section);
                    }
                    parent = groups.get(group);
                }
                const node = element('div', 'custom-select__option', option.label);
                node.id = `${id}-option-${option.index}`;
                node.setAttribute('role', 'option');
                node.setAttribute('aria-selected', String(option.selected));
                node.setAttribute('aria-disabled', String(Boolean(disabled(option))));
                node.dataset.index = option.index;
                parent.append(node);
                if (!disabled(option)) items.push({ node, option });
            }
            if (!items.length) fragment.append(element('div', 'custom-select__empty', 'No matching options.'));
            list.replaceChildren(fragment);
            status.textContent = `${items.length} ${items.length === 1 ? 'option' : 'options'} available.`;
            setHighlight(items.find((item) => item.option.selected) || items[0]);
        }

        function position() {
            if (active !== control) return;
            const rect = input.getBoundingClientRect();
            const viewport = window.visualViewport;
            const top = viewport?.offsetTop || 0;
            const left = viewport?.offsetLeft || 0;
            const height = viewport?.height || window.innerHeight;
            const width = viewport?.width || window.innerWidth;
            if (!select.isConnected || rect.bottom <= top || rect.top >= top + height) return close();
            const below = top + height - rect.bottom - 12;
            const above = rect.top - top - 12;
            const upwards = below < 220 && above > below;
            list.style.width = `${Math.min(Math.max(rect.width, 200), width - 16)}px`;
            list.style.maxHeight = `${Math.max(40, Math.min(288, upwards ? above : below))}px`;
            list.style.left = `${Math.max(left + 8, Math.min(rect.left, left + width - list.offsetWidth - 8))}px`;
            list.style.top = `${upwards ? rect.top - list.offsetHeight - 6 : rect.bottom + 6}px`;
        }

        function sync() {
            root.hidden = select.hidden;
            const compact = select.classList.contains('filter-select');
            root.classList.toggle('custom-select--compact', compact);
            if (compact) {
                const length = Array.from(select.options).reduce((max, option) => Math.max(max, option.label.length), 6);
                root.style.setProperty('--custom-select-width', `calc(${Math.min(length, 22)}ch + 44px)`);
            }
            input.disabled = select.matches(':disabled');
            searchable = select.dataset.customSelect === 'search' || select.options.length > 8;
            input.readOnly = !searchable;
            input.setAttribute('aria-autocomplete', searchable ? 'list' : 'none');
            input.setAttribute('aria-required', String(select.required));
            hint.textContent = `${searchable ? 'Type to search. ' : ''}Use arrow keys to browse, Enter to select, Escape to close.`;
            if (select.validity.valid) {
                error.hidden = true;
                error.textContent = '';
            }
            input.setAttribute('aria-invalid', select.getAttribute('aria-invalid') || String(!error.hidden));
            if (input.disabled || root.hidden) close();
            if (active === control) {
                render(searchable ? input.value : '');
                position();
            } else {
                input.value = select.selectedOptions[0]?.label || '';
                input.placeholder = select.dataset.placeholder || 'Choose an option';
            }
        }

        function open(clear = true) {
            if (active === control || select.matches(':disabled')) return;
            const query = input.value;
            active?.close();
            sync();
            active = control;
            input.setAttribute('aria-expanded', 'true');
            if (searchable) input.value = clear ? '' : query;
            input.placeholder = searchable ? 'Type to search options…' : 'Choose an option';
            list.showPopover();
            render(searchable ? input.value : '');
            position();
        }

        function close() {
            if (list.matches(':popover-open')) list.hidePopover();
            if (active === control) active = null;
            input.setAttribute('aria-expanded', 'false');
            input.removeAttribute('aria-activedescendant');
            input.value = select.selectedOptions[0]?.label || '';
            input.placeholder = select.dataset.placeholder || 'Choose an option';
        }

        function choose(option) {
            if (!option || disabled(option) || select.matches(':disabled')) return;
            const changed = select.selectedIndex !== option.index;
            select.selectedIndex = option.index;
            close();
            sync();
            input.focus({ preventScroll: true });
            if (changed) {
                select.dispatchEvent(new Event('input', { bubbles: true }));
                select.dispatchEvent(new Event('change', { bubbles: true }));
            }
        }

        function destroy() {
            close();
            nativeEvents.abort();
            select.classList.remove('custom-select__native');
            for (const [name, value] of [['tabindex', originalTabindex], ['aria-hidden', originalAriaHidden]]) {
                if (value === null) select.removeAttribute(name);
                else select.setAttribute(name, value);
            }
            for (const [label, value] of originalLabels) {
                if (value === null) label.removeAttribute('for');
                else label.setAttribute('for', value);
            }
            root.replaceWith(select);
        }

        const control = { root, input, list, sync, close, position, destroy, reset() {
            close();
            error.hidden = true;
            sync();
        } };
        controls.set(select, control);
        input.addEventListener('click', () => active === control && !searchable ? close() : open());
        input.addEventListener('focus', sync);
        input.addEventListener('input', () => {
            if (active !== control) open(false);
            else { render(input.value); position(); }
        });
        input.addEventListener('keydown', (event) => {
            if (event.isComposing) return;
            const expanded = active === control;
            if (event.key === 'Escape' && expanded) {
                event.preventDefault();
                event.stopPropagation();
                close();
            } else if (event.key === 'Tab') close();
            else if (['ArrowDown', 'ArrowUp', 'Enter'].includes(event.key) || (!searchable && event.key === ' ')) {
                event.preventDefault();
                if (!expanded) open();
                else if (event.key === 'Enter' || event.key === ' ') choose(highlighted?.option);
                else {
                    const index = items.indexOf(highlighted) + (event.key === 'ArrowDown' ? 1 : -1);
                    setHighlight(items[(index + items.length) % items.length]);
                }
            } else if (expanded && ['Home', 'End'].includes(event.key)) {
                event.preventDefault();
                setHighlight(event.key === 'Home' ? items[0] : items[items.length - 1]);
            } else if (!searchable && event.key.length === 1 && !event.ctrlKey && !event.metaKey && !event.altKey) {
                event.preventDefault();
                typeahead = Date.now() - typedAt < 700 ? typeahead + event.key : event.key;
                typedAt = Date.now();
                open();
                setHighlight(items.find((item) => normalize(item.option.label).startsWith(normalize(typeahead))));
            }
        });
        list.addEventListener('mousedown', (event) => event.preventDefault());
        list.addEventListener('click', (event) => {
            const node = event.target.closest('[role="option"]');
            if (node) choose(select.options[Number(node.dataset.index)]);
        });
        select.addEventListener('focus', () => input.focus(), { signal: nativeEvents.signal });
        select.addEventListener('change', sync, { signal: nativeEvents.signal });
        select.addEventListener('input', sync, { signal: nativeEvents.signal });
        select.addEventListener('invalid', (event) => {
            event.preventDefault();
            error.textContent = select.validationMessage;
            error.hidden = false;
            input.setAttribute('aria-invalid', 'true');
            // Native validation still blocks submission; focus its visible proxy.
            if (!document.querySelector('.custom-select__input[aria-invalid="true"]:focus')) input.focus();
        }, { signal: nativeEvents.signal });
        sync();
    }

    function scan(node) {
        if (!(node instanceof Element)) return;
        if (node.matches(selector)) enhance(node);
        node.querySelectorAll(selector).forEach(enhance);
    }

    document.addEventListener('pointerdown', (event) => {
        if (active && !active.root.contains(event.target)) active.close();
    });
    document.addEventListener('focusin', (event) => {
        if (active && !active.root.contains(event.target)) active.close();
    });
    document.addEventListener('reset', (event) => {
        window.setTimeout(() => {
            for (const select of event.target.elements) controls.get(select)?.reset();
        }, 0);
    });
    document.addEventListener('close', (event) => {
        if (active && event.target.contains(active.root)) active.close();
    }, true);
    document.addEventListener('scroll', (event) => {
        if (active && !active.list.contains(event.target)) active.position();
    }, true);
    window.addEventListener('resize', () => active?.position());
    window.visualViewport?.addEventListener('resize', () => active?.position());

    // Covers fetched pages, lazy modals, and option/disabled-state updates.
    new MutationObserver((records) => {
        const changed = new Set();
        for (const record of records) {
            record.addedNodes.forEach(scan);
            const select = record.target.closest?.('select');
            if (controls.has(select)) changed.add(select);
            if (record.target.matches?.('fieldset')) {
                record.target.querySelectorAll(selector).forEach((node) => changed.add(node));
            }
        }
        for (const [select, control] of controls) {
            if (!select.isConnected) { control.destroy(); controls.delete(select); }
        }
        changed.forEach((select) => controls.get(select)?.sync());
    }).observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ['disabled', 'selected', 'label', 'required', 'hidden'] });
    window.CAPRE = window.CAPRE || {};
    // Silent refresh avoids triggering auto-submit filters during prefilling.
    window.CAPRE.syncSelect = (select) => controls.get(select)?.sync();
    scan(document.body);
})();
