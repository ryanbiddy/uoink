// Dashboard registry tools: errors are readable and a tool call is never
// re-sent (D2).
//
// Before the fix callRegistryTool() re-sent EVERY failure from
// /mcp/v1/tools/call to /tools/<name>: a register_source or set_source_consent
// the tool had already refused (or run) went out a second time with the same
// arguments and user_intent_token. authFetch() built Error(data.error) from the
// {code, message} contract envelope, so users read "[object Object]", and the
// ok:false branches (stale_report recovery among them) were dead because every
// refusal arrived as a throw.
//
// Runs the REAL dashboard script (assets/dashboard/index.html, everything
// before init()) in a node:vm context over a fake page holding every id the
// markup declares. A fake helper answers both transports from one tool
// function, the way server.py does: /mcp/v1/tools/call wraps the tool's reply
// in a JSON-RPC result (structuredContent), /tools/<name> answers a refusal as
// ok:false at 200 and a success as {ok:true, result}. Every request is logged,
// so a scenario can count how often a tool was reached.
//   refusal   -- a tool refusal is returned, shown in words and never re-sent:
//                register_source, set_source_consent, Retry poll, captured items;
//                a plain error string reads as well as an envelope
//   auth_fetch -- authFetch errors read error.message from a contract envelope
//                (registry, consent-intent and /api/corpus/v1 shapes)
//   transport -- only a request that never reached a tool (no response, or no
//                MCP route) is retried on /tools/, once, and its reply is
//                unwrapped; any other HTTP failure is reported, not re-sent
//   activity  -- activity refusals reach their ok:false branches: a summary,
//                summary reload or evidence refusal shows its reason, envelope
//                or plain string; a stale evidence/collection page reloads the
//                summary over MCP (and a late reload leaves a newer evidence
//                page's pagers alone), a refused collection page disables
//                paging, and a summary reload that cannot reach the helper is
//                reported
//
// No network: fetch is a stub inside the vm context.
// Run directly:  node tests/js/dash_registry_errors_test.mjs [group ...]
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import vm from "node:vm";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const PAGE = readFileSync(join(ROOT, "assets", "dashboard", "index.html"), "utf8");
const SCRIPT_OPEN = PAGE.indexOf("<script>");
const SCRIPT_START = SCRIPT_OPEN + "<script>".length;
const INIT_CALL = PAGE.indexOf("    init().catch(", SCRIPT_START);
if (SCRIPT_OPEN < 0 || INIT_CALL < 0) throw new Error("dashboard script or its init() call not found");
const SCRIPT = PAGE.slice(SCRIPT_START, INIT_CALL);
const MARKUP = PAGE.slice(0, SCRIPT_OPEN);

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

async function settle() {
  for (let i = 0; i < 20; i++) await new Promise((r) => setImmediate(r));
}

// id -> tag for every element the dashboard markup declares.
const TAGS = new Map();
{
  const tagRe = /<([a-zA-Z][a-zA-Z0-9]*)\b([^>]*)>/g;
  let m;
  while ((m = tagRe.exec(MARKUP)) !== null) {
    const id = /\sid="([^"]+)"/.exec(m[2]);
    if (id && !TAGS.has(id[1])) TAGS.set(id[1], m[1].toUpperCase());
  }
}

class FakeClassList {
  constructor() { this._set = new Set(); }
  add(...names) { names.forEach((n) => this._set.add(n)); }
  remove(...names) { names.forEach((n) => this._set.delete(n)); }
  contains(name) { return this._set.has(name); }
  toggle(name, force) {
    const on = force === undefined ? !this._set.has(name) : Boolean(force);
    if (on) this._set.add(name); else this._set.delete(name);
    return on;
  }
}

class FakeEl {
  constructor(id, tag) {
    this.id = id;
    this.tagName = tag || "DIV";
    this.value = "";
    this.textContent = "";
    this.innerHTML = "";
    this.title = "";
    this.hidden = false;
    this.disabled = false;
    this.checked = false;
    this.scrollTop = 0;
    this.files = [];
    this.options = [];
    this.dataset = {};
    this.style = {};
    this.classList = new FakeClassList();
    this._attrs = {};
    this._listeners = {};
  }
  addEventListener(type, fn) { (this._listeners[type] ||= []).push(fn); }
  removeEventListener() {}
  setAttribute(name, value) { this._attrs[name] = String(value); }
  getAttribute(name) { return name in this._attrs ? this._attrs[name] : null; }
  hasAttribute(name) { return name in this._attrs; }
  removeAttribute(name) { delete this._attrs[name]; }
  toggleAttribute(name, force) {
    const on = force === undefined ? !(name in this._attrs) : Boolean(force);
    if (on) this._attrs[name] = ""; else delete this._attrs[name];
    return on;
  }
  querySelector() { return null; }
  querySelectorAll() { return []; }
  closest() { return null; }
  contains() { return false; }
  setCustomValidity() {}
  focus() {}
  blur() {}
  select() {}
  click() {}
  scrollIntoView() {}
  append() {}
  appendChild(child) { return child; }
  remove() {}
  getBoundingClientRect() { return { top: 0, left: 0, right: 0, bottom: 0, width: 0, height: 0 }; }
}

