// Check now on the Settings feed rows: real render + click handler functions, fake DOM and transport.
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
const page = readFileSync(new URL('../../assets/dashboard/index.html', import.meta.url), 'utf8');
const between = (a, b) => page.slice(page.indexOf(a), page.indexOf(b, page.indexOf(a)));
const checkLogic = between('    function checkNowMessage(res)', '    // V-2a');
const renderLogic = between('    function renderPodcastFeedList(rows)', '    async function loadPlaylistSettings');

function setup(responder) {
  const calls = [];
  const note = { textContent: '' };
  const list = { innerHTML: '', querySelector: () => ({ parentElement: { querySelector: () => note } }) };
  const btn = { disabled: false, dataset: { sourceId: 'src_abc' }, parentElement: { querySelector: () => note } };
  let reloads = 0;
  const ctx = vm.createContext({
    els: { podcastFeedList: list, standingSubscriptionList: list }, CSS: { escape: (s) => s }, console,
    htmlEscape: (s) => String(s).replaceAll('&', '&amp;').replaceAll('"', '&quot;').replaceAll('<', '&lt;'),
    firstValue: (...v) => v.find(Boolean), emptyPanelRow: () => '',
    loadStandingSubscriptions: async () => { throw new Error('Settings must not reload the Sources list'); },
    authFetch: async (path, opts) => { calls.push({ path, body: JSON.parse(opts.body) }); return responder(); },
  });
  vm.runInContext(checkLogic + renderLogic, ctx);
  return { ctx, calls, note, btn, list, reloads: () => reloads, reload: async () => { reloads++; } };
}

// Rows with a source id get a button that carries it; rows without do not.
{
  const t = setup(() => ({}));
  t.ctx.renderPodcastFeedList([{ id: 1, title: 'A', source_id: 'src_one' }, { id: 2, title: 'B', source_id: null }]);
  assert.equal((t.list.innerHTML.match(/check-now-btn/g) || []).length, 1);
  assert.match(t.list.innerHTML, /data-source-id="src_one"/);
  assert.match(t.list.innerHTML, /check-now-note/);
}

// A real check posts the source id to the shared refresh route and reloads the Settings list.
{
  const t = setup(() => ({ ok: true, outcome: 'refreshed', poll: { ok: true, inserted: 2 } }));
  await t.ctx.checkSourceNow(t.btn, { reload: t.reload, list: () => t.list });
  assert.deepEqual(t.calls, [{ path: '/sources/refresh', body: { source_id: 'src_abc' } }]);
  assert.equal(t.reloads(), 1);
  assert.equal(t.note.textContent, 'Found 2 new episodes.');
  assert.equal(t.btn.disabled, false);
}

// The cooldown, in-progress and backoff answers reuse the same wording and skip the reload.
for (const [res, text] of [
  [{ outcome: 'not_due', retry_after_ms: 90000 }, /Checked a moment ago, try again in about 2 min/],
  [{ outcome: 'not_due', poll_in_progress: true }, /already running/],
  [{ outcome: 'not_due', backoff: true, next_poll_at_ms: 0 }, /asked us to wait/],
]) {
  const t = setup(() => res);
  await t.ctx.checkSourceNow(t.btn, { reload: t.reload, list: () => t.list });
  assert.match(t.note.textContent, text);
  assert.equal(t.reloads(), 0);
}

// A rate limit error is explained.
{
  const t = setup(() => { throw Object.assign(new Error('x'), { data: { error: { code: 'rate_limited' } } }); });
  await t.ctx.checkSourceNow(t.btn, { reload: t.reload, list: () => t.list });
  assert.match(t.note.textContent, /Checking too often/);
}
console.log('settings feed check now: ok');
