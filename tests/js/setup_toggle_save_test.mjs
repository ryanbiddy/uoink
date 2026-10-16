// Setup-page regression harness: the Hook Type and Smart Screenshot Picker
// controls save where they are changed.
//
// Before the fix those controls (and the clipboard screenshot count) were only
// sent by the Comment Intelligence section's "Save settings" button, so a
// change made in their own sections was silently lost on leaving the page.
//
// Drives the REAL extension scripts in a fake browser (ext_fake_env.mjs):
// lib/extract.js, lib/ui.js and setup.js load as setup.html loads them, over a
// DOM holding every id setup.html declares. A stubbed helper answers /health
// and /settings, so the page boots to "helper running" and renders the saved
// settings; the test then changes controls the way a user does. Like the real
// helper, the stub keeps only the settings fields server.py knows and still
// answers ok to the rest.
//   hook_type   -- toggling Hook Type posts just {hook_type_enabled} (authed,
//                  never the API key) and shows "Saved" in its own section
//   screenshot  -- the picker toggle and the screenshot count save on change,
//                  each with its own status line; the count is clamped to
//                  what is actually saved
//   failure     -- a helper error or an unreachable helper shows "Save failed"
//                  and puts the control back to the helper's value; a stale
//                  failure never undoes a newer change; an ok answer that does
//                  not carry the change shows "Not saved", not "Saved"
//   overlap     -- saves made while an earlier one is unanswered: the helper
//                  gets them in the order they were made, whichever answer
//                  comes back first, so what the page shows (and calls Saved)
//                  is what the helper keeps; a slow Comment Intelligence save
//                  never resets a control changed after it; the picker and the
//                  count never report each other's result
//   ci_save     -- the Comment Intelligence "Save settings" button still saves
//                  its toggle and the typed key, and leaves Hook Type, the
//                  picker and the count to their own saves
//   section_status -- Claim verification and the Obsidian vault path (saved with
//                  the rest of their sections) show Saving..., then Saved or
//                  Save failed in their own section; mirroring and evidence
//                  sources, which the helper drops, show "Not saved" naming the
//                  setting; a section whose save failed reads Saved once a
//                  later save from another section stores its change; one
//                  section never reports another save's result for a value
//                  already stored, and an older stored save never calls a
//                  newer change Saved
//   read_timeout -- a settings read on load that the helper never answers is
//                  given up on, so saves queued behind it still go out, and its
//                  late answer does not reset what was changed since
//
// No network: fetch is a stub inside the vm context.
// Run directly:  node tests/js/setup_toggle_save_test.mjs [group ...]
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { EXT, jsonResponse, makeEnv, settle } from "./ext_fake_env.mjs";

let failures = 0;
let checks = 0;
function check(cond, msg, got) {
  checks++;
  if (cond) { console.log(`ok: ${msg}`); return; }
  failures++;
  console.error(`FAIL: ${msg}${got === undefined ? "" : ` -- got ${JSON.stringify(got)}`}`);
}
async function scenario(name, fn) {
  try {
    await fn();
  } catch (e) {
    failures++;
    console.error(`FAIL: ${name} threw: ${(e && e.stack) || e}`);
  }
}
process.on("unhandledRejection", (e) => {
  failures++;
  console.error(`FAIL: unhandled rejection: ${(e && e.stack) || e}`);
});

const SETUP_HTML = readFileSync(join(EXT, "setup.html"), "utf8");
const TOKEN = "test-token";
const BASE_SETTINGS = {
  comment_intelligence_enabled: false,
  hook_type_enabled: false,
  smart_screenshot_picker_enabled: false,
  clipboard_screenshot_cap: 4,
  anthropic_key_set: true,
};
const NOT_SUPPORTED = "Not saved: Uoink helper does not support this setting";

function deferred() {
  let resolve;
  const promise = new Promise((r) => { resolve = r; });
  return { promise, resolve };
}

// Every element setup.html gives an id, with the attributes setup.js reads
// (type, value, checked, class). setup.js only reaches the page through
// getElementById, so a flat body is enough.
function buildSetupDom(env) {
  const proto = Object.getPrototypeOf(env.document.body);
  Object.assign(proto, {
    setAttribute(name, value) { (this._attrs ||= {})[name] = String(value); },
    getAttribute(name) {
      return this._attrs && name in this._attrs ? this._attrs[name] : null;
    },
    removeAttribute(name) { if (this._attrs) delete this._attrs[name]; },
    scrollIntoView() {},
    focus() {},
  });
  const tagRe = /<([a-zA-Z][a-zA-Z0-9]*)\b([^>]*)>/g;
  const attrRe = /([a-zA-Z_:][-a-zA-Z0-9_:.]*)(?:\s*=\s*"([^"]*)")?/g;
  let m;
  while ((m = tagRe.exec(SETUP_HTML)) !== null) {
    const attrs = {};
    let a;
    attrRe.lastIndex = 0;
    while ((a = attrRe.exec(m[2])) !== null) attrs[a[1].toLowerCase()] = a[2] === undefined ? "" : a[2];
    if (!attrs.id) continue;
    const el = env.document.createElement(m[1]);
    el.id = attrs.id;
    if (attrs.class) el.className = attrs.class;
    if (attrs.type) el.type = attrs.type;
    if (/^(input|select|textarea)$/i.test(m[1])) {
      el.value = attrs.value || "";
      el.checked = "checked" in attrs;
    }
    env.document.body.appendChild(el);
  }
}

// A user changing a control: the DOM value moves first, then the page hears
// the event.
function fire(el, type) {
  const ev = { type, target: el, preventDefault() {}, stopPropagation() {} };
  for (const fn of el._listeners[type] || []) fn(ev);
}

// The fields of those this page sends that the real helper keeps
// (server.py _handle_settings_post) and sends back (_public_settings). It
// drops every other field (your_channels, the Creator tools defaults,
// mirroring, evidence sources) and still answers ok.
const KEPT_FIELDS = [
  "comment_intelligence_enabled",
  "hook_type_enabled",
  "smart_screenshot_picker_enabled",
  "clipboard_screenshot_cap",
  "claim_verification_enabled",
  "obsidian_vault_path",
];

function publicSettings(server) {
  const s = server.settings;
  return {
    comment_intelligence_enabled: !!s.comment_intelligence_enabled,
    hook_type_enabled: !!s.hook_type_enabled,
    smart_screenshot_picker_enabled: !!s.smart_screenshot_picker_enabled,
    clipboard_screenshot_cap: s.clipboard_screenshot_cap,
    claim_verification_enabled: !!s.claim_verification_enabled,
    anthropic_key_set: !!s.anthropic_key_set,
    obsidian_vault_path: s.obsidian_vault_path || null,
  };
}

// onPost(body, server) -> Response (or a promise of one) for POST /settings.
// Default: the helper keeps the fields it knows, resolving the vault path the
// way Path.resolve() does (no trailing separator), and echoes the public
// settings.
function storeAndEcho(body, server) {
  if ("anthropic_key" in body) server.settings.anthropic_key_set = !!body.anthropic_key;
  for (const f of KEPT_FIELDS) {
    if (!(f in body)) continue;
    server.settings[f] = f === "obsidian_vault_path"
      ? String(body[f] || "").replace(/[\\/]+$/, "")
      : body[f];
  }
  return jsonResponse({ ok: true, settings: publicSettings(server) });
}

function readSettings(server) {
  return jsonResponse({ ok: true, settings: publicSettings(server) });
}

// A slow helper: each POST /settings waits until the test answers it, and the
// body is applied only when it is answered. With onGet as well, a GET
// /settings reads the settings when it arrives and its answer waits too
// (body null). held lists the unanswered requests, oldest first.
function slowHelper() {
  const held = [];
  const onPost = (body, server) => new Promise((resolve) => {
    held.push({
      body,
      ok: () => resolve(storeAndEcho(body, server)),
      fail: (error) => resolve(jsonResponse({ ok: false, error })),
    });
  });
  const onGet = (server) => {
    const answer = readSettings(server);
    return new Promise((resolve) => {
      held.push({ body: null, ok: () => resolve(answer) });
    });
  };
  return { held, onPost, onGet };
}