function jsonResponse(body, status = 200) {
  const text = body === undefined ? "" : JSON.stringify(body);
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
    text: async () => text,
    blob: async () => ({}),
  };
}

// The phase3-v1 contract envelope a source/activity tool refuses with.
function refusal(code, message) {
  return {
    ok: false,
    schema_version: "phase3-v1",
    contract_version: "phase3-v1-2026-09-07",
    error: { code, message, retryable: false, details: {} },
  };
}

// uoink_mcp_tools._err: call_tool answers a rate limit, an unknown tool or a
// tool that raised with a plain error string, not an envelope.
const PLAIN_REASON = "tool failed: backend unavailable";
function plainRefusal(message = PLAIN_REASON) {
  return { ok: false, error: message };
}

// server.py _mcp_tool_call_result: the tool reply rides in a JSON-RPC result.
function mcpReply(payload) {
  return jsonResponse({
    jsonrpc: "2.0",
    id: "fixture",
    result: {
      content: [{ type: "text", text: JSON.stringify(payload) }],
      structuredContent: payload,
      isError: payload.ok === false,
    },
  });
}

// server.py _handle_tools_call_http: a refusal is ok:false at 200, a success
// is wrapped as {ok:true, result}.
function httpToolReply(payload) {
  return payload && payload.ok === false ? jsonResponse(payload) : jsonResponse({ ok: true, result: payload });
}

const SOURCE_ID = `src_${"a".repeat(64)}`;
const SOURCE = {
  source_id: SOURCE_ID,
  kind: "podcast_rss",
  display_name: "Fixture Feed",
  canonical_url: "https://example.com/feed.xml",
  consent_state: "on",
  revision: 3,
  detection: { cursor_revision: 2 },
  allowance: {},
  item_counts: {},
};
const INTENT_TOKEN = "uit_fixture_token";
const OLD_REVISION = "a".repeat(64);
const NEW_REVISION = "b".repeat(64);

function activityPacket(revision) {
  return {
    ok: true,
    report_revision: revision,
    as_of: "2026-10-15T12:00:00.000Z",
    date_basis: "capture_time",
    interval: { start: "2026-10-08T00:00:00.000Z", end: "2026-10-15T00:00:00.000Z" },
    items: { total: { value: 4 }, coverage_ref: "cov_capture" },
    coverage: { cov_capture: { coverage_status: "retained_records" } },
    shelf_activity: {},
    sources: {},
    events: {},
    warnings: [],
  };
}

