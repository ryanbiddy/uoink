// Tiny, dependency-free fake extension environment for driving the real
// extension scripts (lib/extract.js, content scripts, background.js, popup
// slices) under Node.
//
// Each env is a fresh node:vm context with just enough of the browser and
// chrome.* surface those scripts touch: a minimal DOM (elements, classList,
// title, click listeners), chrome.runtime messaging (promise and callback
// forms, with lastError / rejected-port simulation), chrome.storage areas,
// chrome.notifications, a stubbed fetch (never touches the network), and
// timers that only fire when the test asks. Anything else on chrome.* is a
// permissive no-op stub so background.js can load without a browser.
import { readFileSync } from "node:fs";
import vm from "node:vm";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
export const EXT = join(here, "..", "..", "extension");

function clone(value) {
  if (value === undefined) return undefined;
  return JSON.parse(JSON.stringify(value));
}

// ---- DOM ------------------------------------------------------------------
class FakeClassList {
  constructor() { this.names = new Set(); }
  add(...names) { names.forEach((n) => this.names.add(n)); }
  remove(...names) { names.forEach((n) => this.names.delete(n)); }
  contains(name) { return this.names.has(name); }
  toggle(name, force) {
    const on = force === undefined ? !this.names.has(name) : !!force;
    if (on) this.names.add(name); else this.names.delete(name);
    return on;
  }
}

class FakeElement {
  constructor(tag) {
    this.tagName = String(tag).toUpperCase();
    this.id = "";
    this.type = "";
    this.title = "";
    this.disabled = false;
    this.style = {};
    this.dataset = {};
    this.childNodes = [];
    this.parentElement = null;
    this.classList = new FakeClassList();
    this._listeners = {};
    this._text = "";
    this._html = "";
  }
  get className() { return [...this.classList.names].join(" "); }
  set className(value) {
    this.classList.names = new Set(String(value).split(/\s+/).filter(Boolean));
  }
  get firstChild() { return this.childNodes[0] || null; }
  get children() { return this.childNodes; }
  appendChild(child) {
    if (child.parentElement) child.remove();
    child.parentElement = this;
    this.childNodes.push(child);
    return child;
  }
  insertAdjacentElement(_position, el) {
    return (this.parentElement || this).appendChild(el);
  }
  replaceChildren(...nodes) {
    for (const c of this.childNodes) c.parentElement = null;
    this.childNodes = [];
    nodes.forEach((n) => this.appendChild(n));
  }
  remove() {
    const parent = this.parentElement;
    if (!parent) return;
    parent.childNodes = parent.childNodes.filter((c) => c !== this);
    this.parentElement = null;
  }
  // Static markup only (icons/spinners): kept as a string, no child nodes.
  set innerHTML(value) { this._html = String(value); this.childNodes = []; }
  get innerHTML() { return this._html; }
  set textContent(value) { this._text = String(value); this.childNodes = []; }
  get textContent() {
    return this._text + this.childNodes.map((c) => c.textContent).join("");
  }
  addEventListener(type, fn) { (this._listeners[type] ||= []).push(fn); }
  removeEventListener() {}
  dispatchEvent(ev) {
    for (const fn of this._listeners[ev.type] || []) fn(ev);
    return true;
  }
  click() {
    this.dispatchEvent({ type: "click", isTrusted: false, preventDefault() {}, stopPropagation() {} });
  }
  // Test-only stand-in for browser-dispatched pointer/keyboard activation.
  // Keep click() synthetic, matching HTMLElement.click() in a real page.
  userClick() {
    this.dispatchEvent({ type: "click", isTrusted: true, preventDefault() {}, stopPropagation() {} });
  }
  querySelector() { return null; }
  querySelectorAll() { return []; }
  get offsetWidth() { return 0; }
  _all(acc = []) {
    for (const c of this.childNodes) { acc.push(c); c._all(acc); }
    return acc;
  }
}

class FakeDocument {
  constructor(opts) {
    this.title = opts.title || "";
    this.hidden = false;
    this.head = new FakeElement("head");
    this.body = new FakeElement("body");
    this._selectors = {};
  }
  createElement(tag) { return new FakeElement(tag); }
  getElementById(id) {
    return [...this.head._all(), ...this.body._all()].find((el) => el.id === id) || null;
  }
  querySelector(selector) { return this._selectors[selector] || null; }
  querySelectorAll() { return []; }
  addEventListener() {}
  removeEventListener() {}
}

// Never fires on its own; env.mutate() runs every observer's callback once
// (stands in for the page re-rendering).
class FakeMutationObserver {
  constructor(callback, registry) {
    this.callback = callback;
    if (registry) registry.push(this);
  }
  observe() {}
  disconnect() {}
}

