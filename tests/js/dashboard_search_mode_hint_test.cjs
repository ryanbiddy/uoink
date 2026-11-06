// A6: the Library search box says whether it runs keyword or meaning search.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const page = fs.readFileSync(require('node:path').join(__dirname, '../../assets/dashboard/index.html'), 'utf8');
const code = page.slice(page.indexOf('    let semanticState ='), page.indexOf('    function wireSettingsAutosave()'));
assert.match(page, /id="librarySearchMode"/);

function env(status) {
  const hint = { textContent: '', children: [],
    appendChild(child) { this.children.push(child); } };
  const others = new Map();
  const context = vm.createContext({
    document: {
      getElementById: id => id === 'librarySearchMode' ? hint : (others.get(id) || (others.set(id, { classList: { toggle() {} }, addEventListener() {} }), others.get(id))),
      createElement: () => ({ href: '', textContent: '' }),
      querySelectorAll: () => [],
    },
    window: { clearTimeout() {}, setTimeout() { return 1; } },
    state: { activeTab: 'library' },
    readSettingsResource: async path => { assert.equal(path, '/search/status'); return status; },
    settingsRequest: async () => status, settingError: err => err.message, confirm: () => true,
  });
  vm.runInContext(code, context);
  return { hint, run: value => vm.runInContext(value, context) };
}

(async () => {
  const off = env({ ok: true, state: 'not_installed', enabled: false });
  await off.run('loadLibrarySearchMode()');
  assert.equal(off.hint.textContent, 'Keyword search · ');
  assert.equal(off.hint.children.length, 1);
  assert.equal(off.hint.children[0].textContent, 'Turn on meaning search');
  assert.equal(off.hint.children[0].href, '#settings/search');

  const on = env({ ok: true, state: 'ready', enabled: true, done: 4, total: 4 });
  await on.run('loadLibrarySearchMode()');
  assert.equal(on.hint.textContent, 'Meaning search');
  assert.equal(on.hint.children.length, 0);

  const warming = env({ ok: true, state: 'indexing', enabled: true, done: 1, total: 4 });
  await warming.run('loadLibrarySearchMode()');
  assert.match(warming.hint.textContent, /^Keyword search/);
  assert.match(warming.hint.textContent, /getting ready/);

  // A status that fails to load leaves the hint empty rather than wrong.
  const broken = env({});
  broken.run('readSettingsResource = async () => { throw new Error("down"); }');
  await broken.run('loadLibrarySearchMode()');
  assert.equal(broken.hint.textContent, '');
  console.log('dashboard search mode hint: ok');
})().catch(err => { console.error(err); process.exit(1); });
