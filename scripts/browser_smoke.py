"""Browser regression checks. Start Django before running this script."""
import argparse
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parent.parent
# Also support an isolated, local installation used for development checks.
sys.path.insert(0, str(ROOT / '.test-tools'))

from playwright.sync_api import expect, sync_playwright


def run(base_url, executable):
    output = ROOT / '.test-output'
    output.mkdir(exist_ok=True)
    errors = []
    scenarios = 0

    with sync_playwright() as playwright:
        options = {'headless': True}
        if executable:
            options['executable_path'] = executable
        browser = playwright.chromium.launch(**options)
        context = browser.new_context(reduced_motion='reduce')
        page = context.new_page()
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.on('console', lambda message: errors.append(message.text)
                if message.type == 'error' else None)
        page.on('requestfailed', lambda request: errors.append(
            f'{request.url}: {request.failure}'))
        page.on('response', lambda response: errors.append(
            f'{response.status}: {response.url}') if response.status >= 400 else None)

        for width in (320, 375, 390, 768, 1024, 1199, 1200, 1440):
            page.set_viewport_size({'width': width, 'height': 900})
            for path in ('/', '/saray-menu/', '/saray-menu/menu/'):
                response = page.goto(base_url + path, wait_until='networkidle')
                assert response.status == 200, (path, response.status)
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), (
                    f'Horizontal overflow at {width}px: {path}')
                assert page.locator('img').evaluate_all(
                    '(images) => images.every(img => img.complete && img.naturalWidth > 0)'
                ), f'Broken image: {path}'
                header = page.locator('.site-navbar').bounding_box()
                if 'menu/menu' in path:
                    cards = page.locator('.menu-card')
                    expect(cards).to_have_count(3)
                    assert cards.first.bounding_box()['y'] >= header['height']
                    if width >= 1200:
                        tops = [round(card.bounding_box()['y']) for card in cards.all()]
                        assert len(set(tops)) == 1, f'Misaligned cards: {tops}'
                if width < 1200:
                    expect(page.locator('.site-menu-toggle')).to_be_visible()
                    expect(page.locator('.site-navigation')).to_be_hidden()
                else:
                    expect(page.locator('.site-menu-toggle')).to_be_hidden()
                    expect(page.locator('.site-navigation')).to_be_visible()
                if width in (375, 1440) and path != '/saray-menu/':
                    name = 'menu' if 'menu/menu' in path else 'home'
                    page.screenshot(path=str(output / f'{name}-{width}.png'), full_page=True)
                scenarios += 1

        # Slideshow arrows and indicators must work on every carousel.
        for path in ('/', '/saray-menu/menu/'):
            page.goto(base_url + path, wait_until='networkidle')
            if path == '/':
                page.locator('.carousel').evaluate("el => window.jQuery(el).carousel('pause')")
            for carousel in page.locator('.carousel').all():
                slides = carousel.locator('.carousel-item')
                carousel.locator('.carousel-control-next').click()
                expect(slides.nth(1)).to_have_class(re.compile(r'\bactive\b'))
                carousel.locator('.carousel-control-prev').click()
                expect(slides.nth(0)).to_have_class(re.compile(r'\bactive\b'))
                carousel.locator('[data-slide-to="2"]').click()
                expect(slides.nth(2)).to_have_class(re.compile(r'\bactive\b'))
                scenarios += 1

        # Check touch-sized navigation, keyboard behavior, and breakpoint changes.
        for width in (375, 1024):
            page.set_viewport_size({'width': width, 'height': 900})
            page.goto(base_url + '/', wait_until='networkidle')
            toggle = page.locator('.site-menu-toggle')
            drawer = page.locator('#mobile-menu')
            toggle.click()
            expect(drawer).to_have_attribute('aria-hidden', 'false')
            expect(toggle).to_have_attribute('aria-expanded', 'true')
            expect(drawer.locator('button')).to_be_focused()
            page.keyboard.press('Shift+Tab')
            expect(drawer.locator('a').last).to_be_focused()
            page.keyboard.press('Tab')
            expect(drawer.locator('button')).to_be_focused()
            page.keyboard.press('Escape')
            expect(drawer).to_have_attribute('aria-hidden', 'true')
            expect(toggle).to_be_focused()
            toggle.click()
            drawer.locator('a[href="#contact"]').click()
            expect(drawer).to_have_attribute('aria-hidden', 'true')
            assert page.url.endswith('#contact')
            page.goto(base_url + '/', wait_until='networkidle')
            toggle.click()
            page.mouse.click(10, 200)
            expect(drawer).to_have_attribute('aria-hidden', 'true')
            toggle.click()
            drawer.locator('a[href="/saray-menu/menu/"]').click()
            page.wait_for_url(base_url + '/saray-menu/menu/')
            expect(page.locator('.menu-card')).to_have_count(3)
            page.locator('.site-menu-toggle').click()
            page.set_viewport_size({'width': 1440, 'height': 900})
            expect(drawer).to_have_attribute('aria-hidden', 'true')
            scenarios += 1

        page.goto(base_url + '/', wait_until='networkidle')
        page.locator('.site-navigation a[href="/saray-menu/menu/"]').click()
        page.wait_for_url(base_url + '/saray-menu/menu/')
        page.locator('.site-logo').click()
        page.wait_for_url(base_url + '/')
        browser.close()

    assert not errors, '\n'.join(errors)
    print(f'PASS: {scenarios} browser scenarios, desktop navigation, '
          'no failed requests or JavaScript errors.')
    print(f'Screenshots: {output}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', default='http://127.0.0.1:8011')
    parser.add_argument('--browser', help='Optional Chromium/Chrome/Brave executable path')
    args = parser.parse_args()
    run(args.base_url.rstrip('/'), args.browser)
