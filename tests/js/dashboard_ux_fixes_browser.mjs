// Offline regression checks for the four 3.9 dashboard UX fixes.
// UOINK_PLAYWRIGHT_PATH may point to an already installed Playwright package.
// Screenshots and measurements go only to a fresh directory under OS temp.
// Every browser request is fulfilled locally or aborted; no helper is started.
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { existsSync, readFileSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { resolve, basename, join } from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
let playwrightPath;
try {
  playwrightPath = require.resolve(process.env.UOINK_PLAYWRIGHT_PATH || "playwright");
} catch (error) {
  if (error.code !== "MODULE_NOT_FOUND") throw error;
  console.log("SKIP dashboard UX: Playwright is not installed; use UOINK_PLAYWRIGHT_PATH for an existing package.");
  process.exit(77);
}
const { chromium } = require(playwrightPath);
if (!existsSync(chromium.executablePath())) {
  console.log("SKIP dashboard UX: Playwright Chromium is not installed.");
  process.exit(77);
}
const root = fileURLToPath(new URL("../../", import.meta.url));
const out = mkdtempSync(join(tmpdir(), "uoink-ux-fixes-"));
const source = readFileSync(resolve(root, "assets/dashboard/index.html"), "utf8");
const html = source.slice(0, source.indexOf("    init().catch(")) + "</script></body></html>";
const browser = await chromium.launch({ headless: true });
const results = [];
const errors = [];
const remote = [];

try {
  for (const theme of ["light", "dark"]) for (const width of [1440, 390]) {
    const context = await browser.newContext({ viewport: { width, height: width === 390 ? 844 : 900 }, colorScheme: theme, reducedMotion: "reduce", offline: true, serviceWorkers: "block" });
    await context.route("**/*", (route) => {
      const url = new URL(route.request().url());
      if (url.hostname !== "uoink.test" || url.port) {
        remote.push(url.href);
        return route.abort();
      }
      if (url.pathname === "/dashboard") return route.fulfill({ contentType: "text/html", body: html });
      if (url.pathname.startsWith("/brand/fonts/") && /\.(woff|woff2)$/.test(url.pathname)) {
        return route.fulfill({ contentType: "font/woff", body: readFileSync(resolve(root, "assets/brand/fonts", basename(url.pathname))) });
      }
      return route.fulfill({ contentType: "application/json", body: JSON.stringify({ ok: true, token: "fixture", jobs: [], pending: [] }) });
    });
    const page = await context.newPage();
    page.on("pageerror", (error) => errors.push(error.message));
    await page.goto("http://uoink.test/dashboard#library");
    await page.evaluate(() => {
      // Keep routing, rendering and controls real, with unrelated I/O disabled.
      loadLibraryActivity = startLibraryActivityTimer = stopLibraryActivityTimer = () => {};
      refreshActivity = refreshSettings = loadWriting = renderSources = () => {};
      hydrateMarks();
      wireEvents();
      wireRoutes();
      applyHashRoute();
      state.captureSaveBaseline = true;
      renderHelperStatus(true);
    });
    await page.evaluate(() => document.fonts.ready);
    const bounds = async (selector) => page.locator(selector).boundingBox();
    const fit = async (view) => {
      const overflow = await page.evaluate(() => {
        const doc = document.documentElement;
        const wide = [...document.querySelectorAll(".tab-panel.active *")].filter((el) => {
          const r = el.getBoundingClientRect();
          return el.getClientRects().length && r.width && r.right > doc.clientWidth + 1;
        }).map((el) => el.id || el.className);
        return { scroll: doc.scrollWidth, client: doc.clientWidth, wide };
      });
      assert.ok(overflow.scroll <= overflow.client + 1, `${view} page overflow: ${JSON.stringify(overflow)}`);
      assert.deepEqual(overflow.wide, [], `${view} has an offscreen control`);
      await page.screenshot({ path: join(out, `${view}-${theme}-${width}.png`), animations: "disabled" });
    };
    const focusVisible = async () => page.evaluate(() => {
      const s = getComputedStyle(document.activeElement);
      return (s.outlineStyle !== "none" && parseFloat(s.outlineWidth) > 0) || s.boxShadow !== "none";
    });
    const library = await bounds("#tab-library");
    await page.evaluate(() => navigateTo("#settings"));
    const settings = await bounds("#tab-settings");
    assert.equal(settings.x, library.x, "Settings shares the Library left edge");
    assert.equal(settings.width, library.width, "Settings shares the Library width");
    assert.equal(await page.locator(".settings-index a").count(), 7, "all section chips remain");
    const copy = await page.locator("#tab-settings .setting-copy").first().evaluate((el) => {
      const s = getComputedStyle(el);
      return { width: el.getBoundingClientRect().width, max: parseFloat(s.maxWidth) };
    });
    assert.ok(copy.width <= copy.max + 1, "Settings prose keeps its readable measure");
    assert.equal(await page.locator("#voiceWarningsEnabled").evaluate((el) => el.closest("label").textContent.trim()), "Show canned-phrase warnings");
    await fit("settings");

    await page.evaluate(() => navigateTo("#sources"));
    const stats = await page.locator(".standing-stat").evaluateAll((items) => items.map((el) => {
      const r = el.getBoundingClientRect();
      return { x: r.x, y: r.y, width: r.width };
    }));
    assert.equal(stats.length, 4);
    if (width === 1440) {
      assert.ok(stats.every((r) => Math.abs(r.y - stats[0].y) < 1), "all four stats share one row");
      assert.ok((await bounds("#standingSummaryBar")).height < 110, "summary is compact");
    } else {
      assert.ok(stats.some((r) => r.y > stats[0].y), "stats wrap on mobile");
    }
    const link = page.getByRole("link", { name: "Discover", exact: true });
    const discoverLink = await link.boundingBox();
    assert.ok(discoverLink.y >= 0 && discoverLink.y + discoverLink.height <= page.viewportSize().height, "Discover is reachable from the first screen");
    await fit("sources");
    await link.focus();
    await page.keyboard.press("Tab");
    await page.keyboard.press("Shift+Tab");
    assert.equal(await page.evaluate(() => document.activeElement.getAttribute("href")), "#sources/discover");
    assert.ok(await focusVisible(), "Discover link has keyboard focus styling");
    await page.keyboard.press("Enter");
    await page.waitForFunction(() => document.activeElement.id === "discoveryTitle");
    assert.equal(new URL(page.url()).hash, "#sources/discover");
    const discover = await bounds("#discoveryTitle");
    assert.ok(discover.y >= 0 && discover.y < page.viewportSize().height, "Discover heading scrolls into view");
    await page.keyboard.press("Tab");
    assert.equal(await page.evaluate(() => document.activeElement.getAttribute("href")), "#settings/connected-services", "Tab continues within Discover");
    await page.goBack();
    assert.equal(new URL(page.url()).hash, "#sources", "Discover adds exactly one history entry");
    await page.goForward();
    await page.waitForFunction(() => document.activeElement.id === "discoveryTitle");
    await page.evaluate(() => navigateTo("#library"));
    await page.evaluate(() => navigateTo("#sources/discover"));
    await page.waitForFunction(() => document.activeElement.id === "discoveryTitle");
    assert.ok(await page.locator("#tab-sources").isVisible(), "Discover deep link opens Sources from another page");

    await page.evaluate(() => {
      navigateTo("#activity");
      const now = new Date().toISOString();
      state.jobs = [{ id: "gave-up", state: "failed", title: "Capture that gave up", source_url: "https://youtu.be/stopped0001", retry_exhausted: true, attempt_count: 3, completed_at: now }];
      state.queue = { pending: [
        { pending_id: 7, status: "pending", title: "Capture waiting to retry", url: "https://youtu.be/retry000001", last_error: "HTTP Error 429", attempt_count: 1, queued_at: now, retry_after: new Date(Date.now() + 120000).toISOString() },
        { pending_id: 8, status: "pending", title: "First queued capture", url: "https://youtu.be/first000001", attempt_count: 0, queued_at: now, retry_after: new Date(Date.now() + 120000).toISOString() },
        { pending_id: 9, status: "running", title: "First running capture", url: "https://youtu.be/first000002", attempt_count: 0, phase: "download", queued_at: now },
      ] };
      renderQueue(state.queue);
    });
    const progress = await page.locator("#queueRows").textContent();
    assert.match(progress, /Waiting to retry/);
    assert.match(progress, /Retries on its own at /);
    assert.doesNotMatch(progress, /Failed|not reported/);
    assert.equal(await page.locator("#queueRows .step.fail").count(), 0);
    for (const [id, label] of [[8, "Waiting · one YouTube capture at a time"], [9, "Capturing · video (3 of 5)"]]) {
      const row = page.locator(`[data-activity-key="pending:${id}"]`);
      assert.ok((await row.textContent()).includes(label));
      assert.doesNotMatch(await row.textContent(), /Waiting to retry|Retries on its own|Retrying now/);
      assert.equal(await row.locator(".activity-retry-copy").count(), 0);
    }
    const exhausted = await page.locator("#attentionRows").textContent();
    assert.match(exhausted, /Failed/);
    assert.match(exhausted, /gave up after 3 attempts/);
    assert.doesNotMatch(exhausted, /Waiting to retry|Retries on its own|Retrying now/);
    await fit("activity");
    await page.locator("#queueRows button[data-activity-detail]").click();
    assert.ok(await page.locator("#captureFailureDrawer").isVisible());
    assert.equal(await page.locator("#captureFailureLabel").textContent(), "Failed", "drawer keeps last failure, omitting unknown step");
    assert.doesNotMatch(await page.locator("#captureFailureMeta").textContent(), /not reported| ·  · /);
    await page.keyboard.press("Escape");
    assert.equal(await page.evaluate(() => document.activeElement.dataset.activityDetail), "pending:7", "drawer restores focus");

    await page.evaluate(() => navigateTo("#generate"));
    assert.equal(await page.locator("#voiceWarningPanel strong").textContent(), "Canned-phrase check");
    await page.evaluate(() => renderWritingResult({ body: "A test draft with enough content to render.", voice_warnings: [{ phrase: "canned test phrase" }], warning_copy: "Check this phrase." }));
    assert.equal(await page.locator("#voiceWarningCopy").textContent(), "Check this phrase. canned test phrase", "warning behavior is preserved");
    await fit("generate");
    await page.locator("#generateAdvanced summary").click();
    await page.locator("#writingShowWarnings").uncheck();
    assert.equal(await page.locator("#voiceWarningCopy").textContent(), "Warnings are hidden for this session.");
    await page.locator("#writingSettingsLink").click();
    assert.ok(await page.locator("#tab-settings").isVisible(), "warning Settings button still works");
    results.push({ theme, width, library, settings, stats, discoverLink });
    await context.close();
  }
  assert.deepEqual(errors, [], "no browser errors");
  assert.deepEqual(remote, [], "no remote requests attempted");
  writeFileSync(join(out, "measurements.json"), JSON.stringify(results, null, 2));
  console.log(`PASS dashboard UX: ${results.length} viewport/theme combinations; evidence ${out}`);
} finally {
  await browser.close();
}
