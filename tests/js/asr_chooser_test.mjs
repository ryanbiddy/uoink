import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";
import {Element} from "./mini_dom.mjs";

const page = fs.readFileSync("assets/dashboard/index.html", "utf8");
const chooser = page.split("    // 3.18 transcription model chooser")[1].split("    async function refreshSettings")[0];
const listener = page.split('const asrModelList = document.getElementById("asrModelList");').at(-1).split("if (asrModelList)")[0];
const list = new Element("div"), timers = new Set();
const estimate = {textContent: ""};
assert.ok(/id="backfillCost">[^<]*<span id="backfillEstimate">/.test(page));
const document = Object.assign(new EventTarget(), {
  getElementById: id => ({asrModelList: list, backfillEstimate: estimate})[id] || null,
  createElement: tag => new Element(tag), hidden: false, activeElement: null,
});
Element.prototype.focus = function() { document.activeElement = this; };
let reads = 0;
const model = {id: "tiny", state: "missing", note: "", languages: "English"};
const data = {machine: {cpu_cores: 2, threads_used: 1}, models: [model]};
const ctx = vm.createContext({document, state: {activeTab: "settings"}, htmlEscape: String,
  transcriptModelLabel: String, humanLabel: String, authFetch: async () => { reads++; return data; },
  setTimeout() { const id = Symbol(); timers.add(id); return id; }, clearTimeout: id => timers.delete(id)});
vm.runInContext(chooser.slice(chooser.indexOf("let asrModelPollTimer")) + listener, ctx);
ctx.renderAsrModels(data);
const other = {id: "large", state: "ready", speed: "About 1.9 hours per hour of audio"};
model.speed = "About 4 min per hour of audio";
data.models.push(other);
for (const selected of [model, other]) {
  for (const row of data.models) row.selected = row === selected;
  ctx.renderAsrModels(data);
  assert.equal(estimate.textContent, selected.speed + ".");
}
other.selected = false;
ctx.renderAsrModels(data);
assert.equal(estimate.textContent, "");
const card = list.children[0];
card.querySelector("button").focus();
model.download = {state: "downloading", done: 1, total: 3};
ctx.renderAsrModels(data);
const cancel = card.querySelector("button");
assert.equal(cancel.dataset.asrAction, "cancel");
assert.equal(document.activeElement, cancel);
model.download.done = 2;
ctx.renderAsrModels(data);
assert.equal(card.querySelector("button"), cancel);
assert.equal(card.querySelector(".asr-model-progress").getAttribute("aria-valuenow"), "66");
assert.deepEqual(card.children.slice(-2).map(el => el.classList[0]), ["asr-model-progress", "asr-model-status"]);
assert.equal(timers.size, 1);
document.hidden = true;
document.dispatchEvent(new Event("visibilitychange"));
assert.equal(timers.size, 0);
assert.equal(reads, 0);
document.hidden = false;
document.dispatchEvent(new Event("visibilitychange"));
await new Promise(resolve => setImmediate(resolve));
assert.equal(reads, 1);
assert.equal(timers.size, 1);


// Click the same control and handler as the saved-item detail.
const restoreButton = new EventTarget();
const item = {video_id: "talk0000001"};
const calls = [];
const restoreContext = vm.createContext({
  document: {getElementById: id => id === "yoinkRestoreTranscript" ? restoreButton : null},
  state: {selectedYoink: item, selectedYoinkSidecar: {transcript_backup: "previous"}},
  videoIdOf: row => row.video_id,
  authFetch: async (url, options) => calls.push([url, options.method, JSON.parse(options.body)]),
  openYoinkDetail: async row => calls.push(row.video_id),
  showToast: message => calls.push(message),
});
const start = page.indexOf("    async function restorePreviousTranscript(");
const end = page.indexOf("    async function requestRetranscription(", start);
const binding = page.match(/document\.getElementById\("yoinkRestoreTranscript"\)\.addEventListener\("click", restorePreviousTranscript\);/);
assert.ok(start >= 0 && end > start && binding);
vm.runInContext(page.slice(start, end) + binding[0], restoreContext);
restoreButton.dispatchEvent(new Event("click"));
assert.equal(restoreButton.disabled, true);
await new Promise(resolve => setImmediate(resolve));
assert.deepEqual(calls, [
  ["/transcription/restore", "POST", {video_id: item.video_id, backup: "previous"}],
  item.video_id, "Previous transcript restored.",
]);
assert.equal(restoreButton.disabled, false);
