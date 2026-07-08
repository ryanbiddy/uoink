// Standalone Node test for the extension's client-side capture classifier
// (STC.classifyCaptureUrl in extension/lib/extract.js).
//
// This lives OUTSIDE extension/ on purpose: CI runs `node --check` and an
// eslint no-undef pass (browser/worker env only) over every file under
// extension/, and this harness uses Node globals (process, fs, URL via
// import). Keeping it here lets `pytest tests/` drive it via a wrapper
// (tests/test_extension_classifier.py) without tripping the extension lint.
//
// Run directly:  node tests/js/classifier_test.mjs
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const extractPath = join(here, "..", "..", "extension", "lib", "extract.js");

// extract.js is a classic-script IIFE that attaches globalThis.STC. It only
// *defines* functions at load (no chrome/fetch calls run), so evaluating it
// in this Node context is safe and populates globalThis.STC.
const code = readFileSync(extractPath, "utf8");
(0, eval)(code); // eslint-disable-line no-eval

const STC = globalThis.STC;
if (!STC || typeof STC.classifyCaptureUrl !== "function") {
  console.error("FAIL: STC.classifyCaptureUrl not exported from extract.js");
  process.exit(1);
}

const cases = [
  {
    name: "YouTube video (watch)",
    url: "https://www.youtube.com/watch?v=dQw4w9WgXcQ&si=abc",
    source: "youtube_video",
    endpoint: "/extract",
    action: "video",
    canonical: "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
  },
  {
    name: "YouTube video wins over playlist when list= present",
    url: "https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PL1234567890",
    source: "youtube_video",
    endpoint: "/extract",
  },
  {
    name: "YouTube playlist",
    url: "https://www.youtube.com/playlist?list=PLabcdefghij",
    source: "youtube_playlist",
    endpoint: "/playlist/start",
    action: "playlist",
    canonical: "https://www.youtube.com/playlist?list=PLabcdefghij",
  },
  {
    name: "Reddit thread",
    url: "https://www.reddit.com/r/programming/comments/abc123/some_title/",
    source: "reddit_thread",
    endpoint: "/extract/reddit",
    action: "reddit",
  },
  {
    name: "X status (video)",
    url: "https://x.com/jack/status/1234567890123456789",
    source: "x_video",
    endpoint: "/extract",
    action: "x_video",
    canonical: "https://x.com/jack/status/1234567890123456789",
  },
  {
    name: "Twitter status normalizes to x.com",
    url: "https://twitter.com/jack/status/1234567890123456789",
    source: "x_video",
    canonical: "https://x.com/jack/status/1234567890123456789",
  },
  {
    name: "X article (long-form)",
    url: "https://x.com/jack/article/1900000000001",
    source: "x_article",
    endpoint: "/extract/x-article",
    action: "x_article",
    canonical: "https://x.com/jack/article/1900000000001",
  },
  {
    name: "X /i/article normalizes",
    url: "https://twitter.com/i/article/1900000000002?s=20",
    source: "x_article",
    canonical: "https://x.com/i/article/1900000000002",
  },
  {
    name: "Podcast RSS feed URL",
    url: "https://feeds.megaphone.fm/vergecast",
    source: "podcast_feed",
    endpoint: "/podcasts/feeds",
    action: "podcast",
  },
  {
    name: "Article / web page",
    url: "https://www.theverge.com/2024/1/1/some-article",
    source: "web_page",
    endpoint: "/extract/page",
    action: "page",
    canonical: "https://www.theverge.com/2024/1/1/some-article",
  },
  {
    name: "Unsupported (non-http scheme)",
    url: "javascript:alert(1)",
    source: "unsupported",
    ok: false,
  },
  {
    name: "Unsupported (empty)",
    url: "",
    source: "empty",
    ok: false,
  },
];

let failures = 0;
for (const c of cases) {
  const got = STC.classifyCaptureUrl(c.url);
  const checks = [];
  const expectOk = c.ok === undefined ? true : c.ok;
  if (got.ok !== expectOk) checks.push(`ok ${got.ok} != ${expectOk}`);
  if (got.source !== c.source) checks.push(`source ${got.source} != ${c.source}`);
  if (c.endpoint && got.endpoint !== c.endpoint) {
    checks.push(`endpoint ${got.endpoint} != ${c.endpoint}`);
  }
  if (c.action && got.action !== c.action) {
    checks.push(`action ${got.action} != ${c.action}`);
  }
  if (c.canonical && got.canonical !== c.canonical) {
    checks.push(`canonical ${got.canonical} != ${c.canonical}`);
  }
  if (checks.length) {
    failures++;
    console.error(`FAIL: ${c.name}\n       ${checks.join("\n       ")}`);
  } else {
    console.log(`ok: ${c.name} -> ${got.source} (${got.endpoint || "-"})`);
  }
}

if (failures) {
  console.error(`\n${failures} classifier test(s) failed.`);
  process.exit(1);
}
console.log(`\nAll ${cases.length} classifier tests passed.`);
