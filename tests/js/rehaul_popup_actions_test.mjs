// Real popup controls with in-memory Chrome, fetch and clipboard only.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { EXT } from "./ext_fake_env.mjs";
import { popupEnv, jsonResponse, settle } from "./rehaul_popup_env.mjs";

const saved = { video_id: "abc123def45", title: "A saved video", folder: "C:/Fixture/saved-video", hook_type: "question" };
const rows = () => jsonResponse({ ok: true, recent: [{ ...saved }] });
const button = (parent, label) => parent.querySelectorAll("button").find(el => el.textContent === label);
async function event(el, name) {
  assert.ok(el, `reachable ${name} control`);
  for (const listener of el._listeners[name] || []) await listener({ target: el, currentTarget: el, preventDefault() {} });
  await settle();
}
const groups = {
  async hooks() {
    let release;
    const calls = [];
    const env = await popupEnv({ routes: {
      "/recent": rows,
      "/taxonomy/correct": (_url, init) => {
        calls.push(init);
        return new Promise(resolve => { release = resolve; });
      },
    }});
    const row = env.rows()[0];
    const tools = row.querySelector("details");
    assert.ok(tools, "saved captures expose their secondary actions");
    assert.equal(!!tools.open, false, "secondary actions begin collapsed");
    assert.match(tools.querySelector("summary").textContent, /Use this capture/);
    const select = tools.querySelector("select");
    assert.ok(select, "hook correction remains reachable");
    assert.equal(select.getAttribute("aria-label"), "Correct hook type");
    assert.deepEqual(select.children.map(el => el.value), ["curiosity_gap", "question", "contrarian", "story_open", "promise_list", "demo", "authority", "stakes", "other"]);
    assert.equal(select.value, "question");
    select.value = "contrarian";
    const form = tools.querySelector("form");
    const save = button(form, "Save correction");
    const saving = event(form, "submit");
    await settle();
    assert.equal(calls.length, 1);
    assert.equal(calls[0].method, "POST");
    assert.equal(calls[0].headers["X-Yoink-Token"], "fixture-token");
    assert.deepEqual(JSON.parse(calls[0].body), { video_id: saved.video_id, corrected_hook_type: "contrarian", user_reason: "" });
    assert.equal(select.disabled, true); assert.equal(save.disabled, true);
    await event(form, "submit");
    assert.equal(calls.length, 1, "double submit cannot post two corrections");
    env.ctx.renderCaptures();
    assert.equal(env.rows()[0].querySelector("select"), select, "stream updates keep the correction form");
    release(jsonResponse({ ok: false, error: "Could not store correction" }, 500)); await saving;
    assert.match(form.textContent, /Not saved:.*Could not store correction/);
    assert.equal(select.disabled, false); assert.equal(save.disabled, false);
    assert.equal(select.value, "contrarian", "failed saves keep the chosen correction");
    const retry = event(form, "submit"); await settle();
    release(jsonResponse({ ok: true, correction_id: 4 })); await retry;
    assert.equal(calls.length, 2);
    assert.match(form.textContent, /Saved/);
    assert.doesNotMatch(form.textContent, /Not saved/);
    assert.equal(env.runSource("captureData.recent[0].hook_type"), "contrarian");
    const changed = { ...saved, video_id: "different", folder: "C:/Fixture/other", hook_type: "demo" };
    env.setData({ recent: [changed] });
    const otherForm = env.rows()[0].querySelector("form");
    const otherSelect = otherForm.querySelector("select"); otherSelect.value = "stakes";
    const otherSave = event(otherForm, "submit"); await settle();
    assert.equal(JSON.parse(calls[2].body).video_id, "different", "corrections target their row, never the active tab");
    release(jsonResponse({ ok: true })); await otherSave;
    env.events.unload();
  },
  async destinations() {
    for (const outcome of ["success", "missing", "clipboard", "network"]) {
      const calls = [];
      const env = await popupEnv({ routes: {
        "/recent": rows,
        "/mcp/v1/tools/call": (_url, init) => {
          calls.push(JSON.parse(init.body));
          if (outcome === "network") throw new TypeError("Failed to fetch");
          return jsonResponse({ result: { structuredContent: outcome === "missing"
            ? { ok: false, error: "not found" } : { ok: true, corpus_md: "# This saved video" } } });
        },
      }, onSend: () => ({ ok: false }) });
      if (outcome === "clipboard") env.ctx.navigator.clipboard.writeText = async () => { throw new Error("blocked"); };
      const tools = env.rows()[0].querySelector("details");
      assert.ok(tools);
      const send = button(tools, "Send to ChatGPT");
      assert.ok(send, "Send to ChatGPT is a reachable native button");
      send.click(); await settle();
      assert.deepEqual(calls, [{ name: "get_uoink_corpus", arguments: { slug: "saved-video" } }]);
      if (outcome === "success") {
        assert.equal(env.clipboard.at(-1), "# This saved video");
        assert.equal(env.tabsCreated.at(-1).url, "https://chatgpt.com/");
        assert.match(env.el("popup-toast").textContent, /Copied.*ChatGPT/);
        button(tools, "Send to Claude").click(); await settle();
        assert.equal(env.tabsCreated.at(-1).url, "https://claude.ai/new");
      } else {
        assert.equal(env.tabsCreated.length, 0, `${outcome}: no destination opens without a successful copy`);
        assert.match(env.el("popup-toast").textContent, /Failed|Error|blocked/);
      }
      assert.equal(send.disabled, false); assert.equal(send.textContent, "Send to ChatGPT");
      env.events.unload();
    }
  },
  async prompts() {
    const prompts = JSON.parse(readFileSync(join(EXT, "prompts.json"), "utf8"));
    let fail = true, count = 0;
    const env = await popupEnv({ routes: { "/prompts.json": () => {
      count++;
      if (fail) return jsonResponse({ error: "missing" }, 404);
      return jsonResponse(prompts);
    }}});
    assert.equal(count, 0, "starter prompts are loaded only when opened");
    const panel = env.el("starter-prompts");
    assert.ok(panel, "starter prompts remain reachable");
    panel.open = true; await event(panel, "toggle");
    assert.match(env.el("starter-prompts-status").textContent, /Couldn't load.*HTTP 404/);
    fail = false;
    panel.open = false; await event(panel, "toggle");
    panel.open = true; await event(panel, "toggle");
    const list = env.el("starter-prompts-list");
    assert.equal(list.children.length, prompts.length, "every bundled prompt has a row");
    for (let i = 0; i < prompts.length; i++) {
      const row = list.children[i];
      assert.ok(row.textContent.includes(prompts[i].label));
      const copy = row.querySelector("button");
      assert.equal(copy.getAttribute("aria-label"), `Copy ${prompts[i].label}`);
      copy.click(); await settle();
      assert.equal(env.clipboard.at(-1), prompts[i].prompt);
    }
    assert.match(env.el("starter-prompts-status").textContent, /Prompt copied/);
    assert.equal(count, 2, "opening retries a failure without duplicating successful rows");
    panel.open = false; await event(panel, "toggle"); panel.open = true; await event(panel, "toggle");
    assert.equal(count, 2);
    env.ctx.navigator.clipboard.writeText = async () => { throw new Error("blocked"); };
    env.ctx.chrome.runtime.sendMessage = async () => ({ ok: false });
    const copy = list.children[0].querySelector("button"); copy.click(); await settle();
    assert.match(env.el("starter-prompts-status").textContent, /Clipboard copy blocked/);
    assert.equal(copy.disabled, false);
    env.events.unload();
  },
};
const group = process.argv[2];
assert.ok(groups[group], `unknown group: ${group}`);
await groups[group]();
console.log(`PASS ${group}: reachable saved-capture actions`);
