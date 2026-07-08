// Standalone Node test for A1 authoritative X-Article ROUTING in the
// extension's shared client library.
//
// Covers:
//   - the single JS definition: STC.normalizeXArticleUrl delegates to the one
//     owner (XArticle.normalizeXArticleUrl in lib/x-article.js), so classify,
//     the popup, and the background context menu can't disagree.
//   - STC.resolveTabSource: a live-DOM article signal wins over URL-shape
//     guessing, so an article reached via its announcing /status/ tweet, a
//     t.co redirect, or an unsettled SPA route still routes to the article
//     path instead of silently degrading to "Uoink this page".
//
// Run directly:  node tests/js/x_article_routing_test.mjs
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const libDir = join(here, "..", "..", "extension", "lib");

// Same load order the popup + background use: x-article.js (the single URL
// definition) before extract.js (which delegates to it).
(0, eval)(readFileSync(join(libDir, "x-article.js"), "utf8")); // eslint-disable-line no-eval
(0, eval)(readFileSync(join(libDir, "extract.js"), "utf8")); // eslint-disable-line no-eval

const STC = globalThis.STC;
const XArticle = globalThis.XArticle;

let failures = 0;
function check(cond, msg) {
  if (!cond) { failures++; console.error(`FAIL: ${msg}`); }
  else { console.log(`ok: ${msg}`); }
}

check(STC && typeof STC.resolveTabSource === "function",
  "STC.resolveTabSource is exported");
check(STC && typeof STC.isXArticleUrl === "function",
  "STC.isXArticleUrl is exported");

// ---- single definition: STC delegates to XArticle -----------------------
const ARTICLE = "https://x.com/jack/article/1900000000001";
check(STC.normalizeXArticleUrl(ARTICLE) === XArticle.normalizeXArticleUrl(ARTICLE)
  && STC.normalizeXArticleUrl(ARTICLE) === ARTICLE,
  "STC.normalizeXArticleUrl delegates to XArticle (one definition)");

// ---- article URL variants all classify as article -----------------------
const articleVariants = [
  ["canonical /article/", "https://x.com/jack/article/1900000000001",
    "https://x.com/jack/article/1900000000001"],
  ["/i/article/", "https://x.com/i/article/1900000000002",
    "https://x.com/i/article/1900000000002"],
  ["twitter.com host normalizes to x.com", "https://twitter.com/jack/article/1900000000003",
    "https://x.com/jack/article/1900000000003"],
  ["mobile + ?query stripped", "https://mobile.twitter.com/jack/article/1900000000004?s=20",
    "https://x.com/jack/article/1900000000004"],
];
for (const [name, url, canonical] of articleVariants) {
  const got = STC.resolveTabSource(url, {});
  check(got.source === "x_article" && got.action === "x_article"
    && got.endpoint === "/extract/x-article" && got.canonical === canonical,
    `${name} -> x_article (${JSON.stringify(got.canonical)})`);
}

// ---- a real /status/ post is NOT an article by URL alone ----------------
const STATUS = "https://x.com/jack/status/1234567890123456789";
check(STC.resolveTabSource(STATUS, {}).source === "x_video",
  "a /status/ post classifies as x_video by URL alone");

// ---- DOM signal wins over URL-shape guessing (via-status / t.co / SPA) ---
check(STC.resolveTabSource(STATUS, { hasArticleDom: true }).source === "x_article",
  "reached via announcing /status/ tweet but DOM is an article -> x_article");
check(STC.resolveTabSource("https://t.co/abc123", { hasArticleDom: true }).source === "x_article",
  "t.co redirect rendering an article -> x_article (DOM wins)");
check(STC.resolveTabSource("https://x.com/home", { hasArticleDom: true }).source === "x_article",
  "unsettled x.com SPA route rendering an article -> x_article (DOM wins)");

// A genuine article URL is unaffected by the DOM flag.
check(STC.resolveTabSource(ARTICLE, { hasArticleDom: true }).source === "x_article",
  "canonical article URL stays x_article with DOM flag on");
// A plain web page with no article DOM is left alone.
check(STC.resolveTabSource("https://www.theverge.com/x", {}).source === "web_page",
  "a plain web page stays web_page");

if (failures) {
  console.error(`\n${failures} X Article routing test(s) failed.`);
  process.exit(1);
}
console.log("\nAll X Article routing tests passed.");
