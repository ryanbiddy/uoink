// "After a save" setting (3.17.0): what a finished capture does.
//   stay (default) -- no clipboard write, no new tab; the notification says it was
//                     saved and offers Copy for Claude / Copy for ChatGPT
//   claude / chatgpt -- copy, then open that site
//   copy -- copy only
// Both paths run the real scripts: the service worker queue (background.js) and the
// in-page YouTube button (content.js, talking to a real background.js).
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import test from "node:test";
import { EXT, jsonResponse, makeEnv, settle } from "./ext_fake_env.mjs";

const YT_URL = "https://www.youtube.com/watch?v=abc123def45";
const PASTE = "# Some video\n\nTranscript with embedded screenshots.";
const FILE_MD = "# Some video\n\nTranscript.";
const CAPTURE = {
  ok: true, title: "Some video", folder: "C:\\Uoink\\Tech\\some-video", topic: "Tech",
  corpus_md_paste: PASTE, yoink_md: FILE_MD,
};
const POPUP_SENDER = { id: "test-extension-id", url: "chrome-extension://test-extension-id/popup.html" };
const CLAUDE = "https://claude.ai/new";
const CHATGPT = "https://chatgpt.com/";

function pathOf(url) { return new URL(url).pathname; }

// A real background.js. copyOk:false makes the offscreen clipboard write fail.
// helperFetch replaces the fake helper (the parked one below).
async function worker({ store, capture = CAPTURE, copyOk = true, settings = {}, corpus = FILE_MD, helperDown = false, helperFetch } = {}) {
  store = store || { local: {}, sync: {}, session: {} };
  const writes = [];
  const env = makeEnv({
    store,
    fetch: helperFetch || ((url, init) => {
      const path = pathOf(url);
      if (path === "/token") return jsonResponse({ token: "t" });
      if (path === "/health") return jsonResponse({ ok: true });
      if (path === "/queue/status") return jsonResponse({ ok: true, pending_count: 0 });
      if (path === "/settings") {
        if (helperDown) throw new TypeError("Failed to fetch");
        if (init && init.method === "POST") { env.settingsPosted.push(JSON.parse(init.body)); return jsonResponse({ ok: true }); }
        return jsonResponse({ ok: true, settings });
      }
      if (path === "/mcp/v1/tools/call") {
        env.corpusCalls.push(JSON.parse(init.body));
        return jsonResponse({ result: { structuredContent: corpus ? { ok: true, corpus_md: corpus } : { ok: false } } });
      }
      if (path === "/extract" || path === "/extract/page") return jsonResponse(capture);
      return jsonResponse({ ok: true });
    }),
    onSend: (msg) => {
      if (msg && msg.target === "offscreen") {
        if (msg.type === "copy") writes.push(msg.text);
        return { ok: copyOk };
      }
      return undefined;
    },
  });
  env.settingsPosted = [];
  env.corpusCalls = [];
  env.load("background.js");
  await settle();
  return { env, store, writes };
}

async function saveViaQueue(w) {
  const resp = await w.env.dispatch({ type: "popupCapture", job: { route: "video", url: YT_URL, title: "Some video" } }, POPUP_SENDER);
  assert.equal(resp && resp.ok, true, "the popup capture was accepted");
  await settle(200);
}

const CHOICES = {
  stay: { writes: 0, tabs: [] },
  claude: { writes: 1, tabs: [CLAUDE] },
  chatgpt: { writes: 1, tabs: [CHATGPT] },
  copy: { writes: 1, tabs: [] },
};

for (const [choice, want] of Object.entries(CHOICES)) {
  test(`SW queue, After a save = ${choice}: ${want.writes ? "copies" : "does not copy"}, opens ${want.tabs.join(",") || "nothing"}`, async () => {
    const w = await worker({ store: { local: { after_save: choice }, sync: {}, session: {} } });
    await saveViaQueue(w);
    assert.equal(w.writes.length, want.writes);
    if (want.writes) assert.equal(w.writes[0], PASTE, "copies corpus_md_paste");
    assert.deepEqual(w.env.tabsCreated.map((t) => t.url), want.tabs);
    const note = w.env.notifications.at(-1);
    assert.equal(note.title, "Uoinked ★");
    if (choice === "stay") {
      // The very first save offers See it in Claude (the payoff moment).
      assert.deepEqual(note.buttons.map((b) => b.title), ["See it in Claude", "Copy for ChatGPT"]);
      assert.match(note.message, /library/i);
      assert.equal(w.store.local.yoink_last_clipboard_at, undefined, "clipboard untouched, so no stale-clipboard mark");
    } else {
      assert.equal(note.buttons, undefined);
      assert.ok(w.store.local.yoink_last_clipboard_at);
    }
  });
}

