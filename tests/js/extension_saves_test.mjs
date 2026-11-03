// No browser, credentials, helper, timers or network: all inputs are synthetic.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import vm from "node:vm";
import { EXT, makeEnv, settle } from "./ext_fake_env.mjs";

const STAGED_URL = "uoink-saves:0123456789abcdef";
const clone = (value) => JSON.parse(JSON.stringify(value));
const videoId = (n) => `v${String(n).padStart(10, "0")}`;

function parsers() {
  const context = vm.createContext({ URL, __UOINK_SAVES_TEST__: true });
  vm.runInContext(readFileSync(join(EXT, "content-saves.js"), "utf8"), context);
  const { parseYouTubeId, normalizeXStatus, normalizeRedditPermalink } = context.__UOINK_SAVES_HELPERS__;
  for (const url of ["/watch?v=abc123def45&list=WL", "https://www.youtube.com/watch?list=WL&v=abc123def45",
    "https://m.youtube.com/watch?v=abc123def45#t=1"]) assert.equal(parseYouTubeId(url), "abc123def45");
  assert.equal(parseYouTubeId("/watch?v=abc123DEF_-"), "abc123DEF_-");
  for (const url of [null, 3, "", "/watch?v=short", "/watch?v=abc123def45x", "/watch?v=abc123def4!",
    "/playlist?list=WL", "/shorts/abc123def45", "https://evil.test/watch?v=abc123def45",
    "javascript:alert(1)", "https://www.youtube.com@evil.test/watch?v=abc123def45",
    "https://www.youtube.com:8000/watch?v=abc123def45", "https://user@www.youtube.com/watch?v=abc123def45"])
    assert.equal(parseYouTubeId(url), null, String(url));

  for (const url of ["/Some_User/status/123", "https://x.com/Some_User/status/123?x=1",
    "https://twitter.com/Some_User/status/123/", "https://www.twitter.com/Some_User/status/123#x"])
    assert.equal(normalizeXStatus(url), "https://x.com/Some_User/status/123");
  for (const url of [null, "", "/a/status/123/photo/1", "/a/status/123/analytics", "/a/status/123/video/1",
    "/a/status/nope", "/a/article/123", "/i/bookmarks", "/abcdefghijklmnop/status/1",
    "https://x.com.evil.test/a/status/123", "https://evil.test/a/status/123",
    "https://user@x.com/a/status/123", "http://x.com/a/status/123", "//evil.test/a/status/123"])
    assert.equal(normalizeXStatus(url), null, String(url));

  for (const url of ["/r/test/comments/ab12/synthetic_title", "https://old.reddit.com/r/test/comments/ab12/synthetic_title/?sort=new",
    "https://reddit.com/r/test/comments/ab12/synthetic_title/#comment"])
    assert.equal(normalizeRedditPermalink(url), "https://www.reddit.com/r/test/comments/ab12/synthetic_title/");
  assert.equal(normalizeRedditPermalink("/r/test/comments/ab12/title/cd34?context=3"),
    "https://www.reddit.com/r/test/comments/ab12/title/cd34/");
  for (const url of [null, "", "/user/test/saved", "/r/test/", "/r/test/comments/ab12/../",
    "/r/test/comments/ab12/title/comment/extra", "/r/test/comments/ab!2/title/",
    "https://reddit.com.evil.test/r/test/comments/ab12/title/", "https://evil.test/r/test/comments/ab12/title/",
    "https://user@www.reddit.com/r/test/comments/ab12/title/", "http://www.reddit.com/r/test/comments/ab12/title/"])
    assert.equal(normalizeRedditPermalink(url), null, String(url));
}

