// Uoink this page: the service worker reads the tab and posts the text to the
// helper (fake chrome env), and page-capture.js turns real fixture DOMs into
// clean Markdown (jsdom, dev-only: npm ci --prefix tests/js/reader).
// Run: node --test tests/js/page_capture_test.mjs
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { jsonResponse, makeEnv, settle } from "./ext_fake_env.mjs";

const here = fileURLToPath(new URL(".", import.meta.url));
const FIXTURES = join(here, "..", "fixtures", "reader");
const PAGE = "https://news.example.org/2026/10/harbor-lanterns-relit";
const CAPTURE = { url: PAGE, title: "Harbor lanterns are lit again", markdown: "Lanterns. ".repeat(40),
  engine: "defuddle", engine_version: "0.19.6", capture_version: 1 };
const SAVED = { ok: true, video_id: "page_abc", title: "Harbor lanterns are lit again", url: PAGE };

async function worker({ scripting, dom }) {
  const posts = [];
  const env = makeEnv({
    onSend: () => undefined,
    fetch: (url, init) => {
      const path = new URL(url).pathname;
      if (path === "/token") return jsonResponse({ token: "t" });
      if (path === "/health" || path === "/queue/status") return jsonResponse({ ok: true, pending_count: 0 });
      if (path === "/extract/page/dom") {
        posts.push({ path, body: JSON.parse(init.body) });
        return dom ? dom(JSON.parse(init.body)) : jsonResponse(SAVED);
      }
      if (path === "/extract/page") {
        posts.push({ path, body: JSON.parse(init.body) });
        return jsonResponse(SAVED);
      }
      return jsonResponse({ ok: true });
    },
  });
  const calls = [];
  env.chrome.scripting = {
    executeScript: async (spec) => {
      calls.push({ ...JSON.parse(JSON.stringify(spec)), func: typeof spec.func });
      return scripting(spec, calls.length);
    },
  };
  env.load("background.js");
  await settle();
  return { env, posts, calls };
}

const readsTab = (payload) => async (spec) => (spec.files ? [{ result: undefined }]
  : [{ result: payload === null ? null : { ok: true, payload } }]);

test("context menu: the page is read in the clicked tab and only its text goes to the helper", async () => {
  const w = await worker({ scripting: readsTab(CAPTURE) });
  await w.env.clickContextMenu({ menuItemId: "stc-extract-article-page", pageUrl: PAGE }, { id: 7, url: PAGE });
  await settle(200);
  assert.deepEqual(w.calls[0], { target: { tabId: 7 }, files: ["lib/defuddle.js", "lib/page-capture.js"],
    func: "undefined" });
  assert.equal(w.calls[1].target.tabId, 7);
  assert.equal(w.calls[1].func, "function");
  assert.deepEqual(w.posts.map((p) => p.path), ["/extract/page/dom"]);
  assert.equal(w.posts[0].body.markdown, CAPTURE.markdown);
  assert.ok(w.env.fetches.every((u) => u.startsWith("http://127.0.0.1:5179/")), w.env.fetches);
});

test("popup page captures carry the tab id into the queued job", async () => {
  const w = await worker({ scripting: readsTab(CAPTURE) });
  const sender = { id: "test-extension-id", url: "chrome-extension://test-extension-id/popup.html" };
  const resp = await w.env.dispatch({ type: "popupCapture", job: { route: "page", url: PAGE, tabId: 9 } }, sender);
  assert.equal(resp && resp.ok, true);
  await settle(200);
  assert.equal(w.calls[0].target.tabId, 9);
  assert.deepEqual(w.posts.map((p) => p.path), ["/extract/page/dom"]);
});

test("a tab that moved on, can't be read, or an older helper falls back to the URL fetch", async () => {
  const moved = await worker({ scripting: readsTab({ ...CAPTURE, url: "https://news.example.org/other" }) });
  await moved.env.ctx.runExtractJob({ kind: "extract", url: PAGE, usePage: true, tabId: 3 });
  assert.deepEqual(moved.posts.map((p) => p.path), ["/extract/page"]);

  const blocked = await worker({ scripting: async () => { throw new Error("Cannot access contents of the page"); } });
  await blocked.env.ctx.runExtractJob({ kind: "extract", url: PAGE, usePage: true, tabId: 3 });
  assert.deepEqual(blocked.posts.map((p) => p.path), ["/extract/page"]);

  const old = await worker({ scripting: readsTab(CAPTURE), dom: () => jsonResponse({ ok: false, error: "not found" }, 404) });
  await old.env.ctx.runExtractJob({ kind: "extract", url: PAGE, usePage: true, tabId: 3 });
  assert.deepEqual(old.posts.map((p) => p.path), ["/extract/page/dom", "/extract/page"]);

  const noTab = await worker({ scripting: readsTab(CAPTURE) });
  await noTab.env.ctx.runExtractJob({ kind: "extract", url: PAGE, usePage: true });
  assert.equal(noTab.calls.length, 0);
  assert.deepEqual(noTab.posts.map((p) => p.path), ["/extract/page"]);
});

