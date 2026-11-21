// Uoink — shared X (Twitter) ARTICLE parser (V-2c).
//
// Reads a rendered X Article out of the user's authenticated page DOM and
// turns it into clean structured markdown (title, author, headings,
// paragraphs, lists, quotes, images). Same authorship model as the shipped
// Reddit content script: the parse runs in the page context where the user
// is already logged in, side-stepping X's login wall.
//
// Loaded as a classic script (NOT an ES module) so the same file can be:
//   - listed in manifest content_scripts.js BEFORE content-x-article.js
//   - eval'd in Node for the parser unit test (tests/js/x_article_parser_test.mjs)
// It only *defines* functions at load — no DOM / chrome / fetch calls run —
// so evaluating it outside a browser is safe and populates globalThis.XArticle.
//
// RESILIENCE NOTE (maintenance risk): X ships obfuscated, churning class
// names, so this parser never keys off them. It matches on stable, semantic
// signals in this priority order: data-testid (the most durable hooks X
// exposes), ARIA role / aria-level, then plain HTML tag structure. If X
// renames a testid the parser degrades to the structural walk; if it can't
// find an article body container at all it FAILS HONESTLY (returns
// {ok:false}) rather than serialising page chrome into junk. The candidate
// selector lists below are the single place to update when X changes markup.