function collectorEnv(href, onSend = () => ({ ok: false, error: "Synthetic helper error" })) {
  const env = makeEnv({ href, onSend });
  let now = 0;
  const due = new Map();
  const win = new Map();
  const doc = new Map();
  const nav = new Map();
  const listen = (map, type, fn) => map.set(type, [...(map.get(type) || []), fn]);
  env.fire = (type, event = {}, target = win) => {
    for (const fn of target.get(type) || []) fn({ type, isTrusted: true, ...event });
  };
  env.documentEvent = (type) => env.fire(type, {}, doc);
  env.enableNavigation = () => {
    env.ctx.navigation = { addEventListener: (type, fn) => listen(nav, type, fn) };
  };
  env.ctx.addEventListener = (type, fn) => listen(win, type, fn);
  env.document.addEventListener = (type, fn) => listen(doc, type, fn);
  env.ctx.Date = class extends Date { static now() { return now; } };
  env.ctx.location = new URL(href);
  env.ctx.scrollY = 0;
  env.ctx.innerHeight = 1000;
  env.scrolls = [];
  env.ctx.scrollBy = (options) => {
    env.scrolls.push(options);
    env.ctx.scrollY += options.top;
    env.fire("scroll");
  };
  env.ctx.setTimeout = (fn, ms = 0) => {
    const id = env.nextTimer++;
    env.timeouts.set(id, fn);
    due.set(id, now + ms);
    return id;
  };
  env.advance = (ms) => {
    now += ms;
    for (const [id, fn] of [...env.timeouts]) {
      if (due.get(id) > now) continue;
      env.timeouts.delete(id);
      due.delete(id);
      fn();
    }
  };
  env.tick = (ms) => {
    env.advance(ms);
    for (const [id, fn] of [...env.intervals]) {
      if (env.intervalDelays.get(id) === ms) fn();
    }
  };
  env.ctx.MutationObserver = class {
    constructor(callback) { this.callback = callback; this.active = false; env.observers.push(this); }
    observe(target, options) { this.active = true; this.target = target; this.options = options; }
    disconnect() { this.active = false; }
  };
  env.mutate = (target = env.document.body) => {
    for (const observer of env.observers) if (observer.active) observer.callback([{ target }]);
  };
  const create = env.document.createElement.bind(env.document);
  env.shadows = new Map();
  env.document.createElement = (tag) => {
    const node = create(tag);
    const attrs = new Map();
    node.setAttribute = (name, value) => attrs.set(name, String(value));
    node.getAttribute = (name) => attrs.get(name) ?? null;
    node.contains = (other) => node === other || node._all().includes(other);
    node.attachShadow = (options) => {
      assert.deepEqual(clone(options), { mode: "closed" });
      const shadow = create("shadow-root");
      env.shadows.set(node, shadow);
      node.shadowRoot = null;
      return shadow;
    };
    return node;
  };
  env.document.documentElement = create("html");
  env.document.documentElement.appendChild(env.document.head);
  env.document.documentElement.appendChild(env.document.body);
  env.rows = [];
  env.scans = 0;
  env.document.querySelectorAll = () => { env.scans++; return env.rows; };
  env.host = () => env.document.documentElement._all().find((node) => node.id === "uoink-saves-host");
  // Test-only access to roots captured by attachShadow; page queries cannot see them.
  env.control = (name) => env.shadows.get(env.host())?._all()
    .find((node) => node.className === `uoink-saves-${name}`);
  env.navigate = (url, event = "poll") => {
    env.ctx.location = new URL(url);
    if (event === "yt-navigate-finish") env.documentEvent(event);
    else if (event === "popstate") env.fire(event);
    else if (event === "navigatesuccess") env.fire(event, {}, nav);
    else env.tick(1000);
  };
  return env;
}

function youtubeRow(id) {
  const link = {
    textContent: "Synthetic video", getAttribute: (key) => key === "href" ? `/watch?v=${id}` : "Synthetic title",
  };
  return {
    querySelectorAll: () => [link],
    querySelector: () => assert.fail("Watch Later must not scrape unused metadata"),
  };
}

function tweetRow(href, quotedHref) {
  const row = {};
  const time = (url, owner) => ({ closest: (selector) => selector === 'article[data-testid="tweet"]'
    ? owner : { getAttribute: () => url } });
  row.querySelectorAll = () => [
    ...(quotedHref ? [time(quotedHref, {})] : []), time(href, row),
  ];
  return row;
}

