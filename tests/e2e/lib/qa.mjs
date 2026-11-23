// Shared helpers for the Uoink QA smoke suite (dev only).
// scripts/qa_smoke.py sets the UOINK_QA_* variables and starts the isolated helper.
import { test as base, expect } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
export const REPO = path.resolve(here, "..", "..", "..");
export const RUN_DIR = process.env.UOINK_QA_RUN_DIR || path.join(REPO, "_scratch", "qa-smoke", "manual");
export const BASE_URL = process.env.UOINK_QA_BASE_URL || "";
export const PROFILE = process.env.UOINK_QA_PROFILE || "";
export const STATE = process.env.UOINK_QA_STATE || "seeded";
export const FIXTURE_PORT = Number(process.env.UOINK_QA_FIXTURE_PORT || 0);
export const FIXTURE_HOST = process.env.UOINK_QA_FIXTURE_HOST || "fixture.uoink.test";
export const PRODUCTION_PORT = 5179;

if (!BASE_URL) throw new Error("UOINK_QA_BASE_URL is not set. Run the suite with scripts/qa_smoke.py.");
if (new URL(BASE_URL).port === String(PRODUCTION_PORT)) throw new Error("Refusing to test the production helper port 5179.");

export function expectInfo() {
  const file = path.join(RUN_DIR, `expect-${STATE}.json`);
  return fs.existsSync(file) ? JSON.parse(fs.readFileSync(file, "utf8")) : {};
}

export function token() {
  return fs.readFileSync(path.join(PROFILE, "token.txt"), "utf8").trim();
}

// Token-gated helper call from Node (not the browser).
export async function api(pathname, { method = "GET", body } = {}) {
  const res = await fetch(BASE_URL + pathname, {
    method,
    headers: { "X-Uoink-Token": token(), ...(body ? { "Content-Type": "application/json" } : {}) },
    body: body ? JSON.stringify(body) : undefined,
  });
  const text = await res.text();
  let data = null;
  try { data = JSON.parse(text); } catch { data = { raw: text }; }
  return { status: res.status, data };
}

// Problems the suite already knows about. A matching problem is reported as
// "known", not as a failure, so the run stays green until something new breaks.
const KNOWN = JSON.parse(fs.readFileSync(path.join(here, "..", "known-issues.json"), "utf8"));

export function splitKnown(check, problems) {
  const rules = KNOWN.filter((k) => k.check === check);
  const known = [];
  const fresh = [];
  for (const p of problems) {
    const text = typeof p === "string" ? p : JSON.stringify(p);
    const rule = rules.find((k) => new RegExp(k.match, "i").test(text));
    (rule ? known : fresh).push(rule ? `${rule.id}: ${text}` : text);
  }
  return { known, fresh };
}

// Report known problems on the test without failing it; fail on new ones.
export function expectNoNewProblems(check, problems, testInfo) {
  const { known, fresh } = splitKnown(check, problems);
  for (const k of known) testInfo.annotations.push({ type: "known-issue", description: `${check}: ${k}` });
  expect(fresh, `${check}: new problems (not in tests/e2e/known-issues.json)`).toEqual([]);
}

function projectName(testInfo) {
  return testInfo.project.name;
}

// Viewport screenshot into the run folder, listed for the contact sheet.
export async function shot(page, testInfo, flow, { fullPage = false } = {}) {
  const dir = path.join(RUN_DIR, "shots", STATE);
  fs.mkdirSync(dir, { recursive: true });
  const name = `${flow}--${projectName(testInfo)}.png`;
  const file = path.join(dir, name);
  await page.screenshot({ path: file, fullPage });
  fs.appendFileSync(path.join(RUN_DIR, "shots", "manifest.jsonl"), JSON.stringify({
    state: STATE, flow, project: projectName(testInfo), file: path.relative(RUN_DIR, file).split(path.sep).join("/"),
    test: testInfo.title,
  }) + "\n");
  await testInfo.attach(flow, { path: file, contentType: "image/png" });
  return file;
}

