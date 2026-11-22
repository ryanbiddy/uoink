// Offline dashboard checks. Every request is fulfilled from this checkout or a fixture.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import test from "node:test";

const require = createRequire(import.meta.url);
const { chromium } = require(process.env.UOINK_PLAYWRIGHT_PATH || "playwright");
const dashboard = readFileSync(new URL("../../assets/dashboard/index.html", import.meta.url), "utf8");
const html = dashboard.slice(0, dashboard.indexOf("    init().catch(")) + "</script></body></html>";

test("library cards keep their layout and dialogs retain keyboard focus", async t => {
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
    await t.test("the styled native clear button still clears the library search", async () => {
      await page.locator("#tab-library").evaluate(el => el.classList.add("active"));
      const search = page.locator("#searchInput");
      await search.fill("sample");
      const box = await search.boundingBox();
      await search.click({position: {x: box.width - 22, y: box.height / 2}});
      assert.equal(await search.inputValue(), "");
    });
    await page.evaluate(() => { wireEvents(); wireLibraryActivityEvents(); });
    for (const width of [390, 1280]) {
      await page.setViewportSize({width, height: 900});
      for (const scheme of ["light", "dark"]) {
        await page.emulateMedia({colorScheme: scheme});
        const result = await page.evaluate(() => {
          const grid = els.libraryGrid;
          document.getElementById("tab-library").classList.add("active");
          state.library = [];
          state.libraryState = "empty_corpus";
          renderLibrary();
          const select = els.librarySelectToggle;
          const emptySelectHidden = !select.getClientRects().length;
          grid.replaceChildren();
          const emptyFits = document.documentElement.scrollWidth <= innerWidth;
          state.library = Array.from({length: 1000}, (_, i) => ({
            video_id: String(i), title: i === 1 ? "Short" : "Example ".repeat(20), channel: "Example channel", hook_type: "other",
          }));
          state.libraryState = "matches";
          renderLibrary();
          const selectBox = select.getBoundingClientRect();
          const helpBox = select.parentElement.querySelector("[data-hook-explain]").getBoundingClientRect();
          const linkGap = helpBox.left - selectBox.right;
          const geometry = [...grid.children].slice(0, 2).map(card => {
            const button = card.querySelector(".card-title");
            const box = el => [el.offsetWidth, el.offsetHeight, el.offsetTop, el.offsetLeft];
            const current = [box(card), box(button)];
            const previous = document.createElement("div");
            previous.className = button.className;
            previous.textContent = button.textContent;
            button.replaceWith(previous);
            const original = [box(card), box(previous)];
            previous.replaceWith(button);
            return {current, original};
          });
          return {emptyFits, emptySelectHidden, selectWidth: selectBox.width, linkGap, fits: document.documentElement.scrollWidth <= innerWidth,
            count: grid.childElementCount, geometry, nested: grid.querySelectorAll("[role=button] button, button button").length};
        });
        assert.ok(result.emptyFits && result.fits, `${scheme} at ${width}px`);
        assert.ok(result.emptySelectHidden);
        assert.ok(result.selectWidth > 0 && result.linkGap >= 10, `summary gap ${result.linkGap}px at ${width}px`);
        assert.equal(result.count, 1000);
        assert.equal(result.nested, 0);
        await t.test(`card geometry in ${scheme} at ${width}px`, () => {
          for (const {current, original} of result.geometry) assert.deepEqual(current, original);
        });
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

    await t.test("keyboard focus highlights the row and other controls keep their click", async () => {
      await page.mouse.move(0, 0);
      const card = firstCard;
      const background = () => card.evaluate(el => getComputedStyle(el).backgroundColor);
      await card.locator(".card-title").focus();
      const focused = await background();
      await card.evaluate(el => {
        document.activeElement.blur();
        const button = document.createElement("button");
        button.className = "fixture-control";
        el.append(button);
      });
      assert.notEqual(await background(), focused);
      await card.locator(".fixture-control").click();
      assert.deepEqual(await page.evaluate(() => window.openedRows), ["0", "0"]);
    });

    await t.test("hook opener survives a library redraw", async () => {
      await firstCard.locator(".hook-chip").click();
      await page.evaluate(() => { els.libraryGrid.innerHTML = state.library.slice(0, 2).map(cardHtml).join(""); });
      await page.keyboard.press("Escape");
      assert.ok(await firstCard.locator(".hook-chip").evaluate(el => el === document.activeElement));
    });

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
          case "semanticNoticeDialog": {
            const link = document.querySelector("[data-search-notice]");
            for (let el = link; el; el = el.parentElement) {
              if (el.matches("details")) el.open = true;
              if (el.hidden) el.hidden = false;
              el.classList.remove("hidden");
            }
            readSettingsResource = async () => {
              trigger.focus();
              return "license line\n".repeat(300);
            };
            link.focus();
            link.click();
            return;
          }
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
      await t.test(id + " keyboard focus", async () => {
        const dialog = page.locator("#" + id);
        for (const useEscape of [true, false]) {
          await page.evaluate(id => window.exerciseDialog(id), id);
          await dialog.waitFor({state: "visible"});
          const inside = () => dialog.evaluate(el => el.contains(document.activeElement));
          assert.ok(await inside(), id + " takes focus");
          for (const key of ["Shift+Tab", "Tab", "Tab", "Tab"]) {
            await page.keyboard.press(key);
            assert.ok(await inside(), id + " traps " + key);
          }
          if (id === "semanticNoticeDialog") {
            await dialog.evaluate(el => el.addEventListener("keydown", e => { window.noticeWrapped = e.defaultPrevented; }, {once: true}));
            await dialog.locator("button").focus();
            await page.keyboard.press("Tab");
            assert.equal(await page.evaluate(() => document.activeElement.id), "semanticNoticeText");
            assert.ok(await page.evaluate(() => window.noticeWrapped));
          }
          if (useEscape) await page.keyboard.press("Escape");
          else await dialog.locator(close).click();
          if (id === "semanticNoticeDialog") {
            await page.waitForFunction(() => document.activeElement.matches("[data-search-notice]"));
          } else {
            assert.equal(await page.evaluate(() => document.activeElement.id), "focus-fixture", id + " restores focus");
          }
        }
      });
    }
    await page.evaluate(() => { const dialog = document.getElementById("semanticNoticeDialog"); if (dialog.open) dialog.close(); });
    await t.test("confirming consent focuses the replacement source control", async () => {
      const active = await page.evaluate(async () => {
        const source = {source_id: "fixture", consent_state: "off"};
        document.getElementById("tab-sources").classList.add("active");
        callRegistryTool = async () => ({ok: true, sources: [source]});
        authFetch = async () => ({user_intent_token: "fixture"});
        await loadStandingSubscriptions();
        const opener = els.standingSubscriptionList.querySelector(".toggle-consent-btn");
        for (let el = opener; el; el = el.parentElement) if (el.matches("details")) el.open = true;
        opener.focus();
        opener.click();
        await new Promise(resolve => setTimeout(resolve, 0));
        if (els.sourceConsentModal.classList.contains("hidden")) return false;
        els.confirmSourceConsent.click();
        await new Promise(resolve => setTimeout(resolve, 0));
        return !opener.isConnected && document.activeElement === els.standingSubscriptionList.querySelector(".toggle-consent-btn");
      });
      assert.ok(active);
    });
    await t.test("For You titles open by keyboard and sibling buttons keep their action", async () => {
      await page.evaluate(() => {
        const host = document.createElement("div");
        host.id = "insight-fixture";
        host.innerHTML = insightCard(state.library[0], "Worth another look", {writeFrom: true});
        document.body.prepend(host);
        window.openedRows = [];
        writeFromSource = id => { window.wroteFrom = id; };
      });
      const insight = page.locator("#insight-fixture");
      assert.equal(await insight.locator("[role=button] button").count(), 0);
      await insight.locator("button.insight-title").focus();
      await page.keyboard.press("Space");
      await insight.locator("[data-write-from]").click();
      assert.deepEqual(await page.evaluate(() => [window.openedRows, window.wroteFrom]), [["0"], "0"]);
    });
    await t.test("Sources resolves the browser once per page and keeps fallback wording", async () => {
      const result = await page.evaluate(async () => {
        let calls = 0;
        authFetch = async path => {
          if (path === "/extension/browser") calls++;
          return {};
        };
        switchTab("sources");
        switchTab("sources");
        await Promise.resolve();
        return [calls, document.getElementById("extensionBrowserName").textContent,
          document.getElementById("extensionBrowserUrl").textContent];
      });
      assert.deepEqual(result, [1, "your Chromium browser", "chrome://extensions/"]);
    });
    await t.test("storage polls, confirms and refreshes totals", async () => {
      const storage = await page.evaluate(async () => {
        const requests = [];
        let bytes = 1048576, confirmed = false, polls = 0;
        authFetch = async (path, options) => {
          if (path.includes("/delete")) {
            requests.push(JSON.parse(options.body));
            bytes = 0;
            return {ok: true, removed: true};
          }
          if (path.endsWith("?refresh=1")) return {pending: true};
          polls++;
          return {ok: true, bytes, deletable_bytes: bytes, episodes: bytes ? [7] : []};
        };
        window.confirm = () => confirmed;
        await refreshPodcastStorage();
        const before = document.getElementById("podcastAudioUsage").textContent;
        await deletePodcastAudio();
        const cancelled = requests.length === 0;
        confirmed = true;
        await deletePodcastAudio();
        return {before, cancelled, requests, polls, after: document.getElementById("podcastAudioUsage").textContent};
      });
      assert.deepEqual(storage, {before: "1 MiB on disk. 1 MiB can be removed. 0 bytes will be kept.", cancelled: true, polls: 2,
        requests: [{episode_id: 7, confirmed: true}], after: "0 bytes on disk. 0 bytes can be removed. 0 bytes will be kept."});
    });
    for (const ids of [[1], [1, 2]]) {
      await t.test("stop cleanup during a batch of " + ids.length, async () => {
        const result = await page.evaluate(async ids => {
          podcastCleanupIds = ids;
          window.confirm = () => true;
          let resume, calls = 0;
          authFetch = async path => {
            if (!path.endsWith("/delete")) return {bytes: 0, deletable_bytes: 0, episodes: []};
            calls++;
            await new Promise(resolve => { resume = resolve; });
            return {removed: true};
          };
          const done = deletePodcastAudio();
          const stop = document.getElementById("stopPodcastCleanup");
          stop.click();
          const stopping = stop.disabled && stop.textContent.includes("Stopping");
          resume();
          await done;
          return {stopping, calls, message: document.getElementById("podcastCleanupStatus").textContent};
        }, ids);
        assert.deepEqual(result, {stopping: true, calls: 1, message: (ids.length > 1 ? "Stopped. " : "") + "Removed 1 audio file."});
      });
    }
  } finally {
    await browser.close();
  }
});
