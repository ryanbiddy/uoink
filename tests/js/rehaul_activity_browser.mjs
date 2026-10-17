// Optional visual/keyboard check using an already installed Playwright.
// All requests are fulfilled from fixtures or aborted; no helper is started.
// UOINK_PLAYWRIGHT_PATH points to the existing harness's playwright package.
// UOINK_CAPTURE_HARNESS can point to the handoff's _harness directory to
// reuse its newPage/shot helpers; all AFTER images stay under _scratch/.
import { createRequire } from "node:module";
import { readFileSync, mkdirSync } from "node:fs";
import { resolve, basename } from "node:path";
import assert from "node:assert/strict";
const require = createRequire(import.meta.url);
const root = resolve(new URL("../../", import.meta.url).pathname.replace(/^\/(\w:)/, "$1"));
const out = resolve(root, "_scratch/activity-steps-repairs/visual");
mkdirSync(out, { recursive: true });
process.env.OUT = out;
const capture = process.env.UOINK_CAPTURE_HARNESS ? require(resolve(process.env.UOINK_CAPTURE_HARNESS, "lib.js")) : null;
const { chromium } = capture || require(process.env.UOINK_PLAYWRIGHT_PATH || "playwright");
const shot = (page, name, options = {}) => capture ? capture.shot(page, name, options)
  : page.screenshot({ path: resolve(out, `${name}.png`), ...options });
