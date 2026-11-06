// Update now: the button shows only when the helper says this install can
// update itself, and the progress and error text is plain words.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const page = fs.readFileSync(path.join(__dirname, '../../assets/dashboard/index.html'), 'utf8');
const code = page.slice(page.indexOf('    // ---- Update notice'), page.indexOf('    async function init() {'));
assert.ok(code.includes('startUpdateInstall'), 'update install block found');
assert.match(page, /id="updateBannerInstall"/);
assert.match(page, /id="updateInstallNow"/);
assert.match(page, /downloads the installer from GitHub and checks it against the published checksums before running it/);
assert.match(page, /only thing that does: when you press it/);
assert.match(page, /getElementById\("updateInstallNow"\)\.addEventListener\("click", startUpdateInstall\)/);
assert.match(page, /getElementById\("updateBannerInstall"\)\.addEventListener\("click", startUpdateInstall\)/);

function env({ jobs = [], failPost = null } = {}) {
  const nodes = new Map();
  const node = id => {
    if (!nodes.has(id)) {
      const classes = new Set(['hidden']);
      nodes.set(id, {
        textContent: '', href: '', dataset: {}, disabled: false,
        classList: {
          add: c => classes.add(c), remove: c => classes.delete(c), has: c => classes.has(c),
          toggle: (c, on) => (on ? classes.add(c) : classes.delete(c)),
        },
      });
    }
    return nodes.get(id);
  };
  const calls = [];
  const queue = [...jobs];
  const context = vm.createContext({
    document: { getElementById: node },
    window: { localStorage: { getItem: () => null, setItem() {} } },
    setTimeout: fn => { fn(); return 0; },
    authFetch: async (p, opts) => {
      calls.push([p, opts && opts.method]);
      if (opts && opts.method === 'POST') {
        if (failPost) throw new Error(failPost);
        return { ok: true, state: 'downloading' };
      }
      return queue.length > 1 ? queue.shift() : queue[0];
    },
  });
  vm.runInContext(code, context);
  const visible = id => !node(id).classList.has('hidden');
  return { calls, node, visible, run: src => vm.runInContext(src, context) };
}

const MB = 1048576;

(async () => {
  // Windows install with an update: both buttons show "Update now".
  const win = env();
  win.run('renderUpdateBanner({ update_available: true, latest: "3.16.0", current: "3.15.0", install_action: "Update now" })');
  assert.equal(win.visible('updateBannerInstall'), true);
  assert.equal(win.visible('updateInstallNow'), true);
  assert.equal(win.node('updateBannerInstall').textContent, 'Update now');
  assert.equal(win.node('updateInstallNow').textContent, 'Update now');

  // Mac says "Download update".
  const mac = env();
  mac.run('renderUpdateBanner({ update_available: true, latest: "3.16.0", current: "3.15.0", install_action: "Download update" })');
  assert.equal(mac.node('updateInstallNow').textContent, 'Download update');
  assert.equal(mac.visible('updateInstallNow'), true);

  // Unsupported platform, source run or isolated install: no install_action, no button.
  const other = env();
  other.run('renderUpdateBanner({ update_available: true, latest: "3.16.0", current: "3.15.0", install_action: null })');
  assert.equal(other.visible('updateBannerInstall'), false);
  assert.equal(other.visible('updateInstallNow'), false);
  assert.equal(other.visible('updateBanner'), true, 'What\'s new banner still shows');

  // No update: no button even if the helper could install.
  const none = env();
  none.run('renderUpdateBanner({ update_available: false, latest: "3.15.0", current: "3.15.0", install_action: "Update now" })');
  assert.equal(none.visible('updateInstallNow'), false);

  // A dismissed banner still leaves the Settings button.
  const stored = env();
  stored.run('window.localStorage.getItem = () => "3.16.0"');
  stored.run('renderUpdateBanner({ update_available: true, latest: "3.16.0", current: "3.15.0", install_action: "Update now" })');
  assert.equal(stored.visible('updateBanner'), false);
  assert.equal(stored.visible('updateInstallNow'), true);

  // Progress wording.
  const text = job => win.run(`updateInstallProgressText(${JSON.stringify(job)})`);
  assert.equal(text({ state: 'downloading', bytes_done: 120 * MB, bytes_total: 520 * MB }), 'Downloading 120 of 520 MB');
  assert.equal(text({ state: 'downloading', bytes_done: 5 * MB, bytes_total: 0 }), 'Downloading 5 MB');
  assert.equal(text({ state: 'verifying' }), 'Checking the download');
  assert.equal(text({ state: 'launching' }), 'Starting the installer, Uoink will restart');
  assert.equal(mac.run('updateInstallProgressText({ state: "launching" })'),
    'Opening the download. Drag Uoink into Applications to finish.');
  assert.equal(text({ state: 'error', error: 'The download did not match its checksum, so Uoink did not install it.' }),
    'The download did not match its checksum, so Uoink did not install it.');

  // Pressing the button posts once, then polls to the end and shows each step.
  const run = env({ jobs: [
    { state: 'downloading', bytes_done: 120 * MB, bytes_total: 520 * MB },
    { state: 'verifying', bytes_done: 520 * MB, bytes_total: 520 * MB },
    { state: 'launching' },
  ] });
  run.run('renderUpdateBanner({ update_available: true, latest: "3.16.0", current: "3.15.0", install_action: "Update now" })');
  await run.run('startUpdateInstall()');
  assert.deepEqual(run.calls[0], ['/update/install', 'POST']);
  assert.equal(run.calls.length, 4, 'one POST then three status reads');
  assert.equal(run.node('updateInstallText').textContent, 'Starting the installer, Uoink will restart');
  assert.equal(run.node('updateBannerProgress').textContent, 'Starting the installer, Uoink will restart');
  assert.equal(run.node('updateInstallNow').disabled, false, 'button comes back after the job');

  // A failed checksum shows plain words and a release page link.
  const bad = env({ jobs: [{ state: 'error', error: 'The download did not match its checksum, so Uoink did not install it.',
    url: 'https://github.com/ryanbiddy/uoink/releases/tag/v3.16.0' }] });
  bad.run('renderUpdateBanner({ update_available: true, latest: "3.16.0", current: "3.15.0", install_action: "Update now" })');
  await bad.run('startUpdateInstall()');
  assert.match(bad.node('updateInstallText').textContent, /did not match its checksum/);
  assert.equal(bad.visible('updateInstallRelease'), true);
  assert.equal(bad.node('updateInstallRelease').href, 'https://github.com/ryanbiddy/uoink/releases/tag/v3.16.0');

  // A refused start (isolated, wrong platform) shows the helper's words.
  const refused = env({ failPost: 'This is an isolated test install, so it cannot run the normal installer.' });
  refused.run('renderUpdateBanner({ update_available: true, latest: "3.16.0", current: "3.15.0", install_action: "Update now" })');
  await refused.run('startUpdateInstall()');
  assert.match(refused.node('updateInstallText').textContent, /isolated test install/);
  assert.equal(refused.visible('updateInstallRelease'), true);

  // Without a button label nothing posts.
  const idle = env();
  await idle.run('startUpdateInstall()');
  assert.equal(idle.calls.length, 0);

  console.log('dashboard update install: ok');
})().catch(err => { console.error(err); process.exit(1); });
