import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";

const page = readFileSync(new URL("../../assets/dashboard/index.html", import.meta.url), "utf8");
const code = page.slice(page.indexOf("    async function getToken("), page.indexOf("    async function authFetch("));
test("concurrent dashboard requests share one retry after a busy helper", async () => {
  let calls = 0;
  const ctx = vm.createContext({ state: {}, setTimeout: fn => fn(), fetch: async () => {
    const busy = ++calls === 1;
    return { status: busy ? 429 : 200, ok: !busy,
      json: async () => busy ? {error: "too many requests"} : {ok: true, token: "fixture"} };
  }});
  vm.runInContext(code, ctx);
  assert.deepEqual(await Promise.all([ctx.getToken(), ctx.getToken(), ctx.getToken()]), Array(3).fill("fixture"));
  assert.equal(calls, 2);
});

test("a rate-limited dashboard waits through the helper window", async () => {
  let elapsed = 0;
  const ctx = vm.createContext({state: {}, setTimeout(fn, ms) { elapsed += ms; fn(); },
    fetch: async () => elapsed < 60000
      ? {ok: false, status: 429, json: async () => ({retry_after_seconds: 60})}
      : {ok: true, status: 200, json: async () => ({ok: true, token: "fixture"})}});
  vm.runInContext(code, ctx);
  assert.equal(await ctx.getToken(), "fixture");
});

test("the page presents the one-use bootstrap id from its HTML", async () => {
  let headers;
  const ctx = vm.createContext({state: {}, document: {querySelector: () => ({content: "fixture-load"})},
    fetch: async (_, options) => { headers = options.headers; return {ok: true, json: async () => ({ok: true, token: "fixture"})}; }});
  vm.runInContext(code, ctx);
  await ctx.getToken();
  assert.equal(headers["X-Uoink-Dashboard-Load"], "fixture-load");
});

test("persistent 429 stops after two delays with a readable connection error", async () => {
  const delays = [];
  const ctx = vm.createContext({state: {}, setTimeout(fn, ms) { delays.push(ms); fn(); },
    fetch: async () => ({ok: false, status: 429, json: async () => ({ok: false, error: "too many requests"})})});
  vm.runInContext(code, ctx);
  await assert.rejects(ctx.getToken(), /Check that the helper is running/);
  assert.deepEqual(delays, [250, 750]);
  assert.equal(ctx.state.tokenRequest, null);
});