test("SW queue: no setting stored means Stay on the page", async () => {
  const w = await worker();
  await saveViaQueue(w);
  assert.equal(w.writes.length, 0);
  assert.equal(w.env.tabsCreated.length, 0);
});

test("SW queue: an unknown stored value falls back to Stay on the page", async () => {
  const w = await worker({ store: { local: { after_save: "evil" }, sync: {}, session: {} } });
  await saveViaQueue(w);
  assert.equal(w.writes.length, 0);
  assert.equal(w.env.tabsCreated.length, 0);
});

test("Stay: Copy for Claude copies the paste text and opens Claude", async () => {
  const w = await worker();
  await saveViaQueue(w);
  const id = `n${w.env.notifications.length}`;
  w.env.clickNotificationButton(id, 0);
  await settle(100);
  assert.deepEqual(w.writes, [FILE_MD], "the text is fetched from the helper at click time");
  assert.deepEqual(JSON.parse(JSON.stringify(w.env.corpusCalls)), [{ name: "get_uoink_corpus", arguments: { slug: "some-video" } }]);
  assert.deepEqual(w.env.tabsCreated.map((t) => t.url), [CLAUDE]);
  assert.ok(w.store.local.yoink_last_clipboard_at);
  assert.ok(w.store.local.yoink_last_clipboard_budget, "the clipboard budget is recorded at copy time");
  // The note is gone once used: a second click copies nothing.
  w.env.clickNotificationButton(id, 0);
  await settle(100);
  assert.equal(w.writes.length, 1);
  assert.deepEqual(w.store.session.after_save_notes || {}, {});
});

test("Stay: Copy for ChatGPT copies the item and opens ChatGPT", async () => {
  const w = await worker();
  await saveViaQueue(w);
  w.env.clickNotificationButton(`n${w.env.notifications.length}`, 1);
  await settle(100);
  assert.deepEqual(w.writes, [FILE_MD]);
  assert.deepEqual(w.env.tabsCreated.map((t) => t.url), [CHATGPT]);
});

test("Stay: if the helper cannot return the item, the click says so and opens nothing", async () => {
  const w = await worker({ corpus: null });
  await saveViaQueue(w);
  w.env.clickNotificationButton(`n${w.env.notifications.length}`, 0);
  await settle(100);
  assert.equal(w.writes.length, 0);
  assert.equal(w.env.tabsCreated.length, 0);
  assert.equal(w.env.notifications.at(-1).title, "Copy failed", "the title passes notify()'s filter");
});

test("Stay: a click still works after the worker restarted (only the slug kept in session storage)", async () => {
  const first = await worker();
  await saveViaQueue(first);
  const id = `n${first.env.notifications.length}`;
  assert.doesNotMatch(JSON.stringify(first.store.session), /Transcript|embedded screenshots/, "no transcript text in storage");
  const second = await worker({ store: first.store });
  second.env.clickNotificationButton(id, 1);
  await settle(100);
  assert.deepEqual(second.writes, [FILE_MD]);
  assert.deepEqual(second.env.tabsCreated.map((t) => t.url), [CHATGPT]);
});

test("Stay: closing the notification drops the text", async () => {
  const w = await worker();
  await saveViaQueue(w);
  const id = `n${w.env.notifications.length}`;
  assert.ok(w.store.session.after_save_notes[id]);
  w.env.closeNotification(id);
  await settle(100);
  assert.deepEqual(w.store.session.after_save_notes, {});
  w.env.clickNotificationButton(id, 0);
  await settle(100);
  assert.equal(w.writes.length, 0);
  assert.equal(w.env.tabsCreated.length, 0);
});

test("Stay: only the newest few saves are kept", async () => {
  const w = await worker();
  for (let i = 0; i < 14; i++) await saveViaQueue(w);
  assert.ok(Object.keys(w.store.session.after_save_notes).length <= 10);
});

test("Stay: a blocked clipboard offers Try again and opens no tab", async () => {
  const w = await worker({ copyOk: false });
  await saveViaQueue(w);
  w.env.clickNotificationButton(`n${w.env.notifications.length}`, 0);
  await settle(100);
  assert.equal(w.env.tabsCreated.length, 0);
  assert.equal(w.env.notifications.at(-1).title, "Clipboard copy blocked");
});