async function collectors() {
  const youtube = collectorEnv("https://www.youtube.com/playlist?list=PL_else");
  youtube.rows = [youtubeRow(videoId(1)), youtubeRow(videoId(1)), youtubeRow("bad")];
  youtube.load("content-saves.js");
  assert.equal(youtube.control("panel"), undefined);
  assert.equal(youtube.scans, 0);
  youtube.navigate("https://www.youtube.com/playlist?list=WL", "yt-navigate-finish");
  assert.equal(youtube.control("heading").textContent, "Uoink: 1 Watch Later videos found");
  assert.equal(youtube.host().parentElement, youtube.document.documentElement);
  assert.equal(youtube.host().shadowRoot, null);
  assert.match(youtube.host().style.cssText, /position:\s*fixed\s*!important/);
  assert.match(youtube.host().style.cssText, /right:\s*20px/);
  assert.match(youtube.host().style.cssText, /bottom:\s*20px/);
  assert.match(youtube.host().style.cssText, /z-index:\s*2147483647\s*!important/);
  assert.equal(youtube.document.head.childNodes.length, 0, "styles stay inside the shadow root");
  assert.equal(youtube.shadows.get(youtube.host()).children[0].tagName, "STYLE");
  assert.ok(!youtube.document.documentElement._all().includes(youtube.control("panel")));
  assert.equal(youtube.observers.at(-1).options.characterData, false);
  const before = youtube.scans;
  youtube.rows.push(youtubeRow(videoId(2)));
  youtube.mutate(); youtube.mutate(); youtube.mutate();
  assert.equal(youtube.timeouts.size, 1);
  youtube.advance(499);
  assert.equal(youtube.scans, before);
  youtube.advance(1);
  assert.equal(youtube.scans, before + 1);
  assert.equal(youtube.control("heading").textContent, "Uoink: 2 Watch Later videos found");
  youtube.mutate(youtube.control("heading"));
  assert.equal(youtube.timeouts.size, 0, "panel updates do not trigger rescans");
  youtube.control("send").click(); // Synthetic page clicks are not user intent.
  assert.equal(youtube.sent.length, 0);
  youtube.control("send").userClick();
  await settle();
  assert.deepEqual(youtube.sent, [{ type: "stcStageSaves", source: "watch_later", items: [videoId(1), videoId(2)] }]);
  youtube.navigate("https://www.youtube.com/watch?v=abc123def45", "yt-navigate-finish");
  assert.equal(youtube.control("panel"), undefined);
  assert.ok(youtube.observers.every((observer) => !observer.active));
  youtube.navigate("https://www.youtube.com/playlist?list=WL", "popstate");
  youtube.control("close").userClick();
  youtube.tick(1000);
  assert.equal(youtube.control("panel"), undefined, "close persists on the same saves page");
  youtube.navigate("https://www.youtube.com/playlist?list=PL_else");
  youtube.navigate("https://www.youtube.com/playlist?list=WL");
  assert.ok(youtube.control("panel"), "leaving and returning resets close");

  const clobbered = collectorEnv("https://www.youtube.com/playlist?list=WL");
  clobbered.ctx.__UOINK_SAVES_TEST__ = clobbered.document.createElement("div");
  clobbered.ctx.__UOINK_SAVES_TEST__.id = "__UOINK_SAVES_TEST__";
  clobbered.document.body.appendChild(clobbered.ctx.__UOINK_SAVES_TEST__);
  clobbered.load("content-saves.js");
  assert.ok(clobbered.control("panel"), "a named page element cannot enable the test hook");
  assert.equal(clobbered.ctx.__UOINK_SAVES_HELPERS__, undefined);

  const x = collectorEnv("https://twitter.com/i/bookmarks");
  x.enableNavigation();
  x.rows = [tweetRow("/author/status/123", "/quoted/status/456"), tweetRow("https://x.com/renamed/status/123"),
    tweetRow("/author/status/999/photo/1", "/quoted/status/789"), tweetRow("/author/status/124?ref=bookmarks")];
  x.load("content-saves.js");
  assert.equal(x.control("heading").textContent, "Uoink: 2 bookmarks found");
  assert.equal(x.sent.length, 0);
  x.control("send").userClick();
  await settle();
  assert.deepEqual(x.sent[0].items, ["https://x.com/author/status/123", "https://x.com/author/status/124"]);
  x.navigate("https://twitter.com/home", "navigatesuccess");
  assert.equal(x.control("panel"), undefined);
  x.navigate("https://twitter.com/i/bookmarks", "navigatesuccess");
  assert.ok(x.control("panel"));

  for (const host of ["www.reddit.com", "old.reddit.com"]) {
    for (const selector of ["main", "#siteTable", "shreddit-feed", null]) {
      const reddit = collectorEnv(`https://${host}/user/synthetic/saved`);
      const post = "/r/test/comments/abc/title/";
      const row = (attribute, url) => ({ getAttribute: (name) => name === attribute ? url : null });
      reddit.rows = [row("permalink", post), row("data-permalink", post), row("href", post + "def?context=3"),
        row("href", "/r/test/comments/ABC/another_title/"), row("href", "/user/synthetic/saved")];
      if (selector) {
        const feedRows = reddit.rows;
        reddit.document._selectors[selector] = { querySelectorAll: () => feedRows };
        reddit.rows = [...feedRows, row("href", "/r/sidebar/comments/999/not_saved/")];
      }
      reddit.load("content-saves.js");
      assert.equal(reddit.control("heading").textContent, "Uoink: 2 saved posts found");
      reddit.control("send").userClick();
      await settle();
      assert.deepEqual(reddit.sent[0].items, ["https://www.reddit.com" + post, "https://www.reddit.com" + post + "def/"]);
      const oldSend = reddit.control("send");
      reddit.ctx.location = new URL(`https://${host}/user/another/saved`);
      oldSend.userClick();
      assert.equal(reddit.sent.length, 1, "a stale panel cannot send a different page's saves");
      assert.equal(reddit.control("progress").textContent, "");
      assert.equal(reddit.fetches.length, 0);
      reddit.control("close").userClick();
      reddit.navigate(`https://${host}/user/synthetic/saved`);
      assert.ok(reddit.control("panel"), "another saves page resets close");
    }
  }
  assert.equal(youtube.fetches.length + x.fetches.length, 0);
}

