import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

const id = 'abcdefghijklmnopabcdefghijklmnop';
const url = 'https://chromewebstore.google.com/detail/uoink/' + id;
const setup = readFileSync('extension/setup.js', 'utf8');
const splash = readFileSync('assets/splash/index.html', 'utf8');
const links = readFileSync('extension/lib/store-links.js', 'utf8');

for (const storeUrl of ['', url]) {
  const elements = {'store-install': {hidden: true}, 'store-install-link': {}};
  const config = {chrome_web_store_id: id, chrome_web_store_url: storeUrl};
  const context = vm.createContext({
    fetch: async () => ({ok: true, json: async () => config}),
    chrome: {runtime: {getURL: name => 'chrome-extension://test/' + name}},
    $: name => elements[name],
  });
  vm.runInContext(links, context);
  vm.runInContext(setup.slice(setup.indexOf('async function showStoreInstall()'), setup.indexOf('function setPlatform(')), context);
  await vm.runInContext('showStoreInstall()', context);
  assert.equal(elements['store-install'].hidden, !storeUrl);
  assert.equal(elements['store-install-link'].href || '', storeUrl);
  for (const bad of [url + '\n', url + '.evil.test', url + '?x=1', url.replace('.com', '.com.evil.test'), 'javascript:alert(1)']) {
    assert.equal(context.UoinkStore.url({...config, chrome_web_store_url: bad}), '');
  }

  let mode;
  const clicks = [];
  const splashContext = vm.createContext({
    extensionStatus: null, extensionBrowser: null, extensionPath: '',
    els: {steps: {}, extensionPath: {}, copyStatus: {}},
    setMode: value => {mode = value;}, hideExtensionExtras() {},
    escapeHtml: text => text, callNative() {}, openExternal: value => clicks.push(value),
  });
  vm.runInContext(splash.slice(splash.indexOf('function setExtensionHint('), splash.indexOf('async function loadDiagnostics()')), splashContext);
  vm.runInContext(splash.slice(splash.indexOf('async function runAction('), splash.indexOf('splash.addEventListener("click"')), splashContext);
  splashContext.status = {store_url: storeUrl, manifest_exists: true, path: 'C:/Fixture/extension', browser: {id: 'chrome', name: 'Chrome', url: 'chrome://extensions/'}};
  vm.runInContext('setExtensionHint(status)', splashContext);
  assert.equal(mode.primary.action, storeUrl ? 'extension-store' : 'extension-open');
  if (storeUrl) {
    assert.equal(mode.primary.text, 'Add to Chrome');
    await vm.runInContext('runAction("extension-store")', splashContext);
    assert.deepEqual(clicks, [url]);
    await vm.runInContext('runAction("extension-advanced")', splashContext);
  }
  assert.equal(mode.primary.action, 'extension-open');
  assert.match(splashContext.els.steps.innerHTML, /Load unpacked/);
  assert.equal(splashContext.els.extensionPath.textContent, 'C:/Fixture/extension');
}
console.log('PASS: setup and splash store/sideload states and advanced fallback');

// A second caller must not query the offscreen page while it is still loading.
const background = readFileSync('extension/background.js', 'utf8');
let finishCreate;
let exists = false;
let creations = 0;
let startedCreate;
const started = new Promise(resolve => {startedCreate = resolve;});
const creating = new Promise(resolve => {finishCreate = resolve;});
const offscreenContext = vm.createContext({chrome: {offscreen: {
  hasDocument: async () => exists,
  createDocument: async () => {exists = true; creations++; startedCreate(); await creating;},
}}});
vm.runInContext('let _ensureOffscreenInflight = null; const OFFSCREEN_URL = "offscreen.html"; const OFFSCREEN_REASONS = ["CLIPBOARD", "MATCH_MEDIA"];' +
  background.slice(background.indexOf('async function ensureOffscreen()'), background.indexOf('async function copyToClipboard(')), offscreenContext);
const first = vm.runInContext('ensureOffscreen()', offscreenContext);
await started;
assert.equal(exists, true);
let secondFinished = false;
const second = vm.runInContext('ensureOffscreen()', offscreenContext).then(() => {secondFinished = true;});
await Promise.resolve(); await Promise.resolve();
assert.equal(secondFinished, false, 'hasDocument must not skip the pending load');
finishCreate(); await Promise.all([first, second]);
assert.equal(creations, 1);
console.log('PASS: concurrent offscreen startup waits for the listener');
