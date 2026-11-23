// Extension e2e: the unpacked extension in Chromium against the isolated helper.
//
// The shipped extension talks only to 127.0.0.1:5179, which this suite must
// never touch. So the test copies extension/ to the run folder and points the
// copy at the isolated helper port; the shipped files are never edited. The
// copy also gets host permission for the local fixture page, which stands in
// for the activeTab grant a real toolbar click gives.
//
// Extensions need a headed browser or Chromium's new headless mode:
//   UOINK_E2E_HEADED=1           run with a visible window
//   UOINK_E2E_EXTENSION=headless run in the new headless mode (scripts/qa_smoke.py does this)
// Otherwise these tests skip.
import { test as base, chromium } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import {
  expect, api, BASE_URL, RUN_DIR, REPO, FIXTURE_HOST, FIXTURE_PORT, PRODUCTION_PORT, shot, waitForLibrary,
} from "./lib/qa.mjs";

const PINNED_EXTENSION_ID = "bkcapfidedhfcjpmjabeopfbcjcbmdmi";
const MODE = process.env.UOINK_E2E_HEADED === "1" ? "headed"
  : (process.env.UOINK_E2E_EXTENSION === "headless" ? "headless" : "off");
const FIXTURE_URL = `http://${FIXTURE_HOST}:${FIXTURE_PORT}/article.html`;
const FIXTURE_TITLE = "Field notes from a made-up workshop";
const FIXTURE_PHRASE = "saffron lantern protocol";

// Copy extension/ and point the copy at the isolated helper.
export function patchedExtension(target) {
  const port = new URL(BASE_URL).port;
  const source = path.join(REPO, "extension");
  fs.rmSync(target, { recursive: true, force: true });
  fs.cpSync(source, target, { recursive: true });
  const walk = (dir) => fs.readdirSync(dir, { withFileTypes: true }).flatMap((e) =>
    e.isDirectory() ? walk(path.join(dir, e.name)) : [path.join(dir, e.name)]);
  for (const file of walk(target)) {
    if (!/\.(js|mjs|html|json|css)$/.test(file)) continue;
    const text = fs.readFileSync(file, "utf8");
    const next = text.split(`127.0.0.1:${PRODUCTION_PORT}`).join(`127.0.0.1:${port}`);
    if (next !== text) fs.writeFileSync(file, next);
  }
  const manifestPath = path.join(target, "manifest.json");
  const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
  manifest.host_permissions.push(`http://${FIXTURE_HOST}/*`);
  fs.writeFileSync(manifestPath, JSON.stringify(manifest, null, 2));
  const left = walk(target).filter((f) => /\.(js|mjs|html|json)$/.test(f) && fs.readFileSync(f, "utf8").includes(String(PRODUCTION_PORT)));
  if (left.length) throw new Error(`patched extension still names port ${PRODUCTION_PORT}: ${left.join(", ")}`);
  return target;
}

const test = base.extend({
  ext: [async ({}, use, workerInfo) => {
    const dir = patchedExtension(path.join(RUN_DIR, "extension-patched"));
    const profile = fs.mkdtempSync(path.join(RUN_DIR, "chromium-profile-"));
    const context = await chromium.launchPersistentContext(profile, {
      channel: "chromium",
      headless: MODE !== "headed",
      viewport: { width: 1280, height: 900 },
      args: [
        `--disable-extensions-except=${dir}`,
        `--load-extension=${dir}`,
        `--host-resolver-rules=MAP ${FIXTURE_HOST} 127.0.0.1`,
      ],
    });
    // Nothing leaves the computer: only the helper and the fixture page answer.
    const remote = [];
    await context.route("**/*", (route) => {
      const url = new URL(route.request().url());
      if (["127.0.0.1", FIXTURE_HOST].includes(url.hostname) || url.protocol === "chrome-extension:") return route.continue();
      remote.push(url.href);
      return route.abort();
    });
    let [worker] = context.serviceWorkers();
    if (!worker) worker = await context.waitForEvent("serviceworker", { timeout: 20_000 });
    const id = new URL(worker.url()).host;
    await use({ context, worker, id, remote });
    await context.close();
  }, { scope: "worker" }],
});

