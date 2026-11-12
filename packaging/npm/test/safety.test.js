'use strict';
// The launcher must never run itself in place of the Uoink CLI, and a Mac
// update must never leave the person with no Uoink.app.

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const cp = require('node:child_process');
const http = require('node:http');
const { EventEmitter } = require('node:events');

const { main, findInstalled, installMac, defaultDeps, makeUi, LAUNCHER_ENV, PKG_DIR } = require('../lib/main.js');

const OWN_BIN = path.join(PKG_DIR, 'bin', 'uoink.js');

function sink() {
  const chunks = [];
  return { write: (s) => chunks.push(String(s)), isTTY: false, text: () => chunks.join('') };
}

function tempRoot(t) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'uoink-npm-safety-'));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  return root;
}

function write(p, body = '') {
  fs.mkdirSync(path.dirname(p), { recursive: true });
  fs.writeFileSync(p, body);
  return p;
}

// An fs whose realpathSync follows the given fake symlinks, so the tests run
// the same on Windows (where making a symlink needs extra rights). It also
// hides this computer's own /Applications, so a Mac with Uoink installed
// gives the same results.
function fsWithLinks(links = {}) {
  return {
    ...fs,
    realpathSync: (p) => (Object.hasOwn(links, p) ? links[p] : fs.realpathSync(p)),
    statSync: (p, ...rest) => {
      if (String(p).replace(/\\/g, '/').startsWith('/Applications/')) throw Object.assign(new Error('ENOENT'), { code: 'ENOENT' });
      return fs.statSync(p, ...rest);
    },
  };
}

function posixDeps(t, extra = {}) {
  const root = tempRoot(t);
  const home = path.join(root, 'home');
  fs.mkdirSync(home);
  const calls = { run: [], capture: [] };
  const out = sink();
  const err = sink();
  const deps = {
    platform: 'linux',
    arch: 'x64',
    env: { PATH: '' },
    homedir: home,
    fs: fsWithLinks(),
    tmpRoot: root,
    stdout: out,
    stderr: err,
    isTTY: false,
    counterBase: null,
    run: async (cmd, args, opts = {}) => {
      calls.run.push({ cmd, args, env: opts.env || {} });
      return { code: 0 };
    },
    capture: async (cmd, args, opts = {}) => {
      calls.capture.push({ cmd, args, env: opts.env || {} });
      return { code: 0, stdout: JSON.stringify({ ok: true, version: '9.9.9', helper_running: true }), stderr: '' };
    },
    ...extra,
  };
  return { root, home, deps, calls, out, err };
}

const REAL_CLI = '#!/bin/sh\nexec "$(dirname "$0")/../python/bin/python3" uoink_cli.py "$@"\n';

// ---- findInstalled: never pick this npm package ----

test('a global npm symlink to this package is not taken for the Uoink CLI (no self-recursion)', async (t) => {
  for (const platform of ['linux', 'darwin']) {
    const s = posixDeps(t, { platform, arch: platform === 'darwin' ? 'arm64' : 'x64' });
    const prefixBin = path.join(s.root, 'usr', 'local', 'bin');
    const link = write(path.join(prefixBin, 'uoink'), '#!/usr/bin/env node\n');
    s.deps.env.PATH = prefixBin;
    s.deps.fs = fsWithLinks({ [link]: OWN_BIN });
    s.deps.pkgDir = PKG_DIR;
    assert.equal(findInstalled(s.deps), null, platform);
    assert.equal(await main(['status'], s.deps), 1);
    assert.match(s.err.text(), /not installed yet/);
    assert.equal(s.calls.run.length, 0, 'never spawns itself');
    assert.equal(s.calls.capture.length, 0);
  }
});

test('a symlink into this package directory is rejected even when it is not the .js entry', (t) => {
  const s = posixDeps(t);
  const bin = path.join(s.root, 'bin');
  const link = write(path.join(bin, 'uoink'));
  s.deps.env.PATH = bin;
  s.deps.fs = fsWithLinks({ [link]: path.join(PKG_DIR, 'README.md') });
  assert.equal(findInstalled(s.deps), null);
});

