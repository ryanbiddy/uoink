// Dashboard stress-test fixes: future dates, the speaker timeline over a long
// talk, and the Retry-After wait. Pulls the pure helpers out of the REAL
// dashboard script by name and runs them in a node:vm context. No network.
// Run directly:  node tests/js/dash_break_ui_test.mjs
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
let checks = 0;
function check(cond, msg, got) {
  checks++;
  if (cond) { console.log(`ok: ${msg}`); return; }
  failures++;
  console.error(`FAIL: ${msg}${got === undefined ? "" : ` -- got ${JSON.stringify(got)}`}`);
}

const NOW = Date.parse("2026-11-11T12:00:00Z");
const FakeDate = class extends Date {
  constructor(...args) { super(...(args.length ? args : [NOW])); }
  static now() { return NOW; }
};
const ctx = vm.createContext({ Date: FakeDate, Intl, Number, Math, Map, Set, Array, String });
vm.runInContext([
  grab("fmtDuration"), grab("fmtTimestamp"), grab("fmtAge"),
  PAGE.slice(PAGE.indexOf("const SPEAKER_TIMELINE_SLOTS"), PAGE.indexOf("const SPEAKER_TIMELINE_SLOTS") + "const SPEAKER_TIMELINE_SLOTS = 200;".length),
  grab("speakerTimelineBuckets"),
].join("\n"), ctx);

const at = (ms) => new Date(NOW + ms).toISOString();
const MIN = 60000, HOUR = 60 * MIN, DAY = 24 * HOUR;
check(ctx.fmtAge(at(-5 * MIN)) === "5m ago", "a past time still reads Xm ago", ctx.fmtAge(at(-5 * MIN)));
check(ctx.fmtAge(at(3 * DAY)) === "in 3 days", "three days ahead reads in 3 days", ctx.fmtAge(at(3 * DAY)));
check(ctx.fmtAge(at(2 * HOUR)) === "in 2 hours", "two hours ahead reads in 2 hours", ctx.fmtAge(at(2 * HOUR)));
check(ctx.fmtAge(at(10 * MIN)) === "in 10 minutes", "ten minutes ahead reads in 10 minutes", ctx.fmtAge(at(10 * MIN)));
check(ctx.fmtAge(at(3 * DAY)) !== "just now" && ctx.fmtAge(at(400 * DAY)) !== "just now", "a future date is never just now");
check(/\d/.test(ctx.fmtAge(at(400 * DAY))) && !ctx.fmtAge(at(400 * DAY)).startsWith("in "), "a far future date shows the date", ctx.fmtAge(at(400 * DAY)));

// A 10 hour talk, 3000 segments, two speakers.
const total = 36000;
const segments = Array.from({ length: 3000 }, (_, i) => ({
  speaker: i % 2 ? "B" : "A", start: i * 12, end: i * 12 + 11,
}));
const index = new Map([["A", 0], ["B", 1]]);
const bars = ctx.speakerTimelineBuckets(segments, index, total);
check(bars.length > 0 && bars.length <= 400, "a long talk draws at most about 200 slots per speaker", bars.length);
const last = bars.reduce((m, b) => Math.max(m, b.end), 0);
check(last > total * 0.95, "the bars reach the end of the talk", last);
check(bars.every((b) => /^[AB] \d+:\d\d(:\d\d)?-\d+:\d\d(:\d\d)?$/.test(b.title)), "every bar names its speaker and time span", bars[0] && bars[0].title);
const short = ctx.speakerTimelineBuckets([{ speaker: "A", start: 0, end: 30 }, { speaker: "B", start: 30, end: 60 }], index, 60);
check(short.length === 2 && short[0].index === 0 && short[1].index === 1, "a short talk keeps one bar per turn", short);

// Source-level guards for the CSS and markup fixes.
check(/\.reader-note \{[^}]*overflow-wrap: anywhere/.test(PAGE), "the reader note breaks long words");
check(/grid-template-columns: minmax\(130px, 170px\) minmax\(120px, 160px\) minmax\(150px, 190px\) minmax\(0, 1fr\)/.test(PAGE), "the Library controls have a column each at desktop width");
check(PAGE.includes('data-library-reload>Retry</button>'), "the unavailable state has a Retry button");
check(PAGE.includes("data-reader-more"), "long transcripts get a Show more button");
check(PAGE.includes("Intl.Collator(undefined, { numeric: true"), "topics sort naturally");
check(!PAGE.includes("segments.slice(0, 120)"), "the speaker timeline no longer drops segments after 120");

check(/<button class="card-title" type="button" title="\$\{title\}"[^\n]+>\$\{title\}<\/button>/.test(PAGE), "the Library card title carries the full title as a tooltip");
check(PAGE.includes('id="noteTitleInput" type="text" maxlength="300"'), "the note title box matches the 300 character title limit");
check(/@media \(max-width: 620px\) \{[\s\S]*?\.uoink-card \.row-actions \{\s*opacity: 1;/.test(PAGE), "single-column cards show their actions instead of leaving a hidden blank row");

// 3.18.1: the search box hint fits a 390 px phone. At 16px the full hint is
// about 329 px and the box has about 304 px of room at 390 px (measured in
// headless Chrome), so a phone gets the short hint and a desktop the full one.
{
  const at = PAGE.indexOf("const SEARCH_PLACEHOLDERS");
  const hasFit = at >= 0 && PAGE.includes("function searchPlaceholderFor(");
  check(hasFit, "the search box has a hint that fits its width");
  if (hasFit) {
    const fitCtx = vm.createContext({});
    vm.runInContext(PAGE.slice(at, PAGE.indexOf("];", at) + 2) + "\n" + grab("searchPlaceholderFor") +
      "\nthis.pick = searchPlaceholderFor;", fitCtx);
    const measure = (text) => text.length * 7;  // 7 px a character: 47 chars = 329 px
    const full = "Search your library or paste a link to uoink it";
    check(fitCtx.pick(304, measure) === "Search or paste a link", "a 390 px phone gets the short hint", fitCtx.pick(304, measure));
    check(fitCtx.pick(938, measure) === full, "a desktop keeps the full hint", fitCtx.pick(938, measure));
    check(fitCtx.pick(329, measure) === full, "the full hint shows when it just fits", fitCtx.pick(329, measure));
    check(fitCtx.pick(20, measure) === "Search", "a very narrow box still gets a hint", fitCtx.pick(20, measure));
    check(PAGE.includes(`aria-label="${full}"`), "screen readers still hear the full hint");
    check(/function wireEvents\(\) \{[\s\S]*?bindSearchPlaceholderFit\(\);/.test(PAGE), "the hint is fitted when the dashboard starts");
    check(/function bindSearchPlaceholderFit\(\) \{[\s\S]*?new ResizeObserver\(/.test(PAGE), "the hint is fitted again when the box changes size");
  }
}

console.log(`${checks} checks, ${failures} failures`);
process.exit(failures ? 1 : 0);