test("first-ever save in Stay mode says how to use the library from an AI, and only once", async () => {
  const w = await worker();
  await saveViaQueue(w);
  assert.match(w.env.notifications.at(-1).message, /ask Claude or ChatGPT about it/i);
  assert.deepEqual(w.env.notifications.at(-1).buttons.map((b) => b.title), ["See it in Claude", "Copy for ChatGPT"], "the first save offers See it in Claude");
  assert.equal(w.store.local.has_completed_first_yoink, true);
  await saveViaQueue(w);
  assert.doesNotMatch(w.env.notifications.at(-1).message, /Once Uoink is connected/);
  assert.deepEqual(w.env.notifications.at(-1).buttons.map((b) => b.title), ["Copy for Claude", "Copy for ChatGPT"]);
});

test("copy choices keep the first-save clipboard wording", async () => {
  const w = await worker({ store: { local: { after_save: "claude" }, sync: {}, session: {} } });
  await saveViaQueue(w);
  assert.match(w.env.notifications.at(-1).message, /^Copied to your clipboard\./);
  assert.doesNotMatch(w.env.notifications.at(-1).message, /first corpus/i);
});

// ---- the setting lives in the helper's /settings, chrome.storage is a cache -------
test("the helper's after_save wins over an empty cache and refreshes it", async () => {
  const w = await worker({ settings: { after_save: "claude" } });
  await saveViaQueue(w);
  assert.equal(w.writes.length, 1);
  assert.deepEqual(w.env.tabsCreated.map((t) => t.url), [CLAUDE]);
  assert.equal(w.store.local.after_save, "claude");
});

test("the dashboard's choice replaces a stale cache", async () => {
  const w = await worker({ store: { local: { after_save: "claude" }, sync: {}, session: {} }, settings: { after_save: "stay" } });
  await saveViaQueue(w);
  assert.equal(w.writes.length, 0);
  assert.equal(w.store.local.after_save, "stay");
});

test("helper unreachable: the cached choice is used", async () => {
  const w = await worker({ store: { local: { after_save: "copy" }, sync: {}, session: {} }, helperDown: true });
  assert.equal(await w.env.ctx.STC.getAfterSave(), "copy");
});

test("setAfterSave writes the helper and the cache; offline it marks the change to push later", async () => {
  const w = await worker();
  const STC = w.env.ctx.STC;
  assert.deepEqual(JSON.parse(JSON.stringify(await STC.setAfterSave("chatgpt"))), { value: "chatgpt", synced: true });
  assert.deepEqual(w.env.settingsPosted, [{ after_save: "chatgpt" }]);
  assert.equal(w.store.local.after_save, "chatgpt");
  assert.equal(w.store.local.after_save_dirty, false);
  const off = await worker({ helperDown: true });
  assert.deepEqual(JSON.parse(JSON.stringify(await off.env.ctx.STC.setAfterSave("copy"))), { value: "copy", synced: false });
  assert.equal(off.store.local.after_save_dirty, true);
  assert.equal((await off.env.ctx.STC.setAfterSave("bogus")).value, "stay");
});

// ---- two quick picks: the last one wins -------------------------------------------
// A helper whose /settings requests wait until the test answers them, so the
// requests of two quick picks can come back in either order. A POST answered ok
// lands on the helper at that moment (answer order is the order the helper took
// them in); a failed one never reaches it. auto=true answers at once.
function parkedHelper(initial) {
  const h = { value: initial, parked: [], auto: false };
  h.fetch = (url, init) => {
    const path = pathOf(url);
    if (path === "/token") return jsonResponse({ token: "t" });
    if (path === "/queue/status") return jsonResponse({ ok: true, pending_count: 0 });
    if (path === "/extract" || path === "/extract/page") return jsonResponse(CAPTURE);
    if (path !== "/settings") return jsonResponse({ ok: true });
    const post = !!(init && init.method === "POST");
    const sent = post ? JSON.parse(init.body).after_save : "read";
    return new Promise((resolve, reject) => {
      const req = {
        sent,
        ok() {
          if (post) h.value = sent;
          resolve(jsonResponse(post ? { ok: true } : { ok: true, settings: { after_save: h.value } }));
        },
        fail() { reject(new TypeError("Failed to fetch")); },
      };
      if (h.auto) req.ok(); else h.parked.push(req);
    });
  };
  // Answer ("ok" or "fail") the parked request that sent `sent` ("read" for a GET).
  h.answer = async (sent, how) => {
    await settle();
    const i = h.parked.findIndex((r) => r.sent === sent);
    assert.ok(i >= 0, `a parked /settings request for ${sent} (parked: ${h.parked.map((r) => r.sent).join(",") || "none"})`);
    h.parked.splice(i, 1)[0][how]();
    await settle();
  };
  return h;
}