// ---- chrome.* ---------------------------------------------------------------
// Any chrome API the test doesn't care about: callable, chainable, resolves
// undefined, and invokes a trailing callback -- except listener registration,
// which must never run the listener.
function permissive(name) {
  const cache = new Map();
  return new Proxy(function () {}, {
    get(_target, key) {
      if (typeof key === "symbol" || key === "then") return undefined;
      if (!cache.has(key)) cache.set(key, permissive(key));
      return cache.get(key);
    },
    apply(_target, _this, args) {
      if (/Listener$/.test(String(name))) return undefined;
      const last = args[args.length - 1];
      if (typeof last === "function") Promise.resolve().then(() => last(undefined));
      return Promise.resolve(undefined);
    },
  });
}

function withFallback(obj) {
  const extra = new Map();
  return new Proxy(obj, {
    get(target, key) {
      if (key in target) return target[key];
      if (typeof key === "symbol" || key === "then") return undefined;
      if (!extra.has(key)) extra.set(key, permissive(key));
      return extra.get(key);
    },
  });
}

// delay(request) -> undefined to answer at once, or a promise the answer waits
// on. request: {op: "get"|"set"|"remove", keys: [names] (null: everything)}.
// The request itself is served when it's made (a get reads storage then, a
// set writes then); only its answer is late, the way a slow storage round
// trip looks to the script.
function storageArea(data, delay = () => undefined) {
  const answer = (request, value) => {
    const wait = delay(request);
    return wait ? Promise.resolve(wait).then(() => value) : Promise.resolve(value);
  };
  return {
    get(keys, cb) {
      let out = {};
      let names = null;
      if (keys && typeof keys === "object" && !Array.isArray(keys)) {
        for (const [k, d] of Object.entries(keys)) out[k] = k in data ? clone(data[k]) : d;
        names = Object.keys(keys);
      } else if (typeof keys === "string") {
        if (keys in data) out[keys] = clone(data[keys]);
        names = [keys];
      } else if (Array.isArray(keys)) {
        for (const k of keys) if (k in data) out[k] = clone(data[k]);
        names = keys.slice();
      } else {
        out = clone(data);
      }
      const ready = answer({ op: "get", keys: names }, out);
      if (typeof cb === "function") {
        ready.then((v) => cb(v));
        return undefined;
      }
      return ready;
    },
    set(items, cb) {
      for (const [k, v] of Object.entries(items || {})) data[k] = clone(v);
      const ready = answer({ op: "set", keys: Object.keys(items || {}) });
      if (typeof cb === "function") ready.then(() => cb());
      return ready;
    },
    remove(keys, cb) {
      for (const k of [].concat(keys)) delete data[k];
      const ready = answer({ op: "remove", keys: [].concat(keys) });
      if (typeof cb === "function") ready.then(() => cb());
      return ready;
    },
  };
}

// A fetch Response good enough for extract.js (ok/status/text/json/headers).
export function jsonResponse(body, status = 200) {
  const text = JSON.stringify(body);
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: { get: () => "application/json" },
    text: async () => text,
    json: async () => JSON.parse(text),
  };
}

export function abortError() {
  const e = new Error("This operation was aborted");
  e.name = "AbortError";
  return e;
}

