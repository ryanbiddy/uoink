import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";
import { makeEnv, settle } from "./ext_fake_env.mjs";
import { popupEnv } from "./rehaul_popup_env.mjs";

const videoId = "loom0000001";
const url = "https://www.youtube.com/watch?v=" + videoId;

for (const [time, suffix, expected] of [[872.8, "", "&t=872s"], [15.1, "", "&t=15s"],
  [15, "", ""], [0, "&start=7", "&t=7"], [96, "&t=8", "&t=96s"]]) {
  test(`YouTube save at ${time}s with URL suffix '${suffix}'`, async () => {
    const env = makeEnv({ href: url + suffix, onSend: msg => {
      if (msg.type === "stcPing") return { ok: true };
      if (msg.type === "stcExtract") return { data: { ok: true, reused: true, pinned_seconds: 872 } };
      return { ok: true };
    }});
    env.document._selectors.video = { currentTime: time };
    env.load("lib/extract.js");
    env.load("lib/ui.js");
    env.load("content.js");
    await settle();
    assert.equal((await env.dispatch({ type: "uoinkReadMoment", videoId })).seconds, time);
    assert.equal(await env.dispatch({ type: "uoinkReadMoment", videoId: "other000001" }), undefined);
    await env.dispatch({ type: "uoinkShortcutTriggered" });
    await settle(100);
    assert.equal(env.sent.find(m => m.type === "stcExtract")?.url, url + expected);
    assert.ok(env.notifyMessages().some(m => m.message === "Saved. Pinned 14:32"));
  });
}

test("popup and context-menu tab reads keep a different video's time out of the save", async () => {
  const env = makeEnv();
  env.load("lib/extract.js");
  env.chrome.tabs.sendMessage = async () => ({ videoId: "other000001", seconds: 234 });
  assert.equal(await env.ctx.STC.tabMomentUrl(7, url + "&t=7s"), url + "&t=7s");
  env.chrome.tabs.sendMessage = async () => ({ videoId, seconds: 234.8 });
  assert.equal(await env.ctx.STC.tabMomentUrl(7, url), url + "&t=234s");
  env.chrome.tabs.sendMessage = async () => { throw Error("Tab navigated"); };
  assert.equal(await env.ctx.STC.tabMomentUrl(7, url + "&t=7s"), url + "&t=7s");
});

test("popup sends the visible player time in its video capture handoff", async () => {
  const popup = await popupEnv({tab: {id: 7, title: "Handloom", url},
    onSend: () => ({ok:true, id:"capture"})});
  popup.chrome.tabs.sendMessage = async (id, msg) => {
    assert.equal(id, 7);
    assert.equal(msg.videoId, videoId);
    return {videoId, seconds: 872.5};
  };
  await popup.ctx.runPopupUoinkCurrent();
  const timedUrl = popup.sent.find(msg => msg.type === "popupCapture").job.url;
  assert.equal(timedUrl, url + "&t=872s");
  popup.ctx.applyCaptureQueueState({queue: [{kind: "extract", url: timedUrl}]});
  assert.equal(popup.el("uoink-current-btn").disabled, true);
  popup.events.unload();
});

test("context menu snapshots the page time and keeps a right-clicked link's own time", async () => {
  const env = makeEnv();
  env.load("background.js");
  await settle();
  env.runSource("enqueue = async job => { self.testJob = job; };", "queue-fixture.js");
  env.chrome.tabs.sendMessage = async () => ({videoId, seconds: 872.5});
  const tab = {id: 7, url};
  const [click] = env.contextMenuListeners;
  await click({menuItemId: "stc-extract-page", pageUrl: url}, tab);
  assert.equal(env.ctx.testJob.url, url + "&t=872s");
  await click({menuItemId: "stc-extract-link", linkUrl: url + "&t=3s"}, tab);
  assert.equal(env.ctx.testJob.url, url + "&t=3s");
});

const html = readFileSync(new URL("../../assets/dashboard/index.html", import.meta.url), "utf8");
const chunk = html.slice(html.indexOf("    function pinnedMomentsHtml"), html.indexOf("    function renderYoinkDetail"));

test("dashboard keeps indexed pins readable when a long video's details exceed the read limit", async () => {
  const detail = html.slice(html.indexOf("    async function loadYoinkDetails"), html.indexOf("    async function loadYoinkMarkdown"));
  const failure = Object.assign(Error("sidecar file too large"), {data: {pins: [{seconds: 872}]}});
  const ctx = vm.createContext({authFetch: async () => { throw failure; }});
  vm.runInContext(detail, ctx);
  const data = await ctx.loadYoinkDetails(videoId);
  assert.equal(data.pins[0].seconds, 872);
  assert.equal(data.detailsError, "sidecar file too large");
});

function reader() {
  const pin = {seconds: 872, lines: [], transcript_ready: false, deep_link: url + "&t=872s"};
  let callback, copied, request;
  const state = { selectedYoink: videoId, activeTab: "yoink", selectedYoinkSidecar: {pins: [pin]} };
  const ctx = vm.createContext({state, htmlEscape: s => String(s).replaceAll("<", "&lt;"),
    videoIdOf: id => id, readerClock: s => Math.floor(s/60) + ":" + String(Math.floor(s%60)).padStart(2,"0"),
    renderYoinkDetail() {}, showToast() {}, setTimeout: fn => { callback = fn; }, clearTimeout() {},
    navigator: { clipboard: { writeText: text => { copied = text; } } },
    authFetch: async (path, opts) => { request = [path, JSON.parse(opts.body)]; },
    els: {yoinkDetail: {querySelector: () => null}, yoinkHeading: {focus() {}}},
  });
  vm.runInContext(chunk, ctx);
  return {pin, state, ctx, timer: () => callback(), copied: () => copied, request: () => request};
}

test("dashboard hydrates a waiting pin, copies the quote and removes only that pin", async () => {
  const r = reader();
  assert.equal(r.ctx.pinnedMomentsHtml([]), "");
  assert.match(r.ctx.pinnedMomentsHtml([r.pin]), /14:32[\s\S]*Waiting for the transcript/);
  const ready = {...r.pin, lines:[{start:850,text:"Lift <the shuttle>."}], transcript_ready:true,
    deep_link:url + "&t=848s"};
  r.ctx.loadYoinkDetails = async () => ({pins:[ready, {...r.pin, seconds: 5}]});
  r.ctx.watchPendingPins(r.state.selectedYoinkSidecar);
  await r.timer();
  assert.match(r.ctx.pinnedMomentsHtml(r.state.selectedYoinkSidecar.pins), /Lift &lt;the shuttle>/);
  await r.ctx.actOnPin({hasAttribute: () => true, dataset:{pinCopy:"872"}});
  assert.equal(r.copied(), "Pinned 14:32\nLift <the shuttle>.\n14:10 · " + ready.deep_link);
  await r.ctx.actOnPin({hasAttribute: () => false, dataset:{pinRemove:"872"}});
  assert.deepEqual(r.request(), ["/yoinks/"+videoId+"/moments/remove", {seconds:872}]);
  assert.equal(r.state.selectedYoinkSidecar.pins.length, 1);
  assert.equal(r.state.selectedYoinkSidecar.pins[0].seconds, 5);
});
