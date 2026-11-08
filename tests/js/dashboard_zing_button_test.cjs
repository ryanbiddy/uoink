// Make a Short with Zing: the button shows only when the helper says Zing can
// take items from Uoink, the hand-off is a polled job (progress, an inline
// download prompt, plain errors), and the only local address the dashboard will
// open is the review page the hand-off just returned.
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
assert.match(page, /els\.yoinkZing\.addEventListener\("click", \(\) => startZingHandoff\(false\)\)/);
assert.match(page, /els\.yoinkZingDownload\.addEventListener\("click", \(\) => startZingHandoff\(true\)\)/);
assert.match(page, /els\.yoinkZingCancel\.addEventListener\("click", cancelZingDownload\)/);
assert.match(page, /id="yoinkZingDownload"[^>]*>Download</);
assert.match(page, /id="yoinkZingCancel"[^>]*>Cancel</);
assert.ok(!/window\.confirm|\bconfirm\(/.test(zingCode), 'the prompt is inline, not window.confirm');

const PAGE = 'http://127.0.0.1:51234/?t=abc.DEF-123';

function env({ available = true, features = ['allow_download'], jobs = [], post = null,
  selected = { video_id: 'abc12345' } } = {}) {
  const nodes = {};
  const node = id => nodes[id] || (nodes[id] = (() => {
    const classes = new Set(['hidden']);
    return {
      textContent: '', disabled: false,
      classList: { add: c => classes.add(c), remove: c => classes.delete(c), has: c => classes.has(c),
        toggle: (c, on) => (on ? classes.add(c) : classes.delete(c)) },
    };
  })());
  const els = { yoinkZing: node('z'), yoinkZingStatus: node('s'), yoinkZingAgain: node('a'),
    yoinkZingAsk: node('k'), yoinkZingAskText: node('t'), yoinkZingDownload: node('d'),
    yoinkZingCancel: node('c') };
  const calls = [];
  const opened = [];
  const toasts = [];
  const queue = jobs.slice();
  const context = vm.createContext({
    URL, els, state: { selectedYoink: selected },
    window: { open: (...a) => opened.push(a) },
    setTimeout: fn => Promise.resolve().then(fn),   // the 1 s poll runs at once
    showToast: m => toasts.push(m),
    videoIdOf: row => String(row && (row.video_id || row.id || row.slug) || ''),
    authFetch: async (p, opts) => {
      calls.push([p, opts && opts.method, opts && opts.body]);
      if (p === '/zing/status') {
        if (available === 'throw') throw new Error('down');
        return { ok: true, available, features };
      }
      if (p === '/zing/handoff') return post ? post() : { ok: true, job_id: 'job1' };
      const next = queue.length > 1 ? queue.shift() : queue[0];
      return typeof next === 'function' ? next() : { ok: true, job_id: 'job1', ...next };
    },
  });
  vm.runInContext(opener + zingCode, context);
  const shown = n => !els[n].classList.has('hidden');
  return { context, els, calls, opened, toasts, shown, run: src => vm.runInContext(src, context) };
}

const DONE = { state: 'done', page: PAGE, project: '/p', reused: false, downloaded: false };
const NEEDED = { state: 'error', error: 'download_needed', host: 'www.youtube.com',
  message: 'Uoink did not keep this video. Zing can download it from www.youtube.com.' };
const RUNNING = percent => ({ state: 'running', percent });
const body = c => JSON.parse(c[2]);

(async () => {
  // Zing missing or probe failing: nothing shows, no upsell.
  for (const available of [false, 'throw']) {
    const e = env({ available });
    await e.run('loadZingStatus()');
    assert.equal(e.shown('yoinkZing'), false);
    assert.equal(e.shown('yoinkZingStatus'), false);
    assert.equal(e.shown('yoinkZingAgain'), false);
    assert.equal(e.shown('yoinkZingAsk'), false);
  }

  // Available and an item is open: the button shows. No item open: it does not.
  let e = env();
  await e.run('loadZingStatus()');
  assert.equal(e.shown('yoinkZing'), true);
  e.run('state.selectedYoink = null; renderYoinkZing()');
  assert.equal(e.shown('yoinkZing'), false);

  // Success: Opening Zing, polling, then Opened in Zing with an Open again link.
  let release;
  const gate = new Promise(r => { release = r; });
  e = env({ jobs: [async () => { await gate; return { ok: true, ...DONE }; }] });
  await e.run('loadZingStatus()');
  const pending = e.run('startZingHandoff(false)');
  assert.equal(e.els.yoinkZingStatus.textContent, 'Opening Zing…');
  assert.equal(e.els.yoinkZing.disabled, true);
  release();
  await pending;
  assert.equal(e.els.yoinkZingStatus.textContent, 'Opened in Zing');
  assert.equal(e.els.yoinkZing.disabled, false);
  assert.equal(e.shown('yoinkZingAgain'), true);
  assert.deepEqual(e.calls[1], ['/zing/handoff', 'POST',
    JSON.stringify({ video_id: 'abc12345', allow_download: false })]);
  assert.equal(e.calls[2][0], '/zing/handoff/job1');
  assert.equal(e.opened.length, 0, 'Zing opens its own page; the dashboard does not open a second tab');
  await e.run('openZingPage()');
  assert.equal(e.opened.length, 1, 'Open again reopens the returned page');
  assert.equal(e.opened[0][0], PAGE);

  // The message and link belong to their item.
  e.run('state.selectedYoink = { video_id: "other9999" }; renderYoinkZing()');
  assert.equal(e.shown('yoinkZing'), true);
  assert.equal(e.shown('yoinkZingStatus'), false);
  assert.equal(e.shown('yoinkZingAgain'), false);

  // The click handler's event object is not consent: only a literal true asks to download.
  e = env({ jobs: [DONE] });
  await e.run('loadZingStatus()');
  await e.run('startZingHandoff({ type: "click" })');
  assert.equal(body(e.calls[1]).allow_download, false);

  // Failure: the plain message from the job, no Open again, no download prompt.
  e = env({ jobs: [{ state: 'error', error: 'media_unavailable', message: "Keep this item's media first." }] });
  await e.run('loadZingStatus()');
  await e.run('startZingHandoff(false)');
  assert.equal(e.els.yoinkZingStatus.textContent, "Keep this item's media first.");
  assert.equal(e.shown('yoinkZingAgain'), false);
  assert.equal(e.shown('yoinkZingAsk'), false);
  assert.equal(e.opened.length, 0);

  // A failed start (before any job) shows the helper's plain message too.
  e = env({ post: async () => {
    const err = new Error('zing_unavailable');
    err.data = { ok: false, error: 'zing_unavailable', message: 'Zing is not available on this computer.' };
    throw err;
  } });
  await e.run('loadZingStatus()');
  await e.run('startZingHandoff(false)');
  assert.equal(e.els.yoinkZingStatus.textContent, 'Zing is not available on this computer.');
  assert.equal(e.els.yoinkZing.disabled, false);

  // Download prompt: inline, names the host, nothing is downloaded until Download.
  e = env({ jobs: [NEEDED] });
  await e.run('loadZingStatus()');
  await e.run('startZingHandoff(false)');
  assert.equal(e.shown('yoinkZingAsk'), true);
  assert.equal(e.els.yoinkZingAskText.textContent,
    "Uoink didn't keep this video. Download it from www.youtube.com so Zing can cut a Short?");
  assert.equal(e.els.yoinkZingStatus.textContent === '' || !e.shown('yoinkZingStatus'), true);
  assert.equal(e.calls.filter(c => c[0] === '/zing/handoff').length, 1, 'no second POST before consent');
  assert.equal(body(e.calls[1]).allow_download, false);
  assert.equal(e.els.yoinkZing.disabled, true, 'one decision at a time');
  assert.equal(e.toasts.length, 0, 'not window.confirm, not a toast');

  // Cancel: the prompt goes away and nothing more is sent.
  e.run('cancelZingDownload()');
  assert.equal(e.shown('yoinkZingAsk'), false);
  assert.equal(e.els.yoinkZingStatus.textContent, '');
  assert.equal(e.els.yoinkZing.disabled, false);
  assert.equal(e.calls.filter(c => c[0] === '/zing/handoff').length, 1);

  // Download: re-POSTs with allow_download true, shows progress (with and without a percent),
  // then success with the downloaded note.
  const seen = [];
  const watch = () => { seen.push(e.els.yoinkZingStatus.textContent); };
  e = env({ jobs: [NEEDED] });
  await e.run('loadZingStatus()');
  await e.run('startZingHandoff(false)');
  e.context.watchStatus = watch;
  const script = [RUNNING(null), RUNNING(41.6), RUNNING(41.6), RUNNING(7), { ...DONE, downloaded: true }];
  let step = 0;
  e.context.authFetch = async (p, opts) => {
    e.calls.push([p, opts && opts.method, opts && opts.body]);
    if (p === '/zing/handoff') return { ok: true, job_id: 'job2' };
    watch();
    return { ok: true, ...script[step++] };
  };
  await e.run('startZingHandoff(true)');
  const post2 = e.calls.filter(c => c[0] === '/zing/handoff')[1];
  assert.deepEqual(JSON.parse(post2[2]), { video_id: 'abc12345', allow_download: true });
  assert.deepEqual(seen, ['Downloading…', 'Downloading…', 'Downloading… 41%', 'Downloading… 41%', 'Downloading… 7%']);
  assert.equal(e.els.yoinkZingStatus.textContent, 'Opened in Zing. Zing downloaded the video from www.youtube.com.');
  assert.equal(e.shown('yoinkZingAsk'), false);
  assert.equal(e.shown('yoinkZingAgain'), true);

  // Download failed: plain message, no prompt loop.
  e = env({ jobs: [NEEDED] });
  await e.run('loadZingStatus()');
  await e.run('startZingHandoff(false)');
  e.context.authFetch = async p => (p === '/zing/handoff' ? { ok: true, job_id: 'j3' }
    : { ok: true, state: 'error', error: 'download_failed', message: 'Zing could not download the video.' });
  await e.run('startZingHandoff(true)');
  assert.equal(e.els.yoinkZingStatus.textContent, 'Zing could not download the video.');
  assert.equal(e.shown('yoinkZingAsk'), false);

  // An older Zing that does not list allow_download never gets a prompt or the flag.
  e = env({ features: [], jobs: [NEEDED] });
  await e.run('loadZingStatus()');
  await e.run('startZingHandoff(false)');
  assert.equal(e.shown('yoinkZingAsk'), false);
  assert.match(e.els.yoinkZingStatus.textContent, /did not keep this video/);
  await e.run('startZingHandoff(true)');
  assert.equal(e.calls.filter(c => c[0] === '/zing/handoff').every(c => body(c).allow_download === false), true);

  // The poll gives up on an unknown job instead of spinning.
  e = env({ jobs: [() => { const err = new Error('not found'); err.status = 404;
    err.data = { ok: false, message: 'That hand-off is not known.' }; throw err; }] });
  await e.run('loadZingStatus()');
  await e.run('startZingHandoff(false)');
  assert.equal(e.els.yoinkZingStatus.textContent, 'That hand-off is not known.');
  assert.equal(e.els.yoinkZing.disabled, false);

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