// One fresh dashboard page per scenario. `tool(name, args)` is the helper's
// tool: both transports call it, so p.ran counts how often a tool actually
// ran. `mcpTransport(name, args)` may answer for the MCP route instead
// (return "network" for a fetch that never got a response, or a response).
function makePage({ tool, mcpTransport, httpTransport, intent } = {}) {
  const elements = new Map();
  const getEl = (id) => {
    if (!elements.has(id)) elements.set(id, new FakeEl(id, TAGS.get(id)));
    return elements.get(id);
  };
  const document = {
    getElementById: getEl,
    querySelector: () => null,
    querySelectorAll: () => [],
    addEventListener() {},
    removeEventListener() {},
    createElement: (tag) => new FakeEl("", String(tag).toUpperCase()),
    body: new FakeEl("body", "BODY"),
    documentElement: new FakeEl("html", "HTML"),
    activeElement: null,
    hidden: false,
    visibilityState: "visible",
  };

  const requests = [];
  const ran = [];
  const runTool = (name, args) => {
    ran.push({ name, args });
    return tool ? tool(name, args) : { ok: true };
  };
  const fakeFetch = (url, opts = {}) => {
    const path = String(url);
    let body = null;
    try { body = opts && opts.body ? JSON.parse(opts.body) : null; } catch (_) { body = opts.body; }
    requests.push({ path, method: (opts && opts.method) || "GET", body });
    if (path === "/token") return Promise.resolve(jsonResponse({ ok: true, token: "test-token" }));
    if (path === "/mcp/v1/tools/call") {
      const name = body && body.params && body.params.name;
      const args = (body && body.params && body.params.arguments) || {};
      const override = mcpTransport ? mcpTransport(name, args) : null;
      if (override === "network") return Promise.reject(new TypeError("Failed to fetch"));
      if (override) return Promise.resolve(override);
      return Promise.resolve(mcpReply(runTool(name, args)));
    }
    if (path.startsWith("/tools/")) {
      const name = decodeURIComponent(path.slice("/tools/".length));
      const override = httpTransport ? httpTransport(name, body || {}) : null;
      if (override === "network") return Promise.reject(new TypeError("Failed to fetch"));
      if (override) return Promise.resolve(override);
      return Promise.resolve(httpToolReply(runTool(name, body || {})));
    }
    if (path === "/sources/consent-intent") {
      return Promise.resolve(intent ? intent(body) : jsonResponse({ ok: true, user_intent_token: INTENT_TOKEN, expires_ms: 4102444800000 }));
    }
    if (path.startsWith("/jobs")) return Promise.resolve(jsonResponse({ ok: true, jobs: [] }));
    return Promise.resolve(jsonResponse({ ok: true }));
  };

  const window = {
    addEventListener() {},
    removeEventListener() {},
    dispatchEvent() {},
    setTimeout,
    clearTimeout,
    open() {},
    matchMedia: () => ({ matches: false, addEventListener() {}, removeEventListener() {} }),
    innerWidth: 1280,
    innerHeight: 800,
    location: { hash: "", href: "http://127.0.0.1/", origin: "http://127.0.0.1" },
  };
  const storage = () => {
    const m = new Map();
    return { getItem: (k) => (m.has(k) ? m.get(k) : null), setItem: (k, v) => m.set(k, String(v)), removeItem: (k) => m.delete(k) };
  };
  const ctx = {
    document,
    window,
    location: window.location,
    navigator: { clipboard: { writeText: () => Promise.resolve() }, userAgent: "node" },
    localStorage: storage(),
    sessionStorage: storage(),
    console,
    fetch: fakeFetch,
    setTimeout,
    clearTimeout,
    setInterval: () => 0,
    clearInterval() {},
    requestAnimationFrame: (fn) => setTimeout(fn, 0),
    cancelAnimationFrame() {},
    URL: Object.assign(function FakeURL(u, base) { return new URL(u, base); }, {
      createObjectURL: () => "blob:fake",
      revokeObjectURL() {},
    }),
    URLSearchParams,
    TextDecoder,
    CSS: { escape: (s) => String(s) },
    Event: class { constructor(type) { this.type = type; } },
    CustomEvent: class { constructor(type, init = {}) { this.type = type; this.detail = init.detail; } },
  };
  window.document = document;
  vm.createContext(ctx);
  vm.runInContext(`${SCRIPT}
;globalThis.__page = { state, els, libraryActivityState, authFetch, callRegistryTool,
  registerStandingSource, startConsentFlow, confirmConsentMutation, retrySourcePoll,
  toggleCapturedItems, renderCapturedItems, loadStandingSubscriptions,
  loadLibraryActivity, fetchActivityEvidence, fetchActivityCollection };`, ctx);
  const page = ctx.__page;
  // Every request that carried this tool, on either transport.
  const sent = (name) => requests.filter((r) => (r.path === "/mcp/v1/tools/call" && r.body && r.body.params && r.body.params.name === name)
    || r.path === `/tools/${name}`);
  const viaHttp = () => requests.filter((r) => r.path.startsWith("/tools/"));
  const ranTool = (name) => ran.filter((r) => r.name === name);
  return { page, state: page.state, els: page.els, activity: page.libraryActivityState, requests, sent, viaHttp, ranTool, getEl };
}

function toast(p) {
  return p.els.toast.textContent;
}

function fillAddForm(p) {
  p.els.standingAddUrl.value = SOURCE.canonical_url;
  p.els.standingAddKind.value = "podcast_rss";
  p.els.standingAddDisplayName.value = "Fixture Feed";
}

