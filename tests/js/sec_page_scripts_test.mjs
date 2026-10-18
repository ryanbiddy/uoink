// Audit #3: execute the shipped scripts with in-memory DOM, messaging and fetch.
import assert from "node:assert/strict";
import test from "node:test";
import { jsonResponse, makeEnv, settle } from "./ext_fake_env.mjs";

const CORPUS = "PRIVATE synthetic corpus\n![screenshot](data:image/png;base64,c3ludGhldGlj)";
const VIDEO_ID = "abc123def45";
const YOUTUBE = `https://www.youtube.com/watch?v=${VIDEO_ID}`;
const REDDIT = "https://www.reddit.com/r/test/comments/abc123/thread/";
const ARTICLE = "https://x.com/jack/article/1900000000001";
const CAPTURE = { ok: true, yoink_md: "plain synthetic corpus", corpus_md_paste: CORPUS,
  folder: "synthetic-capture", video_count: 1 };
const CAPTURE_TYPES = new Set(["stcExtract", "stcSessionAdd", "stcExtractXArticle"]);

async function content(platform, options = {}) {
  const href = options.href || { youtube: YOUTUBE, reddit: REDDIT, article: ARTICLE }[platform];
  const env = makeEnv({
    href,
    onSend: (msg) => {
      if (msg.type === "stcPing") return { ok: options.online !== false };
      if (CAPTURE_TYPES.has(msg.type)) return { data: CAPTURE };
      if (msg.type === "copyToClipboard" && options.copy) return options.copy(msg);
      return { ok: true };
    },
    // Settings/token reads are fake too; never contact the helper.
    fetch: (url) => {
      const path = new URL(url).pathname;
      if (path === "/token") return jsonResponse({ token: "synthetic-token" });
      if (path === "/settings") return jsonResponse({ ok: true, settings: {} });
      throw new Error(`Unexpected fixture fetch: ${path}`);
    },
  });
  Object.assign(env.store.local, options.local || {});
  const anchor = env.document.createElement("div");
  env.document.body.appendChild(anchor);
  env.document._selectors["#top-level-buttons-computed"] = anchor;
  env.document._selectors['[data-testid="post-container"]'] = anchor;
  if (platform === "article") {
    env.load("lib/x-article.js");
    env.ctx.XArticle = { ...env.ctx.XArticle, parseXArticle: () => ({
      ok: true, url: ARTICLE, title: "Synthetic article", markdown: "Synthetic body", images: [],
    }) };
    env.load("content-x-article.js");
  } else {
    env.load("lib/extract.js");
    env.load("lib/ui.js");
    env.load(platform === "youtube" ? "content.js" : "content-reddit.js");
  }
  await settle();
  env.runIntervals();
  await settle();
  const id = { youtube: "stc-yt-send-to-claude", reddit: "uoink-reddit-btn",
    article: "uoink-x-article-btn" }[platform];
  const btn = env.document.getElementById(id);
  assert.ok(btn, `${platform} injected its real button`);
  return { env, btn };
}

function captures(env) {
  return env.sent.filter((msg) => CAPTURE_TYPES.has(msg.type));
}

const pages = [
  ["YouTube watch", "youtube", YOUTUBE],
  ["YouTube Shorts", "youtube", `https://www.youtube.com/shorts/${VIDEO_ID}`],
  ["mobile YouTube", "youtube", `https://m.youtube.com/watch?v=${VIDEO_ID}`],
  ["Reddit", "reddit", REDDIT],
  ["X article", "article", ARTICLE],
];
for (const [name, platform, href] of pages) {
  test(`${name}: page click()/dispatchEvent() cannot capture; trusted activation can`, async () => {
    const { env, btn } = await content(platform, { href });
    const before = JSON.stringify({ sent: env.sent, store: env.store, fetches: env.fetches });
    btn.click();
    btn.dispatchEvent({ type: "click", isTrusted: false, preventDefault() {}, stopPropagation() {} });
    await settle();
    assert.equal(JSON.stringify({ sent: env.sent, store: env.store, fetches: env.fetches }), before,
      "synthetic clicks must have no extension side effects");
    btn.userClick();
    await settle();
    assert.equal(captures(env).length, 1, "real activation still captures exactly once");
  });
}