// Answer held requests until none is left: the newest one first whenever more
// than one is waiting (newestFirst), else the oldest. failWith(body) -> an
// error string to refuse that POST, or null to apply it.
async function answerAll(helper, { newestFirst, failWith = () => null }) {
  for (let i = 0; helper.held.length && i < 20; i++) {
    const req = newestFirst ? helper.held.pop() : helper.held.shift();
    const error = req.body ? failWith(req.body) : null;
    if (error) req.fail(error); else req.ok();
    await settle();
  }
}

function orderName(newestFirst) {
  return newestFirst ? "newest answered first" : "oldest answered first";
}

// Answer just the oldest held request (refusing it when error is given).
async function answerOldest(helper, error = null) {
  const req = helper.held.shift();
  if (!req) return;
  if (error) req.fail(error); else req.ok();
  await settle();
}

// Time passes: every timer the page has pending fires once. Returns the
// delays they asked for.
function fireTimeouts(env) {
  const due = [...env.timeouts];
  for (const [id, fn] of due) {
    env.timeouts.delete(id);
    fn();
  }
  return due.map(([id]) => env.timeoutDelays.get(id));
}

// local: chrome.storage.local entries this device already holds when the page
// opens (e.g. uoink_settings_pending from an earlier failed save).
// beforeLoad(env): runs just before the page's scripts load (e.g. to make a
// storage answer late).
async function setupEnv({
  settings = {}, onPost = storeAndEcho, onGet = readSettings, local = {},
  beforeLoad = () => {},
} = {}) {
  const server = { settings: { ...BASE_SETTINGS, ...settings } };
  const env = makeEnv({
    fetch: (url, init = {}) => {
      const path = new URL(url).pathname;
      if (path === "/health") return jsonResponse({ ok: true });
      if (path === "/token") return jsonResponse({ token: TOKEN });
      if (path === "/settings") {
        if ((init.method || "GET") === "GET") return onGet(server);
        const body = JSON.parse(init.body);
        env.posts.push({ body, token: (init.headers || {})["X-Yoink-Token"] });
        return onPost(body, server);
      }
      return jsonResponse({ ok: false, error: "not found" }, 404);
    },
  });
  env.posts = [];
  env.server = server;
  // The fake timers never fire on their own; keep the delay each one asked for.
  env.timeoutDelays = new Map();
  const baseSetTimeout = env.ctx.setTimeout;
  env.ctx.setTimeout = (fn, ms) => {
    const id = baseSetTimeout(fn, ms);
    env.timeoutDelays.set(id, Number(ms) || 0);
    return id;
  };
  env.store.local.yoink_token = TOKEN;
  Object.assign(env.store.local, JSON.parse(JSON.stringify(local)));
  buildSetupDom(env);
  env.document.getElementsByName = () => [];
  env.ctx.location = {
    href: "chrome-extension://test-extension-id/setup.html?source=popup",
    search: "?source=popup",
    hash: "",
  };
  env.ctx.requestAnimationFrame = () => 0;
  env.el = (id) => env.document.getElementById(id);
  beforeLoad(env);
  env.load("lib/extract.js");
  env.load("lib/ui.js");
  env.load("setup.js");
  await settle();
  env.el = (id) => env.document.getElementById(id);
  return env;
}

function checkBooted(env, id, checked) {
  const el = env.el(id);
  check(el && el.disabled === false, `boot: #${id} is enabled once the helper answers`,
    el && el.disabled);
  check(el && el.checked === checked, `boot: #${id} shows the saved value`, el && el.checked);
  check(env.posts.length === 0, "boot: loading the page saves nothing", env.posts);
}

function checkStatus(env, id, text, mode, where) {
  const el = env.el(id);
  check(!!el, `${where}: #${id} status line exists`);
  if (!el) return;
  const want = typeof text === "string" ? (t) => t === text : (t) => text.test(t);
  check(want(el.textContent), `${where}: #${id} reads ${text}`, el.textContent);
  check(el.classList.contains(mode), `${where}: #${id} is styled ${mode}`, el.className);
  const other = mode === "ok" ? "warn" : "ok";
  check(!el.classList.contains(other), `${where}: #${id} is not styled ${other}`, el.className);
}

function checkSaving(env, id, where) {
  const el = env.el(id);
  check(!!el && el.textContent === "Saving...", `${where}: #${id} reads Saving...`,
    el && el.textContent);
  check(!!el && !el.classList.contains("ok") && !el.classList.contains("warn"),
    `${where}: #${id} is styled neither ok nor warn while saving`, el && el.className);
}

// The status line is placed inside the section whose control it reports on.
function checkStatusInSection(statusId, sectionId) {
  const start = SETUP_HTML.indexOf(`<section id="${sectionId}"`);
  const end = SETUP_HTML.indexOf("</section>", start);
  const at = SETUP_HTML.indexOf(`id="${statusId}"`);
  check(start >= 0 && at > start && at < end,
    `setup.html: #${statusId} sits inside #${sectionId}`, { start, at, end });
}

async function hook_type() {
  await scenario("Hook Type saves on change", async () => {
    checkStatusInSection("hook-type-status", "hook-type-settings");
    const env = await setupEnv();
    checkBooted(env, "hook-type-enabled", false);

    // An API key typed but not saved must not ride along with a toggle save.
    const key = env.el("anthropic-key");
    key.value = "sk-ant-typed-not-saved";
    fire(key, "input");

    const toggle = env.el("hook-type-enabled");
    toggle.checked = true;
    fire(toggle, "change");
    await settle();

    check(env.posts.length === 1, "on: one POST /settings without pressing any Save button",
      env.posts.length);
    const post = env.posts[0] || {};
    check(JSON.stringify(post.body) === JSON.stringify({ hook_type_enabled: true }),
      "on: the request carries just hook_type_enabled: true", post.body);
    check(post.token === TOKEN, "on: the request carries the extension token", post.token);
    check(env.server.settings.hook_type_enabled === true, "on: the helper stored Hook Type on");
    check(toggle.checked === true, "on: the toggle stays on", toggle.checked);
    checkStatus(env, "hook-type-status", "Saved", "ok", "on");
    check(key.value === "sk-ant-typed-not-saved" && key.dataset.dirty === "true",
      "on: the unsaved API key field is left as typed", { value: key.value, dirty: key.dataset.dirty });

    toggle.checked = false;
    fire(toggle, "change");
    await settle();
    check(env.posts.length === 2, "off: a second POST /settings", env.posts.length);
    check(JSON.stringify((env.posts[1] || {}).body) === JSON.stringify({ hook_type_enabled: false }),
      "off: the request carries just hook_type_enabled: false", (env.posts[1] || {}).body);
    check(env.server.settings.hook_type_enabled === false, "off: the helper stored Hook Type off");
    checkStatus(env, "hook-type-status", "Saved", "ok", "off");
  });
}