test.describe("extension", { tag: "@extension" }, () => {
  test.describe.configure({ mode: "serial" });
  test.skip(MODE === "off", "Extension tests need UOINK_E2E_HEADED=1 or UOINK_E2E_EXTENSION=headless.");

  test("extension loads with the pinned id", async ({ ext }) => {
    expect(ext.id).toBe(PINNED_EXTENSION_ID);
    expect(ext.worker.url()).toContain("background.js");
  });

  test("setup page loads and finds the helper", async ({ ext }, testInfo) => {
    const page = await ext.context.newPage();
    const errors = [];
    page.on("pageerror", (e) => errors.push(e.message));
    await page.goto(`chrome-extension://${ext.id}/setup.html`);
    await expect(page.locator("#status-instructions")).toContainText("Connected", { timeout: 20_000 });
    await shot(page, testInfo, "40-extension-setup");
    expect(errors).toEqual([]);
    await page.close();
  });

  test("popup opens and shows connected", async ({ ext }, testInfo) => {
    const page = await ext.context.newPage();
    await page.setViewportSize({ width: 380, height: 640 });
    const errors = [];
    page.on("pageerror", (e) => errors.push(e.message));
    await page.goto(`chrome-extension://${ext.id}/popup.html`);
    await expect(page.locator("#status")).toHaveText("Running", { timeout: 20_000 });
    await expect(page.locator("#dot")).toBeVisible();
    await shot(page, testInfo, "41-extension-popup");
    expect(errors).toEqual([]);
    await page.close();
  });

  test("Uoink this page saves a local page that then shows in the library", async ({ ext }, testInfo) => {
    const fixture = await ext.context.newPage();
    await fixture.goto(FIXTURE_URL);
    await expect(fixture).toHaveTitle(FIXTURE_TITLE);
    // A toolbar popup reads "the active tab". Opened as a tab here, the popup
    // would see itself, so it is pointed at the fixture tab instead.
    const popup = await ext.context.newPage();
    await popup.setViewportSize({ width: 380, height: 640 });
    await popup.addInitScript((pattern) => {
      const query = chrome.tabs.query.bind(chrome.tabs);
      chrome.tabs.query = (q, cb) => {
        const result = q && q.active && q.currentWindow ? query({ url: pattern }) : query(q);
        if (cb) { result.then(cb); return undefined; }
        return result;
      };
    }, `http://${FIXTURE_HOST}/*`);
    await popup.goto(`chrome-extension://${ext.id}/popup.html`);
    await expect(popup.locator("#current-source-preview")).toHaveText(FIXTURE_TITLE, { timeout: 20_000 });
    const button = popup.locator("#uoink-current-btn");
    await expect(button).toBeEnabled();
    await expect(button).toHaveText("Uoink this page");
    await shot(popup, testInfo, "42-extension-popup-page");
    await button.click();
    await expect(popup.locator("#popup-toast")).toContainText("Saved", { timeout: 45_000 });
    await shot(popup, testInfo, "43-extension-popup-saved");
    // The helper has it.
    await expect.poll(async () => {
      const res = await api(`/memory/search?q=${encodeURIComponent(FIXTURE_PHRASE)}&limit=5`);
      return (res.data.results || []).map((r) => r.title);
    }, { timeout: 30_000 }).toContain(FIXTURE_TITLE);
    // And the dashboard lists it.
    const dash = await ext.context.newPage();
    await dash.goto(`${BASE_URL}/dashboard#library`);
    await waitForLibrary(dash);
    await dash.locator("#searchInput").fill(FIXTURE_PHRASE);
    const card = dash.locator("#libraryGrid .uoink-card").filter({ hasText: FIXTURE_TITLE });
    await expect(card).toBeVisible();
    await shot(dash, testInfo, "44-extension-saved-in-library");
    expect(ext.remote, "requests that tried to leave the computer").toEqual([]);
    for (const p of [fixture, popup, dash]) await p.close();
  });
});
