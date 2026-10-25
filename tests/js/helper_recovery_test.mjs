import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const html = fs.readFileSync(new URL('../../assets/dashboard/index.html', import.meta.url), 'utf8');
const code = html.slice(html.indexOf('    const HELPER_SOURCE_FIX ='), html.indexOf('    async function refreshQueue('));
const node = () => ({textContent: '', classList: {toggle() {}}, set innerHTML(_) {throw Error('Use textContent');}});
const els = Object.fromEntries(['runningPill', 'helperStatusText', 'helperOfflineFix', 'versionLine', 'aboutVersion', 'aboutPort'].map(k => [k, node()]));
const recovery = {available: true, status: 'crash_loop', last_exit_code: 7, restart_count: 3,
  last_start_at: '2026-10-24T20:00:00Z', last_stop_at: '2026-10-24T20:00:01Z',
  reason: 'Helper exited with code 7. <img onerror="unsafe">', action: 'Run uoink doctor, then open Uoink.'};
const context = vm.createContext({els, state: {}, navigator: {platform: 'Win32'},
  renderLibrarianStatus() {}, window: {pywebview: {api: {helper_recovery: async () => recovery}}},
  fetch: async () => {throw Error('offline');}});
vm.runInContext(code, context);
await vm.runInContext('refreshHealth()', context);
assert.equal(els.helperStatusText.textContent, 'Uoink stopped after repeated failures');
for (const text of ['code 7', '<img onerror="unsafe">', 'uoink doctor', 'Restarts: 3', recovery.last_start_at, recovery.last_stop_at])
  assert.ok(els.helperOfflineFix.textContent.includes(text), text);
context.window = {};
await vm.runInContext('refreshHealth()', context);
assert.equal(els.helperStatusText.textContent, 'Uoink is offline');
assert.ok(els.helperOfflineFix.textContent.includes('Start menu'));
context.fetch = async () => ({json: async () => ({ok: true, version: 'fixture', helper_recovery: {...recovery, status: 'running', reason: 'Helper is ready.', action: ''}})});
await vm.runInContext('refreshHealth()', context);
assert.equal(els.helperStatusText.textContent, 'Running on this PC');
assert.ok(els.helperOfflineFix.textContent.includes('Restarts: 3'));
console.log('Dashboard recovery states and text escaping: passed');
