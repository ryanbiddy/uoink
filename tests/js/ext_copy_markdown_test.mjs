// E5 regression harness: the popup's Copy Markdown button (Last Uoinked
// Video card) really fetches the corpus and copies it.
//
// Drives the REAL extension scripts in a fake browser (ext_fake_env.mjs):
// lib/extract.js and lib/ui.js load as the popup loads them, then popup.js's
// real loadRecentUoinks renders the active card from a stubbed /recent and
// the test clicks Copy Markdown.
//   request     -- the click resolves to an exported, authed call and posts
//                  get_uoink_corpus for the card's folder slug; the corpus
//                  lands on the clipboard
//   failure     -- a helper "not found" reply and a stale token (403, then
//                  refresh) behave; the button always comes back
//   call_sites  -- every STC.* / UoinkUI.* call popup.js makes resolves to a
//                  function the loaded libs actually export
//
// No network: fetch is a stub inside the vm context.
// Run directly:  node tests/js/ext_copy_markdown_test.mjs [group ...]
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { EXT, jsonResponse, makeEnv, settle } from "./ext_fake_env.mjs";

let failures = 0;
let checks = 0;
function check(cond, msg, got) {
  checks++;
  if (cond) { console.log(`ok: ${msg}`); return; }
  failures++;
  console.error(`FAIL: ${msg}${got === undefined ? "" : ` -- got ${JSON.stringify(got)}`}`);
}
async function scenario(name, fn) {
  try {
    await fn();
  } catch (e) {
    failures++;
    console.error(`FAIL: ${name} threw: ${(e && e.stack) || e}`);
  }
}
process.on("unhandledRejection", (e) => {
  failures++;
  console.error(`FAIL: unhandled rejection: ${(e && e.stack) || e}`);
});

const POPUP_SRC = readFileSync(join(EXT, "popup.js"), "utf8");
function popupSlice(from, to) {
  const start = POPUP_SRC.indexOf(from);
  const end = POPUP_SRC.indexOf(to, start);
  if (start < 0 || end <= start) throw new Error(`popup.js slice not found: ${from}`);
  return POPUP_SRC.slice(start, end);
}

const MCP_PATH = "/mcp/v1/tools/call";
const CORPUS_MD = "# A saved video\n\n## Transcript\n\nHello there.\n";
// The helper's real /recent row shape (server.py _enrich_yoink_rows): it
// carries folder, not slug.
function recentRow(folder) {
  return {
    title: "A saved video",
    topic: "Business",
    folder,
    video_id: "abc123def45",
    channel: "Some Channel",
    platform: "youtube",
    hook_type: null,
    health: null,
  };
}
// The helper's real tools/call reply (server.py _mcp_tool_call_result).
function mcpReply(payload) {
  return jsonResponse({
    jsonrpc: "2.0",
    id: null,
    result: {
      content: [{ type: "text", text: JSON.stringify(payload) }],
      structuredContent: payload,
      isError: !payload.ok,
    },
  });
}

// mcp(init, token) -> Response for POST /mcp/v1/tools/call.
async function popupEnv({ folder, mcp, token = "test-token", stored = null }) {
  const env = makeEnv({
    fetch: (url, init) => {
      const path = new URL(url).pathname;
      if (path === "/token") return jsonResponse({ token });
      if (path === "/recent") return jsonResponse({ ok: true, recent: [recentRow(folder)] });
      if (path === MCP_PATH) {
        const headers = (init && init.headers) || {};
        env.mcpCalls.push({
          method: init && init.method,
          headers: { ...headers },
          body: init && init.body,
        });
        return mcp(init, headers["X-Yoink-Token"]);
      }
      throw new TypeError("Failed to fetch");
    },
  });
  env.mcpCalls = [];
  env.clipboard = [];
  if (stored) env.store.local.yoink_token = stored;
  env.load("lib/x-article.js");
  env.load("lib/extract.js");
  env.load("lib/ui.js");

  // The Last Uoinked Video card, as popup.html lays it out.
  const card = env.document.createElement("div");
  card.id = "active-uoink-card";
  card.classList.add("hidden");
  for (const id of ["active-uoink-title", "active-uoink-channel", "active-uoink-duration",
    "active-uoink-hook-container", "active-uoink-open-claude"]) {
    const el = env.document.createElement("div");
    el.id = id;
    card.appendChild(el);
  }
  const copyBtn = env.document.createElement("button");
  copyBtn.id = "active-uoink-copy-md";
  copyBtn.textContent = "Copy Markdown";
  card.appendChild(copyBtn);
  env.document.body.appendChild(card);
  env.copyBtn = copyBtn;

  // popup.js's real loadRecentUoinks, run against stubbed popup state.
  Object.assign(env.ctx, {
    recentUoinksEl: env.document.createElement("div"),
    knownRecentUoinkCount: 0,
    loadRecentFailures: async () => [],
    loadResurfaceCard: async () => {},
    updateFocalMode: () => {},
    initPairwiseCalibration: () => {},
    renderFailureRow: () => env.document.createElement("div"),
    renderHookCalibration: () => null,
    renderHealthRow: () => null,
    renderEntityIndicator: () => null,
    showToast: (m) => env.toasts.push(String(m)),
    writeClipboardText: async (text) => { env.clipboard.push(String(text)); return true; },
  });
  env.runSource(popupSlice("async function loadRecentUoinks(", "\nasync function loadResurfaceCard("), "popup.js");
  await env.ctx.loadRecentUoinks();
  await settle();
  return env;
}

