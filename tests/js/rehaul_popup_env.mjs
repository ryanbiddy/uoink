// Full popup, real scripts, in-memory DOM/chrome/fetch. Never contacts a helper.
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { EXT, makeEnv, jsonResponse, settle } from "./ext_fake_env.mjs";
export { settle, jsonResponse };

export async function popupEnv(options = {}) {
  const routes = options.routes || {};
  const env = makeEnv({ ...options, fetch: (url, init) => {
    const path = new URL(url).pathname;
    if (routes[path]) return routes[path](url, init);
    if (options.fetch) return options.fetch(url, init);
    if (path === "/token") return jsonResponse({ token: "fixture-token" });
    if (path === "/health") return jsonResponse({ ok: true });
    if (path === "/recent") return jsonResponse({ ok: true, recent: [] });
    if (path === "/jobs") return jsonResponse({ ok: true, jobs: [], live_captures: [] });
    if (path === "/queue/status") return jsonResponse({ ok: true, pending: [] });
    if (path === "/engagement/log") return jsonResponse({ ok: true });
    if (path === "/jobs/stream") return new Promise(() => {});
    throw new Error(`Unexpected fixture request: ${path}`);
  }});
  const doc = env.document;
  const original = doc.createElement.bind(doc);
  function enhance(el) {
    el.attributes = {};
    el.setAttribute = (key, value) => { el.attributes[key] = String(value); };
    el.removeAttribute = key => { delete el.attributes[key]; };
    el.getAttribute = key => el.attributes[key] ?? null;
    el.append = (...nodes) => nodes.forEach(n => el.appendChild(n));
    el.insertBefore = (child, before) => {
      child.remove(); child.parentElement = el;
      const index = el.childNodes.indexOf(before);
      el.childNodes.splice(index < 0 ? el.childNodes.length : index, 0, child);
      return child;
    };
    el.querySelectorAll = selector => el._all().filter(child => selector.startsWith(".")
      ? child.classList.contains(selector.slice(1)) : child.tagName === selector.toUpperCase());
    el.querySelector = selector => el.querySelectorAll(selector)[0] || null;
    el.focus = () => { doc.activeElement = el; };
    return el;
  }
  doc.createElement = tag => enhance(original(tag));
  doc.createTextNode = text => { const el = doc.createElement("text"); el.textContent = text; return el; };
  enhance(doc.body);
  const html = readFileSync(join(EXT, "popup.html"), "utf8");
  for (const match of html.matchAll(/<([\w-]+)\b[^>]*\bid="([^"]+)"[^>]*>/g)) {
    const el = doc.createElement(match[1]); el.id = match[2];
    const cls = /class="([^"]*)"/.exec(match[0]); if (cls) el.className = cls[1];
    el.disabled = /\sdisabled\b/.test(match[0]);
    doc.body.appendChild(el);
  }
  env.events = {};
  env.ctx.addEventListener = (event, callback) => { env.events[event] = callback; };
  doc.addEventListener = (event, callback) => { env.events[event] = callback; };
  env.ctx.TextDecoder = TextDecoder;
  env.ctx.chrome.runtime.getManifest = () => ({ version: "3.8.1" });
  env.ctx.chrome.tabs.query = async () => [options.tab || { id: 7, title: "An example video", url: "https://www.youtube.com/watch?v=abc123def45" }];
  env.ctx.chrome.scripting.executeScript = async () => [];
  env.clipboard = [];
  env.ctx.navigator.clipboard.writeText = async text => { env.clipboard.push(text); };
  env.load("lib/x-article.js"); env.load("lib/extract.js"); env.load("lib/ui.js"); env.load("lib/popup-captures.js");
  env.load("popup.js");
  await settle();
  env.el = id => doc.getElementById(id);
  env.setData = data => { env.ctx.fixtureData = data; env.runSource("Object.assign(captureData, fixtureData); renderCaptures();", "fixture.js"); };
  env.rows = () => env.el("captures-list").children.filter(el => el.classList.contains("capture-row"));
  env.copyButton = () => env.rows()[0].querySelectorAll("button").find(b => b.textContent === "Copy Markdown");
  return env;
}