async function screenshot() {
  await scenario("Smart Screenshot Picker and screenshot count save on change", async () => {
    checkStatusInSection("smart-screenshot-picker-status", "smart-screenshot-settings");
    checkStatusInSection("clipboard-screenshot-cap-status", "smart-screenshot-settings");
    const env = await setupEnv();
    checkBooted(env, "smart-screenshot-picker-enabled", false);

    const picker = env.el("smart-screenshot-picker-enabled");
    picker.checked = true;
    fire(picker, "change");
    await settle();
    check(env.posts.length === 1, "picker: one POST /settings", env.posts.length);
    check(JSON.stringify((env.posts[0] || {}).body)
      === JSON.stringify({ smart_screenshot_picker_enabled: true }),
    "picker: the request carries just smart_screenshot_picker_enabled: true",
    (env.posts[0] || {}).body);
    check(env.server.settings.smart_screenshot_picker_enabled === true,
      "picker: the helper stored the picker on");
    checkStatus(env, "smart-screenshot-picker-status", "Saved", "ok", "picker");
    check(env.el("clipboard-screenshot-cap-status").textContent === "",
      "picker: the count's status line is left alone",
      env.el("clipboard-screenshot-cap-status").textContent);

    const cap = env.el("clipboard-screenshot-cap");
    check(cap.value === "4", "cap: boots showing the saved count", cap.value);
    cap.value = "7";
    fire(cap, "change");
    await settle();
    check(env.posts.length === 2, "cap: a POST /settings for the count", env.posts.length);
    check(JSON.stringify((env.posts[1] || {}).body) === JSON.stringify({ clipboard_screenshot_cap: 7 }),
      "cap: the count is sent as the integer 7", (env.posts[1] || {}).body);
    check(env.server.settings.clipboard_screenshot_cap === 7, "cap: the helper stored 7");
    checkStatus(env, "clipboard-screenshot-cap-status", "Saved", "ok", "cap");

    cap.value = "40";
    fire(cap, "change");
    await settle();
    check(JSON.stringify((env.posts[2] || {}).body) === JSON.stringify({ clipboard_screenshot_cap: 12 }),
      "cap: an out-of-range count is clamped to 12 before saving", (env.posts[2] || {}).body);
    check(cap.value === "12", "cap: the field shows the clamped count that was saved", cap.value);
  });
}

async function failure() {
  await scenario("a helper error shows Save failed and restores the toggle", async () => {
    const env = await setupEnv({
      onPost: () => jsonResponse({ ok: false, error: "settings write failed" }),
    });
    const toggle = env.el("hook-type-enabled");
    toggle.checked = true;
    fire(toggle, "change");
    await settle();
    check(env.posts.length === 1, "helper error: the change was sent", env.posts.length);
    check(toggle.checked === false, "helper error: the toggle goes back to the saved value (off)",
      toggle.checked);
    checkStatus(env, "hook-type-status", "Save failed: settings write failed", "warn", "helper error");
  });

  await scenario("an unreachable helper shows Save failed and restores the control", async () => {
    let reachable = true;
    const env = await setupEnv({
      settings: { smart_screenshot_picker_enabled: true, clipboard_screenshot_cap: 5 },
      onPost: (body, server) => {
        if (!reachable) throw new TypeError("Failed to fetch");
        return storeAndEcho(body, server);
      },
    });
    reachable = false;
    const picker = env.el("smart-screenshot-picker-enabled");
    picker.checked = false;
    fire(picker, "change");
    await settle();
    check(picker.checked === true, "unreachable: the picker goes back to the saved value (on)",
      picker.checked);
    checkStatus(env, "smart-screenshot-picker-status", /^Save failed/, "warn", "unreachable picker");

    const cap = env.el("clipboard-screenshot-cap");
    cap.value = "9";
    fire(cap, "change");
    await settle();
    check(cap.value === "5", "unreachable: the count goes back to the saved value (5)", cap.value);
    checkStatus(env, "clipboard-screenshot-cap-status", /^Save failed/, "warn", "unreachable cap");
  });

  await scenario("an ok answer that does not keep the change is not called Saved", async () => {
    // A helper that knows nothing of Hook Type: ok, and it leaves the field
    // out of what it sends back.
    const env = await setupEnv({
      onPost: (body, server) => {
        const settings = publicSettings(server);
        delete settings.hook_type_enabled;
        return jsonResponse({ ok: true, settings });
      },
    });
    const toggle = env.el("hook-type-enabled");
    toggle.checked = true;
    fire(toggle, "change");
    await settle();
    const where = "not kept";
    check(env.posts.length === 1, `${where}: the change was sent`, env.posts.length);
    checkStatus(env, "hook-type-status", NOT_SUPPORTED, "warn", where);
    check(toggle.checked === false, `${where}: the toggle goes back to the helper's value (off)`,
      toggle.checked);
  });

  await scenario("a stale failure does not undo a newer change", async () => {
    const first = deferred();
    let n = 0;
    const env = await setupEnv({
      onPost: (body, server) => {
        n += 1;
        if (n === 1) return first.promise;
        return storeAndEcho(body, server);
      },
    });
    const toggle = env.el("hook-type-enabled");
    toggle.checked = true;
    fire(toggle, "change");
    await settle();
    toggle.checked = false;
    fire(toggle, "change");
    await settle();
    first.resolve(jsonResponse({ ok: false, error: "slow and failed" }));
    await settle();
    check(env.posts.length === 2, "stale: both changes were sent", env.posts.length);
    check(toggle.checked === false, "stale: the toggle keeps the newest choice (off)", toggle.checked);
    checkStatus(env, "hook-type-status", "Saved", "ok", "stale");
  });
}

