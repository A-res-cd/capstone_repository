"""Contrast checks for shared controls under conditional page stylesheets."""
from pathlib import Path
from urllib.parse import urlsplit

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('stylesheet', [
    '_auth.css', '_manage-users.css', '_repository.css', '_archive.css',
    '_analytics.css', '_user-information.css', '_all-requests.css', '_audit-logs.css',
])
def test_dark_form_text_and_placeholders(page, stylesheet):
    def assets(route):
        path = urlsplit(route.request.url).path
        if path.startswith('/static/'):
            route.fulfill(path=ROOT / 'app' / path.lstrip('/'))
        else:
            route.abort()
    page.route('**/*', assets)
    page.set_content(f'''<!doctype html><html data-theme="dark"><head>
        <link rel="stylesheet" href="http://theme.test/static/css/base/global.css">
        <link rel="stylesheet" href="http://theme.test/static/css/components/index.css">
        <link rel="stylesheet" href="http://theme.test/static/css/pages/{stylesheet}">
        </head><body><main>
        <div class="mu-page-header"><h2>Manage Users</h2></div>
        <form><div class="form-group"><label for="text">Name</label>
        <input id="text" value="Readable input"><input id="placeholder" placeholder="Enter a name">
        <input id="readonly" readonly value="Read-only value">
        <input id="disabled" disabled value="Disabled value">
        <textarea id="notes">Readable notes</textarea>
        <select id="native"><option>Native option</option><optgroup label="Group"><option>Another</option></optgroup></select>
        <input id="file" type="file"><span class="field-error">Check this field</span>
        </div></form><a href="#">Readable link</a>
        <p class="extract-status--loading">Reading document</p>
        </main></body></html>''')
    # Measure the settled palette, not the initial light-to-dark CSS transition.
    page.add_style_tag(content='*, *::before, *::after, *::file-selector-button { transition: none !important; animation: none !important; }')
    results = page.evaluate('''() => {
        function luminance(color) {
            return color.match(/[\\d.]+/g).slice(0, 3).map(Number).map(v => {
                v /= 255; return v <= 0.04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4;
            }).reduce((sum, v, i) => sum + v * [.2126, .7152, .0722][i], 0);
        }
        function contrast(node, pseudo) {
            const style = getComputedStyle(node, pseudo);
            let background = style.backgroundColor;
            let parent = node;
            while (background === 'rgba(0, 0, 0, 0)' && parent) {
                background = getComputedStyle(parent).backgroundColor;
                parent = parent.parentElement;
            }
            const a = luminance(style.color), b = luminance(background);
            return (Math.max(a, b) + .05) / (Math.min(a, b) + .05);
        }
        const results = {};
        for (const selector of ['label', '#text', '#readonly', '#disabled', '#notes', '#native', 'option', 'optgroup', 'a', '.field-error']) {
            results[selector] = contrast(document.querySelector(selector));
        }
        results.placeholder = contrast(document.querySelector('#placeholder'), '::placeholder');
        results.fileButton = contrast(document.querySelector('#file'), '::file-selector-button');
        return results;
    }''')
    failures = {name: ratio for name, ratio in results.items() if ratio < 4.5}
    assert not failures, failures