async function clickCopy(env) {
  check(typeof env.copyBtn.onclick === "function",
    "the active card wires a Copy Markdown handler", typeof env.copyBtn.onclick);
  await env.copyBtn.onclick({ stopPropagation() {} });
  await settle();
}

function parsedBody(call) {
  try { return JSON.parse(call.body); } catch { return null; }
}

function checkButtonRestored(env, where) {
  check(env.copyBtn.disabled === false, `${where}: the button is enabled again`, env.copyBtn.disabled);
  check(env.copyBtn.textContent === "Copy Markdown",
    `${where}: the button label is restored`, env.copyBtn.textContent);
}

async function request() {
  await scenario("E5 Copy Markdown copies the corpus (Windows folder)", async () => {
    const env = await popupEnv({
      folder: "C:\\Users\\someone\\Desktop\\Uoink\\Business\\a-saved-video",
      mcp: () => mcpReply({ ok: true, corpus_md: CORPUS_MD }),
    });
    check(!env.ctx.document.getElementById("active-uoink-card").classList.contains("hidden"),
      "the Last Uoinked Video card is shown for a recent uoink");
    await clickCopy(env);

    check(env.mcpCalls.length === 1, "E5: one tools/call request reaches the helper", env.mcpCalls.length);
    const call = env.mcpCalls[0] || { headers: {} };
    check(call.method === "POST", "E5: the request is a POST", call.method);
    check(call.headers["Content-Type"] === "application/json",
      "E5: the request is JSON", call.headers);
    check(call.headers["X-Yoink-Token"] === "test-token",
      "E5: the request carries the extension token", call.headers);
    const body = parsedBody(call);
    check(body && body.name === "get_uoink_corpus", "E5: the request calls get_uoink_corpus", body);
    check(body && body.arguments && body.arguments.slug === "a-saved-video",
      "E5: the slug is the card's folder name", body);

    check(env.clipboard.length === 1 && env.clipboard[0] === CORPUS_MD,
      "E5: the corpus markdown is copied to the clipboard", env.clipboard);
    check(env.toasts.includes("Copied markdown to clipboard!"),
      "E5: the success toast shows", env.toasts);
    check(!env.toasts.includes("Error retrieving markdown."),
      "E5: no 'Error retrieving markdown.' toast", env.toasts);
    checkButtonRestored(env, "E5 success");
  });

  await scenario("E5 Copy Markdown slug from a POSIX folder", async () => {
    const env = await popupEnv({
      folder: "/Users/someone/Desktop/Uoink/Tech/another_saved-video",
      mcp: () => mcpReply({ ok: true, corpus_md: CORPUS_MD }),
    });
    await clickCopy(env);
    const body = parsedBody(env.mcpCalls[0] || {});
    check(body && body.arguments && body.arguments.slug === "another_saved-video",
      "E5: a POSIX folder yields its last path segment as the slug", body);
    check(env.clipboard[0] === CORPUS_MD, "E5: the POSIX-folder corpus is copied", env.clipboard);
  });
}

