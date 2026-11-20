/* Uoink page capture: the page the user sees in this tab, as clean Markdown.
 *
 * The service worker injects lib/defuddle.js and this file with
 * chrome.scripting, only into the tab where the user clicked "Uoink this
 * page", then calls UoinkPageCapture.capture(document). Defuddle reads a copy
 * of the rendered page (the user's own session, after JavaScript ran) and
 * returns the main content as HTML. This file turns that HTML into Markdown
 * and returns it with the page metadata to the service worker, which sends it
 * to the local helper only. Nothing here makes a network request: Defuddle's
 * synchronous parse is used and its fetch hook always refuses.
 */
(function (global) {
  "use strict";

  const CAPTURE_VERSION = 1;
  const ENGINE_VERSION = "0.19.6";
  const MAX_MARKDOWN = 400000;
  const MAX_SCAN = 60000;
  const MAX_DEPTH = 120;

  const INLINE = new Set(["a", "abbr", "b", "bdi", "bdo", "big", "cite", "code", "data", "del", "dfn", "em",
    "font", "i", "img", "ins", "kbd", "label", "mark", "q", "s", "samp", "small", "span", "strike", "strong",
    "sub", "sup", "time", "tt", "u", "var", "wbr", "br", "picture", "source", "math", "input"]);
  const SKIP = new Set(["script", "style", "noscript", "template", "button", "select", "textarea", "form",
    "nav", "iframe", "svg", "canvas", "object", "embed", "audio", "video", "dialog", "head", "link", "meta",
    "option", "frame", "frameset", "map", "area"]);
  const BLOCKISH = "address,article,aside,blockquote,details,dialog,dd,div,dl,dt,fieldset,figcaption,figure," +
    "footer,h1,h2,h3,h4,h5,h6,header,hgroup,hr,li,main,ol,p,pre,section,table,ul";

  function noFetch() {
    return Promise.reject(new Error("Uoink page capture never uses the network"));
  }

  // The UMD bundle sets self.Defuddle, unless the page has elements named
  // "exports" or "module" (named window properties), which redirect it.
  function resolveDefuddle() {
    const candidates = [global.Defuddle, global.exports && global.exports.Defuddle,
      global.module && global.module.exports];
    for (const candidate of candidates) {
      if (typeof candidate === "function") return candidate;
      if (candidate && typeof candidate.default === "function") return candidate.default;
    }
    return null;
  }

  function tagOf(node) {
    return node && node.nodeType === 1 ? String(node.tagName || "").toLowerCase() : "";
  }

  function hiddenIn(view, el) {
    try {
      const style = view.getComputedStyle(el);
      return !!style && style.display === "none";
    } catch (_err) {
      return false;
    }
  }

  // Copy the page so Defuddle's clean-up never changes what the user sees, and
  // drop what the browser is not showing (closed menus, hidden modals).
  function visibleCopy(doc) {
    const copy = doc.cloneNode(true);
    const view = doc.defaultView;
    if (!view || !doc.body || !copy.body) return annotateCopy(copy);
    const live = doc.body.getElementsByTagName("*");
    const mirror = copy.body.getElementsByTagName("*");
    if (live.length !== mirror.length || live.length > MAX_SCAN) return annotateCopy(copy);
    const drop = [];
    let hidden = null;
    for (let i = 0; i < live.length; i++) {
      const el = live[i];
      if (hidden && hidden.contains(el)) continue;
      hidden = null;
      if (SKIP.has(tagOf(el)) || tagOf(el) === "summary") continue;
      if (hiddenIn(view, el)) {
        hidden = el;
        drop.push(mirror[i]);
      }
    }
    for (const el of drop) el.remove();
    return annotateCopy(copy);
  }

  // On the copy only: give Defuddle a lazy image's real source, and a code
  // block the language its highlighter wrapper names (cleaning drops the
  // wrapper before page-capture sees it).
  function annotateCopy(copy) {
    const root = copy.body;
    if (!root) return copy;
    for (const img of root.querySelectorAll("img")) {
      const src = (img.getAttribute("src") || "").trim();
      const real = img.getAttribute("data-src") || img.getAttribute("data-lazy-src") || img.getAttribute("data-original");
      if (real && (!src || /^data:/i.test(src))) img.setAttribute("src", real);
    }
    for (const pre of root.querySelectorAll("pre")) {
      const code = pre.querySelector("code") || pre;
      const own = `${code.getAttribute("class") || ""} ${pre.getAttribute("class") || ""}`;
      if (/(?:^|\s)(?:language|lang)-/.test(own) || code.getAttribute("data-lang") || pre.getAttribute("data-lang")) continue;
      let el = pre.parentElement;
      for (let i = 0; el && i < 5; i++, el = el.parentElement) {
        const m = /(?:^|\s)(?:highlight-source|language|lang)-([\w+#.-]{1,24})(?=\s|$)/.exec(el.getAttribute("class") || "");
        const lang = String(el.getAttribute("data-lang") || (m && m[1]) || "").replace(/[^\w+#.-]/g, "").slice(0, 24);
        if (lang) {
          // Defuddle reads the wrapper when there is one, the block otherwise.
          el.setAttribute("data-lang", lang);
          pre.setAttribute("data-lang", lang);
          code.setAttribute("class", `${code.getAttribute("class") || ""} language-${lang}`.trim());
          break;
        }
      }
    }
    // MathML's alttext is the author's own TeX: keep it over a rebuilt one.
    for (const math of root.getElementsByTagName("math")) {
      const alt = (math.getAttribute("alttext") || "").trim();
      if (alt && !math.getAttribute("data-latex") && !math.querySelector("annotation")) {
        math.setAttribute("data-latex", alt.slice(0, 2000));
      }
    }
    // Line numbers beside highlighted code are not part of the code.
    for (const gutter of root.querySelectorAll(
      "td.linenos, .linenodiv, td.gutter, .rouge-gutter, .line-numbers-rows, .hljs-ln-numbers")) {
      gutter.remove();
    }
    return copy;
  }

  function absUrl(value, base) {
    const raw = String(value || "").trim();
    if (!raw) return "";
    try {
      const url = new URL(raw, base);
      return url.protocol === "http:" || url.protocol === "https:" ? url.href : "";
    } catch (_err) {
      return "";
    }
  }

  function largestFromSrcset(srcset) {
    let best = "";
    let bestSize = -1;
    for (const part of String(srcset || "").split(/,\s+/)) {
      const bits = part.trim().split(/\s+/);
      if (!bits[0]) continue;
      const size = parseFloat(bits[1]) || 1;
      if (size > bestSize) {
        best = bits[0];
        bestSize = size;
      }
    }
    return best;
  }

  function imageSrc(img, base) {
    const attrs = [img.getAttribute("src"), img.getAttribute("data-src"), img.getAttribute("data-lazy-src"),
      img.getAttribute("data-original")];
    for (const value of attrs) {
      if (value && !/^data:/i.test(value.trim())) {
        const url = absUrl(value, base);
        if (url) return url;
      }
    }
    const set = img.getAttribute("srcset") || img.getAttribute("data-srcset");
    return set ? absUrl(largestFromSrcset(set), base) : "";
  }

  function collapse(text) {
    return String(text || "").replace(/[\s\u00a0]+/g, " ");
  }

  function escapeText(text) {
    return text.replace(/([\\`*[\]])/g, "\\$1").replace(/(^|\W)_|_(?=\W|$)/g, (m) => m.replace("_", "\\_"))
      .replace(/</g, "&lt;");
  }

  function latexOf(el) {
    const direct = el.getAttribute("data-latex") || el.getAttribute("alttext");
    if (direct) return direct.trim();
    const note = el.querySelector && el.querySelector('annotation[encoding="application/x-tex"]');
    return note ? note.textContent.trim() : collapse(el.textContent).trim();
  }

  function footnoteLabel(value) {
    return String(value || "").replace(/^#/, "").replace(/^(?:user-content-)?fn(?:ref)?[:\-_]?/i, "")
      .replace(/[^\w-]/g, "") || "1";
  }

  function hasBlockChild(el) {
    try {
      return !!el.querySelector(BLOCKISH);
    } catch (_err) {
      return false;
    }
  }

  function isBlock(el) {
    const tag = tagOf(el);
    if (tag === "math") return el.getAttribute("display") === "block";
    if (INLINE.has(tag)) return tag !== "span" && tag !== "a" && tag !== "picture" ? false : hasBlockChild(el);
    return true;
  }

  function wrap(marker, inner) {
    const match = /^(\s*)([\s\S]*?)(\s*)$/.exec(inner);
    if (!match[2]) return inner;
    return `${match[1]}${marker}${match[2]}${marker}${match[3]}`;
  }

  function inline(node, ctx, depth) {
    if (depth > MAX_DEPTH) return "";
    if (node.nodeType === 3) return escapeText(collapse(node.nodeValue));
    if (node.nodeType !== 1) return "";
    const tag = tagOf(node);
    if (SKIP.has(tag)) return "";
    const kids = () => Array.from(node.childNodes).map((child) => inline(child, ctx, depth + 1)).join("");
    switch (tag) {
      case "br":
        return ctx.inTable ? " " : "  \n";
      case "img": {
        const src = imageSrc(node, ctx.base);
        if (!src) return "";
        const alt = collapse(node.getAttribute("alt")).trim().replace(/[[\]\\]/g, "");
        return `![${alt}](${src.replace(/[()\s]/g, encodeURIComponent)})`;
      }
      case "a": {
        const text = kids().trim();
        const rawHref = node.getAttribute("href") || "";
        if (!text) return "";
        if (rawHref.startsWith("#")) return text;
        const href = absUrl(rawHref, ctx.base);
        return href ? `[${text}](${href.replace(/[()\s]/g, encodeURIComponent)})` : text;
      }
      case "code":
      case "kbd":
      case "samp":
      case "tt": {
        const text = collapse(node.textContent);
        if (!text.trim()) return text;
        const fence = text.includes("`") ? "``" : "`";
        return `${fence}${text.includes("`") ? " " : ""}${text}${text.includes("`") ? " " : ""}${fence}`;
      }
      case "strong":
      case "b":
        return wrap("**", kids());
      case "em":
      case "i":
      case "cite":
        return wrap("*", kids());
      case "del":
      case "s":
      case "strike":
        return wrap("~~", kids());
      case "sup": {
        const link = node.querySelector("a[href^='#']");
        if (/^fnref/i.test(node.id || "") || (link && /^#(?:user-content-)?fn/i.test(link.getAttribute("href")))) {
          return `[^${footnoteLabel(link ? link.getAttribute("href") : node.id)}]`;
        }
        return kids();
      }
      case "math":
        return `$${latexOf(node)}$`;
      case "input":
        return node.getAttribute("type") === "checkbox" ? (node.hasAttribute("checked") ? "[x] " : "[ ] ") : "";
      default:
        return kids();
    }
  }

  function paragraph(text) {
    let out = text.replace(/[ \t]*\n[ \t]*/g, "\n").replace(/ {2,}/g, " ").trim();
    out = out.replace(/(\S) \n/g, "$1  \n");
    if (/^(#{1,6}\s|>|[-+*]\s|\d+[.)]\s|={3,}|-{3,})/.test(out)) out = "\\" + out;
    return out;
  }

  function codeBlock(pre, ctx) {
    const code = pre.querySelector("code") || pre;
    const classes = `${code.getAttribute("class") || ""} ${pre.getAttribute("class") || ""}`;
    const langMatch = /(?:^|\s)(?:language|lang)-([\w+#.-]+)/.exec(classes);
    const lang = (code.getAttribute("data-lang") || pre.getAttribute("data-lang") ||
      (langMatch && langMatch[1]) || "").replace(/[^\w+#.-]/g, "").slice(0, 30);
    const text = String(code.textContent || "").replace(/\r\n?/g, "\n").replace(/^\n+|\s+$/g, "");
    if (!text) return "";
    let fence = "```";
    while (text.includes(fence)) fence += "`";
    ctx.code.push(`${fence}${lang}\n${text}\n${fence}`);
    return `\u0000${ctx.code.length - 1}\u0000`;
  }

  function indent(text, first, rest) {
    return text.split("\n").map((line, i) => (i === 0 ? first + line : (line ? rest + line : ""))).join("\n");
  }

  function list(el, ctx, depth) {
    const ordered = tagOf(el) === "ol";
    let n = parseInt(el.getAttribute("start") || "1", 10);
    if (!Number.isFinite(n)) n = 1;
    const items = [];
    for (const child of el.children) {
      if (tagOf(child) !== "li") continue;
      const inner = blocks(child, ctx, depth + 1, true).join("\n");
      if (!inner.trim()) continue;
      const marker = ordered ? `${n}.` : "-";
      n += 1;
      items.push(indent(inner, marker + " ", " ".repeat(marker.length + 1)));
    }
    return items.join("\n");
  }

  function quote(el, ctx, depth) {
    const callout = el.getAttribute("data-callout");
    const inner = blocks(el, ctx, depth + 1).join("\n\n");
    if (!inner.trim()) return "";
    const head = callout ? `[!${callout.replace(/[^\w-]/g, "")}]\n` : "";
    return (head + inner).split("\n").map((line) => (line ? `> ${line}` : ">")).join("\n");
  }

  function table(el, ctx, depth) {
    const rows = Array.from(el.rows || []).filter((row) => row.closest("table") === el);
    const layout = el.getAttribute("role") === "presentation" ||
      rows.some((row) => Array.from(row.cells).some((cell) => cell.querySelector("table,ul,ol,pre,h1,h2,h3,h4,p,div p")));
    const width = rows.reduce((most, row) => Math.max(most, Array.from(row.cells)
      .reduce((sum, cell) => sum + Math.max(1, Math.min(10, cell.colSpan || 1)), 0)), 0);
    if (layout || width < 2) {
      return rows.flatMap((row) => Array.from(row.cells).flatMap((cell) => blocks(cell, ctx, depth + 1)))
        .join("\n\n");
    }
    const cols = Math.min(width, 30);
    const lines = rows.map((row) => {
      const cells = [];
      for (const cell of row.cells) {
        const text = paragraph(inline(cell, { ...ctx, inTable: true }, depth + 1)).replace(/\n/g, " ")
          .replace(/\|/g, "\\|");
        cells.push(text);
        for (let k = 1; k < Math.min(10, cell.colSpan || 1); k++) cells.push("");
      }
      while (cells.length < cols) cells.push("");
      return `| ${cells.slice(0, cols).join(" | ")} |`;
    });
    if (!lines.length) return "";
    lines.splice(1, 0, `|${" --- |".repeat(cols)}`);
    const caption = el.querySelector("caption");
    const title = caption ? paragraph(inline(caption, ctx, depth + 1)) : "";
    return (title ? `${title}\n\n` : "") + lines.join("\n");
  }

  function footnotes(el, ctx, depth) {
    const out = [];
    for (const li of el.querySelectorAll("li")) {
      if (!/^(?:user-content-)?fn/i.test(li.id || "")) continue;
      for (const back of li.querySelectorAll("a.footnote-backref, a[href^='#fnref'], a[href^='#user-content-fnref']")) {
        back.remove();
      }
      const inner = blocks(li, ctx, depth + 1).join("\n\n").trim();
      if (inner) out.push(indent(inner, `[^${footnoteLabel(li.id)}]: `, "    "));
    }
    return out.join("\n");
  }

  function block(el, ctx, depth) {
    const tag = tagOf(el);
    if (/^h[1-6]$/.test(tag)) {
      const text = paragraph(inline(el, ctx, depth + 1)).replace(/\n/g, " ").replace(/^\\/, "");
      return text ? `${"#".repeat(Number(tag[1]))} ${text}` : "";
    }
    switch (tag) {
      case "pre":
        return codeBlock(el, ctx);
      case "ul":
      case "ol":
        return list(el, ctx, depth);
      case "blockquote":
        return quote(el, ctx, depth);
      case "table":
        return table(el, ctx, depth);
      case "hr":
        return "---";
      case "math":
        return `$$\n${latexOf(el)}\n$$`;
      case "figcaption": {
        const text = paragraph(blocks(el, ctx, depth + 1).join(" "));
        return text ? (text.includes("*") ? text : `*${text}*`) : "";
      }
      case "summary": {
        const text = paragraph(inline(el, ctx, depth + 1));
        return text ? `**${text.replace(/\*\*/g, "")}**` : "";
      }
      case "dl": {
        const out = [];
        for (const child of el.children) {
          const inner = blocks(child, ctx, depth + 1).join("\n\n");
          if (!inner) continue;
          out.push(tagOf(child) === "dd" ? indent(inner, ": ", "  ") : inner);
        }
        return out.join("\n");
      }
      default:
        break;
    }
    if (el.id === "footnotes" || /(^|\s)footnotes(\s|$)/.test(el.getAttribute("class") || "")) {
      return footnotes(el, ctx, depth);
    }
    if (el.getAttribute("data-callout")) return quote(el, ctx, depth);
    return blocks(el, ctx, depth + 1).join("\n\n");
  }

  // Render a container: runs of inline content become paragraphs, block
  // children render on their own. tight=true joins a list item's parts.
  function blocks(container, ctx, depth, tight) {
    if (depth > MAX_DEPTH) return [];
    const out = [];
    let run = "";
    const flush = () => {
      const text = paragraph(run);
      if (text) out.push(text);
      run = "";
    };
    for (const child of container.childNodes) {
      if (child.nodeType === 1 && SKIP.has(tagOf(child))) continue;
      if (child.nodeType === 1 && isBlock(child)) {
        flush();
        const rendered = block(child, ctx, depth + 1);
        if (rendered && rendered.trim()) out.push(rendered);
      } else {
        run += inline(child, ctx, depth + 1);
      }
    }
    flush();
    if (tight) {
      return out.length ? [out.reduce((acc, part) => acc + (/^\s*(?:[-*]|\d+\.)\s/.test(part) ? "\n" : "\n\n") + part)] : [];
    }
    return out;
  }

  function toMarkdown(root, base) {
    const ctx = { base, code: [], inTable: false };
    let md = blocks(root, ctx, 0).join("\n\n");
    md = md.replace(/[ \t]+$/gm, (m) => (m === "  " ? m : "")).replace(/\n{3,}/g, "\n\n").trim();
    return md.replace(/\u0000(\d+)\u0000/g, (_m, i) => ctx.code[Number(i)] || "");
  }

  function clip(value, max) {
    return value === undefined || value === null ? "" : collapse(String(value)).trim().slice(0, max);
  }

  function capture(doc, options) {
    const opts = options || {};
    const url = String(opts.url || (doc && doc.URL) || "");
    if (!/^https?:\/\//i.test(url)) {
      return { ok: false, code: "bad_url", error: "Only http and https pages can be saved this way." };
    }
    const Defuddle = resolveDefuddle();
    if (!Defuddle) return { ok: false, code: "reader_missing", error: "The page reader did not load." };
    let result;
    try {
      result = new Defuddle(visibleCopy(doc), { url, markdown: false, useAsync: false, removeContentPatterns: false, fetch: noFetch }).parse();
    } catch (err) {
      return { ok: false, code: "reader_failed", error: String((err && err.message) || err).slice(0, 200) };
    }
    const html = String((result && result.content) || "");
    const parsed = new (doc.defaultView || global).DOMParser().parseFromString(`<body>${html}</body>`, "text/html");
    let markdown = toMarkdown(parsed.body, url);
    const truncated = markdown.length > MAX_MARKDOWN;
    if (truncated) markdown = markdown.slice(0, MAX_MARKDOWN);
    const title = clip(result.title || doc.title, 500);
    return {
      ok: true,
      payload: {
        url,
        title,
        author: clip(result.author, 300),
        published: clip(result.published, 100),
        site: clip(result.site, 300),
        description: clip(result.description, 1000),
        image: absUrl(result.image, url),
        language: clip(result.language, 40),
        word_count: Number(result.wordCount) || 0,
        markdown,
        truncated,
        engine: "defuddle",
        engine_version: ENGINE_VERSION,
        capture_version: CAPTURE_VERSION,
      },
    };
  }

  global.UoinkPageCapture = { capture, toMarkdown, CAPTURE_VERSION, ENGINE_VERSION };
})(globalThis);
