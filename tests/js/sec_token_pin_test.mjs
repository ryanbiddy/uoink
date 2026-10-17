// Execute the shipped token client with in-memory storage and fetch only.
import assert from "node:assert/strict";
import test from "node:test";
import { jsonResponse, makeEnv, settle } from "./ext_fake_env.mjs";

function tokenClient({ stored, fail = false, staleSettings = false } = {}) {
  const requests = [];
  const env = makeEnv({
    store: { local: stored ? { yoink_token: stored } : {}, sync: {}, session: {} },
    fetch: (url, init) => {
      const path = new URL(url).pathname;
      requests.push({ path, init });
      if (path === "/token") {
        return jsonResponse(fail ? { ok: false } : { ok: true, token: "synthetic-fresh" }, fail ? 403 : 200);
      }
      if (path === "/settings") {
        if (staleSettings && init.headers["X-Yoink-Token"] !== "synthetic-fresh") {
          return jsonResponse({ ok: false }, 403);
        }
        return jsonResponse({ ok: true });
      }
      // Background startup also reads public probes and session/queue state.
      return jsonResponse({ ok: true });
    },
  });
  env.load("lib/extract.js");
  return { env, requests, mints: () => {
    const mints = requests.filter(({ path }) => path === "/token");
    // Assert outside fetch: the shipped client catches fetch exceptions.
    for (const { init } of mints) {
      assert.equal(init.method, "POST", "Chromium extension GET omits Origin");
      assert.equal(init.mode, "cors");
      assert.equal(init.credentials, "omit");
      assert.equal(init.cache, "no-store");
      assert.equal(init.headers["X-Yoink-Client"], "yoink-extension");
      assert.equal(init.body, undefined);
      // Origin must be supplied by the browser, not invented by the script.
      assert.equal(Object.keys(init.headers).some((key) => key.toLowerCase() === "origin"), false);
    }
    return mints;
  } };
}

test("fresh token uses a bodyless POST and caches the result", async () => {
  const { env, mints } = tokenClient();
  assert.equal(await env.ctx.STC.getToken(), "synthetic-fresh");
  assert.equal(env.store.local.yoink_token, "synthetic-fresh");
  assert.equal(await env.ctx.STC.getToken(), "synthetic-fresh");
  assert.equal(mints().length, 1);
});

test("parallel token mints coalesce into one POST", async () => {
  const { env, mints } = tokenClient();
  const values = await Promise.all(Array.from({ length: 4 }, () => env.ctx.STC.getToken()));
  assert.deepEqual(values, Array(4).fill("synthetic-fresh"));
  assert.equal(mints().length, 1);
});

test("403 on an authenticated route refreshes by POST and retries with the fresh token", async () => {
  const { env, requests, mints } = tokenClient({ stored: "synthetic-stale", staleSettings: true });
  assert.equal((await env.ctx.STC.getSettings()).ok, true);
  assert.equal(mints().length, 1);
  assert.deepEqual(requests.filter(({ path }) => path === "/settings")
    .map(({ init }) => init.headers["X-Yoink-Token"]), ["synthetic-stale", "synthetic-fresh"]);
});

test("denied token POST never falls back to an originless GET", async () => {
  const { env, mints } = tokenClient({ fail: true });
  assert.equal(await env.ctx.STC.getToken(), null);
  assert.equal(env.store.local.yoink_token, undefined);
  assert.equal(mints().length, 1);
});

test("the real background worker refreshes through the shared POST client", async () => {
  const { env, mints } = tokenClient({ stored: "synthetic-stale" });
  let installed;
  env.chrome.runtime.onInstalled = { addListener(fn) { installed = fn; } };
  env.load("background.js");
  assert.equal(typeof installed, "function");
  await installed({ reason: "update" });
  await settle();
  assert.equal(mints().length, 1);
  assert.equal(env.store.local.yoink_token, "synthetic-fresh");
});
