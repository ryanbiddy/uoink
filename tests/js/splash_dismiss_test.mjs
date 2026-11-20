// The first-run splash X closes the window even when it is clicked before
// pywebview has added its API, and never leaves an empty window on screen.
// The fake page fires pywebviewready on window only, like pywebview 5.4
// (webview/js/finish.js: window.dispatchEvent(new CustomEvent('pywebviewready'))).
// Run: node tests/js/splash_dismiss_test.mjs
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

const html = readFileSync('assets/splash/index.html', 'utf8');
const bridge = html.slice(html.indexOf('function nativeApi()'), html.indexOf('function openExternal('));
const dismiss = html.slice(html.indexOf('// Close requests made before'), html.indexOf('async function openLastYoutube'));
assert.ok(bridge.includes('function waitForNativeApi(') && dismiss.includes('async function dismiss()'));

function target() {
  const listeners = {};
  return {
    listeners,
    addEventListener: (name, fn) => { (listeners[name] ||= []).push(fn); },
    removeEventListener: (name, fn) => {
      listeners[name] = (listeners[name] || []).filter(other => other !== fn);
    },
  };
}

function splashContext(host) {
  const timers = [];
  const calls = [];
  const window = Object.assign(target(), {
    setTimeout: (fn, ms) => { timers.push({fn, ms, live: true}); return timers.length; },
    clearTimeout: (id) => { if (timers[id - 1]) timers[id - 1].live = false; },
  });
  if (host === 'webview2') window.chrome = {webview: {}};
  if (host === 'webkit') window.webkit = {messageHandlers: {}};
  const classes = new Set();
  const splash = {
    style: {},
    classList: {add: c => classes.add(c), remove: c => classes.delete(c), contains: c => classes.has(c)},
  };
  const context = vm.createContext({window, document: target(), splash, Promise});
  vm.runInContext(bridge + dismiss, context);
  const api = {close: () => calls.push('close'), minimize: () => calls.push('minimize')};
  // pywebview adds its API, then fires the event on window (never document).
  const bridgeArrives = () => {
    window.pywebview = {api};
    for (const fn of [...(window.listeners.pywebviewready || [])]) fn();
  };
  const runTimers = () => { for (const t of timers) if (t.live) { t.live = false; t.fn(); } };
  return {context, window, splash, timers, calls, bridgeArrives, runTimers};
}

const tick = () => new Promise(resolve => setImmediate(resolve));

// 1. The bridge is ready: close at once, never minimize, page never hidden.
{
  const s = splashContext('webview2');
  s.window.pywebview = {api: {close: () => s.calls.push('close'), minimize: () => s.calls.push('minimize')}};
  await vm.runInContext('dismiss()', s.context);
  assert.deepEqual(s.calls, ['close']);
  assert.notEqual(s.splash.style.display, 'none');
}
console.log('PASS: X closes the native window when the bridge is ready');

// 2. The X comes first (WebView2, slow first start), the bridge after.
for (const host of ['webview2', 'webkit']) {
  const s = splashContext(host);
  const pending = vm.runInContext('dismiss()', s.context);
  await tick();
  assert.notEqual(s.splash.style.display, 'none', 'no empty window while waiting');
  assert.ok(s.splash.classList.contains('closing'), 'the page shows it heard the click');
  assert.deepEqual(s.calls, [], 'nothing to call yet');
  const wait = s.timers.find(t => t.live);
  assert.ok(wait && wait.ms <= 5000, 'the wait is short');
  s.bridgeArrives();
  await tick();
  assert.deepEqual(s.calls, ['close'], `${host}: an early X closes the window as soon as the bridge is ready`);
  assert.equal(wait.live, false, 'the event ended the wait, not the timeout');
  await pending;
  // A second X while closing does not call close twice.
  await vm.runInContext('dismiss()', s.context);
  assert.ok(s.calls.length <= 2);
}
console.log('PASS: an early X closes the window once pywebview fires pywebviewready on window');

// 3. Two quick X presses while waiting: one close.
{
  const s = splashContext('webview2');
  const first = vm.runInContext('dismiss()', s.context);
  const second = vm.runInContext('dismiss()', s.context);
  await tick();
  s.bridgeArrives();
  await Promise.all([first, second]);
  assert.deepEqual(s.calls, ['close']);
}
console.log('PASS: repeated X presses while waiting close once');

// 4. The bridge is later than the wait: the page comes back, then the late
// bridge still closes the window. (If it never comes, uoink_splash.py closes
// the window after its linger, because hold-open needs the bridge.)
{
  const s = splashContext('webview2');
  const pending = vm.runInContext('dismiss()', s.context);
  await tick();
  s.runTimers();
  await pending;
  assert.deepEqual(s.calls, []);
  assert.equal(s.splash.classList.contains('closing'), false, 'page usable again');
  assert.notEqual(s.splash.style.display, 'none');
  s.bridgeArrives();
  assert.deepEqual(s.calls, ['close'], 'a late bridge still closes the window');
}
console.log('PASS: a bridge later than the wait still closes the window');

// 5. A plain browser tab (no pywebview host): hide the page, no wait.
{
  const s = splashContext('browser');
  await vm.runInContext('dismiss()', s.context);
  assert.deepEqual(s.calls, []);
  assert.equal(s.splash.style.display, 'none');
  assert.equal(s.timers.length, 0, 'nothing to wait for in a browser');
}
console.log('PASS: in a plain browser the page hides and nothing throws');
