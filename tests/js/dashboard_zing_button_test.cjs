// Make a Short with Zing: the button shows only when the helper says Zing can
// take items from Uoink, the states read in plain words, and the only local
// address the dashboard will open is the review page the hand-off just returned.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const page = fs.readFileSync(path.join(__dirname, '../../assets/dashboard/index.html'), 'utf8');
const cut = (from, to) => page.slice(page.indexOf(from), page.indexOf(to));
const opener = cut('    function nativeApi() {', '    function openExternalLink(event)');
const zingCode = cut('    // ---- Zing hand-off', '    // ---- Update notice');
assert.ok(opener.includes('function openExternal(') && zingCode.includes('startZingHandoff'), 'blocks found');
assert.match(page, /id="yoinkZing"[^>]*>Make a Short with Zing</);
assert.match(page, /getElementById\("yoinkZing"\)\.addEventListener|els\.yoinkZing\.addEventListener\("click", startZingHandoff\)/);

const PAGE = 'http://127.0.0.1:51234/?t=abc.DEF-123';

function env({ available = true, handoff = null, selected = { video_id: 'abc12345' } } = {}) {
  const nodes = {};
  const node = id => nodes[id] || (nodes[id] = (() => {
    const classes = new Set(['hidden']);
    return {
      textContent: '', disabled: false,
      classList: { add: c => classes.add(c), remove: c => classes.delete(c), has: c => classes.has(c),
        toggle: (c, on) => (on ? classes.add(c) : classes.delete(c)) },
    };
  })());
  const els = { yoinkZing: node('z'), yoinkZingStatus: node('s'), yoinkZingAgain: node('a') };
  const calls = [];
  const opened = [];
  const toasts = [];
  const context = vm.createContext({
    URL, els, state: { selectedYoink: selected },
    window: { open: (...a) => opened.push(a) },
    showToast: m => toasts.push(m),
    videoIdOf: row => String(row && (row.video_id || row.id || row.slug) || ''),
    authFetch: async (p, opts) => {
      calls.push([p, opts && opts.method, opts && opts.body]);
      if (p === '/zing/status') {
        if (available === 'throw') throw new Error('down');
        return { ok: true, available };
      }
      return handoff();
    },
  });
  vm.runInContext(opener + zingCode, context);
  const shown = n => !els[n].classList.has('hidden');
  return { context, els, calls, opened, toasts, shown, run: src => vm.runInContext(src, context) };
}

(async () => {
  // Zing missing or probe failing: nothing shows, no upsell.
  for (const available of [false, 'throw']) {
    const e = env({ available });
    await e.run('loadZingStatus()');
    assert.equal(e.shown('yoinkZing'), false);
    assert.equal(e.shown('yoinkZingStatus'), false);
    assert.equal(e.shown('yoinkZingAgain'), false);
  }

  // Available and an item is open: the button shows. No item open: it does not.
  let e = env();
  await e.run('loadZingStatus()');
  assert.equal(e.shown('yoinkZing'), true);
  e.run('state.selectedYoink = null; renderYoinkZing()');
  assert.equal(e.shown('yoinkZing'), false);

  // Success: Opening Zing, then Opened in Zing with an Open again link; the
  // returned local page opens through the zing kind only.
  let release;
  const gate = new Promise(r => { release = r; });
  e = env({ handoff: async () => { await gate; return { ok: true, page: PAGE, project: '/p', reused: false }; } });
  await e.run('loadZingStatus()');
  const pending = e.run('startZingHandoff()');
  assert.equal(e.els.yoinkZingStatus.textContent, 'Opening Zing…');
  assert.equal(e.els.yoinkZing.disabled, true);
  release();
  await pending;
  assert.equal(e.els.yoinkZingStatus.textContent, 'Opened in Zing');
  assert.equal(e.els.yoinkZing.disabled, false);
  assert.equal(e.shown('yoinkZingAgain'), true);
  assert.deepEqual(e.calls[1], ['/zing/handoff', 'POST', JSON.stringify({ video_id: 'abc12345' })]);
  assert.equal(e.opened.length, 1);
  assert.equal(e.opened[0][0], PAGE);
  await e.run('openZingPage()');
  assert.equal(e.opened.length, 2, 'Open again reopens the same page');

  // The message and link belong to their item.
  e.run('state.selectedYoink = { video_id: "other9999" }; renderYoinkZing()');
  assert.equal(e.shown('yoinkZing'), true);
  assert.equal(e.shown('yoinkZingStatus'), false);
  assert.equal(e.shown('yoinkZingAgain'), false);

  // Failure: the plain message from the helper, no Open again.
  e = env({ handoff: async () => {
    const err = new Error('media_unavailable');
    err.data = { ok: false, error: 'media_unavailable', message: "Keep this item's media first." };
    throw err;
  } });
  await e.run('loadZingStatus()');
  await e.run('startZingHandoff()');
  assert.equal(e.els.yoinkZingStatus.textContent, "Keep this item's media first.");
  assert.equal(e.shown('yoinkZingAgain'), false);
  assert.equal(e.opened.length, 0);

  // Link allowlist: the zing kind opens only the page just returned.
  e = env();
  e.run(`zing.page = ${JSON.stringify(PAGE)}`);
  assert.equal(e.run(`openExternal(${JSON.stringify(PAGE)}, "zing")`), true);
  for (const bad of [
    'http://127.0.0.1:51234/',                       // not the returned page
    'http://127.0.0.1:51234/?t=abc.DEF-123#x',
    'http://127.0.0.1:51234/admin?t=abc.DEF-123',
    'http://127.0.0.1:5179/?t=abc.DEF-123',
    'http://localhost:51234/?t=abc.DEF-123',
    'https://127.0.0.1:51234/?t=abc.DEF-123',
    'http://user@127.0.0.1:51234/?t=abc.DEF-123',
    'http://127.0.0.1:51234/?t=abc.DEF-123&x=1',
    'https://example.com/',
  ]) {
    const before = e.opened.length;
    assert.equal(e.run(`openExternal(${JSON.stringify(bad)}, "zing")`), false, bad);
    assert.equal(e.opened.length, before, bad);
  }
  // The other kinds never gain the local exception.
  for (const kind of ['remote', 'product', 'source']) {
    assert.equal(e.run(`openExternal(${JSON.stringify(PAGE)}, "${kind}")`), false, kind);
  }
  assert.ok(e.toasts.length >= 1);
  console.log('dashboard_zing_button_test ok');
})().catch(err => { console.error(err); process.exit(1); });
