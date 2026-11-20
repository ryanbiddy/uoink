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

const ctx = vm.createContext({ Number, Math, Array, String, Set, JSON });
vm.runInContext([
  constant("TIDY_PREVIEW_ITEMS"), constant("SHELF_MOVE_CHUNK"),
  grab("htmlEscape"), grab("uncategorizedCountFrom"), grab("shelfMoveChunks"), grab("savesWord"),
  grab("tidyIntroText"), grab("tidyStaysText"), grab("tidyGroupsHtml"),
].join("\n"), ctx);

check(ctx.uncategorizedCountFrom({ topic: [{ value: "AI", count: 4 }, { value: " uncategorized ", count: 7 }] }) === 7,
  "the Uncategorized count comes from the topic facets, any case or spacing");
check(ctx.uncategorizedCountFrom(null) === 0 && ctx.uncategorizedCountFrom({ topic: [] }) === 0,
  "no facets means nothing to tidy");

const moves = Array.from({ length: 2500 }, (_, i) => ({ video_id: `v${i}`, shelf: "Cooking" }));
const chunks = ctx.shelfMoveChunks(moves);
check(chunks.length === 3 && chunks[0].length === 1000 && chunks[2].length === 500,
  "a big move is sent in parts of 1,000", chunks.map((c) => c.length));
check(JSON.stringify({ moves: chunks[0], label: "Tidy", append_to: "mv_0123456789ab" }).length < 64 * 1024,
  "each part fits under the helper's 64 KB body cap");

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
