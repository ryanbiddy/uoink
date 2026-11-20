// Standalone Node test for the open-post reader (3.18.0) in
// extension/lib/x-article.js: XArticle.readXPost / findXPost / showMoreButton.
// X's link copy of a long post stops near 280 characters, so "Uoink this
// post" reads the whole post from the page the person has open.
//
// Synthetic DOM only: made-up handles, ids and text.
// Run directly:  node tests/js/x_post_reader_test.mjs
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { parseHTML } from "./mini_dom.mjs";

const here = dirname(fileURLToPath(import.meta.url));
(0, eval)(readFileSync(join(here, "..", "..", "extension", "lib", "x-article.js"), "utf8")); // eslint-disable-line no-eval
const X = globalThis.XArticle;

let failures = 0;
function check(cond, msg, extra) {
  if (!cond) { failures++; console.error(`FAIL: ${msg}`, extra === undefined ? "" : extra); }
  else { console.log(`ok: ${msg}`); }
}

const PARENT = "1900000000000000100";
const FOCAL = "1900000000000000101";
const REPLY = "1900000000000000102";
const QUOTED = "1900000000000000103";
const URL = `https://x.com/example_writer/status/${FOCAL}`;

function post(id, handle, textHtml, { tabindex = "0", extra = "", timeLink = true } = {}) {
  const stamp = timeLink
    ? `<a href="/${handle}/status/${id}" role="link"><time datetime="2026-11-01T10:00:00.000Z">Nov 1</time></a>`
    : `<span><time datetime="2026-11-01T10:00:00.000Z">10:00 AM · Nov 1, 2026</time></span>`;
  return `<article data-testid="tweet" tabindex="${tabindex}">
    <div data-testid="User-Name"><span>Example</span><a href="/${handle}">@${handle}</a>${stamp}</div>
    <div data-testid="tweetText" lang="en">${textHtml}</div>${extra}
  </article>`;
}

const LONG_HTML = "<span>Spent the week rebuilding a small notes app. </span>"
  + '<img alt="🔧" src="https://abs.example.test/emoji/1f527.svg">'
  + "<span> The fix was boring.</span><br><br>"
  + '<span>Thanks </span><a href="/example_friend" role="link">@example_friend</a>'
  + "<span> for the review. Write-up: </span>"
  + '<a href="https://t.co/LinkInNote1" rel="noopener noreferrer nofollow" target="_blank" role="link">'
  + '<span aria-hidden="true">https://</span>example.com/notes-che<span aria-hidden="true">cker</span><span aria-hidden="true">…</span></a>'
  + "<span> FULL-TEXT-END</span>";

const quoteCard = `<div role="link" tabindex="0"><div data-testid="User-Name"><span>Quoted</span><span>@example_quoter</span>
  <time datetime="2026-10-30T10:00:00.000Z">Oct 30</time></div>
  <div data-testid="tweetText"><span>QUOTED-TEXT should not be read for ${QUOTED}</span></div></div>`;

const statusPage = parseHTML(`<main>
  ${post(PARENT, "example_parent", "<span>PARENT-TEXT the post above.</span>")}
  ${post(FOCAL, "example_writer", LONG_HTML, { tabindex: "-1", extra: quoteCard })}
  ${post(REPLY, "example_replier", "<span>REPLY-TEXT a reply below.</span>")}
</main>`);

// ---- ids ---------------------------------------------------------------------
check(X.statusIdFromUrl(URL) === FOCAL, "status id from a status URL");
check(X.statusIdFromUrl(`https://x.com/a/status/${FOCAL}/photo/1`) === FOCAL, "status id from a photo URL");
check(X.statusIdFromUrl("https://x.com/home") === null, "no status id on the home timeline");

// ---- the focal post, never a parent, reply or quote ---------------------------
const read = X.readXPost(statusPage, URL);
check(read.ok === true && read.id === FOCAL, "reads the post the URL names", read);
check(read.text.startsWith("Spent the week rebuilding a small notes app. 🔧 The fix was boring."),
  "text nodes and emoji alt text are kept in order", read.text);
check(read.text.includes("\n\nThanks @example_friend for the review."), "line breaks and @mentions stay", read.text);
check(read.text.includes("Write-up: https://example.com/notes-checker FULL-TEXT-END"),
  "a shortened link is saved as its whole address, without the ellipsis", read.text);
check(!/PARENT-TEXT|REPLY-TEXT|QUOTED-TEXT/.test(read.text), "parent, reply and quoted text are not read", read.text);
check(read.show_more === false, "no Show more on the open post");

// ---- the open post without a timestamp link ---------------------------------
const noLink = parseHTML(`<main>
  ${post(PARENT, "example_parent", "<span>PARENT-TEXT</span>")}
  ${post(FOCAL, "example_writer", "<span>FOCAL-ONLY</span>", { tabindex: "-1", timeLink: false })}
</main>`);
const fallback = X.readXPost(noLink, URL);
check(fallback.ok && fallback.text === "FOCAL-ONLY", "falls back to the one article out of the tab order", fallback);

// ---- nothing to read ---------------------------------------------------------
const elsewhere = X.readXPost(statusPage, `https://x.com/a/status/1900000000000000999`);
check(elsewhere.ok === false && elsewhere.code === "no_post", "a post that isn't on the page is not guessed", elsewhere);
const noText = parseHTML(`<main><article data-testid="tweet" tabindex="-1">
  <a href="/example_writer/status/${FOCAL}"><time>Nov 1</time></a><div data-testid="card.wrapper">Article card</div>
</article></main>`);
check(X.readXPost(noText, URL).code === "no_text", "a post with no text (an Article link card) says so");

// ---- Show more ---------------------------------------------------------------
const collapsedButton = parseHTML(`<main>${post(FOCAL, "example_writer", "<span>Start of a long post</span>", {
  extra: '<button data-testid="tweet-text-show-more-link" type="button">Show more</button>' })}</main>`);
const collapsed = X.readXPost(collapsedButton, URL);
check(collapsed.ok && collapsed.show_more === true, "a post still showing Show more is flagged", collapsed);
check(X.showMoreButton(collapsedButton, URL) !== null, "an in-place Show more button is offered to press");
const collapsedLink = parseHTML(`<main>${post(FOCAL, "example_writer", "<span>Start</span>", {
  extra: `<a data-testid="tweet-text-show-more-link" href="/example_writer/status/${FOCAL}">Show more</a>` })}</main>`);
check(X.showMoreButton(collapsedLink, URL) === null, "a Show more link (opens a page) is never pressed");
check(X.readXPost(collapsedLink, URL).show_more === true, "but it is still flagged");

if (failures) {
  console.error(`\n${failures} check(s) failed`);
  process.exit(1);
}
console.log("\nall open-post reader checks passed");
