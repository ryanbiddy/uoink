const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const root = process.cwd();
process.env.OUT = __dirname;
process.env.UOINK_PORT = '51381';
const { chromium, newPage, shot } = require('E:/AI/projects/uoink/handoff/ui-rehaul-2026-10-15/_harness/lib.js');
const html = fs.readFileSync(path.join(root, 'assets/dashboard/index.html'), 'utf8');
const fixture = html.slice(0, html.indexOf('    init().catch(')) + `
state.jobs = [{ id: 'review-failure', kind: 'single', state: 'failed', title: 'Capture with an unavailable video format',
  source_url: 'https://www.youtube.com/watch?v=format12345', failure_phase: 'download',
  error_detail: 'ERROR: [youtube] format12345: Requested format is not available. Use a different format.',
  completed_at: new Date().toISOString() }];
renderLibraryCaptures();
document.getElementById('resultSummary').textContent = '1 capture needs attention';
</script></body></html>`;
(async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    for (const theme of ['light', 'dark']) for (const width of [1440, 390]) {
      const { context, page } = await newPage(browser, width, { colorScheme: theme });
      const errors = [];
      page.on('pageerror', (err) => errors.push(err.message));
      await context.route('**/*', async (route) => {
        const url = new URL(route.request().url());
        assert.notEqual(url.port, '5179');
        if (url.hostname !== 'uoink-review.test') return route.abort();
        if (url.pathname === '/dashboard') return route.fulfill({ contentType: 'text/html', body: fixture });
        if (/^\/brand\/fonts\/[a-z0-9.-]+\.woff2?$/.test(url.pathname)) {
          return route.fulfill({ contentType: 'font/woff', body: fs.readFileSync(path.join(root, 'assets', url.pathname.slice(1))) });
        }
        return route.abort();
      });
      await page.goto('http://uoink-review.test/dashboard');
      await page.evaluate(() => document.fonts.ready);
      const detail = page.locator('.capture-row .error-details');
      const summary = detail.locator('summary');
      await summary.waitFor();
      assert.equal(await detail.getAttribute('open'), null);
      let tabReached = false;
      for (let i = 0; i < 60; i++) {
        await page.keyboard.press('Tab');
        if (await summary.evaluate((el) => document.activeElement === el)) { tabReached = true; break; }
      }
      assert(tabReached, 'Tab reaches Details');
      assert.equal(await summary.evaluate((el) => getComputedStyle(el).outlineWidth), '2px');
      await page.keyboard.press('Enter');
      assert.notEqual(await detail.getAttribute('open'), null);
      assert((await detail.locator('pre').innerText()).includes('Requested format is not available'));
      await shot(page, `library-failure-${theme}-${width}`);
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'no viewport overflow');
      await page.keyboard.press('Space');
      assert.equal(await detail.getAttribute('open'), null);
      assert.deepEqual(errors, []);
      console.log(`PASS ${theme} ${width}: Tab, focus ring, Enter/Space, error text, no horizontal overflow`);
      await context.close();
    }
  } finally { await browser.close(); }
})().catch((err) => { console.error(err); process.exitCode = 1; });