function scroll() {
  const env = collectorEnv("https://www.youtube.com/playlist?list=WL");
  env.rows = [youtubeRow(videoId(1))];
  env.load("content-saves.js");
  const scrolling = () => [...env.intervalDelays.values()].includes(2500);
  assert.equal(scrolling(), false);
  env.control("scroll").click();
  assert.equal(scrolling(), false);
  env.control("scroll").userClick();
  assert.equal(scrolling(), true);
  assert.equal(env.scrolls[0].top, 900);
  assert.equal(env.control("scrolling").textContent, "Scrolling... 1 found");
  for (let n = 0; n < 3; n++) env.tick(2500);
  assert.equal(scrolling(), true);
  env.tick(2500);
  assert.equal(scrolling(), false, "four idle steps stop scrolling");
  assert.equal(env.scrolls.length, 4);
  env.control("scroll").userClick();
  env.tick(2500); env.tick(2500);
  env.rows.push(youtubeRow(videoId(2)));
  env.mutate(); env.advance(500); env.tick(2500);
  env.tick(2500); env.tick(2500);
  assert.equal(scrolling(), true, "new items reset the idle counter");
  env.control("scroll").userClick();
  assert.equal(scrolling(), false, "Stop stops immediately");
  env.control("scroll").userClick();
  env.ctx.scrollY -= 100;
  env.fire("scroll");
  assert.equal(scrolling(), false, "scrolling up takes control back");
  env.control("scroll").userClick();
  env.fire("wheel", { deltaY: -10 });
  assert.equal(scrolling(), false);
  env.control("scroll").userClick();
  env.document.hidden = true;
  env.documentEvent("visibilitychange");
  assert.equal(scrolling(), false, "hiding the tab stops auto-scroll");
  const scans = env.scans;
  const panel = env.control("panel");
  env.mutate(); env.advance(500);
  env.navigate("https://www.youtube.com/");
  assert.equal(env.control("panel"), panel, "the hidden-tab poll does not sync the page");
  assert.equal(env.scans, scans, "hidden tabs do not collect");
  env.document.hidden = false;
  env.documentEvent("visibilitychange");
  assert.equal(env.control("panel"), undefined, "becoming visible syncs navigation immediately");
  env.navigate("https://www.youtube.com/playlist?list=WL");
  env.control("scroll").userClick();
  env.navigate("https://www.youtube.com/", "yt-navigate-finish");
  assert.equal(scrolling(), false);
  env.navigate("https://www.youtube.com/playlist?list=WL");
  env.control("scroll").userClick();
  env.rows = Array.from({ length: 5001 }, (_, n) => youtubeRow(videoId(n)));
  env.mutate(); env.advance(500);
  assert.equal(scrolling(), false, "5,000 collected items stop scrolling");
  assert.equal(env.control("heading").textContent, "Uoink: 5000 Watch Later videos found");
  assert.equal(env.sent.length, 0, "auto-scroll never sends");
  env.control("send").userClick();
  assert.equal(env.sent[0].items.length, 5000);
}