// ---------------------------------------------------------------------------
async function groupRefusal() {
  await scenario("register_source refused by the tool", async () => {
    const p = makePage({
      tool: (name) => (name === "register_source"
        ? refusal("validation_error", "Source URL is not a supported feed")
        : { ok: true, sources: [] }),
    });
    fillAddForm(p);
    await p.page.registerStandingSource();
    await settle();
    check(p.sent("register_source").length === 1, "a refused register_source is sent once", p.sent("register_source").map((r) => r.path));
    check(p.ranTool("register_source").length === 1, "the register_source tool runs once", p.ranTool("register_source").length);
    check(p.viaHttp().length === 0, "nothing is re-sent over /tools/", p.viaHttp().map((r) => r.path));
    check(toast(p) === "Could not register source: Source URL is not a supported feed", "the toast names the tool's reason", toast(p));
    check(!toast(p).includes("[object Object]"), "the toast never reads [object Object]", toast(p));
    check(p.els.standingAddUrl.value === SOURCE.canonical_url, "the URL stays in the box after a refusal", p.els.standingAddUrl.value);
    check(p.els.standingAddButton.disabled === false, "the Subscribe button is enabled again", p.els.standingAddButton.disabled);
  });

  await scenario("register_source refused with a plain error string", async () => {
    const p = makePage({
      tool: (name) => (name === "register_source" ? plainRefusal() : { ok: true, sources: [] }),
    });
    fillAddForm(p);
    await p.page.registerStandingSource();
    await settle();
    check(p.sent("register_source").length === 1 && p.viaHttp().length === 0, "a plain-string refusal is sent once", p.requests.map((r) => r.path));
    check(toast(p) === `Could not register source: ${PLAIN_REASON}`, "the toast names the plain-string reason", toast(p));
  });

  for (const [code, message, expected] of [
    ["invalid_user_intent", "Capability is expired or consumed", "Consent update failed: invalid_user_intent: Capability is expired or consumed"],
    ["stale_revision", "Source changed; reload and confirm again", "Source was modified concurrently. Refreshed with latest server state."],
  ]) {
    await scenario(`set_source_consent refused with ${code}`, async () => {
      const p = makePage({
        tool: (name) => (name === "set_source_consent" ? refusal(code, message) : { ok: true, sources: [SOURCE] }),
      });
      await p.page.startConsentFlow(SOURCE_ID, "off");
      check(p.state.standingPendingIntent && p.state.standingPendingIntent.source_id === SOURCE_ID, "the consent modal opens for the listed source", p.state.standingPendingIntent);
      await p.page.confirmConsentMutation();
      await settle();
      const consent = p.sent("set_source_consent");
      check(consent.length === 1, `a set_source_consent refused with ${code} is sent once`, consent.map((r) => r.path));
      check(p.ranTool("set_source_consent").length === 1, "the consent tool runs once", p.ranTool("set_source_consent").length);
      check(p.viaHttp().length === 0, "the user_intent_token is not re-sent over /tools/", p.viaHttp().map((r) => r.path));
      const args = consent[0] && consent[0].body.params.arguments;
      check(Boolean(args) && args.user_intent_token === INTENT_TOKEN && args.consent_state === "off" && args.expected_revision === 3,
        "the one request carries the minted user_intent_token and the bound revision", args);
      check(toast(p) === expected, `the ${code} refusal is shown in words`, toast(p));
      check(p.els.sourceConsentModal.classList.contains("hidden"), "the consent modal closes", [...p.els.sourceConsentModal.classList._set]);
    });
  }

  await scenario("set_source_consent accepted", async () => {
    const p = makePage({
      tool: (name) => (name === "set_source_consent" ? { ok: true, source: { ...SOURCE, consent_state: "off", revision: 4 } } : { ok: true, sources: [SOURCE] }),
    });
    await p.page.startConsentFlow(SOURCE_ID, "off");
    await p.page.confirmConsentMutation();
    await settle();
    check(p.sent("set_source_consent").length === 1, "an accepted consent change is sent once", p.sent("set_source_consent").length);
    check(toast(p) === "Standing capture turned off.", "the success toast is shown", toast(p));
  });

  await scenario("Retry poll refused by source_status", async () => {
    const p = makePage({
      tool: (name) => (name === "source_status" ? refusal("not_found", "Source not found") : { ok: true, sources: [] }),
    });
    await p.page.retrySourcePoll(SOURCE_ID);
    await settle();
    check(p.sent("source_status").length === 1, "a refused source_status is sent once", p.sent("source_status").length);
    check(p.viaHttp().length === 0, "nothing is re-sent over /tools/", p.viaHttp().map((r) => r.path));
    check(toast(p) === "Status check: Source not found", "the Retry poll toast names the reason", toast(p));
  });

  await scenario("Retry poll refused with a plain error string", async () => {
    const p = makePage({
      tool: (name) => (name === "source_status" ? plainRefusal() : { ok: true, sources: [] }),
    });
    await p.page.retrySourcePoll(SOURCE_ID);
    await settle();
    check(p.sent("source_status").length === 1 && p.viaHttp().length === 0, "a plain-string source_status refusal is sent once", p.requests.map((r) => r.path));
    check(toast(p) === `Status check: ${PLAIN_REASON}`, "the Retry poll toast names the plain-string reason", toast(p));
  });

  await scenario("captured items refused by source_status", async () => {
    const p = makePage({
      tool: (name) => (name === "source_status" ? refusal("not_found", "Source not found") : { ok: true, sources: [] }),
    });
    await p.page.toggleCapturedItems(SOURCE_ID);
    await settle();
    const view = p.state.standingItemsBySource[SOURCE_ID];
    check(p.sent("source_status").length === 1, "a refused captured-items page is asked for once", p.sent("source_status").length);
    check(p.viaHttp().length === 0, "nothing is re-sent over /tools/", p.viaHttp().map((r) => r.path));
    const html = p.page.renderCapturedItems(view);
    check(html.includes("Could not load items: not_found: Source not found"), "the refusal is shown instead of an empty list", html);
    check(!html.includes("No captured items"), "a refusal is not reported as no captured items", html);
  });
}

