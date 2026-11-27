// Offline reader test. The helper responses are fixtures; the reader is the shipped dashboard.
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";

const require = createRequire(import.meta.url);
let playwright;
try {
  playwright = require(process.env.UOINK_PLAYWRIGHT_PATH || "playwright");
} catch (error) {
  if (error.code !== "MODULE_NOT_FOUND") throw error;
  console.log("SKIP transcript review browser test (Playwright unavailable)");
  process.exit(77);
}
const source = readFileSync(new URL("../../assets/dashboard/index.html", import.meta.url), "utf8");
const html = source.slice(0, source.indexOf("    init().catch(")) + "</script></body></html>";
const browser = await playwright.chromium.launch({
  headless: true, executablePath: process.env.UOINK_HEADLESS_CHROMIUM,
  args: ["--disable-gpu", "--disable-background-networking"],
});
let checks = 0;
try {
  for (const width of [390, 1280]) for (const theme of ["light", "dark"]) {
    const context = await browser.newContext({ viewport: { width, height: 900 }, colorScheme: theme,
      offline: true, serviceWorkers: "block" });
    await context.route("**/*", route => {
      if (route.request().url() === "http://uoink.test/dashboard") {
        return route.fulfill({ contentType: "text/html", body: html });
      }
      return route.abort();
    });
    const page = await context.newPage();
    await page.goto("http://uoink.test/dashboard");
    await page.evaluate(theme => {
      document.documentElement.dataset.theme = theme;
      document.querySelectorAll(".tab-panel").forEach(panel =>
        panel.classList.toggle("active", panel.id === "tab-yoink"));
      state.selectedYoink = { video_id: "abcde123456", title: "A saved talk", source_type: "video" };
      state.selectedYoinkSidecar = { ...state.selectedYoink, transcript: [] };
      renderYoinkDetail();
      window.reviewReads = 0;
      loadYoinkDetails = async (id, includeHeld) => {
        if (id !== "abcde123456" || includeHeld !== true) throw Error("unexpected request");
        window.reviewReads++;
        return { held_transcript_lines: [{ line: 3, text: "<b>fiction</b>" + "z".repeat(800) }] };
      };
    }, theme);
    const details = page.locator("[data-held-lines]");
    assert.equal(await details.count(), 0);
    await page.evaluate(() => {
      state.selectedYoinkSidecar.review_note = "Uoink held back 3 lines it thinks Whisper made up in silence.";
      renderYoinkDetail();
    });
    assert.equal(await page.evaluate(() => window.reviewReads), 0);
    await details.locator("summary").click();
    await details.locator("li").waitFor();
    assert.match(await details.locator("li").textContent(), /^Line 3 · <b>fiction/);
    assert.equal(await details.locator("li b").count(), 0);
    assert.ok(await details.evaluate(el => el.scrollWidth <= el.clientWidth + 1));
    await details.locator("summary").click();
    await details.locator("summary").click();
    assert.equal(await page.evaluate(() => window.reviewReads), 1);
    checks += 6;
    await context.close();
  }
} finally {
  await browser.close();
}
console.log(`${checks} checks passed`);
