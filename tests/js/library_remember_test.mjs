// Rediscover shelf and idea starters: pure dashboard helpers pulled out of the
// REAL dashboard script and run in a node:vm context. No network.
// Run directly:  node tests/js/library_remember_test.mjs
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import vm from "node:vm";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const PAGE = readFileSync(join(ROOT, "assets", "dashboard", "index.html"), "utf8");

function grab(name) {
  const at = PAGE.indexOf(`function ${name}(`);
  if (at < 0) throw new Error(`function ${name} not found`);
  const open = PAGE.indexOf("{", PAGE.indexOf(")", at));
  let depth = 0;
  for (let i = open; i < PAGE.length; i++) {
    if (PAGE[i] === "{") depth++;
    else if (PAGE[i] === "}" && --depth === 0) return PAGE.slice(at, i + 1);
  }
  throw new Error(`function ${name} never closes`);
}

let failures = 0;
function check(cond, msg, got) {
  if (cond) { console.log(`ok: ${msg}`); return; }
  failures++;
  console.error(`FAIL: ${msg}${got === undefined ? "" : ` -- got ${JSON.stringify(got)}`}`);
}

const store = {};
const localStorage = { getItem: (k) => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = v; } };
const ctx = vm.createContext({ JSON, Array, Object, Boolean, String, Number, localStorage });
vm.runInContext([
  grab("htmlEscape"),
  'const REMEMBER_COLLAPSE_KEY = "uoink.remember.collapsed";',
  grab("rememberCollapsedMap"), grab("setRememberCollapsed"), grab("rememberShelfPlan"),
  grab("rememberCardHtml"), grab("rememberStarterHtml"), grab("rememberBlockHtml"), grab("rememberShelfHtml"),
].join("\n"), ctx);

const card = (i, extra = {}) => ({ video_id: `v${i}`, title: `Title ${i}`, kind: "video", reason: "Saved 1 month ago", ...extra });
const starter = (topic) => ({ topic, prompt: `You saved 3 things about ${topic}. Compare what they say.`, copy_prompt: "p",
  items: [card(1), card(2), card(3)] });
const data = { enabled: true, rediscover: [1, 2, 3, 4, 5].map((i) => card(i)), starters: [1, 2, 3, 4].map((i) => starter(`T${i}`)) };

// Plan: caps, switch off, filters, empty, server off.
let plan = ctx.rememberShelfPlan(data, { enabled: true, filtersActive: false });
check(plan.rediscover.length === 4 && plan.starters.length === 3, "plan caps at 4 cards and 3 starters", [plan.rediscover.length, plan.starters.length]);
plan = ctx.rememberShelfPlan(data, { enabled: false });
check(!plan.rediscover.length && !plan.starters.length, "switch off hides both shelves");
plan = ctx.rememberShelfPlan(data, { enabled: true, filtersActive: true });
check(!plan.rediscover.length && !plan.starters.length, "an active search or filter hides both shelves");
check(!ctx.rememberShelfPlan(null).rediscover.length && !ctx.rememberShelfPlan({}).starters.length, "no data means empty shelves");
check(!ctx.rememberShelfPlan({ ...data, enabled: false }).rediscover.length, "server says off means empty");

// Empty states render nothing at all.
check(ctx.rememberShelfHtml({ rediscover: [], starters: [] }, {}) === "", "nothing to show renders an empty string");
const onlyCards = ctx.rememberShelfHtml({ rediscover: [card(1)], starters: [] }, {});
check(onlyCards.includes("Rediscover") && !onlyCards.includes("Idea starters"), "one shelf can show without the other");

// Card: why, clamped title with a title attribute, kind, opens the item, escapes.
const html = ctx.rememberCardHtml(card(7, { title: 'A "quoted" <b>title</b> that is very long '.repeat(4), reason: "You haven't opened this yet" }));
check(html.includes('data-remember-open="v7"'), "card opens its item");
check(/title="[^"]*&quot;quoted&quot;[^"]*&lt;b&gt;/.test(html), "full title in the title attribute, escaped");
check(!html.includes("<b>title"), "markup in titles is escaped");
check(html.includes("remember-title") && html.includes("remember-why") && html.includes("remember-kind"), "card has why, title, kind");
check(PAGE.includes("-webkit-line-clamp: 2") && PAGE.includes(".remember-title"), "title is clamped to two lines in CSS");

// Starter: prompt, items with titles, write and copy actions.
const s = ctx.rememberStarterHtml(starter("Onboarding"), 2);
check(s.includes("You saved 3 things about Onboarding."), "starter shows the plain prompt");
check(s.includes('data-remember-write="2"') && s.includes('data-remember-copy="2"'), "starter has Write and Copy prompt buttons");
check((s.match(/<li /g) || []).length === 3, "starter lists its three items");

// Collapse is per browser and tolerates broken storage.
const full = () => ctx.rememberShelfHtml({ rediscover: [card(1)], starters: [starter("X")] }, ctx.rememberCollapsedMap());
check(!full().includes(" hidden>") && full().includes('aria-expanded="true"'), "shelves start expanded");
ctx.setRememberCollapsed("rediscover", true);
const collapsed = full();
check(collapsed.includes('aria-expanded="false"') && collapsed.includes("Show") && / hidden>/.test(collapsed), "collapsed shelf is hidden with a Show button");
check((collapsed.match(/aria-expanded="true"/g) || []).length === 1, "the other shelf stays open");
ctx.setRememberCollapsed("rediscover", false);
check(!full().includes('aria-expanded="false"'), "expanding again persists");
store["uoink.remember.collapsed"] = "{not json";
check(Object.keys(ctx.rememberCollapsedMap()).length === 0, "bad stored value falls back to open");
const broken = vm.createContext({ JSON, Object, Boolean, localStorage: { getItem() { throw new Error("blocked"); }, setItem() { throw new Error("blocked"); } } });
vm.runInContext('const REMEMBER_COLLAPSE_KEY = "k";' + grab("rememberCollapsedMap") + grab("setRememberCollapsed"), broken);
check(Object.keys(broken.rememberCollapsedMap()).length === 0, "blocked storage does not throw");
broken.setRememberCollapsed("x", true);
check(true, "blocked storage on write does not throw");

// Wiring: shared container, setting, hooks.
check(PAGE.includes('id="rediscoverShelf"') && PAGE.includes('id="forYouShelf"') && PAGE.includes('class="home-shelves" id="homeShelves"'), "uses the shared home-shelves container");
check(PAGE.includes('rediscoverShelvesToggle: ["rediscover_shelves_enabled", true]'), "settings switch is wired, on by default");
check(PAGE.includes("noteItemOpened(row);"), "opening an item records last opened");

if (failures) { console.error(`${failures} check(s) failed`); process.exit(1); }
console.log("all library remember checks passed");