async function failure() {
  await scenario("E5 helper reports the uoink missing", async () => {
    const env = await popupEnv({
      folder: "C:\\Users\\someone\\Desktop\\Uoink\\Business\\gone-video",
      mcp: () => mcpReply({ ok: false, error: "uoink not found" }),
    });
    await clickCopy(env);
    check(env.mcpCalls.length === 1, "E5: the not-found case still asked the helper", env.mcpCalls.length);
    check(env.clipboard.length === 0, "E5: nothing is copied when the helper has no corpus", env.clipboard);
    check(env.toasts.includes("Failed to retrieve markdown."),
      "E5: a helper miss says the markdown could not be retrieved", env.toasts);
    check(!env.toasts.includes("Error retrieving markdown."),
      "E5: a helper miss is not reported as a thrown error", env.toasts);
    checkButtonRestored(env, "E5 not found");
  });

  await scenario("E5 stale token is refreshed once", async () => {
    const env = await popupEnv({
      folder: "C:\\Users\\someone\\Desktop\\Uoink\\Business\\a-saved-video",
      stored: "stale-token",
      token: "fresh-token",
      mcp: (_init, token) => (token === "fresh-token"
        ? mcpReply({ ok: true, corpus_md: CORPUS_MD })
        : jsonResponse({ ok: false, error: "missing or invalid token" }, 403)),
    });
    await clickCopy(env);
    const tokens = env.mcpCalls.map((c) => c.headers["X-Yoink-Token"]);
    check(tokens.length === 2 && tokens[0] === "stale-token" && tokens[1] === "fresh-token",
      "E5: a 403 refreshes the token and retries once", tokens);
    check(env.clipboard[0] === CORPUS_MD, "E5: the retried call's corpus is copied", env.clipboard);
    checkButtonRestored(env, "E5 stale token");
  });

  await scenario("E5 helper offline", async () => {
    const env = await popupEnv({
      folder: "C:\\Users\\someone\\Desktop\\Uoink\\Business\\a-saved-video",
      mcp: () => { throw new TypeError("Failed to fetch"); },
    });
    await clickCopy(env);
    check(env.clipboard.length === 0, "E5: nothing is copied when the helper is unreachable", env.clipboard);
    check(env.toasts.includes("Error retrieving markdown."),
      "E5: an unreachable helper reports the error toast", env.toasts);
    checkButtonRestored(env, "E5 offline");
  });
}

// Every STC.* / UoinkUI.* call in popup.js's code (comments stripped) must
// name a function the loaded lib actually exports -- E5 was a call to an
// unexported STC._postJson.
function callSitesOf(src, objectName) {
  const code = src
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .split("\n")
    .filter((line) => !/^\s*\/\//.test(line))
    .join("\n");
  const re = new RegExp(`\\b${objectName}\\.([A-Za-z_$][\\w$]*)\\s*\\(`, "g");
  const names = new Set();
  for (const m of code.matchAll(re)) names.add(m[1]);
  return [...names].sort();
}

async function call_sites() {
  await scenario("popup.js call sites resolve", async () => {
    const env = makeEnv();
    env.load("lib/x-article.js");
    env.load("lib/extract.js");
    env.load("lib/ui.js");
    for (const [objectName, lib] of [["STC", env.ctx.STC], ["UoinkUI", env.ctx.UoinkUI]]) {
      const names = callSitesOf(POPUP_SRC, objectName);
      check(names.length > 0, `popup.js calls ${objectName} helpers`, names);
      const missing = names.filter((n) => !lib || typeof lib[n] !== "function");
      check(missing.length === 0,
        `every ${objectName}.* call in popup.js is an exported function`, missing);
    }
    check(callSitesOf(POPUP_SRC, "STC").includes("_postJson") === false,
      "E5: popup.js no longer calls the private STC._postJson");
  });
}

const GROUPS = { request, failure, call_sites };

const requested = process.argv.slice(2);
const names = requested.length ? requested : Object.keys(GROUPS);
for (const name of names) {
  const run = GROUPS[name];
  if (!run) {
    failures++;
    console.error(`FAIL: unknown group ${name}`);
    continue;
  }
  const before = checks;
  await scenario(name, run);
  await settle();
  console.log(`group ${name}: ${checks - before} checks`);
}

if (failures) {
  console.error(`\n${failures} copy-markdown check(s) failed.`);
  process.exit(1);
}
console.log("\nAll copy-markdown checks passed.");