test('another copy of this package (global install while running from npx) is rejected by its .js target', (t) => {
  const s = posixDeps(t);
  const otherCopy = write(path.join(s.root, 'lib', 'node_modules', 'uoink', 'bin', 'uoink.js'), '#!/usr/bin/env node\n');
  const bin = path.join(s.root, 'bin');
  const link = write(path.join(bin, 'uoink'));
  s.deps.env.PATH = bin;
  s.deps.fs = fsWithLinks({ [link]: otherCopy });
  assert.equal(findInstalled(s.deps), null);
});

test('a pnpm or yarn shell shim that starts this package is rejected', (t) => {
  const s = posixDeps(t);
  const bin = path.join(s.root, 'pnpm');
  write(path.join(bin, 'uoink'), '#!/bin/sh\nbasedir=$(dirname "$0")\nexec node "$basedir/global/5/node_modules/uoink/bin/uoink.js" "$@"\n');
  s.deps.env.PATH = bin;
  assert.equal(findInstalled(s.deps), null);
});

test('the real Uoink CLI later on PATH is found past the npm symlink', (t) => {
  const s = posixDeps(t);
  const npmBin = path.join(s.root, 'npm-bin');
  const appBin = path.join(s.root, 'app-bin');
  const link = write(path.join(npmBin, 'uoink'));
  const real = write(path.join(appBin, 'uoink'), REAL_CLI);
  s.deps.env.PATH = [npmBin, appBin].join(path.delimiter);
  s.deps.fs = fsWithLinks({ [link]: OWN_BIN });
  assert.deepEqual(findInstalled(s.deps), { kind: 'posix', cli: real });
});

test('a symlink to the Uoink.app helper is still accepted', (t) => {
  const s = posixDeps(t, { platform: 'darwin', arch: 'arm64' });
  const helper = write(path.join(s.root, 'Applications', 'Uoink.app', 'Contents', 'Helpers', 'uoink'), REAL_CLI);
  const link = write(path.join(s.home, '.local', 'bin', 'uoink'));
  s.deps.fs = fsWithLinks({ [link]: helper });
  assert.deepEqual(findInstalled(s.deps), { kind: 'posix', cli: link });
});

test('Windows: an npm uoink.cmd shim for this package is rejected', (t) => {
  const s = posixDeps(t, { platform: 'win32' });
  const npmDir = path.join(s.root, 'npm');
  write(path.join(npmDir, 'uoink.cmd'), '@ECHO off\r\n"%_prog%"  "%dp0%\\node_modules\\uoink\\bin\\uoink.js" %*\r\n');
  write(path.join(s.root, 'python', 'python.exe'));
  write(path.join(s.root, 'uoink_cli.py'));
  s.deps.env = { PATH: npmDir };
  assert.equal(findInstalled(s.deps), null);
});

test('a real symlink to bin/uoink.js is rejected (skipped where symlinks need extra rights)', (t) => {
  const s = posixDeps(t);
  const bin = path.join(s.root, 'bin');
  fs.mkdirSync(bin);
  try {
    fs.symlinkSync(OWN_BIN, path.join(bin, 'uoink'));
  } catch (e) {
    t.skip(`cannot make a symlink here (${e.code})`);
    return;
  }
  s.deps.env.PATH = bin;
  assert.equal(findInstalled(s.deps), null);
});

// ---- recursion guard ----

test('every CLI call from the launcher carries the recursion guard', async (t) => {
  const s = posixDeps(t);
  write(path.join(s.home, '.local', 'bin', 'uoink'), REAL_CLI);
  assert.equal(await main(['search', 'x'], s.deps), 0);
  assert.equal(s.calls.run[0].env[LAUNCHER_ENV], '1');
  assert.equal(await main([], s.deps), 0);
  assert.ok(s.calls.capture.length > 0);
  for (const c of s.calls.capture) assert.equal(c.env[LAUNCHER_ENV], '1', c.args.join(' '));
});

test('a launcher started by a launcher refuses to pass through and says why', async (t) => {
  const s = posixDeps(t);
  const cli = write(path.join(s.home, '.local', 'bin', 'uoink'), REAL_CLI);
  s.deps.env[LAUNCHER_ENV] = '1';
  assert.equal(await main(['status'], s.deps), 1);
  assert.equal(s.calls.run.length, 0);
  assert.equal(s.calls.capture.length, 0);
  assert.match(s.err.text(), /avoid a loop/);
  assert.ok(s.err.text().includes(cli));
  assert.match(s.err.text(), /npm uninstall -g uoink/);
});