// Claude, then Stay right after. Each case answers the two requests in another
// order. Whatever happens, Stay is what a capture does and what the helper ends
// up with: a late answer to the Claude pick never clears Stay's dirty mark.
const TWO_PICKS = [
  { name: "Stay fails, then Claude succeeds late", answers: [["stay", "fail"], ["claude", "ok"]], dirty: true },
  { name: "Claude succeeds, then Stay fails", answers: [["claude", "ok"], ["stay", "fail"]], dirty: true },
  { name: "Stay succeeds, then Claude succeeds late (the helper took Claude last)", answers: [["stay", "ok"], ["claude", "ok"]], dirty: true },
  { name: "Claude succeeds, then Stay succeeds", answers: [["claude", "ok"], ["stay", "ok"]], dirty: false },
  { name: "Stay succeeds, then Claude fails late", answers: [["stay", "ok"], ["claude", "fail"]], dirty: false },
];
for (const c of TWO_PICKS) {
  test(`Claude then Stay, ${c.name}: Stay wins`, async () => {
    const helper = parkedHelper("stay");
    const w = await worker({ helperFetch: helper.fetch });
    const STC = w.env.ctx.STC;
    const first = STC.setAfterSave("claude");
    await settle();
    const second = STC.setAfterSave("stay");
    for (const [sent, how] of c.answers) await helper.answer(sent, how);
    await first;
    assert.equal((await second).value, "stay");
    assert.equal(w.store.local.after_save, "stay");
    assert.equal(w.store.local.after_save_dirty, c.dirty, "dirty while the helper may not hold Stay");
    // The next read pushes a dirty Stay and never takes the helper's Claude over it.
    const read = STC.getAfterSave();
    await helper.answer(c.dirty ? "stay" : "read", "ok");
    assert.equal(await read, "stay");
    assert.equal(helper.value, "stay");
    assert.equal(w.store.local.after_save, "stay");
    assert.equal(w.store.local.after_save_dirty, false);
    // A capture now copies nothing and opens no tab.
    helper.auto = true;
    await saveViaQueue(w);
    assert.equal(w.writes.length, 0, "no clipboard write");
    assert.deepEqual(w.env.tabsCreated.map((t) => t.url), [], "no new tab");
  });
}

// A capture starts reading the setting (the cache says Copy, the dashboard has
// since set Claude), and the user picks Stay in the popup before that read
// answers. Stay's request fails. The read's late Claude must not replace Stay.
for (const where of ["the popup's own context", "the worker, with the popup as another context"]) {
  for (const order of [["read", "stay"], ["stay", "read"]]) {
    test(`a helper read answered after a new pick keeps the pick (${where}, ${order.join(" then ")} answered)`, async () => {
      const helper = parkedHelper("claude");
      const store = { local: { after_save: "copy" }, sync: {}, session: {} };
      const w = await worker({ store, helperFetch: helper.fetch });
      let popupSTC = w.env.ctx.STC;
      if (where.startsWith("the worker")) {
        const popup = makeEnv({ store, fetch: helper.fetch });
        popup.load("lib/extract.js");
        popupSTC = popup.ctx.STC;
      }
      const read = w.env.ctx.STC.getAfterSave();
      await settle();
      const pick = popupSTC.setAfterSave("stay");
      for (const sent of order) await helper.answer(sent, sent === "read" ? "ok" : "fail");
      assert.equal(await read, "stay", "the newer local pick is what the read returns");
      assert.deepEqual(JSON.parse(JSON.stringify(await pick)), { value: "stay", synced: false });
      assert.equal(store.local.after_save, "stay");
      assert.equal(store.local.after_save_dirty, true);
      const next = w.env.ctx.STC.getAfterSave();
      await helper.answer("stay", "ok");
      assert.equal(await next, "stay");
      assert.equal(helper.value, "stay");
      assert.equal(store.local.after_save_dirty, false);
    });
  }
}