test("synthetic YouTube clicks cannot add to a session", async () => {
  const { env, btn } = await content("youtube", {
    local: { active_session: { id: "synthetic-session", name: "Research" } },
  });
  btn.click();
  await settle();
  assert.equal(captures(env).length, 0);
  btn.userClick();
  await settle();
  assert.equal(captures(env).length, 1);
  assert.equal(captures(env)[0].type, "stcSessionAdd");
});

for (const platform of ["youtube", "reddit", "article"]) {
  test(`${platform}: synthetic clicks cannot open setup when offline`, async () => {
    const { env, btn } = await content(platform, { online: false });
    const before = env.sent.length;
    btn.click();
    await settle();
    assert.equal(env.sent.length, before);
    btn.userClick();
    await settle();
    assert.equal(env.setupTabsOpened().length, 1);
  });
}

for (const platform of ["youtube", "reddit", "article"]) {
  test(`${platform}: explicit extension storage handoff still captures once`, async () => {
    const auto = platform === "youtube" ? { videoId: VIDEO_ID }
      : { url: platform === "reddit" ? REDDIT : ARTICLE };
    const { env } = await content(platform, { local: { auto_yoink: { ...auto, ts: Date.now() } } });
    assert.equal(captures(env).length, 1);
    assert.equal(env.store.local.auto_yoink, undefined);
    env.mutate();
    env.runIntervals();
    await settle();
    assert.equal(captures(env).length, 1);
  });
}

test("YouTube shortcut still captures without a synthetic button click", async () => {
  const { env, btn } = await content("youtube");
  btn.click = () => { throw new Error("Extension shortcut must bypass the page event"); };
  assert.deepEqual(await env.dispatch({ type: "uoinkShortcutTriggered" }), { success: true });
  await settle();
  assert.equal(captures(env).length, 1);
});

for (const sender of [null, {}, { id: "other-extension" }]) {
  test(`YouTube shortcut rejects untrusted sender ${JSON.stringify(sender)}`, async () => {
    const { env } = await content("youtube");
    assert.equal(await env.dispatch({ type: "uoinkShortcutTriggered" }, sender), undefined);
    await settle();
    assert.equal(captures(env).length, 0);
  });
}

async function worker(options = {}) {
  const offscreen = makeEnv();
  offscreen.ctx.matchMedia = () => ({ matches: false, addEventListener() {} });
  const sink = offscreen.document.createElement("textarea");
  sink.id = "sink";
  sink.focus = () => {};
  sink.select = () => {};
  offscreen.document.body.appendChild(sink);
  const writes = [];
  offscreen.document.execCommand = (command) => {
    assert.equal(command, "copy");
    writes.push(sink.value);
    if (options.throwCopy) throw new Error("Synthetic clipboard failure");
    return options.copyOk !== false;
  };
  offscreen.load("offscreen.js");
  const env = makeEnv({
    fetch: (url) => new URL(url).pathname === "/token"
      ? jsonResponse({ token: "synthetic-token" }) : jsonResponse({ ok: true }),
    onSend: (msg) => {
      if (msg.target !== "offscreen") throw new Error("Unexpected worker message");
      if (msg.type === "copy" && options.missingReply) return undefined;
      return offscreen.dispatch(msg);
    },
  });
  env.chrome.offscreen = {
    hasDocument: async () => !options.creationFails,
    createDocument: async () => { throw new Error("Synthetic offscreen failure"); },
  };
  env.load("background.js");
  await settle();
  return { env, writes, sink };
}

function watchPageClipboard(env) {
  const observed = { nativeWrites: [], insertedValues: [], execCalls: [] };
  env.ctx.navigator.clipboard.writeText = async (text) => {
    observed.nativeWrites.push(text);
    throw new Error("Synthetic page clipboard rejection");
  };
  const create = env.document.createElement.bind(env.document);
  env.document.createElement = (tag) => {
    const el = create(tag);
    el.select = () => {};
    return el;
  };
  const append = env.document.body.appendChild.bind(env.document.body);
  env.document.body.appendChild = (el) => {
    observed.insertedValues.push(el.value || el.textContent);
    return append(el);
  };
  env.document.body.removeChild = (el) => el.remove();
  env.document.execCommand = (cmd) => { observed.execCalls.push(cmd); return true; };
  return observed;
}

