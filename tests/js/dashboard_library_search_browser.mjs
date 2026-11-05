// Offline Library search and timestamp navigation in the shipped dashboard.
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { existsSync, readFileSync, mkdirSync } from "node:fs";
import { resolve, basename } from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
let playwright;
try {
  playwright = require(process.env.UOINK_PLAYWRIGHT_PATH || "playwright");
} catch (error) {
  if (error.code !== "MODULE_NOT_FOUND") throw error;
  console.log("SKIP Library search browser: Playwright is not installed.");
  process.exit(77);
}
if (!existsSync(playwright.chromium.executablePath())) {
  console.log("SKIP Library search browser: Chromium is not installed.");
  process.exit(77);
}
const root = fileURLToPath(new URL("../../", import.meta.url));
const out = resolve(root, "_scratch/library-search-qa");
mkdirSync(out, { recursive: true });
const source = readFileSync(resolve(root, "assets/dashboard/index.html"), "utf8");
const html = source.slice(0, source.indexOf("    init().catch(")) + "</script></body></html>";
const quote = "A pressurized rover keeps the crew and their equipment safe on the Moon.";
const rows = [
  { video_id: "moon", title: "Moon Base episode", source_type: "episode", platform: "podcast", timestamp_seconds: 92.5 },
  { video_id: "rovers", title: "Rovers video", source_type: "video", platform: "youtube", timestamp_seconds: 214 },
  { video_id: "defenders", title: "Planetary Defenders", source_type: "video", platform: "youtube", timestamp_seconds: 18 },
].map((row, i) => ({ ...row, author: "Space Research", yoinked_at: `2026-11-0${i + 1}T12:00:00Z`,
  passage_verified: true, passage: { text: i === 2 ? "A rover detects an asteroid." : quote, start: row.timestamp_seconds },
  source_url: `https://www.youtube.com/watch?v=${row.video_id}`, has_transcript: true, transcript_source: "captions" }));