// ---- the popup's menu ---------------------------------------------------------------
// popup.js's real initAfterSave, in a popup context with the menu and hint elements.
const POPUP_SRC = readFileSync(join(EXT, "popup.js"), "utf8");
function popupAfterSaveSlice() {
  const start = POPUP_SRC.indexOf("const AFTER_SAVE_HINTS");
  const end = POPUP_SRC.indexOf("\ninitAfterSave();", start);
  assert.ok(start >= 0 && end > start, "popup.js After a save slice found");
  return POPUP_SRC.slice(start, end);
}
function popupMenu(helper) {
  const popup = makeEnv({ fetch: helper.fetch });
  popup.load("lib/extract.js");
  const select = popup.document.createElement("select");
  select.id = "after-save-select";
  const hint = popup.document.createElement("p");
  hint.id = "after-save-hint";
  popup.document.body.appendChild(select);
  popup.document.body.appendChild(hint);
  popup.ctx.element = (tag, className, text) => {
    const el = popup.document.createElement(tag);
    el.className = className;
    if (text !== undefined) el.textContent = text;
    return el;
  };
  popup.runSource(popupAfterSaveSlice(), "popup.js");
  const ready = popup.runSource("initAfterSave()", "probe.js");
  const pick = (value) => { select.value = value; select.dispatchEvent({ type: "change" }); };
  return { popup, select, hint, ready, pick };
}

for (const order of [["stay", "claude"], ["claude", "stay"]]) {
  test(`popup: Claude then Stay, ${order.join(" then ")} answered: the menu never goes back to Claude`, async () => {
    const helper = parkedHelper("copy");
    const m = popupMenu(helper);
    await helper.answer("read", "ok");
    await m.ready;
    assert.equal(m.select.value, "copy");
    assert.equal(m.select.children.length, 4);
    m.pick("claude");
    await settle();
    m.pick("stay");
    // Stay's request fails and Claude's succeeds, in either order.
    for (const sent of order) {
      await helper.answer(sent, sent === "stay" ? "fail" : "ok");
      assert.equal(m.select.value, "stay", `after the ${sent} answer`);
    }
    assert.match(m.hint.textContent, /^Saves to your library only\./);
    assert.match(m.hint.textContent, /Saved in this browser\./, "Stay did not reach the helper");
    assert.equal(m.popup.store.local.after_save, "stay");
    assert.equal(m.popup.store.local.after_save_dirty, true);
  });
}

test("popup: a pick made while the menu is still loading is saved and kept", async () => {
  const helper = parkedHelper("claude");
  const m = popupMenu(helper);
  await settle();
  m.pick("copy");
  await helper.answer("read", "ok");
  await m.ready;
  assert.equal(m.select.value, "copy", "the late load does not replace the pick");
  await helper.answer("copy", "ok");
  assert.equal(m.select.value, "copy");
  assert.equal(m.hint.textContent, "Copies the capture to your clipboard and stays where you are.");
  assert.equal(helper.value, "copy");
  assert.equal(m.popup.store.local.after_save_dirty, false);
});

test("popup: the menu shows the helper's choice when nothing was picked", async () => {
  const helper = parkedHelper("chatgpt");
  const m = popupMenu(helper);
  await helper.answer("read", "ok");
  await m.ready;
  assert.equal(m.select.value, "chatgpt");
  assert.equal(m.hint.textContent, "Copies the capture to your clipboard, then opens ChatGPT.");
});

// ---- the right-click X Article fallback path ----------------------------------------
const X_ARTICLE = "https://x.com/jack/article/1900000000001";
for (const [choice, want] of Object.entries(CHOICES)) {
  test(`X article fallback, After a save = ${choice}`, async () => {
    const w = await worker({ store: { local: { after_save: choice }, sync: {}, session: {} } });
    await w.env.clickContextMenu({ menuItemId: "stc-extract-article-page", pageUrl: X_ARTICLE }, { id: 3, url: X_ARTICLE });
    await settle(200);
    assert.equal(w.writes.length, want.writes);
    assert.deepEqual(w.env.tabsCreated.map((t) => t.url).filter((u) => /claude|chatgpt/.test(u)), want.tabs);
  });
}

