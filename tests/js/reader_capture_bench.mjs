// Reader benchmark runner for the extension path ("Uoink this page").
//
// Loads each fixture's rendered DOM (or its served HTML when nothing renders
// differently) into jsdom at the fixture URL, runs the shipped
// extension/lib/defuddle.js and extension/lib/page-capture.js in that window
// exactly as chrome.scripting does, and prints the capture results as JSON.
// tests/reader_bench.py scores them. Offline: jsdom loads no subresources and
// fetch/XMLHttpRequest throw and are counted.
//
// node tests/js/reader_capture_bench.mjs tests/fixtures/reader [name...]
import { readFileSync, readdirSync } from 'node:fs';
import { createRequire } from 'node:module';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const require = createRequire(new URL('./reader/package.json', import.meta.url));
const { JSDOM, VirtualConsole } = require('jsdom');
const root = new URL('../../', import.meta.url);
const defuddle = readFileSync(new URL('extension/lib/defuddle.js', root), 'utf8');
const pageCapture = readFileSync(new URL('extension/lib/page-capture.js', root), 'utf8');

export function captureHtml(html, url, contentType = 'text/html') {
  const quiet = new VirtualConsole();
  const dom = new JSDOM(html, { url, contentType, runScripts: 'outside-only', virtualConsole: quiet });
  const win = dom.window;
  let netCalls = 0;
  win.fetch = () => { netCalls += 1; return Promise.reject(new Error('offline')); };
  win.XMLHttpRequest = function XMLHttpRequest() { netCalls += 1; throw new Error('offline'); };
  win.eval(defuddle);
  win.eval(pageCapture);
  const before = win.document.documentElement.outerHTML;
  const started = Date.now();
  const result = win.UoinkPageCapture.capture(win.document);
  const ms = Date.now() - started;
  const mutated = win.document.documentElement.outerHTML !== before;
  win.close();
  return { ...JSON.parse(JSON.stringify(result)), mutated, net_calls: netCalls, ms };
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const [dir, ...names] = process.argv.slice(2);
  const wanted = names.length ? names
    : readdirSync(dir).filter((f) => f.endsWith('.gold.json')).map((f) => f.replace(/\.gold\.json$/, ''));
  const results = {};
  for (const name of wanted) {
    const gold = JSON.parse(readFileSync(path.join(dir, `${name}.gold.json`), 'utf8'));
    const html = readFileSync(path.join(dir, gold.rendered || `${name}.html`), 'utf8');
    results[name] = captureHtml(html, gold.url);
  }
  process.stdout.write(JSON.stringify({ results }));
}