async function requests() {
  let answer;
  const env = collectorEnv("https://www.youtube.com/playlist?list=WL", () => new Promise((resolve) => { answer = resolve; }));
  env.rows = Array.from({ length: 61 }, (_, n) => youtubeRow(videoId(n)));
  env.load("content-saves.js");
  assert.equal(env.sent.length, 0);
  env.control("send").userClick();
  for (const control of ["send", "next", "scroll"]) assert.equal(env.control(control).disabled, true);
  assert.equal(env.control("close").disabled, false);
  await settle();
  answer({ ok: true, url: STAGED_URL, count: 61, total: 61, found: 50, next_offset: 50, message: "Queued 50 videos." });
  await settle();
  assert.equal(env.control("status").textContent, "Queued 50 videos.");
  assert.equal(env.control("progress").textContent, "50 of 61 sent");
  assert.equal(env.control("next").hidden, false);
  assert.equal(env.sent.length, 1, "the next batch needs another click");
  env.rows.push(youtubeRow(videoId(61)));
  env.mutate(); env.advance(500);
  assert.equal(env.control("progress").textContent, "50 of 61 sent", "stage total stays fixed");
  assert.equal(env.control("send").disabled, true);
  env.control("next").userClick();
  await settle();
  assert.deepEqual(env.sent[1], { type: "stcImportNext", url: STAGED_URL, offset: 50 });
  answer({ ok: false, error: "Uoink app isn't running" });
  await settle();
  assert.equal(env.control("status").textContent, "Uoink app isn't running");
  assert.equal(env.control("progress").textContent, "50 of 61 sent");
  assert.equal(env.control("next").disabled, false);
  env.control("next").userClick();
  await settle();
  assert.equal(env.sent[2].offset, 50);
  answer({ ok: true, total: 61, found: 11, queued: 5, skipped: 6, next_offset: null, message: "Queued 5 videos, 6 already in your library." });
  await settle();
  assert.equal(env.control("progress").textContent, "61 of 61 sent");
  assert.equal(env.control("next").hidden, true);
  assert.equal(env.control("send").disabled, false, "newly collected items can be staged after completion");

  env.control("send").userClick();
  await settle();
  env.navigate("https://www.youtube.com/");
  env.navigate("https://www.youtube.com/playlist?list=WL");
  answer({ ok: true, url: STAGED_URL, total: 62, found: 50, next_offset: 50 });
  await settle();
  assert.equal(env.control("progress").textContent, "", "a response cannot overwrite a new page's state");
  assert.equal(env.control("send").disabled, false);

  let retryResult = {
    ok: false, url: STAGED_URL, total: 1, count: 1, next_offset: 0, error: "Uoink app isn't running",
  };
  const retry = collectorEnv("https://x.com/i/bookmarks", () => retryResult);
  retry.rows = [tweetRow("/a/status/123")];
  retry.load("content-saves.js");
  retry.control("send").userClick();
  await settle();
  assert.equal(retry.control("next").hidden, true, "Next needs a successful batch");
  assert.equal(retry.control("send").textContent, "Retry");
  assert.equal(retry.control("send").disabled, false);
  retry.control("send").userClick();
  await settle();
  assert.deepEqual(retry.sent[1], { type: "stcImportNext", url: STAGED_URL, offset: 0 });
  assert.equal(retry.control("send").textContent, "Retry", "a failed retry keeps the staged list");
  assert.equal(retry.control("next").hidden, true);
  retryResult = { ok: true, total: "73", found: "50", next_offset: 50 };
  retry.control("send").userClick();
  await settle();
  assert.deepEqual(retry.sent[2], { type: "stcImportNext", url: STAGED_URL, offset: 0 });
  assert.equal(retry.control("progress").textContent, "50 of 73 sent");
  assert.equal(retry.control("next").hidden, false);
  retryResult = { ok: true, total: "73", found: "2", next_offset: null };
  retry.control("next").userClick();
  await settle();
  assert.equal(retry.control("progress").textContent, "52 of 73 sent", "counts are added numerically");
  assert.equal(retry.sent.filter(({ type }) => type === "stcStageSaves").length, 1);

  for (const nextOffset of [undefined, null, -1, 1.5, "50", {}, Number.MAX_SAFE_INTEGER + 1]) {
    const malformed = collectorEnv("https://www.youtube.com/playlist?list=WL", () => ({
      ok: true, url: STAGED_URL, total: "invalid", next_offset: nextOffset,
    }));
    malformed.rows = [youtubeRow(videoId(1))];
    malformed.load("content-saves.js");
    malformed.control("send").userClick();
    await settle();
    assert.equal(malformed.control("progress").textContent, "0 of 0 sent");
    assert.equal(malformed.control("next").hidden, true, "invalid offsets cannot enable Next");
  }

  for (const closeNext of [false, true]) {
    let resolveLate;
    const closing = collectorEnv("https://www.youtube.com/playlist?list=WL", (message) => {
      if (closeNext && message.type === "stcStageSaves") {
        return { ok: true, url: STAGED_URL, total: 61, found: 50, next_offset: 50 };
      }
      return new Promise((resolve) => { resolveLate = resolve; });
    });
    closing.rows = [youtubeRow(videoId(1))];
    closing.load("content-saves.js");
    closing.control("send").userClick();
    await settle();
    if (closeNext) { closing.control("next").userClick(); await settle(); }
    assert.equal(closing.control("close").disabled, false);
    closing.control("close").userClick();
    assert.equal(closing.host(), undefined);
    resolveLate({ ok: true, url: STAGED_URL, total: 61, found: 11, next_offset: null });
    await settle();
    closing.tick(1000);
    assert.equal(closing.host(), undefined, "a late response cannot reopen the closed panel");
    closing.navigate("https://www.youtube.com/");
    closing.navigate("https://www.youtube.com/playlist?list=WL");
    assert.equal(closing.control("progress").textContent, "");
    assert.equal(closing.control("send").disabled, false);
  }
}