// ---- the in-page YouTube button -------------------------------------------------
async function inPage(choice, { firstDone = false } = {}) {
  const bg = await worker(firstDone ? { store: { local: { has_completed_first_yoink: true }, sync: {}, session: {} } } : {});
  const env = makeEnv({
    href: YT_URL,
    onSend: (msg) => {
      if (msg.type === "stcPing") return { ok: true };
      if (msg.type === "stcExtract") return { data: { ...CAPTURE, video_count: 1 } };
      return bg.env.dispatch(msg);
    },
    fetch: (url) => {
      const path = pathOf(url);
      if (path === "/token") return jsonResponse({ token: "t" });
      if (path === "/settings") return jsonResponse({ ok: true, settings: {} });
      throw new Error(`Unexpected fetch ${path}`);
    },
  });
  if (choice) env.store.local.after_save = choice;
  if (firstDone) env.store.local.has_completed_first_yoink = true;
  // Same storage for the background: the setting is read from chrome.storage.local.
  Object.assign(bg.store.local, env.store.local);
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
  assert.ok(btn, "the real button was injected");
  btn.userClick();
  await settle(200);
  return { env, bg, btn };
}

for (const [choice, want] of Object.entries(CHOICES)) {
  test(`in-page button, After a save = ${choice}`, async () => {
    const { env, bg, btn } = await inPage(choice);
    assert.equal(bg.writes.length, want.writes, "clipboard writes");
    assert.deepEqual(env.sent.filter((m) => m.type === "openTab").map((m) => m.url), want.tabs, "tabs requested");
    assert.deepEqual(bg.env.tabsCreated.map((t) => t.url), want.tabs, "tabs created");
    assert.match(btn.textContent, choice === "stay" ? /Saved. See it in Claude/ : /Uoinked/);
    if (choice === "stay") {
      assert.equal(env.sent.filter((m) => m.type === "copyToClipboard").length, 0);
      const note = bg.env.notifications.at(-1);
      assert.deepEqual(note.buttons.map((b) => b.title), ["See it in Claude", "Copy for ChatGPT"]);
    }
  });
}

test("in-page button default is Stay on the page, and the buttons copy then open", async () => {
  const { env, bg } = await inPage(undefined);
  assert.equal(bg.writes.length, 0);
  assert.equal(bg.env.tabsCreated.length, 0);
  assert.equal(env.sent.filter((m) => m.type === "copyToClipboard" || m.type === "openTab").length, 0);
  bg.env.clickNotificationButton(`n${bg.env.notifications.length}`, 0);
  await settle(100);
  assert.deepEqual(bg.writes, [FILE_MD], "the notification button refetches the item");
  assert.deepEqual(bg.env.tabsCreated.map((t) => t.url), [CLAUDE]);
});

test("in-page button turns into Saved. See it in Claude, then Copy for Claude; clicking copies and opens", async () => {
  const { env, bg, btn } = await inPage(undefined);
  assert.match(btn.textContent, /Saved. See it in Claude/, "first save");
  assert.equal(bg.writes.length, 0);
  btn.userClick();
  await settle(100);
  assert.deepEqual(bg.writes, [PASTE], "the in-page copy uses the paste text it already has");
  assert.deepEqual(env.sent.filter((m) => m.type === "openTab").map((m) => m.url), [CLAUDE]);
  assert.deepEqual(bg.env.tabsCreated.map((t) => t.url), [CLAUDE]);
  assert.match(btn.textContent, /Copied. Paste in Claude/);
  // A second click does not copy again.
  assert.equal(bg.writes.length, 1);
});

test("in-page button: after the first save the label is Saved. Copy for Claude, and it expires", async () => {
  const { env, bg, btn } = await inPage(undefined, { firstDone: true });
  assert.match(btn.textContent, /Saved. Copy for Claude/);
  const buttons = bg.env.notifications.at(-1).buttons.map((b) => b.title);
  assert.deepEqual(buttons, ["Copy for Claude", "Copy for ChatGPT"]);
  env.runTimeouts();
  assert.doesNotMatch(btn.textContent, /Saved./, "back to the normal label after the window");
  btn.userClick();
  await settle(100);
  assert.equal(bg.writes.length, 0, "an expired button does not copy");
});

test("afterSaveNotice from a web page context is not an extension-page-only message but never copies by itself", async () => {
  const w = await worker();
  const resp = await w.env.dispatch({ type: "afterSaveNotice", text: "x", topic: "T" }, { id: "test-extension-id", url: YT_URL, tab: { id: 1 } });
  assert.equal(resp.ok, true);
  assert.equal(w.writes.length, 0);
  assert.equal(w.env.tabsCreated.length, 0);
});