const source = readFileSync(resolve(root, "assets/dashboard/index.html"), "utf8");
const html = source.slice(0, source.indexOf("    init().catch(")) + "</script></body></html>";
const browser = await chromium.launch({ headless: true });
const errors = [];
try {
  for (const theme of ["light", "dark"]) for (const width of [1440, 390]) {
    const { context, page } = capture ? await capture.newPage(browser, width, { colorScheme: theme })
      : await (async () => {
        const context = await browser.newContext({ viewport: { width, height: width === 390 ? 844 : 900 }, colorScheme: theme });
        return { context, page: await context.newPage() };
      })();
    page.on("pageerror", (error) => errors.push(error.message));
    await context.route("**/*", async (route) => {
      const url = new URL(route.request().url());
      assert.notEqual(url.port, "5179", "never contact production helper");
      if (url.hostname !== "uoink.test") return route.abort();
      if (url.pathname === "/dashboard") return route.fulfill({ contentType: "text/html", body: html });
      if (url.pathname.startsWith("/brand/fonts/") && /\.(woff|woff2)$/.test(url.pathname)) {
        return route.fulfill({ contentType: "font/woff", body: readFileSync(resolve(root, "assets/brand/fonts", basename(url.pathname))) });
      }
      return route.fulfill({ contentType: "application/json", body: JSON.stringify({ ok: true, token: "fixture", jobs: [], pending: [] }) });
    });
    await page.goto("http://uoink.test/dashboard#activity");
    await page.evaluate(() => {
      hydrateMarks();
      wireEvents();
      wireRoutes();
      // Show the real panel without running unrelated tab loaders.
      document.querySelectorAll("[data-tab-panel]").forEach((el) => el.classList.toggle("active", el.dataset.tabPanel === "activity"));
      document.querySelectorAll("[data-tab-button]").forEach((el) => el.classList.toggle("active", el.dataset.tabButton === "activity"));
      state.activeTab = "activity";
      state.captureSaveBaseline = true;
      const now = new Date().toISOString();
      state.jobs = [
        { id: "failed", state: "failed", kind: "single", title: "Inside the 2026 creator economy report", source_url: "https://www.youtube.com/watch?v=abcdefghijk", failure_phase: "transcript", current_video_phase: "done", error_detail: "WARNING: retrying captions\nERROR: [youtube] abcdefghijk: HTTP Error 429: Too Many Requests", completed_at: now, transcript_source: "captions" },
        { id: "active", state: "running", kind: "single", title: "How to make a better opening", source_url: "https://youtu.be/ZYXWVUTSRQP", phase: "download", started_at: now },
        { id: "queued", state: "queued", kind: "single", title: "Designing a place to read", source_url: "https://youtu.be/11111111111", started_at: now },
        { id: "today", state: "completed", kind: "single", title: "The hook formula behind 40 dev-tool launches", source_url: "https://youtu.be/22222222222", completed_at: now, result: { transcript_source: "asr" } },
        { id: "earlier", state: "completed", kind: "single", title: "A conversation about small software", source_url: "https://youtu.be/33333333333", completed_at: new Date(Date.now() - 86400000).toISOString(), transcript_source: "captions" },
      ];
      state.queue = { pending: [{ pending_id: 7, status: "pending", url: "https://www.youtube.com/watch?v=abcdefghijk", attempt_count: 0, retry_after: new Date(Date.now() + 120000).toISOString() }] };
      renderQueue(state.queue);
      renderHelperStatus(true);
    });
    await page.evaluate(() => document.fonts.ready);
    assert.equal(await page.locator(".activity-row").count(), 5);
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false, "page must fit viewport");
    await shot(page, `activity-${theme}-${width}`, { fullPage: true });
    if (width === 1440) {
      // Desktop scrolls .content, so fullPage alone cannot show Earlier.
      const height = await page.locator(".content").evaluate((el) => el.scrollHeight);
      await page.setViewportSize({ width, height });
      await shot(page, `activity-${theme}-${width}-full`);
      await page.setViewportSize({ width, height: 900 });
    }
    await page.getByRole("button", { name: "Details", exact: true }).focus();
    await page.evaluate(() => handleJobsStreamEvent("job", { id: "active", phase: "transcript" }));
    assert.equal(await page.evaluate(() => document.activeElement.dataset.activityDetail), "job:failed", "stream repaint preserves row focus");
    await page.keyboard.press("Enter");
    const drawer = page.locator("#captureFailureDrawer");
    await drawer.waitFor({ state: "visible" });
    assert.equal(await page.evaluate(() => document.activeElement.id), "captureFailureTitle");
    assert.equal(await drawer.locator("li").count(), 5);
    assert.match(await page.locator("#captureFailureError").textContent(), /^ERROR:/);
    assert.equal(await drawer.evaluate((el) => el.scrollWidth > el.clientWidth), false, "drawer must fit viewport");
    for (let i = 0; i < 8; i++) {
      await page.keyboard.press("Tab");
      assert.equal(await drawer.evaluate((el) => el.contains(document.activeElement)), true, "Tab stays in modal");
    }
    await page.locator("#captureFailureTitle").focus();
    await shot(page, `activity-drawer-${theme}-${width}`);
    await page.keyboard.press("Escape");
    assert.equal(await drawer.isVisible(), false);
    assert.equal(await page.evaluate(() => document.activeElement.dataset.activityDetail), "job:failed");
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.evaluate(() => handleJobsStreamEvent("job", { id: "active", phase: "screenshots" }));
    const duration = await page.locator('[data-activity-key="job:active"] .step.now').evaluate((el) => getComputedStyle(el).animationDuration);
    assert.ok(parseFloat(duration) <= 0.00001, `reduced motion: ${duration}`);
    await page.evaluate(() => {
      state.jobs = [];
      state.library = [];
      handleJobsStreamEvent("queue", { pending: [{ pending_id: 8, status: "pending", title: "Captions are waiting for YouTube",
        url: "https://www.youtube.com/watch?v=44444444444", last_error: "youtube_rate_limit", attempt_count: 1,
        queued_at: new Date().toISOString(), retry_after: new Date(Date.now() + 120000).toISOString() }] });
    });
    const captionRow = page.locator('[data-activity-key="pending:8"]');
    assert.equal(await page.locator('#queueRows [data-activity-key="pending:8"]').count(), 1, "pending retry stays in In progress");
    assert.equal(await page.locator("#attentionRows .activity-row").count(), 0, "pending retry is not a hard failure");
    assert.equal(await page.locator("#activityFailedBadge").isVisible(), false, "pending retry has no failed badge");
    assert.equal(await page.locator("#activityNavCount").textContent(), "1", "pending retry counts as active work");
    assert.equal(await captionRow.locator(".step.fail").count(), 1);
    assert.match(await captionRow.textContent(), /Failed at waiting for YouTube \(2 of 5\)/);
    await captionRow.getByRole("button", { name: "Details", exact: true }).click();
    assert.equal(await page.locator("#captureFailureError").textContent(), "ERROR: YouTube refused it (HTTP 429).");
    assert.match(await drawer.locator("li").nth(1).textContent(), /✕waiting for YouTubeFailed/);
    assert.equal(await drawer.evaluate((el) => el.scrollWidth > el.clientWidth), false, "caption failure drawer must fit viewport");
    await shot(page, `activity-caption429-${theme}-${width}`);
    await page.keyboard.press("Escape");
    await page.evaluate(() => { state.jobs = []; state.library = []; state.queue = { pending: [] }; renderQueue(state.queue); });
    assert.equal(await page.locator(".activity-row").count(), 0);
    assert.equal(await page.locator("#activityHeadline").textContent(), "Nothing uoinking right now.");
    assert.equal(await page.locator("#cancelAll").isDisabled(), true);
    assert.equal(await page.locator("#cancelAll").evaluate((el) => getComputedStyle(el).opacity), "1", "disabled text keeps its theme contrast");
    for (const name of ["Needs attention", "In progress", "Today", "Earlier"])
      assert.equal(await page.getByRole("heading", { name: new RegExp(`^${name}`) }).isVisible(), true);
    await shot(page, `activity-empty-${theme}-${width}`, { fullPage: true });
    await context.close();
    console.log(`PASS browser: ${theme} ${width}px, modal focus/Escape, no overflow, reduced motion`);
  }
  assert.deepEqual(errors, [], "no browser errors");
} finally { await browser.close(); }
console.log(`Screenshots: ${out}`);
