// The first-run splash X closes the window even when it is clicked before
// pywebview has added its API. Run: node tests/js/splash_dismiss_test.mjs
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

const html = readFileSync('assets/splash/index.html', 'utf8');
const bridge = html.slice(html.indexOf('function nativeApi()'), html.indexOf('function openExternal('));
const dismissStart = html.lastIndexOf('function dismiss()') - (html.includes('async function dismiss()') ? 'async '.length : 0);
const dismiss = html.slice(dismissStart, html.indexOf('async function openLastYoutube'));
assert.ok(bridge.includes('function waitForNativeApi(') && dismiss.includes('function dismiss()'));

function splashContext() {
  const listeners = {};
  const timers = [];
  const calls = [];
  const window = {setTimeout: (fn, ms) => timers.push({fn, ms})};
  const context = vm.createContext({
    window,
    document: {addEventListener: (name, fn) => { (listeners[name] ||= []).push(fn); }},
    splash: {style: {}},
    Promise,
  });
  vm.runInContext(bridge + dismiss, context);
  const api = {close: () => calls.push('close'), minimize: () => calls.push('minimize')};
  return {context, window, listeners, timers, calls, api};
}

const tick = () => new Promise(resolve => setImmediate(resolve));

// 1. The bridge is ready: close at once, never minimize.
{
  const s = splashContext();
  s.window.pywebview = {api: s.api};
  await vm.runInContext('dismiss()', s.context);
  assert.deepEqual(s.calls, ['close']);
  assert.equal(s.context.splash.style.display, 'none');
}
console.log('PASS: X closes the native window when the bridge is ready');

// 2. The X comes first, the bridge after: the window still closes.
{
  const s = splashContext();
  const pending = vm.runInContext('dismiss()', s.context);
  await tick();
  assert.equal(s.context.splash.style.display, 'none');
  assert.deepEqual(s.calls, [], 'nothing to call yet');
  s.window.pywebview = {api: s.api};
  for (const fn of s.listeners.pywebviewready || []) fn();
  await pending;
  assert.deepEqual(s.calls, ['close'], 'an early X must close the window once the bridge is ready');
  assert.ok(s.timers.some(timer => timer.ms >= 5000), 'waits long enough for a slow first start');
}
console.log('PASS: an early X closes the window once pywebview is ready');

// 3. A plain browser (no pywebview): hide the page and stop, no error.
{
  const s = splashContext();
  const pending = vm.runInContext('dismiss()', s.context);
  await tick();
  for (const timer of s.timers) timer.fn();
  await pending;
  assert.deepEqual(s.calls, []);
  assert.equal(s.context.splash.style.display, 'none');
}
console.log('PASS: without pywebview the page hides and nothing throws');
