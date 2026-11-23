import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import test from "node:test";
import vm from "node:vm";

const dashboard = readFileSync(new URL("../../assets/dashboard/index.html", import.meta.url), "utf8");
const popup = readFileSync(new URL("../../extension/popup.js", import.meta.url), "utf8");
const receive = {ok: true, body: {getReader: () => ({read: async () => ({done: true})})}};

for (const client of ["dashboard", "popup"]) {
  test(client + " reconnects with its issued id, and a new page starts fresh", async () => {
    const sent = [];
    function newPage() {
      const fetch = async (_, {headers}) => {
        sent.push(headers["X-Uoink-Stream"]);
        return receive;
      };
      const ctx = vm.createContext({
        state: {}, getToken: async () => "fixture", fetch, TextDecoder,
        performance: {getEntriesByType: () => [{type: "reload"}]},
        sessionStorage: {getItem: () => "copied-tab-value", setItem() {}},
        renderQueue() {}, captureData: {}, jobsRevision: 0,
        closed: true, loadRecentUoinks() {}, renderCaptures() {},
        PopupCaptures: {stream: options => options},
        UoinkUI: {authedFetch: async (...args) => ({res: await fetch(...args)})},
      });
      if (client === "popup") {
        const start = popup.indexOf("async function pollQueueStatus");
        vm.runInContext(popup.slice(start, popup.indexOf("function popupOfflineHint", start)), ctx);
        return vm.runInContext("({open: captureStream.connect, snapshot: data => captureStream.onEvent('snapshot', data)})", ctx);
      }
      vm.runInContext(dashboard.slice(dashboard.indexOf("    function handleJobsStreamEvent("),
        dashboard.indexOf("    async function connectJobsStream(")), ctx);
      return {open: ctx.readJobsStream, snapshot: data => ctx.handleJobsStreamEvent("snapshot", data)};
    }
    const first = newPage();
    await first.open();
    first.snapshot({stream_id: "issued-for-first-page", queue: {pending: []}});
    await first.open();
    await newPage().open();
    assert.deepEqual(sent, [undefined, "issued-for-first-page", undefined]);
  });
}