async function background() {
  const env = makeEnv();
  env.load("background.js");
  await settle();
  const calls = [];
  let stage = { ok: true, url: STAGED_URL, count: 72, label: "Watch Later", truncated: false };
  let imported = { ok: true, queued: 45, already_queued: 3, skipped: 2, found: 50, total: 72,
    next_offset: 50, message: "Queued 45 videos." };
  env.ctx.STC.postStageSaves = async (...args) => { calls.push(["stage", ...clone(args)]); return stage; };
  env.ctx.STC.postImportList = async (...args) => {
    calls.push(["import", ...clone(args)]);
    if (imported instanceof Error) throw imported;
    return imported;
  };
  const sender = (url = "https://www.youtube.com/playlist?list=WL") => ({
    id: env.chrome.runtime.id, frameId: 0, url, origin: new URL(url).origin, tab: { id: 1, url },
  });
  const message = { type: "stcStageSaves", source: "watch_later", items: [videoId(1)] };
  assert.deepEqual(await env.dispatch(message, sender()), { ...stage, ...imported });
  assert.deepEqual(calls, [["stage", "watch_later", [videoId(1)], null], ["import", STAGED_URL, 0, 50]]);
  for (const [source, url] of [["x_bookmarks", "https://x.com/i/bookmarks"],
    ["x_bookmarks", "https://twitter.com/i/bookmarks"], ["reddit_saved", "https://www.reddit.com/user/a/saved"],
    ["reddit_saved", "https://old.reddit.com/user/a/saved"],
    ["watch_later", "https://www.youtube.com/playlist/?list=WL&index=1"],
    ["x_bookmarks", "https://x.com/i/bookmarks/"],
    ["reddit_saved", "https://www.reddit.com/user/a_b-1/saved/"]]) {
    assert.equal((await env.dispatch({ ...message, source }, sender(url))).ok, true);
    assert.equal((await env.dispatch({ type: "stcImportNext", url: STAGED_URL, offset: 0 }, sender(url))).ok, true);
  }
  const before = calls.length;
  const badSenders = [sender("https://evil.test/"), sender("http://x.com/i/bookmarks"),
    sender("https://www.youtube.com.evil.test/"), sender("https://www.youtube.com:8000/"),
    sender("https://www.youtube.com/watch?v=abc123def45&list=WL"),
    sender("https://www.youtube.com/playlist?list=PL_else"), sender("https://www.youtube.com/playlist"),
    sender("https://x.com/home"), sender("https://twitter.com/i/bookmarks/extra"),
    sender("https://www.reddit.com/user/a"), sender("https://old.reddit.com/user/a/saved/extra"),
    sender("https://www.reddit.com/user//saved"),
    sender("https://user@www.youtube.com/"), { ...sender(), tab: undefined },
    { ...sender(), frameId: 1 }, { ...sender(), origin: "null" },
    { ...sender(), url: undefined }, { ...sender(), tab: { id: 1, url: "https://evil.test/" } },
    { ...sender(), tab: { id: 1, url: "https://www.youtube.com/" } }];
  for (const bad of badSenders) {
    assert.equal((await env.dispatch(message, bad)).ok, false);
    assert.equal((await env.dispatch({ type: "stcImportNext", url: STAGED_URL, offset: 50 }, bad)).ok, false);
  }
  assert.equal(await env.dispatch(message, { ...sender(), id: "foreign" }), undefined);
  for (const bad of [{ ...message, source: "__proto__" }, { ...message, source: {} },
    { ...message, source: "x_bookmarks" }, { ...message, items: "bad" }, { ...message, items: [] },
    { ...message, items: [null] }, { ...message, items: [{ id: "bad" }] },
    { ...message, items: ["x".repeat(301)] }, { ...message, items: Array(5001).fill("x") }])
    assert.equal((await env.dispatch(bad, sender())).ok, false);
  for (const bad of [{ url: "https://evil.test", offset: 0 }, { url: "uoink-saves:ABCDEF0123456789", offset: 0 },
    { url: STAGED_URL + "\n", offset: 0 }, { url: STAGED_URL, offset: -1 },
    { url: STAGED_URL, offset: 1.5 }, { url: STAGED_URL, offset: "50" },
    { url: STAGED_URL, offset: 100001 }, { url: STAGED_URL, offset: Number.MAX_SAFE_INTEGER }])
    assert.equal((await env.dispatch({ type: "stcImportNext", ...bad }, sender())).ok, false);
  assert.equal(calls.length, before, "invalid messages never call the helper");
  await env.dispatch({ type: "stcImportNext", url: STAGED_URL, offset: 50 }, sender());
  assert.deepEqual(calls.at(-1), ["import", STAGED_URL, 50, 50]);
  await env.dispatch({ type: "stcImportNext", url: STAGED_URL, offset: 100000 }, sender());
  assert.deepEqual(calls.at(-1), ["import", STAGED_URL, 100000, 50]);
  stage = { ok: false, error: "No valid saves", http_status: 400 };
  assert.deepEqual(await env.dispatch(message, sender()), stage);
  assert.equal(calls.at(-1)[0], "stage");
  stage = { ok: true, url: "https://evil.test" };
  assert.equal((await env.dispatch(message, sender())).ok, false);
  assert.equal(calls.at(-1)[0], "stage");
  stage = { ok: true, url: STAGED_URL, count: 72 };
  imported = new TypeError("Failed to fetch");
  assert.deepEqual(await env.dispatch(message, sender()), {
    ok: false, url: STAGED_URL, count: 72, total: 72, next_offset: 0, error: "Uoink app isn't running",
  });
  assert.equal((await env.dispatch({ type: "stcImportNext", url: STAGED_URL, offset: 50 }, sender())).error,
    "Uoink app isn't running");
  imported = { ok: false, error: "Synthetic helper error", http_status: 503 };
  assert.equal((await env.dispatch(message, sender())).error, "Synthetic helper error");

  for (const values of [Array.from({ length: 5000 }, (_, n) => videoId(n)),
    Array(750).fill("x".repeat(300)), Array(150).fill('"\\\n'.repeat(100))]) {
    calls.length = 0;
    let total = 0;
    env.ctx.STC.postStageSaves = async (source, items, appendTo) => {
      const body = { source, items, ...(appendTo ? { append_to: appendTo } : {}) };
      assert.ok(JSON.stringify(body).length < 60000, "each full JSON body stays below the cap");
      assert.ok(Buffer.byteLength(JSON.stringify(body)) < 60000);
      assert.ok(items.length > 0 && items.length <= 500);
      assert.equal(appendTo, total ? STAGED_URL : undefined);
      total += items.length;
      calls.push(["stage", clone(body)]);
      return { ok: true, url: STAGED_URL, count: total };
    };
    imported = { ok: true, total: values.length, found: 50, next_offset: 50 };
    const result = await env.dispatch({ ...message, items: values }, sender());
    assert.equal(result.ok, true);
    assert.equal(result.url, STAGED_URL);
    assert.equal(result.count, values.length, "the final stage response supplies the accumulated count");
    assert.deepEqual(calls.at(-1), ["import", STAGED_URL, 0, 50]);
    assert.equal(calls.filter(([op]) => op === "import").length, 1);
    assert.deepEqual(calls.slice(0, -1).flatMap(([, body]) => body.items), values);
    if (values.length === 5000) assert.equal(calls.length, 11, "5,000 IDs need ten 500-item chunks");
    else assert.ok(calls.length > 2, "long or escaped items must split before 500 items");
  }

  const chunks = Array.from({ length: 1200 }, (_, n) => videoId(n));
  for (const failure of [{ ok: false, error: "Append rejected", http_status: 413 },
    new TypeError("Failed to fetch"), null, { ok: true, url: "uoink-saves:fedcba9876543210" }]) {
    calls.length = 0;
    env.ctx.STC.postStageSaves = async (...args) => {
      calls.push(["stage", ...clone(args)]);
      if (calls.length === 1) return { ok: true, url: STAGED_URL, count: 500 };
      if (failure instanceof Error) throw failure;
      return failure;
    };
    const result = await env.dispatch({ ...message, items: chunks }, sender());
    assert.equal(result.ok, false);
    if (failure && !failure.ok && !(failure instanceof Error)) assert.deepEqual(result, failure);
    assert.equal(result.url, undefined, "a partially staged list must not become an import retry");
    assert.equal(calls.length, 2, "a failed append stops before another chunk or import");
  }
}