// Saves made while an earlier one is still unanswered. Each case runs with the
// newest request answered first (the order that used to let an older write
// land last) and with the oldest answered first.
async function overlap() {
  for (const newestFirst of [true, false]) {
    const order = orderName(newestFirst);

    await scenario(`two quick Hook Type changes, ${order}`, async () => {
      const helper = slowHelper();
      const env = await setupEnv({ onPost: helper.onPost });
      const toggle = env.el("hook-type-enabled");
      toggle.checked = true;
      fire(toggle, "change");
      await settle();
      toggle.checked = false;
      fire(toggle, "change");
      await settle();
      const where = `hook twice (${order})`;
      check(helper.held.length === 1,
        `${where}: the second change waits until the first is answered`,
        helper.held.map((h) => h.body));
      checkSaving(env, "hook-type-status", where);

      await answerAll(helper, { newestFirst });
      check(JSON.stringify(env.posts.map((p) => p.body))
        === JSON.stringify([{ hook_type_enabled: true }, { hook_type_enabled: false }]),
      `${where}: the helper got on, then off`, env.posts.map((p) => p.body));
      check(env.server.settings.hook_type_enabled === false,
        `${where}: the helper keeps the newest choice (off)`, env.server.settings.hook_type_enabled);
      check(toggle.checked === false, `${where}: the toggle shows the newest choice (off)`,
        toggle.checked);
      checkStatus(env, "hook-type-status", "Saved", "ok", where);
    });

    await scenario(`a slow Comment Intelligence save, then a Hook Type change, ${order}`,
      async () => {
        const helper = slowHelper();
        const env = await setupEnv({ onPost: helper.onPost });
        env.el("ci-save-btn").click();
        await settle();
        const toggle = env.el("hook-type-enabled");
        toggle.checked = true;
        fire(toggle, "change");
        await settle();
        const where = `CI save then Hook Type (${order})`;
        check(helper.held.length === 1,
          `${where}: the Hook Type save waits for the Comment Intelligence save`,
          helper.held.map((h) => h.body));

        await answerAll(helper, { newestFirst });
        check(env.posts.length === 2, `${where}: both saves were sent`, env.posts.length);
        const ciBody = (env.posts[0] || {}).body || {};
        check("comment_intelligence_enabled" in ciBody && !("hook_type_enabled" in ciBody),
          `${where}: the Comment Intelligence save does not carry Hook Type`, ciBody);
        check(toggle.checked === true,
          `${where}: the Comment Intelligence answer does not reset the toggle (on)`,
          toggle.checked);
        check(env.server.settings.hook_type_enabled === true,
          `${where}: the helper keeps Hook Type on`, env.server.settings.hook_type_enabled);
        checkStatus(env, "hook-type-status", "Saved", "ok", where);
        check(env.el("ci-status").textContent === "Key set",
          `${where}: the Comment Intelligence section reports its save`,
          env.el("ci-status").textContent);
      });

    await scenario(`a slow screenshot count save, then a refused picker change, ${order}`,
      async () => {
        const helper = slowHelper();
        const env = await setupEnv({ onPost: helper.onPost });
        const cap = env.el("clipboard-screenshot-cap");
        cap.value = "7";
        fire(cap, "change");
        await settle();
        const picker = env.el("smart-screenshot-picker-enabled");
        picker.checked = true;
        fire(picker, "change");
        await settle();
        const where = `count then picker (${order})`;
        checkSaving(env, "clipboard-screenshot-cap-status", where);
        checkSaving(env, "smart-screenshot-picker-status", where);

        await answerAll(helper, {
          newestFirst,
          failWith: (body) => ("smart_screenshot_picker_enabled" in body
            ? "picker write refused" : null),
        });
        check(env.posts.length === 2, `${where}: both saves were sent`, env.posts.length);
        check(picker.checked === false, `${where}: the refused picker change is put back (off)`,
          picker.checked);
        check(env.server.settings.smart_screenshot_picker_enabled === false,
          `${where}: the helper still has the picker off`);
        checkStatus(env, "smart-screenshot-picker-status", "Save failed: picker write refused",
          "warn", where);
        check(cap.value === "7", `${where}: the count stays 7`, cap.value);
        check(env.server.settings.clipboard_screenshot_cap === 7,
          `${where}: the helper stored the count 7`, env.server.settings.clipboard_screenshot_cap);
        checkStatus(env, "clipboard-screenshot-cap-status", "Saved", "ok", where);
      });

    await scenario(`a refused Hook Type change, then a Claim verification change, ${order}`,
      async () => {
        const helper = slowHelper();
        const env = await setupEnv({ onPost: helper.onPost });
        const toggle = env.el("hook-type-enabled");
        toggle.checked = true;
        fire(toggle, "change");
        await settle();
        const cv = env.el("cv-enabled");
        cv.checked = true;
        fire(cv, "change");
        await settle();
        const where = `Hook Type then Claim verification (${order})`;

        await answerAll(helper, {
          newestFirst,
          failWith: (body) => ("hook_type_enabled" in body ? "hook write refused" : null),
        });
        const cvPost = env.posts.find((p) => "claim_verification_enabled" in p.body);
        check(!!cvPost && !("hook_type_enabled" in cvPost.body),
          `${where}: the Claim verification save does not carry Hook Type`,
          cvPost && cvPost.body);
        check(toggle.checked === false, `${where}: the refused Hook Type change is put back (off)`,
          toggle.checked);
        check(env.server.settings.hook_type_enabled === false,
          `${where}: the helper still has Hook Type off`, env.server.settings.hook_type_enabled);
        checkStatus(env, "hook-type-status", "Save failed: hook write refused", "warn", where);
        check(cv.checked === true && env.server.settings.claim_verification_enabled === true,
          `${where}: Claim verification is on and saved`,
          { checked: cv.checked, saved: env.server.settings.claim_verification_enabled });
      });

    await scenario(`a slow Comment Intelligence save, then a Claim verification change, ${order}`,
      async () => {
        const helper = slowHelper();
        const env = await setupEnv({ onPost: helper.onPost });
        env.el("ci-save-btn").click();
        await settle();
        const cv = env.el("cv-enabled");
        cv.checked = true;
        fire(cv, "change");
        await settle();
        const where = `CI save then Claim verification (${order})`;

        await answerAll(helper, { newestFirst });
        check(env.posts.length === 2, `${where}: both saves were sent`, env.posts.length);
        check(cv.checked === true,
          `${where}: the Comment Intelligence answer does not reset the toggle (on)`, cv.checked);
        check(env.server.settings.claim_verification_enabled === true,
          `${where}: the helper keeps Claim verification on`,
          env.server.settings.claim_verification_enabled);
      });

    await scenario(`a Hook Type change made before the saved settings load, ${order}`,
      async () => {
        const helper = slowHelper();
        const env = await setupEnv({ onPost: helper.onPost, onGet: helper.onGet });
        const toggle = env.el("hook-type-enabled");
        const where = `Hook Type before settings load (${order})`;
        check(toggle.disabled === false && helper.held.length === 1
          && helper.held[0].body === null,
        `${where}: the page is up and its settings read is unanswered`,
        { disabled: toggle.disabled, held: helper.held.map((h) => h.body) });
        toggle.checked = true;
        fire(toggle, "change");
        await settle();

        await answerAll(helper, { newestFirst });
        check(JSON.stringify(env.posts.map((p) => p.body))
          === JSON.stringify([{ hook_type_enabled: true }]),
        `${where}: the change was sent once`, env.posts.map((p) => p.body));
        check(toggle.checked === true, `${where}: the settings read does not reset the toggle (on)`,
          toggle.checked);
        check(env.server.settings.hook_type_enabled === true,
          `${where}: the helper keeps Hook Type on`, env.server.settings.hook_type_enabled);
        checkStatus(env, "hook-type-status", "Saved", "ok", where);
      });
  }

  // A field the user edits again after one of its saves was made (typing
  // included, not yet left) keeps that newer edit when the save fails, and
  // when any answer, reload or restore lands after it.
  const failAll = { newestFirst: false, failWith: () => "write failed" };

  await scenario("a failed screenshot count save keeps newer typing", async () => {
    const helper = slowHelper();
    const env = await setupEnv({ settings: { clipboard_screenshot_cap: 5 }, onPost: helper.onPost });
    const where = "count 5 -> 7, Save settings, typing 9";
    const cap = env.el("clipboard-screenshot-cap");
    check(cap.value === "5", `${where}: the saved count shows`, cap.value);
    cap.value = "7";
    fire(cap, "input");
    fire(cap, "change");
    env.el("ci-save-btn").click();
    await settle();
    cap.value = "9";
    fire(cap, "input");
    await answerAll(helper, failAll);
    check(cap.value === "9", `${where}: the failed saves do not put back the saved count`,
      cap.value);
    checkStatus(env, "clipboard-screenshot-cap-status", "Save failed: write failed", "warn", where);
    fire(cap, "change");
    await settle();
    await answerAll(helper, { newestFirst: false });
    check(env.server.settings.clipboard_screenshot_cap === 9 && cap.value === "9",
      `${where}: leaving the field saves 9`, env.server.settings.clipboard_screenshot_cap);
    checkStatus(env, "clipboard-screenshot-cap-status", "Saved", "ok", `${where} (left)`);
  });

  await scenario("a failed vault path save keeps newer typing", async () => {
    const helper = slowHelper();
    const env = await setupEnv({
      settings: { obsidian_vault_path: "C:/Saved" }, onPost: helper.onPost,
    });
    const where = "vault C:/Saved -> D:/Seven, Save settings, typing D:/Nine";
    const vault = env.el("ct-obsidian-path");
    vault.value = "D:/Seven";
    fire(vault, "input");
    fire(vault, "change");
    env.el("ci-save-btn").click();
    await settle();
    vault.value = "D:/Nine";
    fire(vault, "input");
    await answerAll(helper, failAll);
    check(vault.value === "D:/Nine", `${where}: the failed saves do not put back a saved path`,
      vault.value);
    checkStatus(env, VAULT.status, "Save failed: write failed", "warn", where);
    fire(vault, "change");
    await settle();
    await answerAll(helper, { newestFirst: false });
    check(env.server.settings.obsidian_vault_path === "D:/Nine" && vault.value === "D:/Nine",
      `${where}: leaving the field saves D:/Nine`, env.server.settings.obsidian_vault_path);
    checkStatus(env, VAULT.status, "Saved", "ok", `${where} (left)`);
  });

  await scenario("a failed Hook Type save keeps the newer choice", async () => {
    const helper = slowHelper();
    const env = await setupEnv({ onPost: helper.onPost });
    const where = "Hook Type on, Save settings, off";
    const toggle = env.el("hook-type-enabled");
    toggle.checked = true;
    fire(toggle, "change");
    env.el("ci-save-btn").click();
    await settle();
    toggle.checked = false;
    fire(toggle, "change");
    await settle();
    await answerOldest(helper, "write failed");
    check(toggle.checked === false, `${where}: the failed "on" save does not undo "off"`,
      toggle.checked);
    await answerAll(helper, { newestFirst: false });
    check(toggle.checked === false && env.server.settings.hook_type_enabled === false,
      `${where}: the helper keeps "off"`, env.server.settings.hook_type_enabled);
    checkStatus(env, "hook-type-status", "Saved", "ok", where);
  });

  await scenario("a key typed while Save settings is out is kept", async () => {
    const helper = slowHelper();
    const env = await setupEnv({ settings: { anthropic_key_set: false }, onPost: helper.onPost });
    const where = "key typed during Save settings";
    const key = env.el("anthropic-key");
    key.value = "sk-ant-first";
    fire(key, "input");
    env.el("ci-save-btn").click();
    await settle();
    key.value = "sk-ant-second";
    fire(key, "input");
    await answerAll(helper, { newestFirst: false });
    check(((env.posts[0] || {}).body || {}).anthropic_key === "sk-ant-first"
      && env.server.settings.anthropic_key_set === true,
    `${where}: the first key was saved`, env.posts.map((p) => p.body));
    check(key.value === "sk-ant-second", `${where}: the answer does not clear the key typed since`,
      key.value);
  });

  await scenario("a key typed while Clear key is out is kept", async () => {
    const helper = slowHelper();
    const env = await setupEnv({ onPost: helper.onPost });
    env.ctx.confirm = () => true;
    const where = "key typed during Clear key";
    env.el("ci-clear-btn").click();
    await settle();
    const key = env.el("anthropic-key");
    key.value = "sk-ant-new";
    fire(key, "input");
    await answerAll(helper, { newestFirst: false });
    check(env.server.settings.anthropic_key_set === false, `${where}: the key was cleared`,
      env.server.settings.anthropic_key_set);
    check(key.value === "sk-ant-new", `${where}: the answer does not clear the key typed since`,
      key.value);
  });

  // Once the helper has stored an edit, the field shows what later answers
  // say again (e.g. a value saved from another tab).
  await scenario("a vault path saved from another tab after this tab's was stored", async () => {
    const env = await setupEnv({ settings: { obsidian_vault_path: "C:/Start" } });
    const where = "tab A saves vault A, tab B saves vault B";
    const vault = env.el("ct-obsidian-path");
    vault.value = "D:/VaultA";
    fire(vault, "input");
    fire(vault, "change");
    await settle();
    check(env.server.settings.obsidian_vault_path === "D:/VaultA", `${where}: tab A stored vault A`,
      env.server.settings.obsidian_vault_path);
    env.server.settings.obsidian_vault_path = "D:/VaultB"; // tab B's save
    env.el("ci-save-btn").click();
    await settle();
    check(vault.value === "D:/VaultB",
      `${where}: tab A's Save settings answer shows vault B`, vault.value);
    changeControl(env, CV);
    await settle();
    check(env.server.settings.obsidian_vault_path === "D:/VaultB"
      && env.server.settings[CV.field] === true,
    `${where}: tab A's Claim verification save does not write vault A back`, env.server.settings);
  });

  await scenario("a pending setting restored after the user edited that field", async () => {
    let release;
    const gate = new Promise((resolve) => { release = resolve; });
    const env = await setupEnv({
      local: {
        uoink_settings_pending: {
          obsidian_vault_path: "D:/PendingVault", mirror_scripts_to_obsidian: true,
        },
      },
      // The page's read of the pending record answers late.
      beforeLoad: (e) => {
        e.storageDelay.local = (req) => (req.op === "get"
          && (req.keys || []).includes("uoink_settings_pending") ? gate : undefined);
      },
    });
    const where = "pending record read late";
    const vault = env.el("ct-obsidian-path");
    vault.value = "D:/Typed";
    fire(vault, "input");
    release();
    await settle();
    check(vault.value === "D:/Typed", `${where}: it does not replace the path typed meanwhile`,
      vault.value);
    check(env.el("ct-obsidian-mirror").checked === true,
      `${where}: it still restores the fields the user hasn't edited`,
      env.el("ct-obsidian-mirror").checked);
  });
}

