// Accessibility smoke with Playwright's own aria snapshots and simple checks
// (no axe-core): every control has an accessible name, keyboard focus is
// visible, and dialogs let the keyboard out.
import {
  test, expect, expectInfo, shot, waitForLibrary, gotoDashboard, expectNoNewProblems,
} from "./lib/qa.mjs";

const NAMED_ROLES = "button|link|textbox|searchbox|combobox|listbox|checkbox|radio|switch|slider|spinbutton|menuitem|tab|img";
const UNNAMED = new RegExp(`^\\s*- (${NAMED_ROLES})(?=\\s*(?::\\s*$|$|\\[))`);

// Lines of the aria snapshot whose control has no accessible name.
async function unnamedControls(locator) {
  const snapshot = await locator.ariaSnapshot();
  return snapshot.split("\n").filter((line) => UNNAMED.test(line)).map((line) => line.trim());
}

// Where an unnamed control lives, so a report can point at it.
async function describeUnnamed(page, scope) {
  return page.evaluate((scope) => {
    const root = document.querySelector(scope) || document.body;
    const out = [];
    const visible = (el) => { const r = el.getBoundingClientRect(); const cs = getComputedStyle(el); return r.width > 0 && r.height > 0 && cs.visibility !== "hidden" && cs.display !== "none"; };
    for (const el of root.querySelectorAll("button, a[href], input:not([type=hidden]), select, textarea, [role=button], [role=link], [role=checkbox], [role=switch], [role=tab], [role=menuitem], img")) {
      if (!visible(el) || el.closest("[aria-hidden=true], [hidden], .hidden")) continue;
      if (el.tagName === "IMG" && el.getAttribute("alt") === "") continue;
      const labelled = el.getAttribute("aria-label") || el.getAttribute("aria-labelledby") || el.getAttribute("title") || el.getAttribute("alt") || el.getAttribute("placeholder");
      const text = (el.textContent || "").trim();
      const byLabel = el.id && document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
      const wrapped = el.closest("label");
      if (!labelled && !text && !byLabel && !wrapped && el.value === undefined) out.push(el.outerHTML.slice(0, 120));
      else if (!labelled && !text && !byLabel && !wrapped && ["INPUT", "SELECT", "TEXTAREA"].includes(el.tagName)) out.push(el.outerHTML.slice(0, 120));
    }
    return out;
  }, scope);
}

async function checkNames(page, testInfo, where, scope = "body") {
  const lines = await unnamedControls(page.locator(scope));
  const detail = lines.length ? await describeUnnamed(page, scope) : [];
  const problems = lines.map((line, i) => `${where}: ${line}${detail[i] ? ` -> ${detail[i]}` : ""}`);
  expectNoNewProblems("a11y-name", problems, testInfo);
  return lines;
}

// Tab through the page and check each stop shows a visible focus change.
async function checkFocusVisible(page, testInfo, where, stops = 25) {
  await page.evaluate(() => { document.activeElement && document.activeElement.blur(); window.scrollTo(0, 0); });
  await page.locator("body").focus();
  const styleOf = (el) => {
    const pick = (e) => {
      if (!e) return "";
      const cs = getComputedStyle(e);
      return [cs.outlineStyle, cs.outlineWidth, cs.outlineColor, cs.boxShadow, cs.borderTopColor, cs.borderBottomColor,
        cs.backgroundColor, cs.color, cs.textDecorationLine].join("|");
    };
    return [pick(el), pick(el.parentElement), pick(el.parentElement && el.parentElement.parentElement)].join("||");
  };
  const seen = [];
  for (let i = 0; i < stops; i++) {
    await page.keyboard.press("Tab");
    const info = await page.evaluate(({ i, styleOfSrc }) => {
      const el = document.activeElement;
      if (!el || el === document.body) return null;
      const styleOf = new Function(`return (${styleOfSrc})`)();
      el.setAttribute("data-qa-focus", String(i));
      const r = el.getBoundingClientRect();
      return { i, tag: el.tagName.toLowerCase(), id: el.id, name: (el.getAttribute("aria-label") || el.textContent || "").trim().slice(0, 40), focused: styleOf(el), size: r.width * r.height };
    }, { i, styleOfSrc: styleOf.toString() });
    if (info) seen.push(info);
  }
  await page.evaluate(() => document.activeElement && document.activeElement.blur());
  const problems = [];
  for (const stop of seen) {
    const unfocused = await page.evaluate(({ i, styleOfSrc }) => {
      const el = document.querySelector(`[data-qa-focus="${i}"]`);
      if (!el) return null;
      const styleOf = new Function(`return (${styleOfSrc})`)();
      const s = styleOf(el);
      el.removeAttribute("data-qa-focus");
      return s;
    }, { i: stop.i, styleOfSrc: styleOf.toString() });
    if (unfocused !== null && unfocused === stop.focused) problems.push(`${where}: no visible focus on ${stop.tag}${stop.id ? "#" + stop.id : ""} "${stop.name}"`);
    if (stop.size === 0) problems.push(`${where}: focus lands on an invisible ${stop.tag}${stop.id ? "#" + stop.id : ""} "${stop.name}"`);
  }
  expect(seen.length, `${where}: Tab reaches at least a few controls`).toBeGreaterThan(3);
  expectNoNewProblems("a11y-focus", problems, testInfo);
}

