// Standalone Node test for the X Article DOM parser
// (globalThis.XArticle.parseXArticle in extension/lib/x-article.js).
//
// Uses a MOCK / SYNTHETIC Article DOM only — no real (copyrighted) article
// text ever appears here; real content only lands in the user's local corpus
// at capture time. Run directly:  node tests/js/x_article_parser_test.mjs
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { parseHTML } from "./mini_dom.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const extractPath = join(here, "..", "..", "extension", "lib", "x-article.js");

// x-article.js is a classic-script IIFE that attaches globalThis.XArticle. It
// only defines functions at load, so eval'ing it here is safe.
const code = readFileSync(extractPath, "utf8");
(0, eval)(code); // eslint-disable-line no-eval

const XArticle = globalThis.XArticle;
if (!XArticle || typeof XArticle.parseXArticle !== "function") {
  console.error("FAIL: XArticle.parseXArticle not exported");
  process.exit(1);
}

let failures = 0;
function check(cond, msg) {
  if (!cond) { failures++; console.error(`FAIL: ${msg}`); }
  else { console.log(`ok: ${msg}`); }
}

// ---- URL normaliser -----------------------------------------------------
check(XArticle.normalizeXArticleUrl("https://x.com/synthauthor/article/1900000000001")
  === "https://x.com/synthauthor/article/1900000000001", "handle article URL canonicalises");
check(XArticle.normalizeXArticleUrl("https://twitter.com/i/article/1900000000002?s=20")
  === "https://x.com/i/article/1900000000002", "/i/article URL canonicalises off twitter.com");
check(XArticle.normalizeXArticleUrl("https://x.com/synthauthor/status/1900000000003") === null,
  "a status URL is NOT an article URL");
check(XArticle.normalizeXArticleUrl("https://x.com/home") === null, "non-article URL rejected");

// ---- SYNTHETIC mock Article DOM -----------------------------------------
const MOCK = `
<html><body>
  <div data-testid="primaryColumn">
    <div data-testid="User-Name">
      <a role="link" href="/synthauthor"><span>Synthetic Author</span></a>
      <a role="link" href="/synthauthor"><span>@synthauthor</span></a>
      <span>·</span><time>Jul 3</time>
    </div>
    <div data-testid="twitterArticleRichTextTitle">
      <span>Synthetic Field Notes</span>
    </div>
    <div data-testid="twitterArticleRichTextComponent">
      <div>
        <h2>A Subheading</h2>
        <p>An opening paragraph with a <a href="https://example.com/docs">the docs</a>
           link and some <strong>bold</strong> emphasis.</p>
        <ul>
          <li>First bullet</li>
          <li>Second bullet</li>
        </ul>
        <blockquote>A pulled quote worth remembering.</blockquote>
        <figure>
          <img src="https://pbs.twimg.com/media/synthetic.jpg" alt="Chart alt" />
          <figcaption>Figure caption text</figcaption>
        </figure>
        <p>A closing paragraph to give the body real length past the guard.</p>
      </div>
    </div>
  </div>
</body></html>`;

const root = parseHTML(MOCK);
const url = "https://x.com/synthauthor/article/1900000000001";
const res = XArticle.parseXArticle(root, url);

check(res.ok === true, `mock article parses ok (got ${JSON.stringify(res).slice(0, 120)})`);
check(res.url === url, "canonical url preserved");
check(res.title === "Synthetic Field Notes", `title parsed (got "${res.title}")`);
check(res.author_handle === "synthauthor", `handle parsed (got "${res.author_handle}")`);
check(res.author_name === "Synthetic Author", `name parsed (got "${res.author_name}")`);
check(/\(@synthauthor\)/.test(res.author), `author byline includes handle (got "${res.author}")`);

const md = res.markdown || "";
check(md.startsWith("**Synthetic Author (@synthauthor)**"), "byline leads the markdown");
check(md.includes("## A Subheading"), "heading preserved");
check(md.includes("[the docs](https://example.com/docs)"), "inline link preserved");
check(md.includes("**bold**"), "inline bold preserved");
check(md.includes("- First bullet") && md.includes("- Second bullet"), "list items preserved");
check(md.includes("> A pulled quote worth remembering."), "blockquote preserved");
check(md.includes("![Chart alt](https://pbs.twimg.com/media/synthetic.jpg)"), "image embedded in body");
check(md.includes("*Figure caption text*"), "figcaption preserved");
check(!md.includes("Synthetic Field Notes\n\nSynthetic Field Notes"), "title not duplicated into body");

check(Array.isArray(res.images) && res.images.length === 1, `one image collected (got ${res.images.length})`);
check(res.images[0] && res.images[0].src === "https://pbs.twimg.com/media/synthetic.jpg",
  "image src captured");
check(res.images[0] && res.images[0].alt === "Chart alt", "image alt captured");

// ---- honest failure: blocked / login-walled (no article container) ------
const BLOCKED = `
<html><body>
  <div data-testid="loginModal">
    <h1>Log in to X</h1>
    <p>Don't miss what's happening. People on X are the first to know.</p>
  </div>
</body></html>`;
const blocked = XArticle.parseXArticle(parseHTML(BLOCKED), "https://x.com/i/article/1900000000009");
check(blocked.ok === false, "blocked page fails");
check(blocked.code === "empty", `blocked page reports empty (got "${blocked.code}")`);
check(typeof blocked.error === "string" && blocked.error.length > 0, "blocked failure has honest copy");

// ---- honest failure: thin body, no title --------------------------------
const THIN = `
<html><body>
  <div data-testid="twitterArticleRichTextComponent"><div><p>tiny.</p></div></div>
</body></html>`;
const thin = XArticle.parseXArticle(parseHTML(THIN), "https://x.com/i/article/1900000000010");
check(thin.ok === false && thin.code === "thin", `thin body fails honestly (got ${JSON.stringify(thin)})`);

if (failures) {
  console.error(`\n${failures} X Article parser test(s) failed.`);
  process.exit(1);
}
console.log("\nAll X Article parser tests passed.");
