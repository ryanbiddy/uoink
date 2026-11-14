// Store screenshots of the setup page and popup at 1280x800, with mock data.
// Headless Chrome over CDP; no helper, no network, no real library involved.
// usage: node scripts/store_screenshots.mjs <out-dir> [chrome-path]
// Serves extension/ from a throwaway local http server and replaces the
// chrome.* APIs and the helper's HTTP surface with in-page stubs.
import { spawn } from "node:child_process";
import { createServer } from "node:http";
import { mkdirSync, readFileSync, writeFileSync, existsSync, rmSync } from "node:fs";
import { dirname, join, extname } from "node:path";
import { fileURLToPath } from "node:url";
import { tmpdir } from "node:os";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const EXT = join(ROOT, "extension");
const OUT = process.argv[2];
if (!OUT) { console.error("usage: node scripts/store_screenshots.mjs <out-dir> [chrome-path]"); process.exit(2); }
mkdirSync(OUT, { recursive: true });
const CHROME = process.argv[3] || "C:/Program Files/Google/Chrome/Application/chrome.exe";
const VERSION = readFileSync(join(ROOT, "VERSION"), "utf8").trim();
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const TYPES = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".woff": "font/woff", ".png": "image/png", ".json": "application/json" };

const web = createServer((req, res) => {
  const path = join(EXT, decodeURIComponent(new URL(req.url, "http://x").pathname));
  if (!path.startsWith(EXT) || !existsSync(path)) { res.writeHead(404); res.end(); return; }
  res.writeHead(200, { "content-type": TYPES[extname(path)] || "application/octet-stream" });
  res.end(readFileSync(path));
});
await new Promise((r) => web.listen(0, "127.0.0.1", r));
const BASE = `http://127.0.0.1:${web.address().port}`;

// Stub injected before the page's own scripts. Scenario comes from the URL hash-free query string.
const STUB = `(() => {
  const q = new URLSearchParams(location.search);
  const os = q.get("os") || "win", arch = q.get("arch") || "x86-64", helper = q.get("helper") || "down";
  const recent = [
    { video_id: "V9w3Fhh9BkM", title: "The Origin of the Moon - OpenStax", channel: "Introduction to Astronomy", source_url: "https://www.youtube.com/watch?v=V9w3Fhh9BkM", folder: "origin-of-the-moon", yoinked_at: Date.now() - 600000 },
    { video_id: "4kDqdNTBJL0", title: "Phases of the Moon - OER", channel: "Center for eLearning, FSCJ", source_url: "https://www.youtube.com/watch?v=4kDqdNTBJL0", folder: "phases-of-the-moon", yoinked_at: Date.now() - 3600000 },
  ];
  const json = (body, status = 200) => new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
  const realFetch = window.fetch.bind(window);
  window.fetch = async (url, init) => {
    const u = new URL(String(url), location.href);
    if (u.port !== "5179") return realFetch(url, init);
    if (helper === "down") throw new TypeError("Failed to fetch");
    const p = u.pathname;
    if (p === "/health" || p === "/ping") return json({ ok: true, platform: os });
    if (p === "/diagnose") return json({ ok: true, checks: [{ name: "index_db_writable", status: "ok" }] });
    if (p === "/token") return json({ token: "mock" });
    if (p === "/recent") return json({ ok: true, recent });
    if (p === "/queue/status") return json({ ok: true, pending: [], pending_count: 0 });
    if (p === "/jobs/stream") return new Response(new ReadableStream({ start(c) { c.enqueue(new TextEncoder().encode("event: snapshot\\ndata: " + JSON.stringify({ active: [], recent: [] }) + "\\n\\n")); } }), { status: 200, headers: { "content-type": "text/event-stream" } });
    if (p.startsWith("/jobs")) return json({ ok: true, jobs: [], live_captures: [] });
    return json({ ok: true });
  };
  const store = (initial) => ({
    get: (keys, cb) => { const out = typeof keys === "object" && keys && !Array.isArray(keys) ? { ...keys } : {}; for (const k of [].concat(typeof keys === "string" ? keys : Array.isArray(keys) ? keys : [])) out[k] = initial[k]; const r = Object.assign(out, Object.fromEntries(Object.entries(initial).filter(([k]) => k in out))); if (cb) { cb(r); return; } return Promise.resolve(r); },
    set: (v, cb) => { Object.assign(initial, v); if (cb) cb(); return Promise.resolve(); },
    remove: (k, cb) => { if (cb) cb(); return Promise.resolve(); },
  });
  const noEvent = { addListener() {}, removeListener() {} };
  const tab = { id: 1, url: "https://www.youtube.com/watch?v=Gg7QsqdoZbg", title: "Lesson 9 - Lecture 4 - Mercury - OpenStax", active: true };
  window.chrome = {
    runtime: { id: "mock", lastError: undefined, getURL: (p) => "/" + p, getManifest: () => ({ version: "${VERSION}" }),
      getPlatformInfo: (cb) => { const r = { os, arch }; if (cb) cb(r); return Promise.resolve(r); },
      sendMessage: async () => ({ ok: true, token: "mock" }), onMessage: noEvent, onInstalled: noEvent, connect: () => ({ onMessage: noEvent, onDisconnect: noEvent, postMessage() {}, disconnect() {} }) },
    storage: { local: store({ yoink_token: "mock" }), session: store({}), sync: store({}), onChanged: noEvent },
    tabs: { query: (o, cb) => { if (cb) cb([tab]); return Promise.resolve([tab]); }, sendMessage: (id, m, cb) => { if (cb) cb(undefined); }, create: async () => ({}), onActivated: noEvent, onUpdated: noEvent },
    scripting: { executeScript: async () => [{ result: null }] },
    alarms: { create() {}, onAlarm: noEvent }, notifications: { create() {}, onClicked: noEvent, onButtonClicked: noEvent }, commands: { onCommand: noEvent },
    contextMenus: { create() {}, removeAll: (cb) => cb && cb(), onClicked: noEvent },
    action: { setBadgeText() {}, setBadgeBackgroundColor() {} }, offscreen: { createDocument: async () => {}, hasDocument: async () => false },
    permissions: { contains: async () => true, request: async () => true },
  };
  // Keep the download link inert so a click shows the next state instead of navigating.
  document.addEventListener("click", (e) => { const a = e.target.closest && e.target.closest("#download-btn"); if (a) e.preventDefault(); }, true);
})();`;

