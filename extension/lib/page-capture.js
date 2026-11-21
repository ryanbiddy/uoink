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
  const MAX_NODES = 150000; // past this the helper's own fetch is the better path
  const MAX_MS = 8000;
  const MAX_DEPTH = 120;
  // Tracking pixels and beacons are never saved as images.
  const PIXEL_SIZE = /^\s*[01](?:\.0*)?\s*(?:px)?\s*$/i;
  const BEACON = new RegExp([
    "^https?://(?:[^/?#]*\\.)?(?:google-analytics\\.com|doubleclick\\.net|googletagmanager\\.com|",
    "scorecardresearch\\.com|quantserve\\.com|bat\\.bing\\.com)(?:[/?#:]|$)",
    "|^https?://(?:[^/?#]*\\.)?facebook\\.com/tr(?:[/?#]|$)",
    "|/(?:pixel|beacon|1x1|spacer|blank|clear|transparent|track|tracking|open)",
    "(?:\\.(?:gif|png|jpe?g|webp))?(?:[?#]|$)",
  ].join(""), "i");

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
    if (!view || !doc.body || !copy.body) return annotateCopy(copy, doc.URL);
    const live = doc.body.getElementsByTagName("*");
    const mirror = copy.body.getElementsByTagName("*");
    if (live.length !== mirror.length || live.length > MAX_SCAN) return annotateCopy(copy, doc.URL);
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
    return annotateCopy(copy, doc.URL);
  }

  // On the copy only: give Defuddle a lazy image's real source, and a code
  // block the language its highlighter wrapper names (cleaning drops the
  // wrapper before page-capture sees it).
  function annotateCopy(copy, base) {
    const root = copy.body;
    if (!root) return copy;
    for (const img of Array.from(root.querySelectorAll("img"))) {
      // A lazy loader's real source wins over its placeholder (data: or a blank image).
      const real = lazySource(img);
      if (real) img.setAttribute("src", real);
      if (isPixel(img, absUrl(img.getAttribute("src"), base))) img.remove();
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
    // A TeX annotation under any encoding name (TeX, text/x-latex) counts too:
    // Defuddle drops the annotation's encoding before page-capture sees it.
    for (const math of root.getElementsByTagName("math")) {
      if (math.getAttribute("data-latex")) continue;
      const note = Array.from(math.getElementsByTagName("annotation"))
        .find((a) => /tex/i.test(a.getAttribute("encoding") || ""));
      const tex = (note ? note.textContent : "").trim() || (math.getAttribute("alttext") || "").trim();
      if (tex) math.setAttribute("data-latex", tex.slice(0, 2000));
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

  function lazySource(img) {
    for (const name of ["data-src", "data-lazy-src", "data-original"]) {
      const value = (img.getAttribute(name) || "").trim();
      if (value && !/^data:/i.test(value)) return value;
    }
    return "";
  }

  function isPixel(img, src) {
    return PIXEL_SIZE.test(img.getAttribute("width") || "x") || PIXEL_SIZE.test(img.getAttribute("height") || "x") ||
      BEACON.test(src || "");
  }

  function imageSrc(img, base) {
    for (const value of [lazySource(img), img.getAttribute("src")]) {
      if (value && !/^data:/i.test(value.trim())) {
        const url = absUrl(value, base);
        if (url) return isPixel(img, url) ? "" : url;
      }
    }
    const set = img.getAttribute("srcset") || img.getAttribute("data-srcset");
    const url = set ? absUrl(largestFromSrcset(set), base) : "";
    return url && !isPixel(img, url) ? url : "";
  }

  // A URL as a Markdown link target: nothing that could end it early or
  // escape out of it (the helper refuses any other form).
  function mdUrl(url) {
    return url.replace(/[()\s`\\<>]/g, encodeURIComponent);
  }

  function collapse(text) {
    // \u0000 and \u0001 are this file's own markers: page text never carries them.
    return String(text || "").replace(/[\u0000\u0001]/g, "").replace(/[\s\u00a0]+/g, " ");
  }

  function escapeText(text) {
    return text.replace(/([\\`*[\]])/g, "\\$1").replace(/(^|\W)_|_(?=\W|$)/g, (m) => m.replace("_", "\\_"))
      .replace(/</g, "&lt;");
  }

  // TeX from any annotation that names TeX (application/x-tex, TeX,
  // text/x-latex...). "<" is written \lt so it never opens an HTML tag.
  function latexOf(el, display) {
    let tex = el.getAttribute("data-latex") || el.getAttribute("alttext") || "";
    if (!tex.trim()) {
      const note = Array.from(el.getElementsByTagName("annotation"))
        .find((a) => /tex/i.test(a.getAttribute("encoding") || ""));
      tex = note ? note.textContent : el.textContent;
    }
    tex = String(tex || "").replace(/</g, "\\lt ").trim();
    return display ? tex.split("\n").map((line) => collapse(line).trim()).filter(Boolean).join("\n")
      : collapse(tex).trim();
  }

  const NOTE_ID = /^#?(?:user-content-)?(?:fn|footnote-?)(?:ref)?[:\-_.]?/i;

  // One label per note, the same for its reference and its definition, never
  // shared by two notes (ids like fn1 and footnote-1 both reduce to "1").
  function footnoteLabel(value, ctx) {
    const key = String(value || "").replace(/^#/, "").replace(/^(user-content-)?(fn|footnote-?)ref/i, "$1$2");
    if (ctx.notes.has(key)) return ctx.notes.get(key);
    const base = key.replace(NOTE_ID, "").replace(/[^\p{L}\p{N}_-]/gu, "").slice(0, 30) || "1";
    let label = base;
    for (let n = 2; ctx.labels.has(label); n++) label = `${base}-${n}`;
    ctx.notes.set(key, label);
    ctx.labels.add(label);
    return label;
  }

  const BLOCK_TAGS = new Set(BLOCKISH.split(","));

  // Which elements hold a block anywhere inside: one pass, bottom up, instead
  // of a querySelector per span (quadratic on deep pages).
  function blockHolders(root) {
    const holders = new WeakSet();
    const all = root.getElementsByTagName("*");
    for (let i = all.length - 1; i >= 0; i--) {
      const el = all[i];
      if (el.parentElement && (BLOCK_TAGS.has(tagOf(el)) || holders.has(el))) holders.add(el.parentElement);
    }
    return holders;
  }

  function isBlock(el, ctx) {
    const tag = tagOf(el);
    if (tag === "math") return el.getAttribute("display") === "block";
    if (INLINE.has(tag)) return tag !== "span" && tag !== "a" && tag !== "picture" ? false : ctx.blocky.has(el);
    return true;
  }

  function tick(ctx) {
    if (++ctx.steps % 2000 === 0 && Date.now() > ctx.deadline) throw new Error("capture_timeout");
  }

  function wrap(marker, inner) {
    const match = /^(\s*)([\s\S]*?)(\s*)$/.exec(inner);
    if (!match[2]) return inner;
    return `${match[1]}${marker}${match[2]}${marker}${match[3]}`;
  }

  function inline(node, ctx, depth) {
    if (depth > MAX_DEPTH) return "";
    tick(ctx);
    if (node.nodeType === 3) return escapeText(collapse(node.nodeValue));
    if (node.nodeType !== 1) return "";
    const tag = tagOf(node);
    if (SKIP.has(tag)) return "";
    const kids = () => Array.from(node.childNodes).map((child) => inline(child, ctx, depth + 1)).join("");
    // In a table cell, paragraphs, lists and code keep a space between them.
    if (ctx.inTable && BLOCK_TAGS.has(tag)) return ` ${kids()} `;
    switch (tag) {
      case "br":
        return ctx.inTable ? " " : "\u0001"; // a hard line break, set in paragraph()
      case "img": {
        const src = imageSrc(node, ctx.base);
        if (!src) return "";
        const alt = collapse(node.getAttribute("alt")).trim().replace(/[[\]\\]/g, "");
        return `![${alt}](${mdUrl(src)})`;
      }
      case "a": {
        const raw = kids();
        const text = raw.trim();
        const rawHref = node.getAttribute("href") || "";
        if (!text) return raw ? " " : "";
        // Spaces at the edges of a link stay outside it: "see [this](...) now".
        const lead = /^\s/.test(raw) ? " " : "";
        const trail = /\s$/.test(raw) ? " " : "";
        if (rawHref.startsWith("#")) return lead + text + trail;
        const href = absUrl(rawHref, ctx.base);
        return lead + (href ? `[${text}](${mdUrl(href)})` : text) + trail;
      }
      case "code":
      case "kbd":
      case "samp":
      case "tt": {
        const text = collapse(node.textContent);
        if (!text.trim()) return text;
        // The fence is longer than any backtick run inside, as CommonMark needs.
        const longest = (text.match(/`+/g) || []).reduce((most, run) => Math.max(most, run.length), 0);
        const fence = "`".repeat(longest + 1);
        const pad = /^`|`$/.test(text) ? " " : "";
        return `${fence}${pad}${text}${pad}${fence}`;
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
        if (/^(?:user-content-)?(?:fn|footnote-?)ref/i.test(node.id || "") ||
          (link && /^#(?:user-content-)?(?:fn|footnote)(?!-?ref)/i.test(link.getAttribute("href")))) {
          return `[^${footnoteLabel(link ? link.getAttribute("href") : node.id, ctx)}]`;
        }
        return kids();
      }
      case "math": {
        const tex = latexOf(node, false);
        return tex ? `$${tex}$` : "";
      }
      case "input":
        return node.getAttribute("type") === "checkbox" ? (node.hasAttribute("checked") ? "[x] " : "[ ] ") : "";
      default:
        return kids();
    }
  }

  function paragraph(text) {
    let out = text.replace(/[ \t]*\n[ \t]*/g, "\n").replace(/ {2,}/g, " ").trim();
    out = out.replace(/(\S) \n/g, "$1  \n");
    out = out.replace(/^[\s\u0001]+|[\s\u0001]+$/g, "").replace(/[ \t]*\u0001[ \t]*/g, "  \n");
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
    const cells = rows.flatMap((row) => Array.from(row.cells));
    const width = rows.reduce((most, row) => Math.max(most, Array.from(row.cells)
      .reduce((sum, cell) => sum + Math.max(1, Math.min(10, cell.colSpan || 1)), 0)), 0);
    // The same call as the helper's _layout_table: a caption, a header or
    // header cells make a data table even when its cells hold paragraphs,
    // lists or code; nested tables, headings or quotes without them are layout.
    const role = (el.getAttribute("role") || "").toLowerCase();
    const headed = Array.from(el.children).some((child) => tagOf(child) === "caption" || tagOf(child) === "thead");
    const layout = role === "presentation" || role === "none" ||
      (!headed && cells.some((cell) => cell.querySelector("table,h1,h2,h3,h4,h5,h6,ul,ol,blockquote")));
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
      if (!/^(?:user-content-)?(?:fn|footnote)/i.test(li.id || "")) continue;
      for (const back of li.querySelectorAll("a.footnote-backref, a.footnote-back, a[href*='fnref'], " +
        "a[href*='footnote-ref'], a[href*='footnoteref']")) {
        back.remove();
      }
      const inner = blocks(li, ctx, depth + 1).join("\n\n").trim();
      if (inner) out.push(indent(inner, `[^${footnoteLabel(li.id, ctx)}]: `, "    "));
    }
    // A notes box without note ids is still text the page shows.
    return out.length ? out.join("\n") : blocks(el, ctx, depth + 1).join("\n\n");
  }

  function block(el, ctx, depth) {
    const tag = tagOf(el);
    if (/^h[1-6]$/.test(tag)) {
      const text = paragraph(inline(el, ctx, depth + 1)).replace(/\s*\n\s*/g, " ").replace(/^\\/, "");
      return text ? `${"#".repeat(Number(tag[1]))} ${text}` : "";
    }
    if (el.id === "footnotes" || /(^|\s)footnotes(\s|$)/.test(el.getAttribute("class") || "")) {
      return footnotes(el, ctx, depth); // an <ol class="footnotes"> too, before it reads as a list
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
      case "math": {
        const tex = latexOf(el, true);
        return tex ? `$$\n${tex}\n$$` : "";
      }
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
      tick(ctx);
      if (child.nodeType === 1 && SKIP.has(tagOf(child))) continue;
      if (child.nodeType === 1 && isBlock(child, ctx)) {
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

  // A code block inside a list item, quote or footnote goes out to column 0,
  // between the parts of its container: the helper only keeps column-0 fences
  // (every Markdown app agrees on those), and the code stays a code block.
  function placeCode(md, code) {
    const out = [];
    for (const line of md.split("\n")) {
      if (!line.includes("\u0000")) {
        out.push(line);
        continue;
      }
      const parts = line.split(/\u0000(\d+)\u0000/);
      for (let i = 0; i < parts.length; i++) {
        if (i % 2) {
          while (out.length && /^[\s>]*$/.test(out[out.length - 1]) && out[out.length - 1]) out.pop();
          out.push("", code[Number(parts[i])] || "", "");
        } else if (i === 0 ? /[^\s>\-*+.)\d]/.test(parts[i]) : parts[i].trim()) {
          out.push(i === 0 ? parts[i].trimEnd() : parts[i].trim());
        }
      }
    }
    return out.join("\n").replace(/\n{3,}/g, "\n\n").trim();
  }

  function toMarkdown(root, base, deadline) {
    const ctx = { base, code: [], inTable: false, notes: new Map(), labels: new Set(), steps: 0,
      deadline: deadline || Date.now() + MAX_MS, blocky: blockHolders(root) };
    let md = blocks(root, ctx, 0).join("\n\n");
    md = md.replace(/[ \t]+$/gm, (m) => (m === "  " ? m : "")).replace(/\n{3,}/g, "\n\n").trim();
    return placeCode(md, ctx.code);
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
    // A PDF, image or text file open in the tab is not a page to read here;
    // the service worker then lets the helper fetch the URL instead.
    const type = String(doc.contentType || "text/html").toLowerCase();
    if (!/^(?:text\/html|application\/xhtml\+xml)\b/.test(type)) {
      return { ok: false, code: "not_html", error: "This tab is not a web page Uoink can read." };
    }
    if (doc.getElementsByTagName("*").length > MAX_NODES) {
      return { ok: false, code: "too_large", error: "This page is too large to read in the tab." };
    }
    const Defuddle = resolveDefuddle();
    if (!Defuddle) return { ok: false, code: "reader_missing", error: "The page reader did not load." };
    const deadline = Date.now() + MAX_MS;
    let result;
    let markdown;
    try {
      result = new Defuddle(visibleCopy(doc), { url, markdown: false, useAsync: false, removeContentPatterns: false, fetch: noFetch }).parse();
      const html = String((result && result.content) || "");
      const parsed = new (doc.defaultView || global).DOMParser().parseFromString(`<body>${html}</body>`, "text/html");
      markdown = toMarkdown(parsed.body, url, deadline);
    } catch (err) {
      const slow = String(err && err.message) === "capture_timeout";
      return { ok: false, code: slow ? "too_slow" : "reader_failed",
        error: slow ? "This page took too long to read in the tab." : String((err && err.message) || err).slice(0, 200) };
    }
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