const browser = await playwright.chromium.launch({ headless: true });
const errors = [];
const remote = [];
let combinations = 0;
try {
  for (const theme of ["light", "dark"]) for (const width of [1440, 390]) {
    const searches = [];
    let detailReads = 0;
    const context = await browser.newContext({ viewport: { width, height: 900 }, colorScheme: theme,
      reducedMotion: "reduce", offline: true, serviceWorkers: "block" });
    await context.route("**/*", (route) => {
      const url = new URL(route.request().url());
      if (url.hostname !== "uoink.test" || url.port) {
        remote.push(url.href);
        return route.abort();
      }
      if (url.pathname === "/dashboard") return route.fulfill({ contentType: "text/html", body: html });
      if (url.pathname.startsWith("/brand/fonts/")) return route.fulfill({ contentType: "font/woff", body: readFileSync(resolve(root, "assets/brand/fonts", basename(url.pathname))) });
      let body = { ok: true, token: "fixture", jobs: [], pending: [] };
      if (url.pathname === "/memory/search") {
        const params = Object.fromEntries(url.searchParams);
        searches.push(params);
        let results = params.q && params.match === "strict" ? rows.slice(0, 2) : rows.slice();
        if (params.sort === "newest") results.reverse();
        if (params.sort === "title") results.sort((a, b) => a.title.localeCompare(b.title));
        body = { ok: true, results, total: results.length, corpus_total: 3, state: "matches", search_mode: "keyword" };
      }
      if (url.pathname.endsWith("/details")) {
        detailReads++;
        body = { ok: true, title: "Moon Base episode", transcript: [
          ...Array.from({ length: 8 }, (_, i) => ({ start: i * 10, end: i * 10 + 4,
            text: "An introduction to the lunar mission and the crew's daily work. ".repeat(4) })),
          { start: 92.5, end: 105, text: quote },
          ...Array.from({ length: 8 }, (_, i) => ({ start: 110 + i * 10, end: 114 + i * 10,
            text: "The team continues the mission and checks the equipment. ".repeat(4) })),
        ] };
      }
      return route.fulfill({ contentType: "application/json", body: JSON.stringify(body) });
    });
    const page = await context.newPage();
    page.on("pageerror", (error) => errors.push(error.message));
    await page.goto("http://uoink.test/dashboard#library");
    const prepare = () => page.evaluate(() => {
      loadLibraryActivity = startLibraryActivityTimer = stopLibraryActivityTimer = () => {};
      hydrateMarks();
      wireEvents();
      wireRoutes();
      applyHashRoute();
    });
    await prepare();
    await page.evaluate(() => loadLibrary({ reset: true, jobs: false }));
    assert.equal(searches.at(-1).sort, "newest");
    await page.locator("#searchInput").fill("pressurized rover");
    await page.waitForFunction(() => document.querySelectorAll("#libraryGrid .card-match q").length === 2);
    assert.equal(searches.at(-1).match, "strict");
    assert.equal(searches.at(-1).sort, "relevance");
    assert.equal(searches.at(-1).mode, "keyword");
    assert.equal(await page.locator("#libraryGrid .card-match q").first().textContent(), quote);
    assert.equal(await page.locator('[data-card-id="defenders"]').count(), 0);
    await page.screenshot({ path: resolve(out, `search-${theme}-${width}.png`) });
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1), "search fits the viewport");
    const link = page.getByRole("link", { name: "Open Moon Base episode at 1:32" });
    if (width === 1440) {
      await link.focus();
      await page.keyboard.press("Enter");
    } else {
      await link.click();
    }
    await page.waitForFunction(() => document.activeElement.dataset.readerSeconds === "92.5");
    assert.equal(new URL(page.url()).hash, "#item/moon?t=92.5");
    assert.equal(detailReads, 1, "timestamp link opens once, without the row's generic click winning");
    const paragraph = page.locator('.reader-para[data-reader-seconds="92.5"]');
    assert.equal(await paragraph.locator("p").textContent(), quote);
    const box = await paragraph.boundingBox();
    await page.screenshot({ path: resolve(out, `moment-${theme}-${width}.png`) });
    const crumbs = await page.locator("#tab-yoink > .reader-crumbs").boundingBox();
    assert.ok(box.y >= crumbs.y + crumbs.height && box.y < 900, `matched paragraph is visible below the sticky breadcrumb: ${JSON.stringify({ box, crumbs })}`);
    await page.goBack();
    await page.waitForFunction(() => state.activeTab === "library");
    await page.locator("#sortFilter").selectOption("oldest");
    await page.waitForFunction(() => !state.loading && state.filters.sort === "oldest" && !state.libraryResetPending);
    assert.equal(searches.at(-1).sort, "oldest");
    await page.locator("#matchFilter").selectOption("forgiving");
    await page.waitForFunction(() => document.querySelectorAll("#libraryGrid .uoink-card").length === 3);
    assert.equal(searches.at(-1).sort, "oldest");
    assert.equal(searches.at(-1).mode, "auto");
    await page.locator("#searchInput").fill("");
    await page.waitForFunction(() => !state.loading && !state.libraryResetPending && !state.filters.q);
    assert.equal(searches.at(-1).sort, "newest");
    assert.equal(await page.locator("#libraryGrid .card-match").count(), 0);
    await page.goto("http://uoink.test/dashboard#item/moon?t=92.5");
    await page.reload();
    await prepare();
    await page.waitForFunction(() => document.activeElement.dataset.readerSeconds === "92.5");
    assert.equal(await page.locator("#yoinkHeading").textContent(), "Moon Base episode");
    combinations++;
    await context.close();
  }
  assert.deepEqual(errors, [], "no browser errors");
  assert.deepEqual(remote, [], "no remote requests");
  console.log(`PASS Library search browser: ${combinations} viewport/theme combinations; evidence ${out}`);
} finally {
  await browser.close();
}
