// 3.18 shelves: Tidy Uncategorized and Select in the dashboard. Pulls the
// pure helpers out of the REAL dashboard script by name and runs them in a
// node:vm context. No browser, no network, made-up saves only.
// Run directly:  node tests/js/dash_shelves_test.mjs
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

function constant(name) {
  const match = PAGE.match(new RegExp(`const ${name} = [^;]+;`));
  if (!match) throw new Error(`const ${name} not found`);
  return match[0];
}

let failures = 0;
let checks = 0;
function check(cond, msg, got) {
  checks++;
  if (cond) { console.log(`ok: ${msg}`); return; }
  failures++;
  console.error(`FAIL: ${msg}${got === undefined ? "" : ` -- got ${JSON.stringify(got)}`}`);
}

const ctx = vm.createContext({ Number, Math, Array, String, Set, JSON, TextEncoder });
vm.runInContext([
  constant("TIDY_PREVIEW_ITEMS"), constant("SHELF_MOVE_BYTES"),
  grab("htmlEscape"), grab("isFallbackShelf"), grab("uncategorizedCountFrom"), grab("shelfMoveChunks"),
  grab("savesWord"), grab("shelfUndoFromSummary"), grab("shelfMoveText"), `async ${grab("moveToShelves")}`,
  grab("tidyIntroText"), grab("tidyStaysText"), grab("tidyGroupsHtml"),
].join("\n"), ctx);

check(ctx.uncategorizedCountFrom({ topic: [{ value: "AI", count: 4 }, { value: " uncategorized ", count: 7 }] }) === 7,
  "the Uncategorized count comes from the topic facets, any case or spacing");
check(ctx.uncategorizedCountFrom(null) === 0 && ctx.uncategorizedCountFrom({ topic: [] }) === 0,
  "no facets means nothing to tidy");

// Real ids and the longest shelf name, in a script that takes three bytes a
// character: every part, with the rest of the body, still fits under 64 KB.
const wide = "\u98df".repeat(64);
const moves = Array.from({ length: 2500 }, (_, i) => ({
  video_id: `reddit_${(i * 7919).toString(16).padStart(11, "0")}`, shelf: wide, from: "Uncategorized" }));
const chunks = ctx.shelfMoveChunks(moves);
const bodyBytes = (part) => new TextEncoder().encode(JSON.stringify({
  moves: part, label: "Tidy", source: "tidy", append_to: "mv_0123456789ab" })).length;
check(chunks.length > 3 && chunks.every((part) => bodyBytes(part) < 64 * 1024),
  "each part fits under the helper's 64 KB body cap, measured in bytes", chunks.map(bodyBytes));
check(chunks.reduce((n, part) => n + part.length, 0) === 2500 && chunks[0][0] === moves[0],
  "every move is sent once, in order");
check(ctx.shelfMoveChunks([{ video_id: "v1", shelf: "Cooking" }]).length === 1, "a small move is one part");

// A later part that fails leaves the earlier parts moved, with their undo.
const sent = [];
ctx.authFetch = async (path, init) => {
  const body = JSON.parse(init.body);
  sent.push(body);
  if (sent.length === 2) throw new Error("Request body too large.");
  return { batch_id: "mv_aaaaaaaaaaaa", moves: body.moves.map((m) => ({ video_id: m.video_id })), skipped: [] };
};
const partial = await ctx.moveToShelves(moves, "Tidy", { source: "tidy" });
check(partial.batchId === "mv_aaaaaaaaaaaa" && partial.movedIds.length === chunks[0].length
    && partial.failed === 2500 - chunks[0].length,
  "a failed part keeps what moved and counts what did not", { moved: partial.movedIds.length, failed: partial.failed });
check(sent[0].source === "tidy" && !sent[0].append_to && sent[1].append_to === "mv_aaaaaaaaaaaa",
  "later parts join the first part's undo");
check(/did not move\. Request body too large\. Try again for the rest\./.test(ctx.shelfMoveText(partial, "Bread")),
  "the toast says how many did not move", ctx.shelfMoveText(partial, "Bread"));
ctx.authFetch = async () => { throw new Error("offline"); };
let threw = false;
try { await ctx.moveToShelves(moves.slice(0, 3), "Move"); } catch (err) { threw = true; }
check(threw, "a move that never started still reports the error");

check(ctx.shelfUndoFromSummary({ id: "mv_1", count: 3, shelves: ["Bread"], undone: false }).text === "Moved 3 saves to Bread.",
  "Undo after a reload reads the helper's last move");
check(ctx.shelfUndoFromSummary({ id: "mv_1", count: 3, shelves: ["A", "B"] }).text === "Moved 3 saves to 2 shelves.",
  "a move to several shelves says how many");
check(ctx.shelfUndoFromSummary({ id: "mv_1", count: 3, undone: true }) === null && ctx.shelfUndoFromSummary(null) === null,
  "nothing to undo shows no Undo");
check(ctx.uncategorizedCountFrom({ topic: [{ value: "Inbox", count: 5 }, { value: "Uncategorized", count: 2 }] }, "Inbox") === 5,
  "Tidy follows a fallback shelf renamed in topics.json");