async function ci_save() {
  await scenario("Comment Intelligence saves on change, Save settings saves the key", async () => {
    checkStatusInSection("ci-enabled-status", "comment-intelligence");
    const env = await setupEnv({ settings: { anthropic_key_set: false } });
    const ci = env.el("ci-enabled");
    const key = env.el("anthropic-key");
    key.value = "sk-ant-new-key";
    fire(key, "input");
    ci.checked = true;
    fire(ci, "change");
    await settle();
    check(env.posts.length === 1
      && sameJson(env.posts[0].body, { comment_intelligence_enabled: true }),
    "switching Comment Intelligence on sends one POST /settings with just that toggle "
      + "(never the typed key), without pressing Save settings", env.posts.map((p) => p.body));
    check(env.server.settings.comment_intelligence_enabled === true,
      "the helper stored the toggle on", env.server.settings.comment_intelligence_enabled);
    checkStatus(env, "ci-enabled-status", "Saved", "ok", "CI toggle");
    check(key.value === "sk-ant-new-key", "the typed key stays in its box", key.value);

    env.el("ci-save-btn").click();
    await settle();
    check(env.posts.length === 2, "Save settings sends one POST /settings", env.posts.length);
    const body = (env.posts[1] || {}).body || {};
    check(body.comment_intelligence_enabled === true, "Save settings sends the CI toggle", body);
    check(!("hook_type_enabled" in body) && !("smart_screenshot_picker_enabled" in body)
      && !("clipboard_screenshot_cap" in body),
    "Save settings leaves Hook Type / picker / count to their own saves", body);
    check(body.anthropic_key === "sk-ant-new-key", "Save settings sends the typed key", body);
    check(env.server.settings.comment_intelligence_enabled === true,
      "the helper stored the CI toggle");
    check(env.el("ci-status").textContent === "Key set", "Save settings reports the key as set",
      env.el("ci-status").textContent);
  });

  await scenario("a refused Comment Intelligence change shows Save failed", async () => {
    const env = await setupEnv({
      onPost: () => jsonResponse({ ok: false, error: "nope" }),
    });
    const ci = env.el("ci-enabled");
    ci.checked = true;
    fire(ci, "change");
    await settle();
    const where = "CI toggle refused";
    check(env.posts.length === 1, `${where}: the change was sent`, env.posts.length);
    checkStatus(env, "ci-enabled-status", "Save failed: nope", "warn", where);
    check(ci.checked === false, `${where}: the toggle goes back to the helper's value (off)`,
      ci.checked);
    check(env.server.settings.comment_intelligence_enabled === false,
      `${where}: the helper still has it off`, env.server.settings.comment_intelligence_enabled);
  });

  await scenario("Save settings with nothing to save sends nothing", async () => {
    // The settings read timed out, so the toggle shows only its HTML default,
    // and no key is typed: the helper would refuse an empty save.
    const helper = slowHelper();
    const env = await setupEnv({ onGet: helper.onGet });
    fireTimeouts(env);
    await settle();
    env.el("ci-save-btn").click();
    await settle();
    const where = "Save settings, nothing to save";
    check(env.posts.length === 0, `${where}: no POST /settings`, env.posts.map((p) => p.body));
    checkStatus(env, "ci-status", "Type an API key to save it.", "warn", where);
  });

  for (const newestFirst of [true, false]) {
    const order = orderName(newestFirst);
    await scenario(`Save settings pressed while the toggle's own save is out, ${order}`,
      async () => {
        const helper = slowHelper();
        const env = await setupEnv({ settings: { anthropic_key_set: false }, onPost: helper.onPost });
        const ci = env.el("ci-enabled");
        ci.checked = true;
        fire(ci, "change");
        const key = env.el("anthropic-key");
        key.value = "sk-ant-new-key";
        fire(key, "input");
        env.el("ci-save-btn").click();
        await settle();
        const where = `CI toggle then Save settings (${order})`;
        await answerAll(helper, { newestFirst });
        check(env.posts.length === 2 && env.posts[1].body.anthropic_key === "sk-ant-new-key",
          `${where}: both were sent, the key with Save settings`, env.posts.map((p) => p.body));
        check(env.server.settings.comment_intelligence_enabled === true
          && env.server.settings.anthropic_key_set === true,
        `${where}: the helper keeps the toggle on and the key`, env.server.settings);
        checkStatus(env, "ci-enabled-status", "Saved", "ok", where);
        check(ci.checked === true, `${where}: the toggle shows on`, ci.checked);
      });
  }
}

