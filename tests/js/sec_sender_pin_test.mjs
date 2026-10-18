// Offline audit #10 regression: execute the real worker in a fake browser.
import assert from "node:assert/strict";
import test from "node:test";
import { jsonResponse, makeEnv, settle } from "./ext_fake_env.mjs";

async function worker() {
  const env = makeEnv({
    fetch: (url) => {
      if (new URL(url).pathname === "/token") return jsonResponse({ token: "synthetic-token" });
      return jsonResponse({ ok: true });
    },
  });
  env.load("background.js");
  await settle();
  return env;
}

function effects(env) {
  return JSON.stringify({
    store: env.store, tabs: env.tabsCreated, sent: env.sent,
    notifications: env.notifications, fetches: env.fetches,
  });
}

const messages = [
  { type: "openTab", url: "https://claude.ai/new" },
  { type: "clearQueue" }, { type: "stcPing" }, { type: "refreshActiveSession" },
  { type: "notify", title: "Untrusted", message: "Untrusted" },
  { type: "copyToClipboard", text: "Untrusted" },
  { type: "clipboardRetry", text: "Untrusted" },
  { type: "themeChanged", isDark: true },
  { type: "stcExtract", url: "https://www.youtube.com/watch?v=abc123def45" },
  { type: "stcExtractXArticle", article: { url: "https://x.com/i/article/123" } },
  { type: "stcSessionAdd", session_id: "test", url: "https://example.com/" },
  { type: "rememberFailure", url: "https://example.com/", error: "Untrusted" },
  { type: "forgetFailure", id: "test" },
  { type: "popupCapture", job: { kind: "extract", url: "https://example.com/" } },
];

for (const sender of [undefined, null, {}, { id: "another-extension" },
  { id: "another-extension", url: "chrome-extension://test-extension-id/popup.html" }]) {
  test(`drops every runtime operation from sender ${JSON.stringify(sender)}`, async () => {
    const env = await worker();
    assert.equal(env.messageListeners.length, 1);
    const before = effects(env);
    for (const msg of messages) {
      const replies = [];
      const keep = env.messageListeners[0](msg, sender, (reply) => replies.push(reply));
      assert.equal(keep, undefined, `${msg.type}: must not keep the message port open`);
      await settle();
      assert.deepEqual(replies, [], `${msg.type}: must silently drop the message`);
      assert.equal(effects(env), before, `${msg.type}: must have no side effects`);
    }
  });
}

for (const url of ["chrome-extension://test-extension-id/popup.html",
  "https://www.youtube.com/watch?v=abc123def45"]) {
  test(`accepts its own extension sender at ${url}`, async () => {
    const env = await worker();
    const sender = { id: env.chrome.runtime.id, url };
    const reply = await env.dispatch({ type: "openTab", url: "https://claude.ai/new" }, sender);
    assert.equal(reply.ok, true);
    assert.equal(env.tabsCreated.at(-1).url, "https://claude.ai/new");
    const ping = await env.dispatch({ type: "stcPing" }, sender);
    assert.equal(ping.ok, true);
  });
}