async function groupAuthFetch() {
  const cases = [
    ["a contract envelope", 409, { ok: false, error: { code: "stale_revision", message: "Source changed; reload and confirm again" } }, "Source changed; reload and confirm again"],
    ["an ok:false envelope at 200", 200, { ok: false, error: { code: "validation_error", message: "operation is invalid" } }, "operation is invalid"],
    // corpus_contract.failure(): the /api/corpus/v1/* error shape.
    ["a corpus contract failure", 503, { ok: false, contract: "uoink.corpus", version: "v1", operation: "assemble", error: { code: "unavailable", message: "corpus assemble is unavailable", retryable: true } }, "corpus assemble is unavailable"],
    ["a plain error string", 400, { ok: false, error: "confirmed must be true" }, "confirmed must be true"],
    ["an envelope without a message", 500, { ok: false, error: { code: "internal_error" } }, "HTTP 500"],
    ["an empty body", 502, undefined, "HTTP 502"],
  ];
  for (const [label, status, body, expected] of cases) {
    await scenario(`authFetch error from ${label}`, async () => {
      const p = makePage({ intent: () => jsonResponse(body, status) });
      let err = null;
      try {
        await p.page.authFetch("/sources/consent-intent", { method: "POST", body: JSON.stringify({ confirmed: true }) });
      } catch (e) {
        err = e;
      }
      check(Boolean(err), `authFetch throws on ${label}`);
      check(err && err.message === expected, `authFetch reads "${expected}" from ${label}`, err && err.message);
      check(err && err.status === status, "the HTTP status is kept on the error", err && err.status);
    });
  }

  await scenario("a refused consent mint is shown in words", async () => {
    const p = makePage({
      tool: () => ({ ok: true, sources: [SOURCE] }),
      intent: () => jsonResponse({ ok: false, error: { code: "user_intent_required", message: "User session required" } }, 403),
    });
    await p.page.startConsentFlow(SOURCE_ID, "on");
    await p.page.confirmConsentMutation();
    await settle();
    check(toast(p) === "Consent update failed: user_intent_required: User session required", "the mint refusal is shown in words", toast(p));
    check(p.sent("set_source_consent").length === 0, "no consent change is sent without a minted token", p.sent("set_source_consent").length);
  });
}

async function groupTransport() {
  await scenario("helper without the MCP route (404)", async () => {
    const p = makePage({
      tool: (name) => (name === "list_sources" ? { ok: true, sources: [SOURCE], next_cursor: null } : { ok: true }),
      mcpTransport: () => jsonResponse({ ok: false, error: "not found" }, 404),
    });
    await p.page.loadStandingSubscriptions();
    await settle();
    check(p.viaHttp().length === 1 && p.viaHttp()[0].path === "/tools/list_sources", "a 404 from the MCP route retries once over /tools/", p.viaHttp().map((r) => r.path));
    check(p.ranTool("list_sources").length === 1, "the list tool runs once", p.ranTool("list_sources").length);
    const ids = (p.state.standingSources || []).map((s) => s.source_id);
    check(JSON.stringify(ids) === JSON.stringify([SOURCE_ID]), "the /tools/ reply is unwrapped to the MCP shape", ids);
  });

  await scenario("MCP request gets no response", async () => {
    const p = makePage({
      tool: (name) => (name === "register_source" ? { ok: true, created: true, source: SOURCE } : { ok: true, sources: [SOURCE] }),
      mcpTransport: (name) => (name === "register_source" ? "network" : null),
    });
    fillAddForm(p);
    await p.page.registerStandingSource();
    await settle();
    check(p.sent("register_source").length === 2, "a register_source that got no response is retried", p.sent("register_source").map((r) => r.path));
    check(p.viaHttp().filter((r) => r.path === "/tools/register_source").length === 1, "the retry goes over /tools/ once", p.viaHttp().map((r) => r.path));
    check(p.ranTool("register_source").length === 1, "the register tool runs once", p.ranTool("register_source").length);
    check(toast(p) === "Source subscribed. Capture is off by default; detection watches metadata.", "the retried subscription succeeds", toast(p));
    check(p.els.standingAddUrl.value === "", "the add form clears after the retried success", p.els.standingAddUrl.value);
  });

  for (const [label, status, body, expected] of [
    ["rate limited", 429, { ok: false, error: "too many requests" }, "Could not register source: too many requests"],
    ["a server error with a contract envelope", 500, { ok: false, error: { code: "internal_error", message: "The helper hit an internal error" } }, "Could not register source: The helper hit an internal error"],
    ["a token refusal", 403, { ok: false, error: "token required" }, "Could not register source: token required"],
  ]) {
    await scenario(`MCP route answers ${label}`, async () => {
      const p = makePage({
        tool: () => ({ ok: true, created: true, source: SOURCE }),
        mcpTransport: () => jsonResponse(body, status),
      });
      fillAddForm(p);
      await p.page.registerStandingSource();
      await settle();
      check(p.sent("register_source").length === 1, `an MCP ${status} is not re-sent`, p.sent("register_source").map((r) => r.path));
      check(p.viaHttp().length === 0, "nothing goes to /tools/", p.viaHttp().map((r) => r.path));
      check(toast(p) === expected, `the ${status} is shown in words`, toast(p));
    });
  }

  await scenario("a tool refusal over the /tools/ retry", async () => {
    const p = makePage({
      tool: (name) => (name === "register_source" ? refusal("validation_error", "Source URL is not a supported feed") : { ok: true, sources: [] }),
      mcpTransport: () => jsonResponse({ ok: false, error: "not found" }, 404),
    });
    const res = await p.page.callRegistryTool("register_source", { kind: "podcast_rss", url: SOURCE.canonical_url });
    check(Boolean(res) && res.ok === false && res.error && res.error.code === "validation_error", "the /tools/ refusal is returned as the tool's ok:false reply", res);
    check(p.ranTool("register_source").length === 1, "the register tool runs once", p.ranTool("register_source").length);
  });

  await scenario("a tool refusal over MCP is returned, not thrown", async () => {
    const p = makePage({ tool: () => refusal("rate_limited", "Too many register_source calls") });
    let thrown = null;
    let res = null;
    try {
      res = await p.page.callRegistryTool("register_source", { kind: "podcast_rss", url: SOURCE.canonical_url });
    } catch (e) {
      thrown = e;
    }
    check(thrown === null, "callRegistryTool does not throw on a tool refusal", thrown && thrown.message);
    check(Boolean(res) && res.ok === false && res.error && res.error.message === "Too many register_source calls", "the refusal payload is returned whole", res);
    check(p.requests.filter((r) => r.path === "/mcp/v1/tools/call" || r.path.startsWith("/tools/")).length === 1, "exactly one tool request is made", p.requests.map((r) => r.path));
  });
}