// The Claim verification and Creator tools controls save with the rest of
// their sections' settings on every change; each section reports on its own
// line. set(el) makes the change, sent is what the save carries for it, kept
// what the helper stores (absent: the helper drops the field).
const CV = { id: "cv-enabled", status: "claim-verification-status",
  section: "claim-verification-settings", field: "claim_verification_enabled",
  set: (el) => { el.checked = true; }, shown: (el) => el.checked === true,
  sent: true, kept: true };
const VAULT = { id: "ct-obsidian-path", status: "creator-tools-status",
  section: "creator-tools-settings", field: "obsidian_vault_path",
  set: (el) => { el.value = "C:\\Vault\\"; }, shown: (el) => el.value === "C:\\Vault\\",
  sent: "C:\\Vault\\", kept: "C:\\Vault" };
const MIRROR = { id: "ct-obsidian-mirror", status: "creator-tools-status",
  section: "creator-tools-settings", field: "mirror_scripts_to_obsidian",
  label: "Mirror scripts to Obsidian vault", set: (el) => { el.checked = true; }, sent: true };
const EVIDENCE = { id: "cv-sources", status: "claim-verification-status",
  section: "claim-verification-settings", field: "default_evidence_sources",
  label: "Default evidence sources", set: (el) => { el.value = "https://example.org\n"; },
  sent: ["https://example.org"] };

function notKept(...controls) {
  return `Not saved: Uoink helper does not support ${controls.map((c) => `"${c.label}"`).join(", ")}`;
}

function changeControl(env, control) {
  const el = env.el(control.id);
  control.set(el);
  fire(el, "change");
  return el;
}

function sameJson(a, b) {
  return JSON.stringify(a) === JSON.stringify(b);
}

function bannerShown(env) {
  return !env.el("settings-pending-banner").classList.contains("hidden");
}

async function section_status() {
  for (const control of [CV, VAULT]) {
    await scenario(`${control.id} shows Saving..., then Saved`, async () => {
      checkStatusInSection(control.status, control.section);
      const helper = slowHelper();
      const env = await setupEnv({ onPost: helper.onPost });
      const el = changeControl(env, control);
      await settle();
      const where = `${control.id} saved`;
      check(helper.held.length === 1
        && sameJson((helper.held[0].body || {})[control.field], control.sent),
      `${where}: the change was sent`, helper.held.map((h) => h.body));
      checkSaving(env, control.status, where);

      await answerAll(helper, { newestFirst: false });
      check(env.server.settings[control.field] === control.kept, `${where}: the helper stored it`,
        env.server.settings[control.field]);
      check(control.shown(el), `${where}: the control keeps the change`,
        { checked: el.checked, value: el.value });
      checkStatus(env, control.status, "Saved", "ok", where);
      check(!bannerShown(env), `${where}: no "stored locally" banner`);
      const other = control === CV ? VAULT : CV;
      check(env.el(other.status).textContent === "",
        `${where}: #${other.status} is left alone`, env.el(other.status).textContent);
    });

    await scenario(`${control.id} refused by the helper shows Save failed`, async () => {
      const env = await setupEnv({
        onPost: () => jsonResponse({ ok: false, error: "settings write failed" }),
      });
      changeControl(env, control);
      await settle();
      const where = `${control.id} refused`;
      check(env.posts.length === 1, `${where}: the change was sent`, env.posts.length);
      check(env.server.settings[control.field] !== control.kept,
        `${where}: the helper did not store it`);
      checkStatus(env, control.status, "Save failed: settings write failed", "warn", where);
      check(bannerShown(env), `${where}: the "stored locally" banner is shown`);
      const pending = env.store.local.uoink_settings_pending || {};
      check(sameJson(pending[control.field], control.sent),
        `${where}: the change is kept on this device`, pending);
    });

    await scenario(`${control.id} with the helper unreachable shows Save failed`, async () => {
      let reachable = true;
      const env = await setupEnv({
        onPost: (body, server) => {
          if (!reachable) throw new TypeError("Failed to fetch");
          return storeAndEcho(body, server);
        },
      });
      reachable = false;
      changeControl(env, control);
      await settle();
      checkStatus(env, control.status, "Save failed: Uoink helper unreachable", "warn",
        `${control.id} unreachable`);
    });
  }

  // The helper answers ok to these and drops them; the page must not call
  // them Saved (a reload would show them back at their defaults).
  for (const control of [MIRROR, EVIDENCE]) {
    await scenario(`${control.id}, which the helper does not keep, is not called Saved`,
      async () => {
        checkStatusInSection(control.status, control.section);
        const env = await setupEnv();
        changeControl(env, control);
        await settle();
        const where = `${control.id} not kept`;
        check(env.posts.length === 1
          && sameJson((env.posts[0].body || {})[control.field], control.sent),
        `${where}: the change was sent`, env.posts.map((p) => p.body));
        check(!(control.field in env.server.settings), `${where}: the helper did not keep it`,
          env.server.settings);
        checkStatus(env, control.status, notKept(control), "warn", where);
      });
  }

  await scenario("a kept change after one the helper drops, in the same section", async () => {
    const env = await setupEnv();
    changeControl(env, MIRROR);
    await settle();
    changeControl(env, VAULT);
    await settle();
    const where = "mirroring then vault path";
    check(env.posts.length === 2, `${where}: both changes were sent`, env.posts.length);
    check(env.server.settings[VAULT.field] === VAULT.kept, `${where}: the vault path is stored`,
      env.server.settings[VAULT.field]);
    checkStatus(env, VAULT.status, notKept(MIRROR), "warn", where);
  });

  // A section whose save failed waits on: a later save from another section
  // carries its change too, and once that is stored the failed line is
  // settled. The first failure has fully completed before the later change.
  for (const later of [VAULT, MIRROR]) {
    await scenario(`a refused Claim verification save, then a ${later.id} save`, async () => {
      const helper = slowHelper();
      const env = await setupEnv({ onPost: helper.onPost });
      const cv = changeControl(env, CV);
      await settle();
      await answerOldest(helper, "first write refused");
      const where = `Claim verification refused, then ${later.id}`;
      checkStatus(env, CV.status, "Save failed: first write refused", "warn",
        `${where} (first answered)`);
      check(helper.held.length === 0, `${where}: the first save has completed`,
        helper.held.map((h) => h.body));

      changeControl(env, later);
      await settle();
      checkStatus(env, CV.status, "Save failed: first write refused", "warn",
        `${where} (second sent)`);
      await answerOldest(helper);
      check(env.posts.length === 2, `${where}: both saves were sent`, env.posts.length);
      const second = (env.posts[1] || {}).body || {};
      check(second[CV.field] === true, `${where}: the second save carries Claim verification on`,
        second);
      check(cv.checked === true && env.server.settings[CV.field] === true,
        `${where}: the helper stored Claim verification on`, env.server.settings[CV.field]);
      checkStatus(env, CV.status, "Saved", "ok", where);
      if (later.kept === undefined) {
        checkStatus(env, later.status, notKept(later), "warn", where);
      } else {
        checkStatus(env, later.status, "Saved", "ok", where);
      }
      check(!bannerShown(env), `${where}: the "stored locally" banner is gone`);
    });
  }

  await scenario("a refused save, then a stored one carrying both sections", async () => {
    const helper = slowHelper();
    const env = await setupEnv({ onPost: helper.onPost });
    changeControl(env, CV);
    await settle();
    changeControl(env, VAULT);
    await settle();
    const where = "refused then stored";
    check(helper.held.length === 1, `${where}: the second save waits for the first`,
      helper.held.map((h) => h.body));

    await answerOldest(helper, "first write refused");
    checkSaving(env, CV.status, `${where} (first answered)`);
    checkSaving(env, VAULT.status, `${where} (first answered)`);

    await answerOldest(helper);
    check(env.posts.length === 2, `${where}: both saves were sent`, env.posts.length);
    const second = (env.posts[1] || {}).body || {};
    check(second[CV.field] === true && second[VAULT.field] === VAULT.sent,
      `${where}: the second save carries both changes`, second);
    check(env.server.settings[CV.field] === true
      && env.server.settings[VAULT.field] === VAULT.kept,
    `${where}: the helper stored both`, env.server.settings);
    checkStatus(env, CV.status, "Saved", "ok", where);
    checkStatus(env, VAULT.status, "Saved", "ok", where);
    check(!bannerShown(env), `${where}: the "stored locally" banner is gone`);
  });

  await scenario("a stored save, then a refused one from another section", async () => {
    const helper = slowHelper();
    const env = await setupEnv({ onPost: helper.onPost });
    changeControl(env, CV);
    await settle();
    changeControl(env, VAULT);
    await settle();
    const where = "stored then refused";

    await answerOldest(helper);
    checkStatus(env, CV.status, "Saved", "ok", `${where} (first answered)`);
    checkSaving(env, VAULT.status, `${where} (first answered)`);

    await answerOldest(helper, "second write refused");
    check(env.server.settings[CV.field] === true
      && env.server.settings[VAULT.field] !== VAULT.kept,
    `${where}: the helper has Claim verification on and no vault path`, env.server.settings);
    checkStatus(env, CV.status, "Saved", "ok", where);
    checkStatus(env, VAULT.status, "Save failed: second write refused", "warn", where);
  });

  await scenario("an older stored save does not call a newer change Saved", async () => {
    const helper = slowHelper();
    const env = await setupEnv({ onPost: helper.onPost });
    const cv = changeControl(env, CV);
    await settle();
    cv.checked = false;
    fire(cv, "change");
    await settle();
    const where = "Claim verification on, then off";

    await answerOldest(helper);
    checkSaving(env, CV.status, `${where} (on stored)`);

    await answerOldest(helper, "off refused");
    check(env.server.settings[CV.field] === true, `${where}: the helper still has it on`,
      env.server.settings[CV.field]);
    checkStatus(env, CV.status, "Save failed: off refused", "warn", where);
  });
}