async function http() {
  const requests = [];
  let response = { ok: true, status: 200, json: async () => ({ ok: true, url: STAGED_URL }) };
  const env = makeEnv({ store: { local: { yoink_token: "synthetic-helper-token" }, sync: {}, session: {} },
    fetch: async (url, init) => { requests.push({ url, init }); return response; } });
  const deadlines = [];
  const originalTimeout = env.ctx.setTimeout;
  env.ctx.setTimeout = (fn, ms) => { deadlines.push(ms); return originalTimeout(fn, ms); };
  env.load("lib/extract.js");
  await env.ctx.STC.postStageSaves("watch_later", [videoId(1)]);
  await env.ctx.STC.postStageSaves("watch_later", [videoId(2)], STAGED_URL);
  await env.ctx.STC.postImportList(STAGED_URL, 50, 50);
  assert.deepEqual(requests.map(({ url, init }) => [url, JSON.parse(init.body)]), [
    ["http://127.0.0.1:5179/import-list/stage", { source: "watch_later", items: [videoId(1)] }],
    ["http://127.0.0.1:5179/import-list/stage", { source: "watch_later", items: [videoId(2)], append_to: STAGED_URL }],
    ["http://127.0.0.1:5179/import-list", { url: STAGED_URL, offset: 50, limit: 50 }],
  ]);
  for (const { init } of requests) {
    assert.equal(init.method, "POST");
    assert.equal(init.credentials, "omit");
    assert.equal(init.headers["Content-Type"], "application/json");
    assert.equal(init.headers["X-Yoink-Token"], "synthetic-helper-token");
    assert.ok(init.signal instanceof AbortSignal);
  }
  assert.deepEqual(deadlines, [60000, 60000, 60000]);
  assert.equal(env.timeouts.size, 0);
  response = { ok: false, status: 400, json: async () => ({ ok: false, error: "Bad saves" }) };
  assert.deepEqual(clone(await env.ctx.STC.postStageSaves("watch_later", [])), { ok: false, error: "Bad saves", http_status: 400 });
  response = { ok: false, status: 502, json: async () => { throw new SyntaxError("invalid JSON"); } };
  assert.equal((await env.ctx.STC.postImportList(STAGED_URL, 0, 50)).http_status, 502);
  assert.equal(env.timeouts.size, 0);
}

const groups = { parsers, collectors, scroll, requests, background, http };
const group = process.argv[2];
assert.ok(group === undefined || Object.hasOwn(groups, group), `Unknown group ${group}`);
for (const name of group ? [group] : Object.keys(groups)) {
  await groups[name]();
  await settle();
  console.log(`PASS ${name}`);
}