async function groupActivity() {
  function primed(p) {
    p.activity.packet = activityPacket(OLD_REVISION);
    p.activity.stale = false;
    p.activity.error = null;
    p.activity.loading = false;
  }
  const activityCalls = (p) => p.sent("get_library_activity").map((r) => (r.body && r.body.params ? r.body.params.arguments : r.body));

  await scenario("activity summary refused", async () => {
    const p = makePage({ tool: () => refusal("validation_error", "interval end must be after start") });
    await p.page.loadLibraryActivity(true);
    await settle();
    check(p.sent("get_library_activity").length === 1 && p.viaHttp().length === 0, "a refused summary is asked for once, not re-sent over /tools/", p.requests.map((r) => r.path));
    const err = p.activity.error || {};
    check(err.code === "validation_error", "the panel keeps the tool's error code", err);
    check(err.message === "interval end must be after start", "the panel keeps the tool's message", err);
    const status = p.getEl("activityCoverageStatus").textContent;
    check(status === "Unavailable (interval end must be after start)", "the coverage line shows the reason in words", status);
    check(p.getEl("libraryActivityBadge").textContent === "Error", "the badge reads Error, not Unavailable", p.getEl("libraryActivityBadge").textContent);
  });

  await scenario("activity summary refused with a plain error string", async () => {
    const p = makePage({ tool: () => plainRefusal() });
    await p.page.loadLibraryActivity(true);
    await settle();
    check(p.sent("get_library_activity").length === 1 && p.viaHttp().length === 0, "a plain-string summary refusal is asked for once", p.requests.map((r) => r.path));
    const err = p.activity.error || {};
    check(err.message === PLAIN_REASON, "the panel keeps the plain-string reason", err);
    const status = p.getEl("activityCoverageStatus").textContent;
    check(status === `Unavailable (${PLAIN_REASON})`, "the coverage line shows the plain-string reason, not a generic failure", status);
  });

  await scenario("stale evidence page whose summary reload is refused with a plain error string", async () => {
    const p = makePage({
      tool: (name, args) => (args.detail ? refusal("stale_report", "Report revision mismatch; refresh summary before paging detail") : plainRefusal()),
    });
    primed(p);
    await p.page.fetchActivityEvidence("items.total", 20);
    await settle();
    check(activityCalls(p).length === 2 && p.viaHttp().length === 0, "the stale page reloads the summary once", p.requests.map((r) => r.path));
    const err = p.activity.error || {};
    check(err.message === PLAIN_REASON, "the refused reload keeps the plain-string reason", err);
    const status = p.getEl("activityCoverageStatus").textContent;
    check(status === `Unavailable (${PLAIN_REASON})`, "the coverage line shows the reload's plain-string reason", status);
  });

  // tests/library_work_astra/test_phase5_dashboard.py runs only this slice of the
  // script, with callRegistryTool stubbed; reading a refusal must not reach outside it.
  await scenario("the activity script reads a refusal on its own", async () => {
    const first = PAGE.indexOf("    const libraryActivityState =");
    const last = PAGE.indexOf("    async function loadStandingSubscriptions()", first);
    check(first > 0 && last > first, "the activity script slice is found", [first, last]);
    const elements = new Map();
    const ctx = vm.createContext({
      document: {
        hidden: false,
        activeElement: null,
        getElementById: (id) => {
          if (!elements.has(id)) elements.set(id, new FakeEl(id, TAGS.get(id)));
          return elements.get(id);
        },
        querySelectorAll: () => [],
        addEventListener() {},
      },
      URL,
      window: { addEventListener() {} },
      setInterval: () => 1,
      clearInterval() {},
      callRegistryTool: async () => plainRefusal(),
    });
    vm.runInContext(`${PAGE.slice(first, last)}
;globalThis.__activity = { libraryActivityState, loadLibraryActivity };`, ctx);
    await ctx.__activity.loadLibraryActivity(true);
    const err = ctx.__activity.libraryActivityState.error || {};
    check(err.code === "error" && err.message === PLAIN_REASON, "the sliced activity script keeps the plain-string reason", err);
  });

  for (const [label, reply, reason] of [
    ["a contract envelope", refusal("rate_limited", "Too many activity reads"), "Too many activity reads"],
    ["a plain error string", plainRefusal(), PLAIN_REASON],
  ]) {
    await scenario(`evidence page refused with ${label}`, async () => {
      const p = makePage({ tool: (name, args) => (args.detail ? reply : activityPacket(OLD_REVISION)) });
      primed(p);
      await p.page.fetchActivityEvidence("items.total", 20);
      await settle();
      check(activityCalls(p).length === 1 && p.viaHttp().length === 0, `an evidence page refused with ${label} is asked for once`, p.requests.map((r) => r.path));
      const html = p.getEl("evidenceRowsContainer").innerHTML;
      check(html.includes(`Failed to load evidence: ${reason}`), `the evidence view shows the reason from ${label}`, html);
      check(!html.includes("unknown") && !html.includes("[object Object]"), "the evidence view never falls back to a generic reason", html);
      check(p.getEl("evidenceNextPageBtn").disabled === true && p.getEl("evidencePrevPageBtn").disabled === true, "evidence paging is disabled");
    });
  }

  await scenario("stale evidence page reloads the summary", async () => {
    const p = makePage({
      tool: (name, args) => (args.detail ? refusal("stale_report", "Report revision mismatch; refresh summary before paging detail") : activityPacket(NEW_REVISION)),
    });
    primed(p);
    await p.page.fetchActivityEvidence("items.total", 20);
    await settle();
    const calls = activityCalls(p);
    check(calls.length === 2, "a stale evidence page is followed by one summary request", calls);
    check(Boolean(calls[0]) && calls[0].detail === "evidence" && calls[0].expected_revision === OLD_REVISION, "the first request pages evidence of the old revision", calls[0]);
    check(Boolean(calls[1]) && !("detail" in calls[1]), "the second request is the summary", calls[1]);
    check(p.viaHttp().length === 0, "nothing is re-sent over /tools/", p.viaHttp().map((r) => r.path));
    check(p.activity.packet && p.activity.packet.report_revision === NEW_REVISION, "the new summary replaces the stale report", p.activity.packet && p.activity.packet.report_revision);
    check(p.activity.stale === false && p.activity.error === null, "the panel is live again", [p.activity.stale, p.activity.error]);
    check(p.getEl("evidenceNextPageBtn").disabled === true && p.getEl("evidencePrevPageBtn").disabled === true, "old evidence pages stay disabled");
    const html = p.getEl("evidenceRowsContainer").innerHTML;
    check(html.includes("Report is stale"), "the evidence view says the report went stale", html);
    check(!html.includes("[object Object]"), "the evidence view never reads [object Object]", html);
  });

  await scenario("stale collection page reloads the summary", async () => {
    const p = makePage({
      tool: (name, args) => (args.detail ? refusal("stale_report", "Report revision mismatch; refresh summary before paging detail") : activityPacket(NEW_REVISION)),
    });
    primed(p);
    await p.page.fetchActivityCollection("creator_hints", 20);
    await settle();
    const calls = activityCalls(p);
    check(calls.length === 2 && Boolean(calls[1]) && !("detail" in calls[1]), "a stale collection page is followed by one summary request", calls);
    check(p.viaHttp().length === 0, "nothing is re-sent over /tools/", p.viaHttp().map((r) => r.path));
    check(p.activity.packet && p.activity.packet.report_revision === NEW_REVISION, "the new summary replaces the stale report", p.activity.packet && p.activity.packet.report_revision);
  });

  await scenario("a late stale-report reload leaves newer evidence paging alone", async () => {
    const LATE_REVISION = "c".repeat(64);
    const freshRows = Array.from({ length: 20 }, (_, i) => ({
      source_table: "items", source_key: `vid${i}`, event_time: "2026-10-14T00:00:00.000Z", details: { video_id: `vid${i}` },
    }));
    let releaseLateReload = null;
    let summaries = 0;
    const p = makePage({
      tool: (name, args) => {
        if (args.detail !== "evidence") return activityPacket(NEW_REVISION);
        if (args.expected_revision === OLD_REVISION) {
          return refusal("stale_report", "Report revision mismatch; refresh summary before paging detail");
        }
        return { ok: true, report_revision: NEW_REVISION, rows: freshRows, total_rows: 45, next: { offset: 20 } };
      },
      // Hold the stale page's summary reload until a newer refresh has finished.
      mcpTransport: (name, args) => {
        if (args.detail) return null;
        summaries += 1;
        if (summaries !== 1) return null;
        return new Promise((resolve) => { releaseLateReload = () => resolve(mcpReply(activityPacket(LATE_REVISION))); });
      },
    });
    primed(p);
    const stalePage = p.page.fetchActivityEvidence("items.total", 20);
    await settle();
    check(typeof releaseLateReload === "function", "the stale evidence page starts a summary reload", summaries);

    await p.page.loadLibraryActivity(true);
    await settle();
    check(p.activity.packet && p.activity.packet.report_revision === NEW_REVISION, "the manual refresh loads the new summary", p.activity.packet && p.activity.packet.report_revision);
    await p.page.fetchActivityEvidence("items.total", 0);
    await settle();
    const nextBtn = p.getEl("evidenceNextPageBtn");
    const prevBtn = p.getEl("evidencePrevPageBtn");
    check(nextBtn.disabled === false, "the newer evidence page enables Next", nextBtn.disabled);

    if (releaseLateReload) releaseLateReload();
    await stalePage;
    await settle();
    check(nextBtn.disabled === false, "the late reload does not disable the newer page's Next", nextBtn.disabled);
    check(prevBtn.disabled === true, "Prev stays disabled on the first page", prevBtn.disabled);
    check(p.activity.packet && p.activity.packet.report_revision === NEW_REVISION, "the late reload does not replace the newer summary", p.activity.packet && p.activity.packet.report_revision);
    check(p.activity.evidenceRows.length === 20 && p.activity.evidenceNext && p.activity.evidenceNext.offset === 20, "the newer evidence page is kept", [p.activity.evidenceRows.length, p.activity.evidenceNext]);
    const html = p.getEl("evidenceRowsContainer").innerHTML;
    check(html.includes("vid0") && !html.includes("Report is stale"), "the evidence view still shows the newer rows", html.slice(0, 200));
  });

  await scenario("collection page refused", async () => {
    const p = makePage({ tool: () => refusal("rate_limited", "Too many activity reads") });
    primed(p);
    for (const id of ["activityHintsPrevBtn", "activityHintsNextBtn"]) p.getEl(id).disabled = false;
    await p.page.fetchActivityCollection("creator_hints", 20);
    await settle();
    check(activityCalls(p).length === 1 && p.viaHttp().length === 0, "a refused collection page is asked for once", p.requests.map((r) => r.path));
    check(p.getEl("activityHintsNextBtn").disabled === true && p.getEl("activityHintsPrevBtn").disabled === true, "its pager is disabled, as before");
  });

  await scenario("summary reload cannot reach the helper", async () => {
    const p = makePage({
      tool: () => refusal("stale_report", "Report revision mismatch; refresh summary before paging detail"),
      mcpTransport: (name, args) => (args.detail ? null : "network"),
      httpTransport: () => "network",
    });
    primed(p);
    await p.page.fetchActivityEvidence("items.total", 20);
    await settle();
    const err = p.activity.error || {};
    check(err.code === "storage_unavailable", "a summary reload that got no response is reported", p.activity.error);
    check(p.getEl("libraryActivityBadge").textContent === "Unavailable", "the badge reads Unavailable, not a stuck Stale", p.getEl("libraryActivityBadge").textContent);
    check(p.ranTool("get_library_activity").length === 1, "only the evidence page reached the tool", p.ranTool("get_library_activity").length);
  });
}

const GROUPS = {
  refusal: groupRefusal,
  auth_fetch: groupAuthFetch,
  transport: groupTransport,
  activity: groupActivity,
};

const wanted = process.argv.slice(2);
const names = wanted.length ? wanted : Object.keys(GROUPS);
for (const name of names) {
  const fn = GROUPS[name];
  if (!fn) {
    failures++;
    console.error(`FAIL: unknown group ${name}`);
    continue;
  }
  const before = checks;
  await fn();
  console.log(`group ${name}: ${checks - before} checks`);
}
console.log(`${checks} checks, ${failures} failures`);
process.exit(failures ? 1 : 0);