async function read_timeout() {
  for (const newestFirst of [true, false]) {
    const order = orderName(newestFirst);
    await scenario(`an unanswered settings read does not hold saves, ${order}`, async () => {
      const helper = slowHelper();
      const env = await setupEnv({ onPost: helper.onPost, onGet: helper.onGet });
      const where = `unanswered read (${order})`;
      check(helper.held.length === 1 && helper.held[0].body === null,
        `${where}: the settings read is out`, helper.held.map((h) => h.body));

      const toggle = env.el("hook-type-enabled");
      toggle.checked = true;
      fire(toggle, "change");
      await settle();
      check(env.posts.length === 0, `${where}: the save waits its turn behind the read`,
        env.posts.map((p) => p.body));
      checkSaving(env, "hook-type-status", where);

      const delays = fireTimeouts(env);
      check(delays.length >= 1 && delays.every((ms) => ms > 0 && ms <= 60000),
        `${where}: the read has a time limit of a minute or less`, delays);
      await settle();
      check(JSON.stringify(env.posts.map((p) => p.body))
        === JSON.stringify([{ hook_type_enabled: true }]),
      `${where}: the save goes out once the read is given up`, env.posts.map((p) => p.body));
      checkStatus(env, "ci-status", "Settings unavailable: Uoink helper did not answer", "warn",
        where);

      // The POST and the late read answer, in either order.
      await answerAll(helper, { newestFirst });
      check(env.server.settings.hook_type_enabled === true,
        `${where}: the helper stored Hook Type on`, env.server.settings.hook_type_enabled);
      check(toggle.checked === true, `${where}: the late read answer does not reset the toggle`,
        toggle.checked);
      checkStatus(env, "hook-type-status", "Saved", "ok", where);
      checkStatus(env, "ci-status", "Settings unavailable: Uoink helper did not answer", "warn",
        `${where} (late answer)`);

      // Later saves are not held either.
      const cv = changeControl(env, CV);
      await settle();
      await answerAll(helper, { newestFirst });
      check(cv.checked === true && env.server.settings[CV.field] === true,
        `${where}: a later Claim verification change is saved`, env.server.settings[CV.field]);
      checkStatus(env, CV.status, "Saved", "ok", where);
    });
  }

  await scenario("a settings read answered in time clears its time limit", async () => {
    const helper = slowHelper();
    const env = await setupEnv({
      settings: { hook_type_enabled: true },
      onPost: helper.onPost,
      onGet: helper.onGet,
    });
    await answerAll(helper, { newestFirst: false });
    const where = "read answered";
    check(env.timeouts.size === 0, `${where}: no timer is left pending`, [...env.timeouts.keys()]);
    check(env.el("hook-type-enabled").checked === true, `${where}: the saved settings show`,
      env.el("hook-type-enabled").checked);
    checkStatus(env, "ci-status", "Key set", "ok", where);
  });

  // Saved settings that differ from setup.html's defaults, and a settings
  // read on load that times out: the untouched controls still show those
  // defaults, so a save must never send them, and the first save the helper
  // answers fills them in.
  const SAVED_VAULT = "D:\\Notes\\Vault";
  // What the untouched controls show for those saved settings.
  const savedShown = (env) => ({
    vault: env.el("ct-obsidian-path").value,
    ci: env.el("ci-enabled").checked,
    picker: env.el("smart-screenshot-picker-enabled").checked,
    cap: env.el("clipboard-screenshot-cap").value,
  });
  const SAVED_SHOWN = { vault: SAVED_VAULT, ci: true, picker: true, cap: "8" };
  for (const first of ["Hook Type", "Clear key", "Claim verification"]) {
    await scenario(`a timed-out settings read never overwrites saved settings, ${first} first`,
      async () => {
        const helper = slowHelper();
        const env = await setupEnv({
          settings: {
            obsidian_vault_path: SAVED_VAULT,
            comment_intelligence_enabled: true,
            smart_screenshot_picker_enabled: true,
            clipboard_screenshot_cap: 8,
          },
          onGet: helper.onGet,
        });
        const where = `timed-out read, ${first} first`;
        fireTimeouts(env);
        await settle();
        checkStatus(env, "ci-status", "Settings unavailable: Uoink helper did not answer", "warn",
          where);
        if (first === "Hook Type") {
          const toggle = env.el("hook-type-enabled");
          toggle.checked = true;
          fire(toggle, "change");
          await settle();
          checkStatus(env, "hook-type-status", "Saved", "ok", where);
        }
        if (first === "Clear key") {
          env.ctx.confirm = () => true;
          env.el("ci-clear-btn").click();
          await settle();
          const clear = (env.posts[0] || {}).body || {};
          check(sameJson(clear, { anthropic_key: null }),
            `${where}: Clear key sends just the cleared key`, clear);
          check(env.server.settings.anthropic_key_set === false
            && env.el("ci-status").textContent === "Key not set.",
          `${where}: the key is cleared`, env.el("ci-status").textContent);
        }
        if (first !== "Claim verification") {
          check(sameJson(savedShown(env), SAVED_SHOWN),
            `${where}: that save's answer fills in the controls the read never did`,
            savedShown(env));
        }
        changeControl(env, CV);
        await settle();
        const bulk = env.posts.map((p) => p.body).filter((b) => CV.field in b);
        check(bulk.length === 1
          && (!("obsidian_vault_path" in bulk[0]) || bulk[0].obsidian_vault_path === SAVED_VAULT)
          && (!("comment_intelligence_enabled" in bulk[0])
            || bulk[0].comment_intelligence_enabled === true),
        `${where}: the Claim verification save sends no control still at its HTML default`, bulk);
        check(env.server.settings.obsidian_vault_path === SAVED_VAULT
          && env.server.settings.comment_intelligence_enabled === true
          && env.server.settings.smart_screenshot_picker_enabled === true
          && env.server.settings.clipboard_screenshot_cap === 8,
        `${where}: the helper keeps the saved vault path, toggles and screenshot count`,
        env.server.settings);
        check(env.server.settings[CV.field] === true, `${where}: and stores Claim verification on`,
          env.server.settings[CV.field]);
        checkStatus(env, CV.status, "Saved", "ok", where);
        check(sameJson(savedShown(env), SAVED_SHOWN),
          `${where}: the helper's answer fills in the controls the read never did`,
          savedShown(env));
        check(env.el(CV.id).checked === true, `${where}: the changed control keeps the change`,
          env.el(CV.id).checked);
      });
  }

  // Changes an earlier failed save kept on this device (uoink_settings_pending)
  // are the user's: after a timed-out read, a later save carries them, the
  // helper's answer does not put its old values back over them, and only what
  // the helper stored leaves the pending record.
  await scenario("a pending vault path survives a timed-out read", async () => {
    const helper = slowHelper();
    const env = await setupEnv({
      settings: { obsidian_vault_path: "C:/OldVault" },
      onGet: helper.onGet,
      local: { uoink_settings_pending: { obsidian_vault_path: "D:/PendingVault" } },
    });
    const where = "pending vault, timed-out read";
    check(env.el("ct-obsidian-path").value === "D:/PendingVault" && bannerShown(env),
      `${where}: the page shows the pending vault path and the "stored locally" banner`,
      env.el("ct-obsidian-path").value);
    fireTimeouts(env);
    await settle();
    changeControl(env, CV);
    await settle();
    const body = (env.posts[0] || {}).body || {};
    check(env.posts.length === 1 && body[CV.field] === true
      && body.obsidian_vault_path === "D:/PendingVault",
    `${where}: the Claim verification save carries the pending vault path`, body);
    check(env.server.settings.obsidian_vault_path === "D:/PendingVault"
      && env.server.settings[CV.field] === true,
    `${where}: the helper stores the pending vault path`, env.server.settings);
    check(env.el("ct-obsidian-path").value === "D:/PendingVault",
      `${where}: the answer does not put the old vault path back`,
      env.el("ct-obsidian-path").value);
    check(!("uoink_settings_pending" in env.store.local) && !bannerShown(env),
      `${where}: once stored, it leaves the pending record`, env.store.local.uoink_settings_pending);
  });

  await scenario("a pending setting the helper does not keep stays pending", async () => {
    const helper = slowHelper();
    const env = await setupEnv({
      settings: { obsidian_vault_path: "C:/OldVault" },
      onGet: helper.onGet,
      // A record an earlier version wrote: it also carried Hook Type, which
      // this page no longer sends with these settings.
      local: {
        uoink_settings_pending: {
          obsidian_vault_path: "D:/PendingVault",
          mirror_scripts_to_obsidian: true,
          hook_type_enabled: false,
        },
      },
    });
    const where = "pending setting the helper drops";
    fireTimeouts(env);
    await settle();
    changeControl(env, CV);
    await settle();
    const body = (env.posts[0] || {}).body || {};
    check(body.mirror_scripts_to_obsidian === true && body.obsidian_vault_path === "D:/PendingVault",
      `${where}: the save carries both pending settings`, body);
    check(env.server.settings.obsidian_vault_path === "D:/PendingVault",
      `${where}: the helper stores the vault path`, env.server.settings.obsidian_vault_path);
    check(sameJson(env.store.local.uoink_settings_pending, { mirror_scripts_to_obsidian: true })
      && bannerShown(env),
    `${where}: only what the helper stored leaves the pending record; mirroring stays`,
    env.store.local.uoink_settings_pending);
    check(env.el("ct-obsidian-mirror").checked === true,
      `${where}: the mirroring toggle still shows the pending choice`,
      env.el("ct-obsidian-mirror").checked);
  });

  // The settings read on load failed, so the first answered save fills the
  // page in. A field the user edited (typing included, focused or not) is
  // never replaced by that answer; a focused field not yet edited is filled.
  const failedRead = () => jsonResponse({ ok: false, error: "settings read failed" });

  await scenario("a vault path typed while a save is out is kept (failed read)", async () => {
    const helper = slowHelper();
    const env = await setupEnv({ onPost: helper.onPost, onGet: failedRead });
    const where = "vault typed during a save";
    changeControl(env, CV);
    await settle();
    const vault = env.el("ct-obsidian-path");
    vault.value = "D:/TypedVault";
    fire(vault, "input");
    await answerAll(helper, { newestFirst: false });
    check(vault.value === "D:/TypedVault",
      `${where}: the Claim verification answer does not replace the typed path`, vault.value);
    fire(vault, "change"); // leaving the field
    await settle();
    await answerAll(helper, { newestFirst: false });
    check(env.server.settings.obsidian_vault_path === "D:/TypedVault"
      && vault.value === "D:/TypedVault",
    `${where}: leaving the field saves the typed path`, env.server.settings.obsidian_vault_path);
    checkStatus(env, VAULT.status, "Saved", "ok", where);
  });

  await scenario("a screenshot count typed while a save is out is kept (failed read)", async () => {
    const helper = slowHelper();
    const env = await setupEnv({ onPost: helper.onPost, onGet: failedRead });
    const where = "screenshot count typed during a save";
    const toggle = env.el("hook-type-enabled");
    toggle.checked = true;
    fire(toggle, "change");
    await settle();
    const cap = env.el("clipboard-screenshot-cap");
    cap.value = "9";
    fire(cap, "input");
    await answerAll(helper, { newestFirst: false });
    check(cap.value === "9", `${where}: the Hook Type answer does not replace the typed count`,
      cap.value);
    fire(cap, "change");
    await settle();
    await answerAll(helper, { newestFirst: false });
    check(env.server.settings.clipboard_screenshot_cap === 9 && cap.value === "9",
      `${where}: leaving the field saves the typed count`, env.server.settings.clipboard_screenshot_cap);
    checkStatus(env, "clipboard-screenshot-cap-status", "Saved", "ok", where);
  });

  await scenario("a focused field is filled unless the user edited it (failed read)", async () => {
    const helper = slowHelper();
    const env = await setupEnv({
      settings: { obsidian_vault_path: "C:/Saved" }, onPost: helper.onPost, onGet: failedRead,
    });
    const where = "focused vault path";
    const vault = env.el("ct-obsidian-path");
    env.document.activeElement = vault;
    changeControl(env, CV);
    await settle();
    await answerAll(helper, { newestFirst: false });
    check(vault.value === "C:/Saved",
      `${where}: an answer fills in the focused field the user hasn't edited`, vault.value);

    // Typing in it, still focused, while another save is out.
    changeControl(env, MIRROR);
    await settle();
    const body = (env.posts[1] || {}).body || {};
    check(body.obsidian_vault_path === "C:/Saved",
      `${where}: a save made before typing carries the filled-in path`, body);
    vault.value = "D:/TypedVault";
    fire(vault, "input");
    await answerAll(helper, { newestFirst: false });
    check(vault.value === "D:/TypedVault",
      `${where}: once edited, the next answer keeps the typed path`, vault.value);
    check(env.server.settings.obsidian_vault_path === "C:/Saved",
      `${where}: the helper keeps its saved path until the typed one is saved`,
      env.server.settings.obsidian_vault_path);
  });
}

const GROUPS = { hook_type, screenshot, failure, overlap, ci_save, section_status, read_timeout };

const requested = process.argv.slice(2);
const names = requested.length ? requested : Object.keys(GROUPS);
for (const name of names) {
  const run = GROUPS[name];
  if (!run) {
    failures++;
    console.error(`FAIL: unknown group ${name}`);
    continue;
  }
  const before = checks;
  await scenario(name, run);
  await settle();
  console.log(`group ${name}: ${checks - before} checks`);
}

if (failures) {
  console.error(`\n${failures} setup toggle save check(s) failed.`);
  process.exit(1);
}
console.log("\nAll setup toggle save checks passed.");
