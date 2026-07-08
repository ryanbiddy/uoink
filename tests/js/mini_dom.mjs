// Tiny, dependency-free HTML -> DOM for the X Article parser test.
//
// Node has no DOM and jsdom isn't vendored, so this implements just enough of
// the standard DOM API that extension/lib/x-article.js uses:
//   querySelector / querySelectorAll / matches, getAttribute, textContent,
//   tagName, children (elements), childNodes (elements + text), nodeType,
//   nodeValue, parentNode.
// Selector support is the subset the parser needs: tag names, attribute
// clauses [a], [a="v"], [a^="v"], [a*="v"], [a$="v"], compound (tag+attrs),
// and the descendant combinator (space). That's exactly what a genuine
// browser querySelector would evaluate for those selectors, so a parse that
// passes here exercises real selector-matching logic.

const VOID = new Set(["img", "br", "hr", "meta", "input", "link", "source"]);

class TextNode {
  constructor(text) {
    this.nodeType = 3;
    this.nodeValue = text;
    this.parentNode = null;
  }
  get textContent() { return this.nodeValue; }
}

class Element {
  constructor(tag) {
    this.nodeType = 1;
    this.tagName = tag.toUpperCase();
    this.attributes = {};
    this.childNodes = [];
    this.parentNode = null;
  }
  get children() {
    return this.childNodes.filter((n) => n.nodeType === 1);
  }
  getAttribute(name) {
    const v = this.attributes[name.toLowerCase()];
    return v === undefined ? null : v;
  }
  get textContent() {
    let s = "";
    for (const n of this.childNodes) s += n.textContent;
    return s;
  }
  _descendants(acc) {
    for (const n of this.childNodes) {
      if (n.nodeType === 1) { acc.push(n); n._descendants(acc); }
    }
    return acc;
  }
  matches(selector) {
    const steps = parseSelector(selector);
    return matchesChain(this, steps);
  }
  querySelector(selector) {
    const all = this.querySelectorAll(selector);
    return all.length ? all[0] : null;
  }
  querySelectorAll(selector) {
    const steps = parseSelector(selector);
    return this._descendants([]).filter((el) => matchesChain(el, steps));
  }
}

// ---- selector engine ----------------------------------------------------
function parseSimple(token) {
  const step = { tag: null, attrs: [] };
  let rest = token;
  const tagMatch = rest.match(/^[a-zA-Z][a-zA-Z0-9]*/);
  if (tagMatch) { step.tag = tagMatch[0].toUpperCase(); rest = rest.slice(tagMatch[0].length); }
  const attrRe = /\[([a-zA-Z0-9_-]+)(?:([\^\*\$]?)=(?:"([^"]*)"|'([^']*)'))?\]/g;
  let m;
  while ((m = attrRe.exec(rest)) !== null) {
    step.attrs.push({
      name: m[1].toLowerCase(),
      op: m[2] || (m[3] === undefined && m[4] === undefined ? null : "="),
      val: m[3] !== undefined ? m[3] : (m[4] !== undefined ? m[4] : null),
    });
  }
  return step;
}

function parseSelector(selector) {
  return selector.trim().split(/\s+/).map(parseSimple);
}

function matchesSimple(el, step) {
  if (!el || el.nodeType !== 1) return false;
  if (step.tag && el.tagName !== step.tag) return false;
  for (const a of step.attrs) {
    const got = el.getAttribute(a.name);
    if (got === null) return false;
    if (a.val === null) continue; // presence only
    if (a.op === "=" && got !== a.val) return false;
    if (a.op === "^" && !got.startsWith(a.val)) return false;
    if (a.op === "*" && !got.includes(a.val)) return false;
    if (a.op === "$" && !got.endsWith(a.val)) return false;
  }
  return true;
}

function matchesChain(el, steps) {
  if (!matchesSimple(el, steps[steps.length - 1])) return false;
  let i = steps.length - 2;
  let node = el.parentNode;
  while (i >= 0 && node) {
    if (matchesSimple(node, steps[i])) i -= 1;
    node = node.parentNode;
  }
  return i < 0;
}

// ---- HTML parser --------------------------------------------------------
function parseHTML(html) {
  const root = new Element("root");
  const stack = [root];
  let i = 0;
  const decode = (s) => s
    .replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&nbsp;/g, " ");
  while (i < html.length) {
    if (html[i] === "<") {
      if (html.startsWith("<!--", i)) { i = html.indexOf("-->", i); i = i < 0 ? html.length : i + 3; continue; }
      if (html[i + 1] === "!") { i = html.indexOf(">", i); i = i < 0 ? html.length : i + 1; continue; }
      const close = html[i + 1] === "/";
      const end = html.indexOf(">", i);
      if (end < 0) break;
      let inner = html.slice(i + (close ? 2 : 1), end).trim();
      i = end + 1;
      if (close) {
        const tag = inner.split(/\s/)[0].toUpperCase();
        for (let s = stack.length - 1; s > 0; s--) {
          if (stack[s].tagName === tag) { stack.length = s; break; }
        }
        continue;
      }
      const selfClose = inner.endsWith("/");
      if (selfClose) inner = inner.slice(0, -1).trim();
      const sp = inner.search(/\s/);
      const tag = (sp < 0 ? inner : inner.slice(0, sp));
      const el = new Element(tag);
      if (sp >= 0) {
        const attrStr = inner.slice(sp);
        const attrRe = /([a-zA-Z0-9_:-]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'))?/g;
        let am;
        while ((am = attrRe.exec(attrStr)) !== null) {
          if (!am[1]) continue;
          const val = am[2] !== undefined ? am[2] : (am[3] !== undefined ? am[3] : "");
          el.attributes[am[1].toLowerCase()] = decode(val);
        }
      }
      const parent = stack[stack.length - 1];
      el.parentNode = parent;
      parent.childNodes.push(el);
      if (!selfClose && !VOID.has(tag.toLowerCase())) stack.push(el);
    } else {
      const next = html.indexOf("<", i);
      const text = html.slice(i, next < 0 ? html.length : next);
      i = next < 0 ? html.length : next;
      if (text.length) {
        const tn = new TextNode(decode(text));
        const parent = stack[stack.length - 1];
        tn.parentNode = parent;
        parent.childNodes.push(tn);
      }
    }
  }
  return root;
}

export { parseHTML, Element, TextNode };