check(ctx.tidyIntroText({ total: 0, groups: [] }) === "Nothing is on Uncategorized. Every save has a shelf.",
  "the empty state says every save has a shelf");
check(/No shelf fits the 5 saves on Uncategorized yet, so they stay there/.test(ctx.tidyIntroText({ total: 5, groups: [], stays: 5 })),
  "with no proposals the saves stay and Select is offered");
check(/the 1 save on Uncategorized yet, so it stays there/.test(ctx.tidyIntroText({ total: 1, groups: [], stays: 1 })),
  "one save reads as one");

const long = "A very long shelf name that keeps going and going past the edge of a phone";
const data = {
  total: 600, stays: 590, more: false,
  groups: [
    { shelf: "Cooking", new: false, items: [{ video_id: "a1", title: "<b>Sourdough</b>", reason: "Words like sourdough" }] },
    { shelf: long, new: true, items: Array.from({ length: 9 }, (_, i) => ({ video_id: `t${i}`, title: `Tomato ${i}`, reason: "Shared words" })) },
  ],
};
check(/found a shelf for 10 of the 600 saves/.test(ctx.tidyIntroText(data)), "the intro counts proposals", ctx.tidyIntroText(data));
check(/590 saves stay on Uncategorized/.test(ctx.tidyStaysText(data)), "the saves that stay are counted");
const html = ctx.tidyGroupsHtml(data, new Set());
check(!html.includes("<b>Sourdough</b>") && html.includes("&lt;b&gt;Sourdough&lt;/b&gt;"), "titles are escaped");
check(html.includes('data-tidy-move-group="0"') && html.includes("Move it"), "a one-save group offers Move it");
check(html.includes("Move all 9") && html.includes("Show all 9"), "a big group offers Move all and Show all");
check((html.match(/data-tidy-move-item="1:/g) || []).length === 5, "a closed group previews five saves");
check(html.includes(`data-tidy-name="1"`) && html.includes("New shelf"), "a new shelf can be renamed before moving");
check(html.includes(`<strong title="Cooking">Cooking</strong>`), "an existing shelf name carries its full name as a tooltip");
data.groups[1].draft = "Tomatoes <b>";
data.groups[1].key = "1:tomatoes";
const drafted = ctx.tidyGroupsHtml(data, new Set());
check(drafted.includes('value="Tomatoes &lt;b&gt;"'), "a name typed before re-render stays, escaped");
data.groups[1].draft = `x" onfocus="alert(1)' y`;
const quoted = ctx.tidyGroupsHtml(data, new Set());
check(quoted.includes('value="x&quot; onfocus=&quot;alert(1)&#39; y"') && !quoted.includes('" onfocus="'),
  "quotes in a typed name cannot leave the value attribute");
check(ctx.htmlEscape(`<a href='x'>"&"</a>`) === "&lt;a href=&#39;x&#39;&gt;&quot;&amp;&quot;&lt;/a&gt;",
  "htmlEscape covers all five characters");
check((ctx.tidyGroupsHtml(data, new Set(["1:tomatoes"])).match(/data-tidy-move-item="1:/g) || []).length === 9,
  "an open group stays open by its key, whatever its name becomes");
delete data.groups[1].key;
delete data.groups[1].draft;
const openHtml = ctx.tidyGroupsHtml(data, new Set([long]));
check((openHtml.match(/data-tidy-move-item="1:/g) || []).length === 9 && openHtml.includes("Show fewer"),
  "an open group lists every save");

// Source guards for layout (PR #443 lessons) and wiring.
check(/\.tidy-item \{[^}]*grid-template-columns: minmax\(0, 1fr\) auto/.test(PAGE), "tidy rows let the title shrink");
check(/\.tidy-item-title \{[^}]*text-overflow: ellipsis/.test(PAGE), "long titles ellipsize");
check(/\.tidy-item-why,\s*\.tidy-stays \{[^}]*overflow-wrap: anywhere/.test(PAGE), "reasons wrap long words");
check(/\.shelf-bar \{[^}]*width: min\(640px, calc\(100vw - 32px\)\)/.test(PAGE), "the shelf bar fits a phone");
check(PAGE.includes('id="librarySelectToggle"') && PAGE.includes("data-tidy-open"), "Select and Tidy have entry points");
check(/markOpenLibraryRow\(\);\r?\n\s*syncSelection\(\);/.test(PAGE)
    && /renderShelfBar\(\);\r?\n\s*if \(typeof scheduleResearchPoll/.test(PAGE),
  "the list keeps picks across re-renders and the bar follows the tab");
for (const word of ["—", "seamless", "leverage", "robust", "delve", "straightforward", "unlock"]) {
  const block = PAGE.slice(PAGE.indexOf("// ---- 3.18 shelves"), PAGE.indexOf("async function moveSelectedSaves"));
  check(!block.toLowerCase().includes(word), `shelves copy avoids ${JSON.stringify(word)}`);
}

console.log(`${checks} checks, ${failures} failures`);
process.exit(failures ? 1 : 0);