// opts:
//   href      -- page URL (window.location.href)
//   title     -- document.title
//   platform  -- navigator.platform / userAgentData.platform
//   onSend    -- (msg, env) => response for chrome.runtime.sendMessage.
//                Return {__reject: "msg"} to simulate a closed port
//                (promise rejects / callback sees runtime.lastError).
//   fetch     -- (url, init) => Response (or throw) -- the ONLY network.
//   store     -- {local, sync, session} objects to back chrome.storage with;
//                pass the same one to two envs (popup + background.js) to
//                share storage the way real extension contexts do.
// env.storageDelay -- {local, sync, session}: set an area's entry to a
//                storageArea delay function (any time) to make this env's
//                answers from that area arrive late. Unset: answers at once.
export function makeEnv(opts = {}) {
  const env = {
    sent: [],
    notifications: [],
    tabsCreated: [],
    fetches: [],
    toasts: [],
    logs: [],
    store: opts.store || { local: {}, sync: {}, session: {} },
    messageListeners: [],
    observers: [],
    windowClosed: false,
    timeouts: new Map(),
    intervals: new Map(),
    // id -> the period the script asked for (intervals never fire on their own)
    intervalDelays: new Map(),
    nextTimer: 1,
    storageDelay: {},
  };
  const delayFor = (area) => (request) => (
    env.storageDelay[area] ? env.storageDelay[area](request) : undefined);
  const onSend = opts.onSend || (() => ({ ok: true }));
  const fetchImpl = opts.fetch || (() => { throw new TypeError("Failed to fetch"); });

  const runtime = {
    id: "test-extension-id",
    lastError: undefined,
    getURL: (p) => `chrome-extension://test-extension-id/${p}`,
    onMessage: { addListener(fn) { env.messageListeners.push(fn); } },
    sendMessage(msg, cb) {
      env.sent.push(clone(msg));
      const outcome = Promise.resolve().then(() => onSend(msg, env));
      if (typeof cb === "function") {
        outcome.then((resp) => {
          if (resp && resp.__reject) {
            runtime.lastError = { message: resp.__reject };
            try { cb(undefined); } finally { runtime.lastError = undefined; }
            return;
          }
          cb(clone(resp));
        });
        return undefined;
      }
      return outcome.then((resp) => {
        if (resp && resp.__reject) throw new Error(resp.__reject);
        return clone(resp);
      });
    },
  };
  const chrome = withFallback({
    runtime: withFallback(runtime),
    storage: withFallback({
      local: storageArea(env.store.local, delayFor("local")),
      sync: storageArea(env.store.sync, delayFor("sync")),
      session: storageArea(env.store.session, delayFor("session")),
      onChanged: { addListener() {} },
    }),
    notifications: withFallback({
      create(options, cb) {
        env.notifications.push(clone(options));
        const id = `n${env.notifications.length}`;
        if (typeof cb === "function") Promise.resolve().then(() => cb(id));
        return Promise.resolve(id);
      },
    }),
    tabs: withFallback({
      create(props, cb) {
        env.tabsCreated.push(clone(props));
        const tab = { id: env.tabsCreated.length };
        if (typeof cb === "function") Promise.resolve().then(() => cb(tab));
        return Promise.resolve(tab);
      },
    }),
  });

  const document = new FakeDocument({ title: opts.title });
  const platform = opts.platform || "Win32";
  const show = (a) => {
    try { return String(a); } catch { return "[unprintable]"; }
  };
  const quiet = {};
  for (const level of ["log", "info", "warn", "error", "debug"]) {
    quiet[level] = (...args) => env.logs.push([level, args.map(show).join(" ")]);
  }

  const ctx = {
    console: quiet,
    URL,
    URLSearchParams,
    AbortController,
    chrome,
    document,
    location: { href: opts.href || "https://example.com/" },
    navigator: {
      platform,
      userAgent: "",
      userAgentData: { platform },
      clipboard: { writeText: async () => {} },
    },
    MutationObserver: class extends FakeMutationObserver {
      constructor(callback) { super(callback, env.observers); }
    },
    addEventListener() {},
    removeEventListener() {},
    close() { env.windowClosed = true; },
    fetch: async (url, init) => {
      env.fetches.push(String(url));
      return fetchImpl(String(url), init);
    },
    setTimeout: (fn) => { const id = env.nextTimer++; env.timeouts.set(id, fn); return id; },
    clearTimeout: (id) => { env.timeouts.delete(id); },
    setInterval: (fn, ms) => {
      const id = env.nextTimer++;
      env.intervals.set(id, fn);
      env.intervalDelays.set(id, Number(ms) || 0);
      return id;
    },
    clearInterval: (id) => { env.intervals.delete(id); env.intervalDelays.delete(id); },
  };
  ctx.window = ctx;
  ctx.self = ctx;
  ctx.importScripts = (...files) => {
    for (const f of files) env.load(f);
  };
  vm.createContext(ctx);

  env.ctx = ctx;
  env.chrome = chrome;
  env.document = document;
  env.load = (rel) => {
    vm.runInContext(readFileSync(join(EXT, rel), "utf8"), ctx, { filename: rel });
  };
  env.runSource = (code, filename) => vm.runInContext(code, ctx, { filename });
  // Fire every pending interval callback once (button injection retries,
  // status polling). Timeouts never fire, so error states stay inspectable.
  env.runIntervals = () => {
    for (const [id, fn] of [...env.intervals]) if (env.intervals.has(id)) fn();
  };
  // Fire every MutationObserver callback once (the page DOM changed).
  env.mutate = () => {
    for (const o of [...env.observers]) o.callback([], o);
  };
  // Dispatch a runtime message to the listeners the loaded scripts
  // registered (background.js handlers) and resolve with the response.
  // Chrome supplies its own extension ID for internal messages. Explicit
  // senders are passed unchanged so tests can exercise missing/foreign IDs.
  env.dispatch = (msg, sender = { id: runtime.id }) => new Promise((resolve) => {
    for (const fn of env.messageListeners) {
      let answered = false;
      const keep = fn(clone(msg), sender, (resp) => { answered = true; resolve(clone(resp)); });
      if (keep === true || answered) return;
    }
    resolve(undefined);
  });
  env.notifyMessages = () => env.sent.filter((m) => m && m.type === "notify");
  env.setupTabsOpened = () => env.sent.filter((m) => m && m.type === "openTab"
    && /setup\.html/.test(String(m.url || "")));
  return env;
}

// Let queued promise callbacks (and their follow-ups) run.
export async function settle(rounds = 40) {
  for (let i = 0; i < rounds; i++) await new Promise((r) => setImmediate(r));
}
