"""Browser regression checks for the Saray website.

Start the Django server first, then run:

    python scripts/browser_smoke.py [--base-url http://127.0.0.1:8000]

The script checks every public page at phone, tablet and desktop widths
(no horizontal overflow, no broken images, no JavaScript errors or failed
requests) and exercises the interactive parts: the mobile drawer, menu search
and filters, the dish dialog, and reservation form validation. It never
creates a reservation unless --submit-reservation is passed.
Screenshots are saved in .test-output/.
"""
import argparse
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parent.parent
# Also support an isolated, local installation used for development checks.
sys.path.insert(0, str(ROOT / '.test-tools'))

from playwright.sync_api import expect, sync_playwright

PAGES = ('/', '/menu/', '/reserve/', '/about/', '/contact/', '/credits/')
WIDTHS = (320, 375, 768, 1024, 1280, 1440)


def launch(playwright, engine, executable):
    browser_type = getattr(playwright, engine)
    options = {'headless': True}
    if executable:
        options['executable_path'] = executable
    return browser_type.launch(**options)


def run(base_url, engine, executable, submit_reservation):
    output = ROOT / '.test-output'
    output.mkdir(exist_ok=True)
    errors = []
    scenarios = 0

    with sync_playwright() as playwright:
        browser = launch(playwright, engine, executable)
        context = browser.new_context(reduced_motion='reduce')
        page = context.new_page()
        page.on('pageerror', lambda error: errors.append(f'{page.url}: {error}'))
        page.on('console', lambda message: errors.append(f'{page.url}: {message.text}')
                if message.type == 'error' else None)
        page.on('requestfailed', lambda request: errors.append(
            f'{request.url}: {request.failure}'))
        page.on('response', lambda response: errors.append(
            f'{response.status}: {response.url}') if response.status >= 400 else None)

        # Layout: every page at every width.
        for width in WIDTHS:
            page.set_viewport_size({'width': width, 'height': 900})
            for path in PAGES:
                response = page.goto(base_url + path, wait_until='networkidle')
                assert response.status == 200, (path, response.status)
                # Scroll through the page so lazy images load.
                page.evaluate("""async () => {
                    for (let y = 0; y < document.body.scrollHeight; y += 700) {
                        window.scrollTo(0, y);
                        await new Promise(r => setTimeout(r, 30));
                    }
                    window.scrollTo(0, 0);
                }""")
                page.wait_for_load_state('networkidle')
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), (
                    f'Horizontal overflow at {width}px: {path}')
                broken = page.locator('img').evaluate_all(
                    '(images) => images.filter(img => img.getAttribute("src")'
                    ' && img.complete && img.naturalWidth === 0)'
                    '.map(img => img.currentSrc || img.src)')
                assert not broken, f'Broken images on {path} at {width}px: {broken}'
                expect(page.locator('h1')).to_have_count(1)
                if width in (375, 1440):
                    name = (path.strip('/') or 'home') + f'-{width}.png'
                    page.screenshot(path=str(output / name), full_page=True)
                scenarios += 1

        # Mobile drawer: open, focus, Escape, link navigation.
        page.set_viewport_size({'width': 375, 'height': 800})
        page.goto(base_url + '/', wait_until='networkidle')
        toggle = page.locator('[data-drawer-open]')
        drawer = page.locator('[data-drawer]')
        toggle.click()
        expect(drawer).to_be_visible()
        expect(toggle).to_have_attribute('aria-expanded', 'true')
        page.keyboard.press('Escape')
        expect(drawer).to_be_hidden()
        expect(toggle).to_have_attribute('aria-expanded', 'false')
        expect(toggle).to_be_focused()
        toggle.click()
        drawer.locator('.drawer__nav a[href="/menu/"]').click()
        page.wait_for_url(base_url + '/menu/')
        page.wait_for_load_state('networkidle')
        scenarios += 1

        # Menu: search (with Arabic letter forms), filters, dialog.
        page.set_viewport_size({'width': 1280, 'height': 900})
        page.goto(base_url + '/menu/', wait_until='networkidle')
        dishes = page.locator('[data-dish]')
        total = dishes.count()
        assert total >= 70, f'Expected the full menu, found {total} dishes'
        search = page.locator('[data-menu-search]')
        search.fill('كباب')  # Arabic kaf must match Persian کباب
        page.wait_for_timeout(300)
        visible = dishes.evaluate_all('(els) => els.filter(e => !e.hidden).length')
        assert 0 < visible < total, f'Search did not filter: {visible}/{total}'
        search.fill('zzzz-no-such-dish')
        page.wait_for_timeout(300)
        expect(page.locator('[data-menu-empty]')).to_be_visible()
        search.fill('')
        page.locator('[data-filter="veg"]').click()
        page.wait_for_timeout(300)
        veg = dishes.evaluate_all('(els) => els.filter(e => !e.hidden).length')
        assert 0 < veg < total, f'Vegetarian filter did not filter: {veg}/{total}'
        page.locator('[data-filter="all"]').click()
        first_card = page.locator('[data-dish]').first
        first_card.locator('.dish__hit').click()
        dialog = page.locator('[data-dish-dialog]')
        expect(dialog).to_be_visible()
        expect(dialog.locator('[data-dd-title]')).to_have_text(
            re.compile(re.escape(first_card.locator('.dish__name').inner_text().strip())))
        page.keyboard.press('Escape')
        expect(dialog).to_be_hidden()
        scenarios += 1

        # Reservation: invalid submission shows Persian errors and keeps the page.
        page.goto(base_url + '/reserve/', wait_until='networkidle')
        form = page.locator('[data-reserve-form]')
        form.locator('input[name="name"]').fill('آزمون مرورگر')
        form.locator('input[name="phone"]').fill('12345')
        form.locator('input[name="date"]').first.check(force=True)
        page.locator('input[name="time"]:not([disabled])').last.check(force=True)
        form.locator('[data-submit]').click()
        page.wait_for_load_state('networkidle')
        assert '/reserve/done/' not in page.url, 'Invalid phone number was accepted'
        expect(page.locator('.field__error, [data-client-error], .errorlist').first).to_be_visible()
        scenarios += 1

        if submit_reservation:
            form.locator('input[name="phone"]').fill('۰۹۱۲۳۴۵۶۷۸۹')
            form.locator('[data-submit]').click()
            page.wait_for_url(re.compile(r'/reserve/done/[A-Z0-9]+/'))
            scenarios += 1

        # Unknown URLs use the branded 404 page.
        response = page.goto(base_url + '/no-such-page/')
        assert response.status == 404
        expect(page.locator('h1')).to_be_visible()
        errors[:] = [e for e in errors if '/no-such-page/' not in e]
        browser.close()

    assert not errors, '\n'.join(errors)
    print(f'PASS: {scenarios} browser scenarios, no failed requests or JavaScript errors.')
    print(f'Screenshots: {output}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--base-url', default='http://127.0.0.1:8000')
    parser.add_argument('--engine', choices=('firefox', 'chromium', 'webkit'), default='firefox')
    parser.add_argument('--browser', help='Optional browser executable path')
    parser.add_argument('--submit-reservation', action='store_true',
                        help='Also create one real reservation (writes to the database)')
    args = parser.parse_args()
    run(args.base_url.rstrip('/'), args.engine, args.browser, args.submit_reservation)
