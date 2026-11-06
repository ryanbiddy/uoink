// Update notices: no /update/check on load unless the switch is on, and a
// slim banner that "Not now" hides for one version only.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const page = fs.readFileSync(path.join(__dirname, '../../assets/dashboard/index.html'), 'utf8');
const code = page.slice(page.indexOf('    // ---- Update notice'), page.indexOf('    async function init() {'));
assert.ok(code.includes('renderUpdateBanner'), 'update notice block found');
assert.match(page, /id="autoUpdateCheck" type="checkbox"/);
assert.match(page, /Check for new versions once a day/);
assert.match(page, /autoUpdateCheck: \["auto_update_check", false\]/);
assert.match(page, /\r?\n      autoCheckUpdatesOnLoad\(\);\r?\n/);

function env({ autoCheck = false, update = {}, storage = new Map(), brokenStorage = false } = {}) {
  const nodes = new Map();
  const node = id => {
    if (!nodes.has(id)) {
      const classes = new Set(['hidden']);
      nodes.set(id, {
        textContent: '', href: '', dataset: {},
        classList: { add: c => classes.add(c), remove: c => classes.delete(c), has: c => classes.has(c) },
      });
    }
    return nodes.get(id);
  };
  const calls = [];
  const localStorage = brokenStorage
    ? { getItem() { throw new Error('blocked'); }, setItem() { throw new Error('blocked'); } }
    : { getItem: k => (storage.has(k) ? storage.get(k) : null), setItem: (k, v) => storage.set(k, v) };
  const context = vm.createContext({
    document: { getElementById: node },
    window: { localStorage },
    settingsRequest: async p => { calls.push(p); return { ok: true, settings: { auto_update_check: autoCheck } }; },
    authFetch: async p => { calls.push(p); return { ok: true, current: '3.15.0', latest: '3.16.0', update_available: true,
      url: 'https://github.com/ryanbiddy/uoink/releases/tag/v3.16.0', ...update }; },
  });
  vm.runInContext(code, context);
  const hidden = () => node('updateBanner').classList.has('hidden');
  return { calls, node, hidden, run: src => vm.runInContext(src, context), storage };
}

(async () => {
  // Switch off: load makes no update request and shows nothing.
  const off = env({ autoCheck: false });
  await off.run('autoCheckUpdatesOnLoad()');
  assert.ok(!off.calls.includes('/update/check'));
  assert.equal(off.hidden(), true);

  // Switch on: load checks once and the banner appears.
  const on = env({ autoCheck: true });
  await on.run('autoCheckUpdatesOnLoad()');
  assert.deepEqual(on.calls.filter(c => c === '/update/check').length, 1);
  assert.equal(on.hidden(), false);
  assert.equal(on.node('updateBannerText').textContent, 'Uoink 3.16.0 is out. You have 3.15.0.');
  assert.equal(on.node('updateBannerLink').href, 'https://github.com/ryanbiddy/uoink/releases/tag/v3.16.0');

  // A reply that is not a release page of this project never becomes the link.
  const odd = env({ update: { url: 'https://example.com/x' } });
  odd.run('renderUpdateBanner({ update_available: true, latest: "3.16.0", current: "3.15.0", url: "https://example.com/x" })');
  assert.equal(odd.node('updateBannerLink').href, 'https://github.com/ryanbiddy/uoink/releases');

  // No update: banner stays hidden.
  const none = env();
  none.run('renderUpdateBanner({ update_available: false, latest: "3.15.0", current: "3.15.0" })');
  assert.equal(none.hidden(), true);

  // Not now hides that version only; a newer version shows it again.
  const storage = new Map();
  const first = env({ storage });
  first.run('renderUpdateBanner({ update_available: true, latest: "3.16.0", current: "3.15.0" })');
  assert.equal(first.hidden(), false);
  first.run('dismissUpdateVersion(document.getElementById("updateBanner").dataset.version)');
  first.run('renderUpdateBanner({ update_available: true, latest: "3.16.0", current: "3.15.0" })');
  assert.equal(first.hidden(), true, 'dismissed version stays hidden');
  const later = env({ storage });
  later.run('renderUpdateBanner({ update_available: true, latest: "3.16.0", current: "3.15.0" })');
  assert.equal(later.hidden(), true, 'still hidden after a reload');
  later.run('renderUpdateBanner({ update_available: true, latest: "3.17.0", current: "3.15.0" })');
  assert.equal(later.hidden(), false, 'newer version reappears');
  assert.equal(later.node('updateBannerText').textContent, 'Uoink 3.17.0 is out. You have 3.15.0.');

  // Blocked storage (private window) must not break the banner.
  const blocked = env({ brokenStorage: true });
  blocked.run('renderUpdateBanner({ update_available: true, latest: "3.16.0", current: "3.15.0" })');
  assert.equal(blocked.hidden(), false);
  blocked.run('dismissUpdateVersion("3.16.0")');

  // The Not now button is wired to the dismiss helper.
  assert.match(page, /updateBannerDismiss"\)\.addEventListener\("click"/);
  console.log('dashboard update notice: ok');
})().catch(err => { console.error(err); process.exit(1); });
