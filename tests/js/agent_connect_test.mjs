// Exercise the dashboard's response to one or two config writes, or a refusal.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";
import { test } from "node:test";

const html = readFileSync(new URL("../../assets/dashboard/index.html", import.meta.url), "utf8");
const source = html.slice(html.indexOf("async function connectAgent("), html.indexOf("function rawMachineDetails("));

for (const count of [1, 2, 0]) {
  test(`dashboard connect with ${count} saved files`, async () => {
    const feedback = [];
    const toasts = [];
    let reloads = 0;
    const context = vm.createContext({
      authFetch: async (url, options) => {
        assert.equal(url, "/agents/connect/claude-desktop");
        assert.equal(options.method, "POST");
        if (!count) throw Error("Invalid JSON.");
        return { label: "Claude Desktop", config_paths: ["roaming.json", "store.json"].slice(0, count) };
      },
      loadAgentSetup: () => { reloads++; },
      setSettingFeedback: (...args) => feedback.push(args),
      settingError: err => err.message,
      showToast: msg => toasts.push(msg),
    });
    await vm.runInContext(source + 'connectAgent("claude-desktop")', context);
    const [id, message, state, retry] = feedback.at(-1);
    assert.equal(id, "settingsAgentSetupCard");
    assert.equal(state, count ? "saved" : "error");
    assert.equal(reloads, count ? 1 : 0);
    if (count) {
      assert.equal(toasts[0], message);
      assert.match(message, /Restart Claude Desktop/);
      assert.equal(message.includes("2 Claude Desktop config files"), count === 2);
    } else {
      assert.match(message, /Invalid JSON/);
      assert.equal(typeof retry, "function");
    }
  });
}