// Open a dialog, Tab around inside it, then leave it with Escape.
async function checkDialog(page, testInfo, where, opener, dialogSelector) {
  await opener.click();
  const dialog = page.locator(dialogSelector);
  await expect(dialog).toBeVisible();
  const inside = () => page.evaluate((sel) => { const d = document.querySelector(sel); return !!d && d.contains(document.activeElement); }, dialogSelector);
  const problems = [];
  if (!(await inside())) problems.push(`${where}: focus does not move into the dialog when it opens`);
  const stops = new Set();
  for (const key of ["Tab", "Tab", "Tab", "Tab", "Tab", "Tab", "Shift+Tab", "Shift+Tab", "Shift+Tab"]) {
    await page.keyboard.press(key);
    if (!(await inside())) { problems.push(`${where}: ${key} moves focus out of the open dialog`); break; }
    stops.add(await page.evaluate(() => document.activeElement.outerHTML.slice(0, 80)));
  }
  await checkNames(page, testInfo, `${where} dialog`, dialogSelector);
  await shot(page, testInfo, `a11y-${where}`);
  await page.keyboard.press("Escape");
  await expect(dialog, `${where}: Escape closes the dialog`).toBeHidden();
  const returned = await opener.evaluate((el) => el === document.activeElement || el.contains(document.activeElement)).catch(() => false);
  if (!returned) problems.push(`${where}: focus does not return to the button that opened the dialog`);
  expectNoNewProblems("a11y-dialog", problems, testInfo);
}

test.describe("accessibility", { tag: "@seeded" }, () => {
  test("every control has a name and focus is visible", async ({ dash: { page } }, testInfo) => {
    const info = expectInfo();
    await gotoDashboard(page);
    await waitForLibrary(page);
    await checkNames(page, testInfo, "library");
    await checkFocusVisible(page, testInfo, "library");
    await gotoDashboard(page, `#item/${info.search_item_id}`);
    await expect(page.locator("#yoinkHeading")).toHaveText(info.search_item_title, { timeout: 20_000 });
    await checkNames(page, testInfo, "reader");
    await checkFocusVisible(page, testInfo, "reader", 15);
    for (const tab of ["settings", "activity", "sources"]) {
      await gotoDashboard(page, `#${tab}`);
      await expect(page.locator(`#tab-${tab}`)).toBeVisible({ timeout: 20_000 });
      await checkNames(page, testInfo, tab);
    }
  });

  test("dialogs keep focus inside and let Escape out", async ({ dash: { page } }, testInfo) => {
    const info = expectInfo();
    await gotoDashboard(page);
    await waitForLibrary(page);
    // Health drawer (a modal dialog).
    await page.locator("#searchInput").fill(info.no_transcript_title);
    const badge = page.locator(`#libraryGrid .uoink-card[data-card-id="${info.no_transcript_id}"] .health-exception`);
    await expect(badge).toBeVisible();
    await checkDialog(page, testInfo, "health-drawer", badge, "#itemHealthDrawer");
    // Hook explainer.
    await page.locator("#searchInput").fill("");
    await waitForLibrary(page);
    await checkDialog(page, testInfo, "hook-explainer", page.locator(".summary-line .hook-help-link").first(), "#hookExplainer");
    // Stop Uoink confirmation: opened and closed with Escape only, never confirmed.
    await gotoDashboard(page, "#settings/app");
    const stop = page.locator("#stopHelperSettings");
    await expect(stop).toBeVisible({ timeout: 20_000 });
    await checkDialog(page, testInfo, "stop-confirm", stop, "#stopHelperConfirm");
    const health = await fetch(new URL("/health", page.url()).href).then((r) => r.ok);
    expect(health, "the helper is still running after the Stop dialog closed").toBe(true);
  });
});
