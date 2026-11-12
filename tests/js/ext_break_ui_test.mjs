// Regression tests for the 2026-11-12 extension break-ui pass (rel-run/after-save/REPORT.md).
import assert from "node:assert/strict";
import test from "node:test";
import { jsonResponse, makeEnv, settle } from "./ext_fake_env.mjs";

const YT = "https://www.youtube.com/watch?v=abc123def45";
const SESSION = "Research session about creator economy tools and local-first software for 2027 planning notes";

async function button({ width, store = {} } = {}) {
  const env = makeEnv({
    href: YT,
    onSend: (msg) => {
      if (msg.type === "stcPing") return { ok: true };
      if (msg.type === "stcExtract") return { data: { ok: true, folder: "C:\\Uoink\\Tech\\v", topic: "Tech", corpus_md_paste: "# T", yoink_md: "# T" } };
      return { ok: true };
    },
    fetch: (url) => {
      const path = new URL(url).pathname;
      if (path === "/token") return jsonResponse({ token: "t" });
      if (path === "/settings") return jsonResponse({ ok: true, settings: {} });
      throw new Error(`Unexpected fetch ${path}`);
    },
  });
  if (width) env.ctx.innerWidth = width;
  Object.assign(env.store.local, store);
  const anchor = env.document.createElement("div");
  env.document.body.appendChild(anchor);
  env.document._selectors["#top-level-buttons-computed"] = anchor;
  env.load("lib/extract.js");
  env.load("lib/ui.js");
  env.load("content.js");
  await settle();
  env.runIntervals();
  await settle();
  const btn = env.document.getElementById("stc-yt-send-to-claude");
  assert.ok(btn);
  return { env, btn };
}

test("a long active session name is clipped by CSS and kept in full in the tooltip", async () => {
  const { env, btn } = await button({ store: { active_session: { id: "s1", name: SESSION } } });
  assert.match(btn.textContent, /Add to session: Research session/);
  assert.equal(btn.title, `Add to session: ${SESSION}`);
  const label = btn.childNodes.at(-1);
  assert.equal(label.className, "stc-yt-label");
  const css = env.document.getElementById("stc-yt-styles").textContent;
  assert.match(css, /\.stc-yt-label\s*\{[^}]*max-width:\s*min\(260px[^}]*text-overflow:\s*ellipsis/);
});

test("the short default label has no tooltip", async () => {
  const { btn } = await button();
  assert.equal(btn.title, "");
});

for (const [width, first, expected] of [
  [1280, true, /Saved\. See it in Claude/], [1280, false, /Saved\. Copy for Claude/],
  [400, true, /^\s*See it in Claude/], [400, false, /^\s*Copy for Claude/],
]) {
  test(`after-save button label at ${width}px, first save ${first}`, async () => {
    const { env, btn } = await button({ width, store: first ? {} : { has_completed_first_yoink: true } });
    btn.userClick();
    await settle(200);
    assert.match(btn.textContent, expected);
    assert.doesNotMatch(btn.textContent, width < 520 ? /Saved\./ : /^$/);
    assert.equal(env.tabsCreated.length, 0);
  });
}

test("stay-mode notification text: no 'below', short topic, names the popup", async () => {
  const env = makeEnv();
  env.load("lib/extract.js");
  const STC = env.ctx.STC;
  const long = await STC.buildUoinkedMessage({ topic: "A topic with a really long name that goes on and on and on and on" }, false, "stay");
  env.store.local.has_completed_first_yoink = true;
  const later = await STC.buildUoinkedMessage({ topic: "A topic with a really long name that goes on and on and on and on" }, false, "stay");
  assert.ok(later.length < 170, later);
  assert.match(later, /…/);
  assert.match(later, /Uoink popup/);
  assert.doesNotMatch(later, /below/);
  assert.match(long, /ask Claude or ChatGPT about it/i, "first save keeps the library hint");
  const plain = await STC.buildUoinkedMessage({ topic: "Uncategorized" }, false, "stay");
  assert.match(plain, /^Saved to your library\. /);
});

test("a raw script error in a failed row becomes a plain sentence", async () => {
  const env = makeEnv();
  env.load("lib/extract.js");
  env.load("lib/popup-captures.js");
  const { safeError } = env.ctx.PopupCaptures;
  assert.equal(safeError({ error: "TypeError: Cannot read properties of undefined (reading 'title')" }), "Something went wrong inside Uoink. Try again.");
  assert.equal(safeError({ error: "Uncaught ReferenceError: x is not defined" }), "Something went wrong inside Uoink. Try again.");
  assert.match(safeError({ error_detail: "ERROR: [youtube] abc: This video requires a GVS PO Token" }), /PO Token/);
  assert.equal(safeError({}), "The capture failed. Try again.");
});