test('the default spawners set the guard on real child processes', async () => {
  const d = defaultDeps();
  const probe = `process.stdout.write(String(process.env.${LAUNCHER_ENV}))`;
  const got = await d.capture(process.execPath, ['-e', probe], { env: { [LAUNCHER_ENV]: '0' } });
  assert.equal(got.code, 0, got.stderr);
  assert.equal(got.stdout, '1');
  const ran = await d.run(process.execPath, ['-e', `process.exit(process.env.${LAUNCHER_ENV} === '1' ? 0 : 3)`]);
  assert.equal(ran.code, 0);
});

test('bin/uoink.js with the guard set exits 1 without running the CLI', (t) => {
  const root = tempRoot(t);
  const home = path.join(root, 'home');
  // A fake install on every platform. With the guard set none of it may run.
  write(path.join(root, 'local', 'Uoink', 'cli', 'uoink.cmd'));
  write(path.join(root, 'local', 'Uoink', 'python', 'python.exe'));
  write(path.join(root, 'local', 'Uoink', 'uoink_cli.py'));
  write(path.join(home, '.local', 'bin', 'uoink'), REAL_CLI);
  const env = { ...process.env, HOME: home, USERPROFILE: home, LOCALAPPDATA: path.join(root, 'local'), PATH: '', Path: '', [LAUNCHER_ENV]: '1' };
  const r = cp.spawnSync(process.execPath, [OWN_BIN, 'status'], { env, encoding: 'utf8', timeout: 20000 });
  assert.equal(r.status, 1, r.stderr);
  assert.match(r.stderr, /avoid a loop/);
});

// ---- Mac install: the old app survives a failed swap ----

test('the graceful quit request sends its token only in a header to the local endpoint and follows no redirects', async (t) => {
  const calls = [];
  let statusCode = 200;
  t.mock.method(http, 'request', (opts, response) => {
    const req = new EventEmitter();
    req.end = (body) => {
      calls.push({ opts, body });
      queueMicrotask(() => {
        response({ statusCode, headers: { location: 'https://example.com/quit' }, resume() {} });
        req.emit('close');
      });
    };
    return req;
  });
  const deps = defaultDeps();
  assert.equal(await deps.quitHelper('test-local-quit-token', 1000), true);
  statusCode = 302;
  assert.equal(await deps.quitHelper('test-local-quit-token', 1000), false);
  assert.equal(calls.length, 2, 'a redirect does not create another request');
  for (const { opts, body } of calls) {
    assert.deepEqual(opts, {
      hostname: '127.0.0.1', port: 5179, path: '/helper/quit', method: 'POST',
      headers: { 'X-Uoink-Token': 'test-local-quit-token', 'Content-Type': 'application/json', 'Content-Length': 2 },
    });
    assert.equal(body, '{}');
  }
});

test('the graceful quit request times out when the local endpoint does not reply', async (t) => {
  let destroyed = false;
  t.mock.method(http, 'request', () => {
    const req = new EventEmitter();
    req.end = () => {};
    req.destroy = (error) => {
      destroyed = true;
      req.emit('error', error);
      req.emit('close');
    };
    return req;
  });
  assert.equal(await defaultDeps().quitHelper('test-local-quit-token', 1), false);
  assert.equal(destroyed, true);
});

function macSetup(t, fsOver = {}) {
  const root = tempRoot(t);
  const home = path.join(root, 'home');
  const apps = path.join(home, 'Applications');
  const appDir = path.join(apps, 'Uoink.app');
  write(path.join(appDir, 'Contents', 'marker'), 'old');
  write(path.join(appDir, 'Contents', 'Helpers', 'uoink'), REAL_CLI);
  const tmp = path.join(root, 'tmp');
  fs.mkdirSync(tmp);
  const captures = [];
  const err = sink();
  const deps = {
    platform: 'darwin',
    arch: 'arm64',
    osRelease: '24.1.0',
    homedir: home,
    env: {},
    stdout: sink(),
    stderr: err,
    fs: {
      ...fsWithLinks(),
      // Never touch a real /Applications: it is "not writable" here.
      accessSync: (p, mode) => {
        if (p === '/Applications') throw Object.assign(new Error('EACCES'), { code: 'EACCES' });
        return fs.accessSync(p, mode);
      },
      ...fsOver,
    },
    capture: async (cmd, args) => {
      captures.push([path.basename(cmd), ...args]);
      if (cmd === '/usr/bin/hdiutil' && args[0] === 'attach') {
        write(path.join(args[args.indexOf('-mountpoint') + 1], 'Uoink.app', 'Contents', 'marker'), 'new');
      }
      if (cmd === '/usr/bin/ditto') fs.cpSync(args[0], args[1], { recursive: true });
      if (args.includes('status')) {
        return { code: 0, stdout: JSON.stringify({ ok: true, version: '9.9.8', helper_running: false }), stderr: '' };
      }
      return { code: 0, stdout: '', stderr: '' };
    },
  };
  const ui = makeUi(deps);
  const marker = () => fs.readFileSync(path.join(appDir, 'Contents', 'marker'), 'utf8');
  const entries = () => fs.readdirSync(apps).sort();
  const detached = () => captures.some((c) => c[0] === 'hdiutil' && c[1] === 'detach');
  return { deps, ui, tmp, apps, appDir, marker, entries, detached, err, file: path.join(tmp, 'Uoink.dmg') };
}