(function (global) {
  "use strict";

  // ---- URL detection ---------------------------------------------------
  // Article URLs look like x.com/<handle>/article/<id> or x.com/i/article/<id>.
  const X_ARTICLE_HOSTS = new Set([
    "x.com", "www.x.com", "twitter.com", "www.twitter.com",
    "mobile.twitter.com", "mobile.x.com",
  ]);
  const _HANDLE_RE = /^[A-Za-z0-9_]{1,15}$/;
  const _ARTICLE_ID_RE = /^[A-Za-z0-9]{5,}$/;

  function normalizeXArticleUrl(raw) {
    if (!raw) return null;
    let u;
    try {
      u = new URL(raw.includes("://") ? raw : "https://" + raw);
    } catch {
      return null;
    }
    if (!X_ARTICLE_HOSTS.has(u.hostname.toLowerCase())) return null;
    const parts = u.pathname.replace(/^\/+|\/+$/g, "").split("/");
    if (parts.length < 3) return null;
    // /i/article/<id>
    if (parts[0].toLowerCase() === "i" && parts[1] === "article"
        && _ARTICLE_ID_RE.test(parts[2])) {
      return `https://x.com/i/article/${parts[2]}`;
    }
    // /<handle>/article/<id>
    if (parts[1] === "article" && _HANDLE_RE.test(parts[0])
        && _ARTICLE_ID_RE.test(parts[2])) {
      return `https://x.com/${parts[0]}/article/${parts[2]}`;
    }
    return null;
  }

  function isXArticleUrl(raw) {
    return !!normalizeXArticleUrl(raw);
  }

  // ---- selector candidate lists (the maintenance surface) --------------
  // Ordered most-specific/most-durable first. querySelector returns the
  // first hit, so earlier entries win.
  const TITLE_SELECTORS = [
    '[data-testid="twitterArticleRichTextTitle"]',
    '[data-testid="ArticleTitle"]',
    '[data-testid="articleTitle"]',
    '[role="heading"][aria-level="1"]',
    "article h1",
    "h1",
  ];
  const BODY_SELECTORS = [
    '[data-testid="twitterArticleRichTextComponent"]',
    '[data-testid="longformRichTextComponent"]',
    '[data-testid="ArticleBody"]',
    '[data-testid="articleBody"]',
    '[data-testid="longform-article"]',
    "article",
  ];
  const AUTHOR_SELECTORS = [
    '[data-testid="User-Name"]',
    '[data-testid="User-Names"]',
    '[data-testid="UserName"]',
  ];

  const MIN_BODY_CHARS = 40; // below this the parse is "thin" -> honest fail

  function _firstMatch(root, selectors) {
    for (const sel of selectors) {
      let el = null;
      try { el = root.querySelector(sel); } catch { el = null; }
      if (el) return el;
    }
    return null;
  }

  function _collapse(s) {
    // Collapse runs of horizontal whitespace but keep intentional newlines.
    return (s || "").replace(/[^\S\n]+/g, " ").replace(/[ \t]+\n/g, "\n").trim();
  }

  // Inline serialisation: turn an element's inline children into markdown,
  // preserving links / bold / italic / code / line breaks. Walks childNodes
  // so it sees text nodes (nodeType 3) between inline elements.
  function _inline(el) {
    if (!el) return "";
    let out = "";
    const kids = el.childNodes || [];
    for (const node of kids) {
      if (node.nodeType === 3) {
        out += node.nodeValue || node.textContent || "";
        continue;
      }
      if (node.nodeType !== 1) continue;
      const tag = (node.tagName || "").toUpperCase();
      if (tag === "BR") {
        out += "\n";
      } else if (tag === "A") {
        const href = node.getAttribute && node.getAttribute("href");
        const txt = _inline(node);
        out += (href && txt) ? `[${txt}](${href})` : txt;
      } else if (tag === "STRONG" || tag === "B") {
        const txt = _inline(node);
        out += txt ? `**${txt}**` : "";
      } else if (tag === "EM" || tag === "I") {
        const txt = _inline(node);
        out += txt ? `*${txt}*` : "";
      } else if (tag === "CODE") {
        const txt = _inline(node);
        out += txt ? "`" + txt + "`" : "";
      } else if (tag === "IMG") {
        // handled at block level; skip inline duplication
      } else {
        out += _inline(node);
      }
    }
    return out;
  }

  const _HEADINGS = {
    H1: "#", H2: "##", H3: "###", H4: "####", H5: "#####", H6: "######",
  };

  function _pushImage(el, out, images) {
    const src = el.getAttribute && el.getAttribute("src");
    if (!src) return;
    const alt = (el.getAttribute && el.getAttribute("alt")) || "";
    images.push({ src, alt });
    out.push(`![${alt}](${src})`);
  }

  function _serializeList(el, out, ordered) {
    let n = 0;
    for (const li of el.children || []) {
      if ((li.tagName || "").toUpperCase() !== "LI") continue;
      n += 1;
      const marker = ordered ? `${n}.` : "-";
      const txt = _collapse(_inline(li));
      if (txt) out.push(`${marker} ${txt}`);
    }
  }

  function _serializeFigure(el, out, images) {
    const img = el.querySelector ? el.querySelector("img") : null;
    if (img) _pushImage(img, out, images);
    const cap = el.querySelector ? el.querySelector("figcaption") : null;
    if (cap) {
      const txt = _collapse(_inline(cap));
      if (txt) out.push(`*${txt}*`);
    }
  }

  // Block-level walk. Recurses through structural wrappers (div/section/…)
  // and emits markdown for the block elements it recognises. Structural
  // recursion is what makes this resilient to X wrapping content in extra
  // divs — we don't depend on the exact nesting.
  function _walk(el, out, images) {
    for (const child of el.children || []) {
      const tag = (child.tagName || "").toUpperCase();
      if (_HEADINGS[tag]) {
        const txt = _collapse(_inline(child));
        if (txt) out.push(`${_HEADINGS[tag]} ${txt}`);
      } else if (tag === "P") {
        const txt = _collapse(_inline(child));
        if (txt) out.push(txt);
      } else if (tag === "BLOCKQUOTE") {
        const txt = _collapse(_inline(child));
        if (txt) {
          out.push(txt.split("\n").map((l) => `> ${l}`.trimEnd()).join("\n"));
        }
      } else if (tag === "UL" || tag === "OL") {
        _serializeList(child, out, tag === "OL");
      } else if (tag === "FIGURE") {
        _serializeFigure(child, out, images);
      } else if (tag === "IMG") {
        _pushImage(child, out, images);
      } else if (tag === "LI") {
        const txt = _collapse(_inline(child));
        if (txt) out.push(`- ${txt}`);
      } else if (tag === "BR") {
        /* ignore standalone breaks between blocks */
      } else {
        // Structural container (div/section/span/article/main/…): recurse.
        _walk(child, out, images);
      }
    }
  }

  function _findAuthor(root) {
    const el = _firstMatch(root, AUTHOR_SELECTORS);
    let name = "";
    let handle = "";
    const scan = el || root;
    const text = (scan && scan.textContent) || "";
    const m = text.match(/@([A-Za-z0-9_]{1,15})\b/);
    if (m) handle = m[1];
    if (el) {
      // Display name is the text before the @handle in the User-Name block.
      let head = text;
      const at = head.indexOf("@");
      if (at > 0) head = head.slice(0, at);
      // X separates fields with a middot; keep only the first chunk.
      head = head.split("·")[0];
      name = _collapse(head);
    }
    return { name, handle };
  }

  // parseXArticle(root?, sourceUrl?) -> normalised article payload.
  //   {ok:true, url, title, author, author_name, author_handle, markdown, images}
  //   {ok:false, code, error}  on an empty / blocked / thin page
  function parseXArticle(root, sourceUrl) {
    root = root || (typeof document !== "undefined" ? document : null);
    if (!root) {
      return { ok: false, code: "no_dom",
               error: "No page to read the article from." };
    }
    // Require a recognised article body container. A logged-out / blocked /
    // still-loading page won't have one — failing here is what keeps us from
    // saving page chrome as if it were the article.
    const bodyRoot = _firstMatch(root, BODY_SELECTORS);
    if (!bodyRoot) {
      return { ok: false, code: "empty",
               error: "Couldn't find the article on this page. X may still "
                 + "be loading it, it may be login-walled, or X changed its "
                 + "markup. Nothing was saved." };
    }

    const titleEl = _firstMatch(root, TITLE_SELECTORS);
    const title = titleEl ? _collapse(_inline(titleEl)) : "";

    const { name, handle } = _findAuthor(root);

    const images = [];
    const blocks = [];
    _walk(bodyRoot, blocks, images);
    // Drop a leading block that merely repeats the title.
    if (title && blocks.length && _collapse(blocks[0]).replace(/^#+\s*/, "") === title) {
      blocks.shift();
    }
    const bodyMd = blocks.join("\n\n").trim();
    const bodyText = bodyMd.replace(/[#>*`\-!\[\]()]/g, " ")
      .replace(/\s+/g, " ").trim();

    if (bodyText.length < MIN_BODY_CHARS && !title) {
      return { ok: false, code: "thin",
               error: "The article came back empty. X may still be loading "
                 + "it or has changed its markup. Nothing was saved." };
    }

    const author = handle
      ? (name && name.toLowerCase() !== handle.toLowerCase()
          ? `${name} (@${handle})` : `@${handle}`)
      : name;
    const url = normalizeXArticleUrl(sourceUrl)
      || (typeof location !== "undefined" ? normalizeXArticleUrl(location.href) : null)
      || sourceUrl
      || (typeof location !== "undefined" ? location.href : "");
    const finalTitle = title || (author ? `${author} on X` : "X Article");
    const markdown = (author ? `**${author}**\n\n` : "") + bodyMd;

    return {
      ok: true,
      url,
      title: finalTitle,
      author,
      author_name: name,
      author_handle: handle,
      markdown,
      images,
    };
  }

  // ---- the open X post (3.18.0) ------------------------------------------
  // X's link copy of a long post stops near 280 characters. The status page
  // the person has open shows the whole post, so "Uoink this post" reads it
  // here and sends it to the local helper with the link. The helper keeps
  // it only when it has the same post id and continues X's own copy, so a
  // wrong pick on a busy page is dropped there, never saved.
  const POST_SELECTOR = 'article[data-testid="tweet"]';
  const POST_TEXT_SELECTOR = '[data-testid="tweetText"]';
  const SHOW_MORE_SELECTOR = '[data-testid="tweet-text-show-more-link"]';
  const POST_TEXT_MAX = 30000; // X's own limit is 25,000 characters

  function statusIdFromUrl(raw) {
    const m = String(raw || "").match(/\/status(?:es)?\/(\d{5,25})(?:[/?#]|$)/);
    return m ? m[1] : null;
  }

  // A quoted post is drawn inside the post as a card with role="link" (a
  // div, unlike the post's own links). Nothing in that card is the post's.
  function _inQuoteCard(el, article) {
    for (let node = el && el.parentNode; node && node !== article; node = node.parentNode) {
      const role = node.getAttribute ? node.getAttribute("role") : null;
      if (role === "link" && (node.tagName || "").toUpperCase() !== "A") return true;
    }
    return false;
  }

  // The post's own elements that match, in page order, quote cards left out.
  function _own(article, selector) {
    let all = [];
    try { all = article.querySelectorAll(selector); } catch { all = []; }
    return Array.from(all).filter((el) => !_inQuoteCard(el, article));
  }

  // The post an <article> shows: its timestamp links to its own status.
  function _postIdOf(article) {
    const links = _own(article, 'a[href*="/status/"]');
    for (const a of links) {
      let hasTime = false;
      try { hasTime = !!a.querySelector("time"); } catch { hasTime = false; }
      if (!hasTime) continue;
      const id = statusIdFromUrl(a.getAttribute("href"));
      if (id) return id;
    }
    return null;
  }

  // The <article> for this status, or null. Never a parent or a reply.
  function findXPost(root, url) {
    root = root || (typeof document !== "undefined" ? document : null);
    const id = statusIdFromUrl(url || (typeof location !== "undefined" ? location.href : ""));
    if (!root || !id) return null;
    let articles = [];
    try { articles = root.querySelectorAll(POST_SELECTOR); } catch { articles = []; }
    for (const article of articles) {
      if (_postIdOf(article) === id) return { id, article };
    }
    // The open post itself sometimes has no timestamp link: X marks it as
    // the one article that isn't in the tab order. That only says which post
    // it is when the tab is showing this status (X swaps pages in place).
    const here = typeof location !== "undefined" && location && location.href
      ? statusIdFromUrl(location.href) : id;
    if (here !== id) return null;
    for (const article of articles) {
      if (article.getAttribute && article.getAttribute("tabindex") === "-1"
          && _postIdOf(article) === null) return { id, article };
    }
    return null;
  }

  // A link as X shows it: a short label, the rest of the address in hidden
  // spans, then "…". The whole address is the text minus the ellipsis.
  function _postLink(a) {
    const href = (a.getAttribute && a.getAttribute("href")) || "";
    const shown = (a.textContent || "").replace(/…\s*$/, "").trim();
    if (!/^https?:\/\//i.test(href)) return a.textContent || ""; // @handle, #tag, $cash
    if (/^https?:\/\/\S+$/i.test(shown)) return shown;
    if (/^[\w.-]+\.[a-z]{2,}(\/\S*)?$/i.test(shown)) return "https://" + shown;
    return href;
  }

  function _postText(el) {
    let out = "";
    for (const node of el.childNodes || []) {
      if (node.nodeType === 3) {
        out += node.nodeValue || node.textContent || "";
        continue;
      }
      if (node.nodeType !== 1) continue;
      const tag = (node.tagName || "").toUpperCase();
      if (tag === "BR") out += "\n";
      else if (tag === "IMG") out += (node.getAttribute && node.getAttribute("alt")) || ""; // emoji
      else if (tag === "A") out += _postLink(node);
      else out += _postText(node);
    }
    return out;
  }

  // The open post's own button that expands it in place, if it shows one.
  // A "Show more" that is a link would open another page, so it's left be.
  function showMoreButton(root, url) {
    const found = findXPost(root, url);
    if (!found) return null;
    const el = _own(found.article, SHOW_MORE_SELECTOR)[0] || null;
    return el && (el.tagName || "").toUpperCase() === "BUTTON" ? el : null;
  }

  // readXPost(root?, url?) -> {ok:true, id, text, show_more}
  //                         | {ok:false, code, error}
  function readXPost(root, url) {
    const found = findXPost(root, url);
    if (!found) {
      return { ok: false, code: "no_post", error: "Couldn't find this post on the page." };
    }
    const textEl = _own(found.article, POST_TEXT_SELECTOR)[0] || null;
    if (!textEl) {
      return { ok: false, code: "no_text", error: "This post has no text on the page." };
    }
    const text = _postText(textEl).replace(/[^\S\n]+\n/g, "\n").trim().slice(0, POST_TEXT_MAX);
    const more = _own(found.article, SHOW_MORE_SELECTOR)[0] || null;
    return { ok: !!text, id: found.id, text, show_more: !!more };
  }

  global.XArticle = {
    X_ARTICLE_HOSTS,
    normalizeXArticleUrl,
    isXArticleUrl,
    parseXArticle,
    statusIdFromUrl,
    findXPost,
    readXPost,
    showMoreButton,
    MIN_BODY_CHARS,
    TITLE_SELECTORS,
    BODY_SELECTORS,
    AUTHOR_SELECTORS,
  };
})(typeof self !== "undefined" ? self : globalThis);