// Page-level layout problems: horizontal scroll and visible elements past the right edge.
export async function layoutProblems(page) {
  return page.evaluate(() => {
    const vw = document.documentElement.clientWidth;
    const out = [];
    if (document.documentElement.scrollWidth > vw + 1) out.push(`page scrolls sideways: ${document.documentElement.scrollWidth}px in a ${vw}px window`);
    const clipped = (el) => {
      for (let p = el.parentElement; p && p !== document.body; p = p.parentElement) {
        const cs = getComputedStyle(p);
        if (/(auto|scroll|hidden|clip)/.test(cs.overflowX)) return true;
      }
      return false;
    };
    for (const el of document.querySelectorAll("body *")) {
      const r = el.getBoundingClientRect();
      if (!r.width || !r.height || r.right <= vw + 1) continue;
      const cs = getComputedStyle(el);
      if (cs.visibility === "hidden" || cs.position === "fixed" || el.closest("[hidden], .hidden, dialog:not([open])")) continue;
      if (clipped(el)) continue;
      out.push(`${el.tagName.toLowerCase()}${el.id ? "#" + el.id : ""}.${String(el.className).split(" ")[0]} right=${Math.round(r.right)} "${(el.textContent || "").trim().slice(0, 40)}"`);
      if (out.length > 8) break;
    }
    return out;
  });
}

// Library list: wait until the first page of cards (or the empty state) is drawn.
export async function waitForLibrary(page, { empty = false } = {}) {
  if (empty) {
    await expect(page.locator("#libraryEmpty")).toBeVisible({ timeout: 20_000 });
    return;
  }
  await expect(page.locator("#libraryGrid .uoink-card").first()).toBeVisible({ timeout: 20_000 });
  await expect(page.locator("#resultSummary")).toContainText("shown of", { timeout: 20_000 });
}

export async function gotoDashboard(page, hash = "#library") {
  await page.goto(`${BASE_URL}/dashboard${hash}`);
}

// Background colour luminance (0 dark .. 1 light) of the page body.
export async function bodyLuminance(page) {
  return page.evaluate(() => {
    const parse = (c) => (c.match(/[\d.]+/g) || []).slice(0, 3).map(Number);
    let el = document.body;
    let rgb = parse(getComputedStyle(el).backgroundColor);
    const alpha = (getComputedStyle(el).backgroundColor.match(/[\d.]+/g) || [])[3];
    if (alpha === "0") rgb = parse(getComputedStyle(document.documentElement).backgroundColor);
    const [r, g, b] = rgb.map((v) => v / 255);
    return 0.2126 * r + 0.7152 * g + 0.0722 * b;
  });
}

// The dashboard fixture: blocks every non-local request, records console
// errors, uncaught exceptions and 5xx answers, and checks them after the test.
export const test = base.extend({
  dash: async ({ page }, use, testInfo) => {
    const problems = { console: [], pageErrors: [], serverErrors: [], remote: [] };
    await page.route("**/*", (route) => {
      const url = new URL(route.request().url());
      if (url.hostname === "127.0.0.1" || url.protocol === "data:" || url.protocol === "blob:") return route.continue();
      problems.remote.push(url.href);
      return route.abort();
    });
    page.on("console", (msg) => { if (msg.type() === "error") problems.console.push(msg.text()); });
    page.on("pageerror", (err) => problems.pageErrors.push(err.message));
    page.on("response", (res) => { if (res.status() >= 500) problems.serverErrors.push(`${res.status()} ${new URL(res.url()).pathname}`); });
    await use({ page, problems });
    await testInfo.attach("browser-problems.json", { body: JSON.stringify(problems, null, 2), contentType: "application/json" });
    expectNoNewProblems("page-error", problems.pageErrors, testInfo);
    expectNoNewProblems("console-error", problems.console, testInfo);
    expectNoNewProblems("server-error", problems.serverErrors, testInfo);
    expectNoNewProblems("remote-request", problems.remote, testInfo);
  },
});

export { expect };