test("a wall the tab shows is reported, not retried through the helper fetch", async () => {
  const wall = { ok: false, code: "article_body_not_found", page_state: "wall",
    error: "This tab shows a sign-in, paywall or robot check instead of the page, so nothing was saved." };
  const w = await worker({ scripting: readsTab(CAPTURE), dom: () => jsonResponse(wall, 400) });
  await w.env.ctx.runExtractJob({ kind: "extract", url: PAGE, usePage: true, tabId: 3 });
  assert.deepEqual(w.posts.map((p) => p.path), ["/extract/page/dom"]);
  const note = w.env.notifications.at(-1);
  assert.equal(note.title, "Uoink failed");
  assert.match(note.message, /sign-in, paywall or robot check/);
});

// ---- page-capture.js on real DOMs (jsdom) --------------------------------------
const jsdomReady = existsSync(join(here, "reader", "node_modules", "jsdom"));
const domTest = (name, fn) => test(name, { skip: !jsdomReady && process.env.UOINK_READER_BENCH_REQUIRED !== "1"
  ? "jsdom not installed (npm ci --prefix tests/js/reader)" : false }, fn);

async function capture(name) {
  const { captureHtml } = await import("./reader_capture_bench.mjs");
  const gold = JSON.parse(readFileSync(join(FIXTURES, `${name}.gold.json`), "utf8"));
  const html = readFileSync(join(FIXTURES, gold.rendered || `${name}.html`), "utf8");
  return captureHtml(html, gold.url);
}

async function markdownOf(html, url = "https://docs.example.dev/a/b") {
  const { captureHtml } = await import("./reader_capture_bench.mjs");
  const page = `<!doctype html><html><head><title>T</title></head><body><main><article>${html}</article></main></body></html>`;
  const res = captureHtml(page, url);
  assert.equal(res.ok, true, JSON.stringify(res));
  return res.payload.markdown;
}

domTest("docs page: code fences keep their language and the sidebar stays out", async () => {
  const res = await capture("docs-code");
  assert.equal(res.ok, true);
  const md = res.payload.markdown;
  assert.match(md, /```python\nfrom quill import Queue\n/);
  assert.match(md, /```bash\nquill worker --backoff exponential --max-delay 300\n```/);
  assert.match(md, /^## Basic retries$/m);
  assert.doesNotMatch(md, /Installation|On this page/);
  assert.equal(res.mutated, false, "the live page is never changed");
  assert.equal(res.net_calls, 0, "no network");
});

domTest("blog: footnotes become Markdown footnotes and metadata comes through", async () => {
  const res = await capture("blog-footnotes");
  const md = res.payload.markdown;
  assert.match(md, /\[\^1\]\n/);
  assert.match(md, /^\[\^2\]: Plot nine has always drained badly/m);
  assert.equal(res.payload.author, "Nell Brightwater");
  assert.equal(res.payload.published.slice(0, 10), "2026-05-02");
  assert.doesNotMatch(md, /Lovely write-up|Nell writes about small gardens/);
});

domTest("a JavaScript app saves what rendered in the tab, and a consent overlay stays out", async () => {
  const shell = await capture("js-shell");
  assert.equal(shell.ok, true);
  assert.ok(shell.payload.markdown.length > 1500, shell.payload.markdown.length);
  const overlay = await capture("cookie-overlay");
  assert.doesNotMatch(overlay.payload.markdown, /We use cookies|Vendor partner/);
  assert.equal(overlay.payload.author, "Bram Oakhollow");
});

domTest("Markdown: tables, nested lists, quotes, images with alt text and safe links", async () => {
  const md = await markdownOf(
    "<h1>T</h1><p>Intro words that are long enough to keep this little test page around for the reader. " +
    "More words follow here so the reader treats it as the article body and not as page chrome.</p>" +
    "<table><thead><tr><th>Site</th><th>Rating</th></tr></thead><tbody><tr><td>Mill | race</td><td>fair</td></tr></tbody></table>" +
    "<ul><li>Outer one<ul><li>Inner one</li></ul></li><li>Outer two</li></ul>" +
    "<ol start=\"3\"><li>Third</li><li>Fourth</li></ol>" +
    "<blockquote><p>Quoted words stay quoted.</p></blockquote>" +
    "<p><img src=\"/img/a.jpg\" alt=\"A quay at dusk\"> <a href=\"javascript:alert(1)\">bad link</a> " +
    "<a href=\"/docs/next\">next page</a> <code>a_b</code> and *stars* stay literal.</p>");
  assert.match(md, /\| Site \| Rating \|\n\| --- \| --- \|\n\| Mill \\\| race \| fair \|/);
  assert.match(md, /- Outer one\n  - Inner one\n- Outer two/);
  assert.match(md, /3\. Third\n4\. Fourth/);
  assert.match(md, /^> Quoted words stay quoted\.$/m);
  assert.match(md, /!\[A quay at dusk\]\(https:\/\/docs\.example\.dev\/img\/a\.jpg\)/);
  assert.match(md, /bad link/);
  assert.doesNotMatch(md, /javascript:/);
  assert.match(md, /\[next page\]\(https:\/\/docs\.example\.dev\/docs\/next\)/);
  assert.match(md, /`a_b`/);
  assert.match(md, /\\\*stars\\\*/);
});

domTest("page capture refuses non-web pages", async () => {
  const { captureHtml } = await import("./reader_capture_bench.mjs");
  const res = captureHtml("<p>x</p>", "file:///C:/notes/page.html");
  assert.equal(res.ok, false);
  assert.equal(res.code, "bad_url");
});