const chrome = spawn(CHROME, ["--headless=new", "--remote-debugging-port=9347", `--user-data-dir=${join(tmpdir(), "uoink-store-shots-profile")}`,
  "--no-first-run", "--disable-gpu", "--hide-scrollbars", "--force-color-profile=srgb", "about:blank"], { stdio: "ignore" });
let ok = false;
for (let i = 0; i < 60 && !ok; i++) { try { await (await fetch("http://127.0.0.1:9347/json/version")).json(); ok = true; } catch { await sleep(200); } }
const page = (await (await fetch("http://127.0.0.1:9347/json")).json()).find((t) => t.type === "page");
const ws = new WebSocket(page.webSocketDebuggerUrl);
await new Promise((r) => (ws.onopen = r));
let id = 0; const pending = new Map(); const errors = [];
ws.onmessage = (m) => { const d = JSON.parse(m.data);
  if (d.id && pending.has(d.id)) { pending.get(d.id)(d); pending.delete(d.id); }
  else if (d.method === "Runtime.exceptionThrown") errors.push((d.params.exceptionDetails.exception?.description || d.params.exceptionDetails.text).slice(0, 200)); };
const send = (method, params = {}) => new Promise((res) => { const i = ++id; pending.set(i, res); ws.send(JSON.stringify({ id: i, method, params })); });
const ev = async (expr) => (await send("Runtime.evaluate", { expression: expr, returnByValue: true, awaitPromise: true })).result?.result?.value;
await send("Page.enable"); await send("Runtime.enable");
await send("Page.addScriptToEvaluateOnNewDocument", { source: STUB });

async function shot(file, query, { click, popup, width = 1280, height = 800 } = {}) {
  await send("Emulation.setDeviceMetricsOverride", { width, height, deviceScaleFactor: 1, mobile: false });
  await send("Emulation.setEmulatedMedia", { features: [{ name: "prefers-color-scheme", value: "light" }] });
  await send("Page.navigate", { url: "about:blank" }); await sleep(200);
  await send("Page.navigate", { url: `${BASE}/${query}` });
  await sleep(1800);
  if (click) { await ev(`document.querySelector(${JSON.stringify(click)}).click()`); await sleep(600); }
  if (popup) {
    // The popup is a 360x600 toolbar bubble. Center it on a 1280x800 neutral canvas
    // by framing the real page inside an iframe-less wrapper: scale nothing, just offset.
    await ev(`(() => { document.documentElement.style.cssText += ';width:360px;margin:100px auto 0;box-shadow:0 8px 32px rgba(0,0,0,.28);border-radius:8px;overflow:hidden'; document.body.style.cssText += ';width:360px'; })()`);
    await ev(`document.documentElement.style.background = '#e9e4dc'`);
  }
  const r = await send("Page.captureScreenshot", { format: "png" });
  writeFileSync(join(OUT, file), Buffer.from(r.result.data, "base64"));
  console.log("wrote", file, errors.splice(0).join(" | ") || "no page errors");
}

await shot("setup-1-needs-app.png", "setup.html?os=win&helper=down");
await shot("setup-2-connecting.png", "setup.html?os=win&helper=down", { click: "#download-btn" });
await shot("setup-3-connected.png", "setup.html?os=win&helper=up");
await shot("setup-4-mac-apple-silicon.png", "setup.html?os=mac&arch=arm&helper=down");
await shot("setup-5-intel-mac.png", "setup.html?os=mac&arch=x86-64&helper=down");
await shot("popup-connected.png", "popup.html?os=win&helper=up", { popup: true });
await shot("popup-offline.png", "popup.html?os=win&helper=down", { popup: true });
ws.close(); chrome.kill(); web.close();
setTimeout(() => { try { rmSync(join(tmpdir(), "uoink-store-shots-profile"), { recursive: true, force: true }); } catch {} process.exit(0); }, 500);
