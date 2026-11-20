// Offline dashboard checks. Every request is fulfilled from this checkout or a fixture.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import test from "node:test";

const require = createRequire(import.meta.url);
const { chromium } = require(process.env.UOINK_PLAYWRIGHT_PATH || "playwright");
const dashboard = readFileSync(new URL("../../assets/dashboard/index.html", import.meta.url), "utf8");
const html = dashboard.slice(0, dashboard.indexOf("    init().catch(")) + "</script></body></html>";

test("library cards keep their layout and dialogs retain keyboard focus", async () => {
  const browser = await chromium.launch({headless: true, args: ["--disable-gpu"]});
  try {
    const page = await browser.newPage();
    await page.route("**/*", route => {
      const url = new URL(route.request().url());
      if (url.origin !== "http://fixture.test") return route.abort();
      if (url.pathname === "/dashboard") return route.fulfill({contentType: "text/html", body: html});
      if (url.pathname === "/dashboard/qrcode.js") return route.fulfill({contentType: "text/javascript", body: ""});
      if (url.pathname.startsWith("/brand/fonts/")) return route.abort();
      return route.fulfill({json: {ok: true, token: "fixture", hooks: []}});
    });
    await page.goto("http://fixture.test/dashboard");
    await page.evaluate(() => { wireEvents(); wireLibraryActivityEvents(); });
    for (const width of [390, 1280]) {
      await page.setViewportSize({width, height: 900});
      for (const scheme of ["light", "dark"]) {
        await page.emulateMedia({colorScheme: scheme});
        const result = await page.evaluate(() => {
          const grid = els.libraryGrid;
          document.getElementById("tab-library").classList.add("active");
          grid.replaceChildren();
          const emptyFits = document.documentElement.scrollWidth <= innerWidth;
          state.library = Array.from({length: 1000}, (_, i) => ({
            video_id: String(i), title: "Example ".repeat(20), channel: "Example channel", hook_type: "other",
          }));
          grid.innerHTML = state.library.map(cardHtml).join("");
          const card = grid.firstElementChild, button = card.querySelector(".card-title");
          const box = el => [el.offsetWidth, el.offsetHeight, el.offsetTop, el.offsetLeft];
          const current = [box(card), box(button)];
          const previous = document.createElement("div");
          previous.className = button.className;
          previous.textContent = button.textContent;
          button.replaceWith(previous);
          const original = [box(card), box(previous)];
          previous.replaceWith(button);
          return {emptyFits, fits: document.documentElement.scrollWidth <= innerWidth,
            count: grid.childElementCount, current, original, nested: grid.querySelectorAll("[role=button] button, button button").length};
        });
        assert.ok(result.emptyFits && result.fits, `${scheme} at ${width}px`);
        assert.equal(result.count, 1000);
        assert.equal(result.nested, 0);
        assert.deepEqual(result.current, result.original, `card geometry at ${width}px`);
      }
    }

    await page.evaluate(() => {
      window.openedRows = [];
      openYoinkDetail = row => window.openedRows.push(videoIdOf(row));
    });
    const firstCard = page.locator('[data-card-id="0"]');
    await firstCard.locator(".card-title").focus();
    await page.keyboard.press("Enter");
    await firstCard.locator(".row-thumb").click();
    await firstCard.locator(".hook-chip").click();
    await page.keyboard.press("Escape");
    assert.deepEqual(await page.evaluate(() => window.openedRows), ["0", "0"]);
    assert.ok(await firstCard.locator(".hook-chip").evaluate(el => document.activeElement === el));

    await page.evaluate(() => {
      const trigger = document.createElement("button");
      trigger.id = "focus-fixture";
      document.body.prepend(trigger);
      const modal = id => document.getElementById(id);
      window.exerciseDialog = id => {
        const dialog = modal(id);
        dialog.closest(".tab-panel")?.classList.add("active");
        const details = dialog.closest("details");
        if (details) details.open = true;
        trigger.focus();
        switch (id) {
          case "hookExplainer": return openHookExplainer("other", trigger);
          case "sourceConsentModal": return openConsentModal({source_id: "fixture"}, "on");
          case "listImportModal": return openListImport();
          case "defaultAnchorsModal": return openDefaultAnchorsModal();
          case "stopHelperConfirm": return openStopHelperConfirm(trigger);
          case "writingHandoffPopup": return renderWritingHandoff([]);
          case "itemHealthDrawer": return openItemHealth("0", trigger);
          case "captureFailureDrawer":
            state.activityEntries = [{key: "fixture", row: {title: "Example"}, model: activitySteps({state: "failed"})}];
            return openCaptureFailure("fixture", trigger);
          case "activityEvidenceModal": captureActivityEvidenceFocus(); return focusActivityEvidenceModal();
          case "semanticNoticeDialog": return dialog.showModal();
        }
      };
    });
    for (const [id, close] of Object.entries({
      hookExplainer: "#hookExplainerClose", sourceConsentModal: "#cancelSourceConsent",
      listImportModal: "#closeListImport", defaultAnchorsModal: "#closeDefaultAnchors",
      stopHelperConfirm: "#cancelStopHelper", writingHandoffPopup: "#closeWritingHandoff",
      itemHealthDrawer: "#closeItemHealth", captureFailureDrawer: "#closeCaptureFailure",
      activityEvidenceModal: "#closeEvidenceBtn", semanticNoticeDialog: "button",
    })) {
      const dialog = page.locator("#" + id);
      for (const useEscape of [true, false]) {
        await page.evaluate(id => window.exerciseDialog(id), id);
        const inside = () => dialog.evaluate(el => el.contains(document.activeElement));
        assert.ok(await inside(), id + " takes focus");
        for (const key of ["Shift+Tab", "Tab", "Tab", "Tab"]) {
          await page.keyboard.press(key);
          assert.ok(await inside(), id + " traps " + key);
        }
        if (useEscape) await page.keyboard.press("Escape");
        else await dialog.locator(close).click();
        assert.equal(await page.evaluate(() => document.activeElement.id), "focus-fixture", id + " restores focus");
      }
    }
    const storage = await page.evaluate(async () => {
      const requests = [];
      let bytes = 1048576, confirmed = false;
      authFetch = async (path, options) => {
        if (path.includes("/delete")) {
          requests.push(JSON.parse(options.body));
          bytes = 0;
          return {ok: true, removed: true};
        }
        return {ok: true, bytes, episodes: bytes ? [7] : []};
      };
      window.confirm = () => confirmed;
      await refreshPodcastStorage();
      const before = document.getElementById("podcastAudioUsage").textContent;
      await deletePodcastAudio();
      const cancelled = requests.length === 0;
      confirmed = true;
      await deletePodcastAudio();
      return {before, cancelled, requests, after: document.getElementById("podcastAudioUsage").textContent};
    });
    assert.deepEqual(storage, {before: "1 MiB on disk", cancelled: true,
      requests: [{episode_id: 7, confirmed: true}], after: "0 bytes on disk"});
  } finally {
    await browser.close();
  }
});