for (const [name, options, copied] of [
  ["success", {}, true],
  ["clipboard denied", { copyOk: false }, false],
  ["clipboard throws", { throwCopy: true }, false],
  ["offscreen creation fails", { creationFails: true }, false],
  ["offscreen reply missing", { missingReply: true }, false],
  ["worker port closes", { portCloses: true }, false],
]) {
  test(`YouTube copy via worker/offscreen: ${name}; corpus never enters page DOM`, async () => {
    const background = await worker(options);
    const { env, btn } = await content("youtube", { copy: (msg) => options.portCloses
      ? { __reject: "Synthetic closed worker port" } : background.env.dispatch(msg) });
    const observed = watchPageClipboard(env);
    btn.userClick();
    await settle();
    assert.deepEqual(observed.insertedValues, [], "no corpus-bearing node, even transiently");
    assert.deepEqual(observed.nativeWrites, [], "copy is confined to extension contexts");
    assert.deepEqual(observed.execCalls, [], "no page execCommand fallback");
    assert.equal(env.sent.filter((msg) => msg.type === "copyToClipboard").length, 1);
    if (copied) {
      assert.deepEqual(background.writes, [CORPUS]);
      assert.equal(background.sink.value, "");
      assert.ok(env.sent.some((msg) => msg.type === "openTab" && msg.url === "https://claude.ai/new"));
      assert.ok(env.store.local.yoink_last_clipboard_at);
      assert.equal(env.sent.filter((msg) => msg.type === "clipboardRetry").length, 0);
    } else {
      assert.match(btn.textContent, /Copy blocked/);
      assert.deepEqual(env.sent.filter((msg) => msg.type === "clipboardRetry"),
        [{ type: "clipboardRetry", text: CORPUS }]);
      assert.equal(env.sent.filter((msg) => msg.type === "openTab").length, 0);
      assert.equal(env.store.local.yoink_last_clipboard_at, undefined);
    }
  });
}

const allowedTabs = [
  "chrome-extension://test-extension-id/setup.html?source=offline",
  "chrome-extension://test-extension-id/popup.html",
  "https://claude.ai/new", "https://chatgpt.com", "https://chatgpt.com/",
  "http://127.0.0.1:5179/dashboard",
  "http://127.0.0.1:5179/dashboard?tab=foryou#recent",
];
test("openTab keeps the explicit destinations working", async () => {
  const { env } = await worker();
  for (const url of allowedTabs) {
    const before = env.tabsCreated.length;
    assert.equal((await env.dispatch({ type: "openTab", url })).ok, true, url);
    assert.equal(env.tabsCreated.length, before + 1);
    assert.equal(new URL(env.tabsCreated.at(-1).url).href, new URL(url).href);
  }
});

const blockedTabs = [
  undefined, null, false, 123, {}, [], "", "not a URL", "/popup.html", "//claude.ai/new",
  "javascript:alert(1)", "data:text/html,test", "file:///synthetic.txt", "about:blank",
  "chrome://settings", "https://attacker.test/", "http://claude.ai/new",
  "https://claude.ai.evil.test/new", "https://claude.ai@evil.test/new",
  "https://evil.test@claude.ai/new", "https://claude.ai:444/new", "https://claude.ai/new/evil",
  "https://claude.ai/new/../settings", "https://claude.ai/", "https://claude.ai/newish",
  "https://chatgpt.com.evil.test/", "http://chatgpt.com/", "https://chatgpt.com:444/",
  "https://chatgpt.com/other", "https://evil.test@chatgpt.com/",
  "chrome-extension://other-extension/popup.html",
  "chrome-extension://test-extension-id.evil.test/popup.html",
  "chrome-extension://evil@test-extension-id/popup.html",
  "chrome-extension://test-extension-id:80/popup.html",
  "http://127.0.0.1:5179/settings", "http://127.0.0.1:5179/dashboard-evil",
  "http://127.0.0.1:5179/dashboard/../settings", "http://127.0.0.1:5180/dashboard",
  "http://127.0.0.1:5179@evil.test/dashboard", "http://evil@127.0.0.1:5179/dashboard",
  "http://127.0.0.1.evil.test:5179/dashboard", "http://localhost:5179/dashboard",
  "https://127.0.0.1:5179/dashboard", "https://claude.ai/ne\nw",
];
for (const url of blockedTabs) {
  test(`openTab blocks ${JSON.stringify(url)}`, async () => {
    const { env } = await worker();
    const before = env.tabsCreated.length;
    const reply = await env.dispatch({ type: "openTab", url });
    assert.equal(env.tabsCreated.length, before, "rejected URL must never reach tabs.create");
    assert.equal(reply?.ok, false, "invalid destinations fail explicitly");
  });
}