const fail = (code) => Object.assign(new Error(`${code}: simulated`), { code });

test('mac update: the new app replaces the old one and nothing is left behind', async (t) => {
  const m = macSetup(t);
  assert.equal(await installMac(m.file, m.tmp, m.deps, m.ui), m.appDir);
  assert.equal(m.marker(), 'new');
  assert.deepEqual(m.entries(), ['Uoink.app']);
  assert.ok(m.detached());
});

test('mac update: if the new app cannot be moved in, the old app is put back', async (t) => {
  const m = macSetup(t, {
    renameSync: (from, to) => {
      if (path.basename(from) === '.Uoink.app.new') throw fail('EXDEV');
      return fs.renameSync(from, to);
    },
  });
  await assert.rejects(installMac(m.file, m.tmp, m.deps, m.ui), /EXDEV.*put back unchanged/s);
  assert.equal(m.marker(), 'old', 'the old app is still in place');
  assert.deepEqual(m.entries(), ['Uoink.app'], 'no staged or old copy left over');
  assert.ok(m.detached());
});

test('mac update: if the old app cannot be put back, the error says where it is', async (t) => {
  const m = macSetup(t, {
    renameSync: (from, to) => {
      const name = path.basename(from);
      if (name === '.Uoink.app.new' || name.startsWith('.Uoink.app.old-')) throw fail('EIO');
      return fs.renameSync(from, to);
    },
  });
  const old = path.join(m.apps, `.Uoink.app.old-${process.pid}`);
  await assert.rejects(installMac(m.file, m.tmp, m.deps, m.ui), (e) => {
    assert.ok(e.message.includes(old), e.message);
    assert.ok(e.message.includes(`mv "${old}" "${m.appDir}"`), e.message);
    return true;
  });
  assert.equal(fs.readFileSync(path.join(old, 'Contents', 'marker'), 'utf8'), 'old', 'the old app is kept, never deleted');
  assert.ok(!fs.existsSync(path.join(m.apps, '.Uoink.app.new')));
});

test('mac update: if the old app cannot be moved aside, nothing changes', async (t) => {
  let appDir = null;
  const m = macSetup(t, {
    renameSync: (from, to) => {
      if (from === appDir) throw fail('EBUSY');
      return fs.renameSync(from, to);
    },
  });
  appDir = m.appDir;
  await assert.rejects(installMac(m.file, m.tmp, m.deps, m.ui), /EBUSY.*not changed/s);
  assert.equal(m.marker(), 'old');
  assert.deepEqual(m.entries(), ['Uoink.app']);
});

test('mac update: a leftover old copy that cannot be deleted is only a warning', async (t) => {
  const m = macSetup(t, {
    rmSync: (p, opts) => {
      if (path.basename(p).startsWith('.Uoink.app.old-')) throw fail('EPERM');
      return fs.rmSync(p, opts);
    },
  });
  assert.equal(await installMac(m.file, m.tmp, m.deps, m.ui), m.appDir);
  assert.equal(m.marker(), 'new');
  assert.match(m.err.text(), /previous copy could not be removed/);
});

test('mac fresh install: no old app, the new one goes in', async (t) => {
  const m = macSetup(t);
  fs.rmSync(m.appDir, { recursive: true });
  assert.equal(await installMac(m.file, m.tmp, m.deps, m.ui), m.appDir);
  assert.equal(m.marker(), 'new');
  assert.deepEqual(m.entries(), ['Uoink.app']);
});
