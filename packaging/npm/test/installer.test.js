'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const http = require('node:http');
const crypto = require('node:crypto');

const { main, pickAsset, cmpVersion, unsupportedMessage } = require('../lib/main.js');
const net = require('../lib/net.js');

const sha = (buf) => crypto.createHash('sha256').update(buf).digest('hex');

function sink() {
  const chunks = [];
  return { write: (s) => chunks.push(String(s)), isTTY: false, text: () => chunks.join('') };
}

// Local server standing in for GitHub releases.
function fakeRelease(files, opts = {}) {
  const hits = [];
  const server = http.createServer((req, res) => {
    hits.push({ url: req.url, range: req.headers.range || null, ua: req.headers['user-agent'] || '' });
    if (opts.handler && opts.handler(req, res, files)) return;
    const m = /\/download\/(?:v[^/]+\/)?([^/]+)$/.exec(req.url);
    const body = m && files[m[1]];
    if (!body) {
      res.writeHead(404).end();
      return;
    }
    res.writeHead(200, { 'content-length': body.length }).end(body);
  });
  return new Promise((resolve) =>
    server.listen(0, '127.0.0.1', () =>
      resolve({
        hits,
        base: `http://127.0.0.1:${server.address().port}`,
        close: () => new Promise((r) => { server.closeAllConnections(); server.close(r); }),
      })
    )
  );
}

const launched = { ok: true, version: '9.9.9', pid: 1402, supervisor_run_id: 'run-new' };

function recordLaunch(deps, appDir) {
  const data = appDir ? path.join(deps.homedir, 'Library', 'Application Support', 'Uoink')
    : path.join(deps.env.LOCALAPPDATA, 'Uoink');
  fs.mkdirSync(data, { recursive: true });
  fs.writeFileSync(path.join(data, 'helper-recovery.json'), JSON.stringify({
    status: 'running', helper_pid: launched.pid, supervisor_run_id: launched.supervisor_run_id,
  }));
  if (appDir) {
    const script = path.join(appDir, 'Contents', 'Resources', 'server.py');
    fs.writeFileSync(path.join(data, 'runtime-identity.json'), JSON.stringify({ pid: launched.pid, script }));
  } else {
    fs.writeFileSync(path.join(data, 'server.pid'), String(launched.pid));
    fakeWindowsInstall({ deps });
  }
}

function setup(t, extra = {}) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'uoink-npm-test-'));
  const tmpRoot = path.join(root, 'tmp');
  const home = path.join(root, 'home');
  fs.mkdirSync(tmpRoot);
  fs.mkdirSync(home);
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const out = sink();
  const err = sink();
  const calls = { run: [], capture: [], health: [] };
  const deps = {
    platform: 'win32',
    // Never probe the real helper port from a test. The fake helper answers
    // with the release's version, as a helper that came back would.
    helperHealth: async (timeoutMs, preinstall) => {
      calls.health.push(timeoutMs);
      return preinstall ? { listening: false } : launched;
    },
    arch: 'x64',
    env: { PATH: '', LOCALAPPDATA: path.join(root, 'local') },
    homedir: home,
    tmpRoot,
    stdout: out,
    stderr: err,
    isTTY: false,
    sleep: async () => {},
    netOpts: { allowHttp: true, allowedHosts: ['127.0.0.1'] },
    counterBase: null,
    run: async (cmd, args) => {
      calls.run.push({ cmd, args });
      if (cmd.endsWith('.exe') && args.includes('/VERYSILENT')) recordLaunch(deps);
      return { code: 0 };
    },
    capture: async (cmd, args) => {
      calls.capture.push({ cmd, args });
      if (args.includes('status')) {
        return { code: 0, stdout: JSON.stringify({ ok: true, version: '9.9.9', helper_running: true }), stderr: '' };
      }
      return { code: 0, stdout: 'claude-code\ncodex\n', stderr: '' };
    },
    ...extra,
  };
  return { deps, out, err, calls, root, tmpRoot };
}

const EXE = Buffer.from('fake windows installer bytes '.repeat(100));
const exeFiles = (body = EXE, hash = sha(body)) => ({
  'Uoink-Setup-9.9.9.exe': body,
  'SHA256SUMS.txt': Buffer.from(`${hash}  Uoink-Setup-9.9.9.exe\n${'0'.repeat(64)}  Uoink-9.9.9-macos-arm64.dmg\n`),
});

function fakeLinuxInstall(s) {
  const bin = path.join(s.deps.homedir, '.local', 'bin');
  fs.mkdirSync(bin, { recursive: true });
  fs.writeFileSync(path.join(bin, 'uoink'), '#!/bin/sh\n');
  return bin;
}

test('package.json version matches the repo VERSION file', () => {
  const version = fs.readFileSync(path.join(__dirname, '..', '..', '..', 'VERSION'), 'utf8').trim();
  const pkg = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'package.json'), 'utf8'));
  assert.equal(pkg.version, version);
});

test('package has no install-time scripts and no dependencies', () => {
  const pkg = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'package.json'), 'utf8'));
  for (const k of ['preinstall', 'install', 'postinstall', 'prepare', 'prepublish']) {
    assert.equal(pkg.scripts && pkg.scripts[k], undefined, k);
  }
  assert.equal(pkg.dependencies, undefined);
  assert.deepEqual(pkg.bin, { uoink: 'bin/uoink.js' });
});

test('asset selection per platform', () => {
  const sums = net.parseSums(
    [
      `${'a'.repeat(64)}  Uoink-Setup-3.16.3.exe`,
      `${'b'.repeat(64)}  uoink-3.16.3.mcpb`,
      `${'c'.repeat(64)}  Uoink-3.16.3-macos-arm64.dmg`,
      `${'d'.repeat(64)}  uoink-3.16.3-macos.mcpb`,
    ].join('\n')
  );
  assert.equal(pickAsset('win32', 'x64', sums).name, 'Uoink-Setup-3.16.3.exe');
  assert.equal(pickAsset('darwin', 'arm64', sums).name, 'Uoink-3.16.3-macos-arm64.dmg');
  assert.equal(pickAsset('darwin', 'arm64', sums).version, '3.16.3');
  assert.equal(pickAsset('darwin', 'x64', sums), null);
  assert.equal(pickAsset('linux', 'x64', sums), null);
  assert.equal(pickAsset('win32', 'arm64', sums), null);
  assert.equal(cmpVersion('3.16.3', '3.17.0'), -1);
  assert.equal(cmpVersion('3.16.0', '3.20.0'), -1);
  assert.equal(cmpVersion('3.17.0', '3.17.0'), 0);
  assert.equal(cmpVersion('3.10.0', '3.9.9'), 1);
});

test('prerelease precedence and installer asset names', () => {
  assert.equal(cmpVersion('3.18.2-rc.1', '3.18.1'), 1);
  assert.equal(cmpVersion('3.18.2-rc.2', '3.18.2-rc.10'), -1);
  assert.equal(cmpVersion('3.18.2-rc.1', '3.18.2'), -1);
  assert.equal(cmpVersion('3.18.2-rc.1', '3.18.2-rc.1'), 0);
  const name = 'Uoink-Setup-3.18.2-rc.1.exe';
  assert.equal(pickAsset('win32', 'x64', [[name, 'hash']]).version, '3.18.2-rc.1');
  const dmg = 'Uoink-3.18.2-rc.1-macos-arm64.dmg';
  assert.equal(pickAsset('darwin', 'arm64', [[dmg, 'hash']]).version, '3.18.2-rc.1');
});

test('Linux and Intel Mac get a docs link and exit 0 without any network', async (t) => {
  for (const [platform, arch, link] of [['linux', 'x64', 'docs/linux.md'], ['darwin', 'x64', 'docs/mac/INSTALL.md']]) {
    const s = setup(t, { platform, arch });
    const code = await main([], s.deps);
    assert.equal(code, 0);
    assert.ok(s.out.text().includes(link), s.out.text());
    assert.ok(unsupportedMessage(platform, arch).includes(link));
    assert.equal(s.calls.run.length, 0);
  }
});

test('an unsupported platform returns an error when a specific install was requested', async (t) => {
  const s = setup(t, { platform: 'linux' });
  assert.equal(await main(['install', '--version', '9.9.9'], s.deps), 1);
  assert.match(s.out.text(), /Linux guide/);
  assert.equal(s.calls.run.length, 0);
});

test('dry run prints the plan and URLs and downloads no installer', async (t) => {
  const rel = await fakeRelease(exeFiles());
  t.after(rel.close);
  const s = setup(t, { base: rel.base });
  const code = await main(['--dry-run'], s.deps);
  assert.equal(code, 0);
  const text = s.out.text();
  assert.match(text, /Uoink-Setup-9\.9\.9\.exe/);
  assert.match(text, /latest\/download\/SHA256SUMS\.txt/);
  assert.match(text, /nothing was downloaded/i);
  assert.ok(rel.hits.every((h) => h.url.endsWith('SHA256SUMS.txt')), JSON.stringify(rel.hits));
  assert.equal(s.calls.run.length, 0);
  assert.deepEqual(fs.readdirSync(s.tmpRoot), []);
});

test('--version uses the versioned release URL', async (t) => {
  const rel = await fakeRelease(exeFiles());
  t.after(rel.close);
  const s = setup(t, { base: rel.base });
  assert.equal(await main(['--dry-run', '--version', '9.9.9'], s.deps), 0);
  assert.ok(rel.hits.some((h) => h.url === '/download/v9.9.9/SHA256SUMS.txt'));
  assert.equal(await main(['--dry-run', '--version', 'bogus'], s.deps), 1);
});

test('install: verifies the hash, runs the installer silently, cleans up', async (t) => {
  const rel = await fakeRelease(exeFiles());
  t.after(rel.close);
  const s = setup(t, { base: rel.base });
  const realRun = s.deps.run;
  s.deps.run = async (cmd, args) => {
    const r = await realRun(cmd, args);
    for (const f of [['cli', 'uoink.cmd'], ['python', 'python.exe'], ['uoink_cli.py']]) {
      const p = path.join(s.deps.env.LOCALAPPDATA, 'Uoink', ...f);
      fs.mkdirSync(path.dirname(p), { recursive: true });
      fs.writeFileSync(p, '');
    }
    return r;
  };
  const code = await main(['--yes'], s.deps);
  assert.equal(code, 0, s.err.text());
  assert.equal(s.calls.run.length, 1);
  assert.match(s.calls.run[0].cmd, /Uoink-Setup-9\.9\.9\.exe$/);
  assert.deepEqual(s.calls.run[0].args, ['/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/SP-',
    '/DIR=' + path.join(s.deps.env.LOCALAPPDATA, 'Uoink')]);
  assert.deepEqual(fs.readdirSync(s.tmpRoot), [], 'temp dir removed');
  assert.match(s.out.text(), /Checksum matches/);
  assert.match(s.out.text(), /npx uoink connect claude-code/);
});

test('--no-connect skips agent hints', async (t) => {
  const rel = await fakeRelease(exeFiles());
  t.after(rel.close);
  const s = setup(t, { base: rel.base });
  assert.equal(await main(['--yes', '--no-connect'], s.deps), 0);
  assert.doesNotMatch(s.out.text(), /Connect your AI agent/);
});

test('hash mismatch aborts loudly, deletes the download, never runs the installer', async (t) => {
  const rel = await fakeRelease(exeFiles(EXE, '1'.repeat(64)));
  t.after(rel.close);
  const s = setup(t, { base: rel.base });
  const code = await main(['--yes'], s.deps);
  assert.equal(code, 1);
  assert.match(s.err.text(), /SHA-256 mismatch/);
  assert.equal(s.calls.run.length, 0);
  assert.deepEqual(fs.readdirSync(s.tmpRoot), []);
});

test('without --yes and without a terminal it stops before downloading', async (t) => {
  const rel = await fakeRelease(exeFiles());
  t.after(rel.close);
  const s = setup(t, { base: rel.base });
  assert.equal(await main([], s.deps), 1);
  assert.match(s.err.text(), /--yes/);
  assert.ok(rel.hits.every((h) => h.url.endsWith('SHA256SUMS.txt')));
});

test('answering no cancels', async (t) => {
  const rel = await fakeRelease(exeFiles());
  t.after(rel.close);
  const s = setup(t, { base: rel.base, isTTY: true, ask: async () => 'n' });
  assert.equal(await main([], s.deps), 0);
  assert.match(s.out.text(), /Cancelled/);
  assert.equal(s.calls.run.length, 0);
});

test('a dropped connection resumes with a Range request', async (t) => {
  let first = true;
  const rel = await fakeRelease(exeFiles(), {
    handler(req, res, files) {
      if (!req.url.endsWith('.exe')) return false;
      const body = files['Uoink-Setup-9.9.9.exe'];
      if (first) {
        first = false;
        res.writeHead(200, { 'content-length': body.length });
        res.write(body.subarray(0, 1000));
        setTimeout(() => res.destroy(), 20);
        return true;
      }
      const m = /bytes=(\d+)-/.exec(req.headers.range || '');
      const start = m ? Number(m[1]) : 0;
      res.writeHead(206, {
        'content-length': body.length - start,
        'content-range': `bytes ${start}-${body.length - 1}/${body.length}`,
      });
      res.end(body.subarray(start));
      return true;
    },
  });
  t.after(rel.close);
  const s = setup(t, { base: rel.base });
  assert.equal(await main(['--yes'], s.deps), 0, s.err.text());
  assert.ok(rel.hits.some((h) => h.range === 'bytes=1000-'), JSON.stringify(rel.hits));
  assert.equal(s.calls.run.length, 1);
});

test('not enough disk space fails before installing', async (t) => {
  const rel = await fakeRelease(exeFiles());
  t.after(rel.close);
  const s = setup(t, { base: rel.base, freeBytes: () => 10 });
  assert.equal(await main(['--yes'], s.deps), 1);
  assert.match(s.err.text(), /free disk space/i);
  assert.equal(s.calls.run.length, 0);
  assert.deepEqual(fs.readdirSync(s.tmpRoot), []);
});

test('redirects: only allowlisted https hosts are followed', async (t) => {
  assert.throws(() => net.checkUrl('https://evil.example.com/x'), /not on the allowed list/);
  assert.throws(() => net.checkUrl('http://github.com/x'), /non-HTTPS/);
  for (const h of ['github.com', 'objects.githubusercontent.com', 'release-assets.githubusercontent.com', 'usage.uoink.app']) {
    assert.doesNotThrow(() => net.checkUrl(`https://${h}/x`));
  }
  const rel = await fakeRelease({}, {
    handler(req, res) {
      if (req.url === '/ok') { res.writeHead(302, { location: '/final' }).end(); return true; }
      if (req.url === '/final') { res.writeHead(200).end('hi'); return true; }
      if (req.url === '/bad') { res.writeHead(302, { location: 'http://127.0.0.2:1/x' }).end(); return true; }
      return false;
    },
  });
  t.after(rel.close);
  const opts = { allowHttp: true, allowedHosts: ['127.0.0.1'] };
  assert.equal(await net.fetchText(`${rel.base}/ok`, opts), 'hi');
  await assert.rejects(net.fetchText(`${rel.base}/bad`, opts), /not on the allowed list/);
});

test('installed: arguments pass straight to the CLI and nothing is downloaded', async (t) => {
  const rel = await fakeRelease(exeFiles());
  t.after(rel.close);
  const s = setup(t, { base: rel.base, platform: 'linux' });
  const bin = fakeLinuxInstall(s);
  const code = await main(['connect', 'claude-code', '--toolset', 'core'], s.deps);
  assert.equal(code, 0);
  assert.equal(s.calls.run.length, 1);
  assert.equal(s.calls.run[0].cmd, path.join(bin, 'uoink'));
  assert.deepEqual(s.calls.run[0].args, ['connect', 'claude-code', '--toolset', 'core']);
  assert.equal(rel.hits.length, 0);
});

test('installed: bare command shows the version and suggests update, never reinstalls', async (t) => {
  const rel = await fakeRelease(exeFiles());
  t.after(rel.close);
  const s = setup(t, { base: rel.base, platform: 'linux' });
  fakeLinuxInstall(s);
  assert.equal(await main([], s.deps), 0);
  assert.match(s.out.text(), /9\.9\.9 is installed/);
  assert.match(s.out.text(), /npx uoink update/);
  assert.equal(rel.hits.length, 0);
});

test('update does nothing when the installed version is current', async (t) => {
  const rel = await fakeRelease(exeFiles());
  t.after(rel.close);
  const s = setup(t, { base: rel.base });
  for (const f of [['cli', 'uoink.cmd'], ['python', 'python.exe'], ['uoink_cli.py']]) {
    const p = path.join(s.deps.env.LOCALAPPDATA, 'Uoink', ...f);
    fs.mkdirSync(path.dirname(p), { recursive: true });
    fs.writeFileSync(p, '');
  }
  assert.equal(await main(['update'], s.deps), 0, s.err.text());
  assert.match(s.out.text(), /up to date/);
  assert.equal(s.calls.run.length, 0);
  assert.ok(rel.hits.every((h) => h.url.endsWith('SHA256SUMS.txt')));
});

test('arguments with nothing installed explain how to install', async (t) => {
  const s = setup(t);
  assert.equal(await main(['search', 'x'], s.deps), 1);
  assert.match(s.err.text(), /npx uoink/);
});

for (const args of [['update'], ['update', '--version', '9.9.9'], ['install', '--version', '9.9.9']]) {
  test(`newer installed version stays in place for ${args.join(' ')}`, async (t) => {
    const rel = await fakeRelease(exeFiles());
    t.after(rel.close);
    const s = setup(t, { base: rel.base, capture: async () => ({
      code: 0, stdout: JSON.stringify({ version: '9.12.0' }),
    }) });
    for (const file of ['cli/uoink.cmd', 'python/python.exe', 'uoink_cli.py']) {
      const p = path.join(s.deps.env.LOCALAPPDATA, 'Uoink', file);
      fs.mkdirSync(path.dirname(p), { recursive: true });
      fs.writeFileSync(p, '');
    }
    assert.equal(await main([...args, '--yes'], s.deps), args.includes('--version') ? 1 : 0);
    assert.match(s.out.text(), /9\.12\.0.*newer.*9\.9\.9/);
    assert.doesNotMatch(s.out.text(), /Update Uoink to/);
    assert.equal(s.calls.run.length, 0);
    assert.ok(rel.hits.every(hit => hit.url.endsWith('SHA256SUMS.txt')));
  });
}

test('an explicit prerelease cannot downgrade the installed stable release', async (t) => {
  const tag = '9.9.9-rc.2';
  const name = `Uoink-Setup-${tag}.exe`;
  const rel = await fakeRelease({ [name]: EXE, 'SHA256SUMS.txt': Buffer.from(`${sha(EXE)}  ${name}\n`) });
  t.after(rel.close);
  const s = setup(t, { base: rel.base });
  for (const file of ['cli/uoink.cmd', 'python/python.exe', 'uoink_cli.py']) {
    const p = path.join(s.deps.env.LOCALAPPDATA, 'Uoink', file);
    fs.mkdirSync(path.dirname(p), { recursive: true });
    fs.writeFileSync(p, '');
  }
  assert.equal(await main(['install', '--version', tag, '--yes'], s.deps), 1, s.err.text());
  assert.match(s.out.text(), /9\.9\.9 is newer than the offered version 9\.9\.9-rc\.2/);
  assert.equal(s.calls.run.length, 0);
  assert.deepEqual(rel.hits.map(hit => hit.url), [`/download/v${tag}/SHA256SUMS.txt`]);
});

test('--help works and unknown options are rejected', async (t) => {
  const s = setup(t);
  assert.equal(await main(['--help'], s.deps), 0);
  assert.match(s.out.text(), /--dry-run/);
  const s2 = setup(t);
  assert.equal(await main(['--wat'], s2.deps), 1);
});

test('mac install: starts the installed app bundle even when the CLI found is a symlink', async (t) => {
  const DMG = Buffer.from('fake mac disk image bytes '.repeat(50));
  const rel = await fakeRelease({
    'Uoink-9.9.9-macos-arm64.dmg': DMG,
    'SHA256SUMS.txt': Buffer.from(`${sha(DMG)}  Uoink-9.9.9-macos-arm64.dmg\n`),
  });
  t.after(rel.close);
  const s = setup(t, { base: rel.base, platform: 'darwin', arch: 'arm64', osRelease: '24.1.0' });
  const home = s.deps.homedir;
  const appDir = path.join(home, 'Applications', 'Uoink.app');
  // ~/.local/bin/uoink is a symlink to the app's helper (made by an earlier install).
  const link = path.join(home, '.local', 'bin', 'uoink');
  fs.mkdirSync(path.dirname(link), { recursive: true });
  fs.writeFileSync(link, '#!/bin/sh\n');
  const helper = path.join(appDir, 'Contents', 'Helpers', 'uoink');
  const enoent = () => Object.assign(new Error('ENOENT'), { code: 'ENOENT' });
  s.deps.fs = {
    ...fs,
    // Never touch this computer's own /Applications: "not writable", and hidden.
    accessSync: (p, mode) => {
      if (p === '/Applications') throw Object.assign(new Error('EACCES'), { code: 'EACCES' });
      return fs.accessSync(p, mode);
    },
    statSync: (p, ...rest) => {
      if (String(p).replace(/\\/g, '/').startsWith('/Applications/')) throw enoent();
      return fs.statSync(p, ...rest);
    },
    realpathSync: (p) => (p === link ? helper : fs.realpathSync(p)),
  };
  let started = false;
  s.deps.capture = async (cmd, args) => {
    s.calls.capture.push({ cmd, args });
    if (cmd === '/usr/bin/hdiutil' && args[0] === 'attach') {
      fs.mkdirSync(path.join(args[args.indexOf('-mountpoint') + 1], 'Uoink.app', 'Contents'), { recursive: true });
    }
    if (cmd === '/usr/bin/ditto') fs.cpSync(args[0], args[1], { recursive: true });
    if (cmd === '/usr/bin/open') { started = true; recordLaunch(s.deps, appDir); }
    if (args.includes('status')) {
      return { code: 0, stdout: JSON.stringify({ ok: true, version: '9.9.9', helper_running: started }), stderr: '' };
    }
    return { code: 0, stdout: '', stderr: '' };
  };
  assert.equal(await main(['install', '--version', '9.9.9', '--yes', '--no-connect'], s.deps), 0, s.err.text());
  assert.ok(fs.existsSync(path.join(appDir, 'Contents')), 'the app was installed');
  const status = s.calls.capture.filter((c) => c.args.includes('status'));
  assert.equal(status[0].cmd, link, 'the old CLI is found through the symlink');
  assert.equal(status.at(-1).cmd, helper, 'the new version is checked using the installed bundle');
  const opens = s.calls.capture.filter((c) => c.cmd === '/usr/bin/open').map((c) => c.args);
  assert.deepEqual(opens, [['-a', appDir]], 'opens the bundle, not three folders above the symlink');
  assert.match(s.out.text(), /Started Uoink/);
});

async function macInstallSetup(t, options = {}) {
  const dmg = Buffer.from('fake mac update');
  const rel = await fakeRelease({
    'Uoink-9.9.9-macos-arm64.dmg': dmg,
    'SHA256SUMS.txt': Buffer.from(`${sha(dmg)}  Uoink-9.9.9-macos-arm64.dmg\n`),
  });
  t.after(rel.close);
  const s = setup(t, { base: rel.base, platform: 'darwin', arch: 'arm64', osRelease: '24.1.0' });
  const appDir = path.join(s.deps.homedir, 'Applications', 'Uoink.app');
  const helper = path.join(appDir, 'Contents', 'Helpers', 'uoink');
  const marker = path.join(appDir, 'Contents', 'marker');
  fs.mkdirSync(path.dirname(helper), { recursive: true });
  fs.writeFileSync(helper, '#!/bin/sh\n');
  fs.writeFileSync(marker, 'old');
  const dataDir = path.join(s.root, 'profile');
  fs.mkdirSync(dataDir);
  if (!options.noToken) fs.writeFileSync(path.join(dataDir, 'token.txt'), 'test-local-quit-token');
  const systemCli = '/Applications/Uoink.app/Contents/Helpers/uoink';
  const otherCli = path.join(s.root, 'other-uoink');
  if (options.otherInstall) fs.writeFileSync(otherCli, '#!/bin/sh\n');
  const events = [];
  let now = 0;
  let running = options.running ?? true;
  let stopping = false;
  let opened = false;
  let stopPolls = 0;
  let startPolls = 0;
  s.deps.now = () => now;
  s.deps.sleep = async (ms) => { now += ms; };
  s.deps.fs = {
    ...fs,
    accessSync: (p, mode) => {
      if (p === '/Applications') throw Object.assign(new Error('EACCES'), { code: 'EACCES' });
      return fs.accessSync(p, mode);
    },
    statSync: (p, ...rest) => {
      if (options.otherInstall && p === systemCli) return fs.statSync(otherCli);
      if (String(p).replace(/\\/g, '/').startsWith('/Applications/')) throw Object.assign(new Error('ENOENT'), { code: 'ENOENT' });
      return fs.statSync(p, ...rest);
    },
    realpathSync: (p) => (options.otherInstall && p === systemCli ? otherCli : fs.realpathSync(p)),
    renameSync: (from, to) => {
      assert.equal(running, false, 'the helper must stop before either bundle is renamed');
      events.push(path.basename(from) === '.Uoink.app.new' ? 'swap' : 'move-old');
      return fs.renameSync(from, to);
    },
  };
  s.deps.quitHelper = async (token, timeoutMs) => {
    assert.equal(token, 'test-local-quit-token');
    assert.ok(timeoutMs > 0 && timeoutMs <= 15000);
    events.push('quit-endpoint');
    stopping = true;
    return !options.quitRejected;
  };
  s.deps.capture = async (cmd, args, opts = {}) => {
    s.calls.capture.push({ cmd, args, opts });
    if (cmd === '/usr/bin/hdiutil' && args[0] === 'attach') {
      const source = path.join(args[args.indexOf('-mountpoint') + 1], 'Uoink.app', 'Contents');
      fs.mkdirSync(path.join(source, 'Helpers'), { recursive: true });
      fs.writeFileSync(path.join(source, 'Helpers', 'uoink'), '#!/bin/sh\n');
      fs.writeFileSync(path.join(source, 'marker'), 'new');
    }
    if (cmd === '/usr/bin/ditto') fs.cpSync(args[0], args[1], { recursive: true });
    if (cmd === '/usr/bin/osascript') {
      assert.deepEqual(args, ['-e', 'quit app "Uoink"']);
      events.push('quit-applescript');
      if (options.appleScriptFails) return { code: 1, stdout: '', stderr: 'Quit failed' };
      stopping = true;
    }
    if (cmd === '/usr/bin/open') {
      assert.deepEqual(args, ['-a', appDir]);
      assert.equal(fs.readFileSync(marker, 'utf8'), 'new', 'open happens after the swap');
      events.push('open');
      opened = true;
      if (options.openFails) return { code: 1, stdout: '', stderr: 'Launch failed' };
      recordLaunch(s.deps, appDir);
    }
    if (args.includes('status')) {
      if (options.otherInstall && cmd === systemCli) {
        events.push('status:other:false');
        return { code: 0, stdout: JSON.stringify({ ok: true, version: '9.9.8', helper_running: false }), stderr: '' };
      }
      assert.equal(cmd, helper);
      const version = fs.readFileSync(marker, 'utf8') === 'old' ? (options.oldVersion || '9.9.8') : (options.startVersion || '9.9.9');
      if (opened) {
        startPolls++;
        running = !options.startFails && startPolls >= 2;
      } else if (stopping) {
        stopPolls++;
        if (!options.wontStop && stopPolls >= 2) running = false;
      }
      events.push(`status:${version}:${running}`);
      if (options.badStatus && (!options.badStatusAfterQuit || stopping)) {
        return { code: 0, stdout: 'not JSON', stderr: '' };
      }
      return { code: 0, stdout: JSON.stringify({ ok: true, version, helper_running: running, data_dir: dataDir }), stderr: '' };
    }
    return { code: 0, stdout: '', stderr: '' };
  };
  return { ...s, appDir, events, elapsed: () => now, marker: () => fs.readFileSync(marker, 'utf8') };
}

for (const command of ['update', 'install']) {
  test(`mac ${command}: quits, waits, swaps, opens the bundle and confirms the new version`, async (t) => {
    const s = await macInstallSetup(t);
    const args = command === 'install' ? ['install', '--version', '9.9.9'] : ['update'];
    assert.equal(await main([...args, '--yes', '--no-connect'], s.deps), 0, s.err.text());
    assert.equal(s.marker(), 'new');
    const quit = s.events.indexOf('quit-endpoint');
    const stopped = s.events.indexOf('status:9.9.8:false');
    const swap = s.events.indexOf('swap');
    const opened = s.events.indexOf('open');
    const confirmed = s.events.indexOf('status:9.9.9:true');
    assert.ok(quit > 0 && quit < stopped && stopped < swap && swap < opened && opened < confirmed, s.events.join(', '));
    assert.ok(s.elapsed() >= 1000, 'waits for shutdown and startup');
    assert.ok(!s.events.includes('quit-applescript'), 'uses the graceful endpoint when available');
    assert.match(s.out.text(), /Started Uoink 9\.9\.9/);
    assert.deepEqual(fs.readdirSync(path.dirname(s.appDir)), ['Uoink.app']);
    assert.deepEqual(fs.readdirSync(s.tmpRoot), []);
  });
}

test('mac update: a helper that will not stop leaves the old bundle untouched and exits 1', async (t) => {
  const s = await macInstallSetup(t, { wontStop: true });
  assert.equal(await main(['update', '--yes'], s.deps), 1);
  assert.equal(s.elapsed(), 15000, 'stops waiting at the deadline');
  assert.equal(s.marker(), 'old');
  assert.ok(!s.events.some((e) => ['move-old', 'swap', 'open'].includes(e)));
  assert.match(s.err.text(), /Quit Uoink from the menu bar, then run npx uoink update again\./);
  assert.ok(s.calls.capture.some((c) => c.cmd === '/usr/bin/hdiutil' && c.args[0] === 'detach'));
  assert.deepEqual(fs.readdirSync(path.dirname(s.appDir)), ['Uoink.app']);
  assert.deepEqual(fs.readdirSync(s.tmpRoot), []);
});

test('mac update: a stopped helper needs no quit request', async (t) => {
  const s = await macInstallSetup(t, { running: false });
  assert.equal(await main(['update', '--yes', '--no-connect'], s.deps), 0, s.err.text());
  assert.ok(!s.events.some((e) => e.startsWith('quit-')));
  assert.equal(s.marker(), 'new');
  assert.match(s.out.text(), /Started Uoink 9\.9\.9/);
});

test('mac update: an idle system copy does not hide a running app in the user Applications folder', async (t) => {
  const s = await macInstallSetup(t, { otherInstall: true });
  assert.equal(await main(['update', '--yes', '--no-connect'], s.deps), 0, s.err.text());
  assert.ok(s.events.includes('status:other:false'));
  assert.ok(s.events.includes('quit-endpoint'));
  const stopped = s.events.indexOf('status:9.9.8:false');
  assert.ok(stopped >= 0 && stopped < s.events.indexOf('swap'));
  assert.equal(s.marker(), 'new');
  assert.match(s.out.text(), /Started Uoink 9\.9\.9/);
});

test('mac update: a failed AppleScript quit cannot authorize a swap', async (t) => {
  const s = await macInstallSetup(t, { noToken: true, appleScriptFails: true });
  assert.equal(await main(['update', '--yes'], s.deps), 1);
  assert.equal(s.elapsed(), 15000);
  assert.equal(s.marker(), 'old');
  assert.ok(s.events.includes('quit-applescript'));
  assert.ok(!s.events.includes('move-old') && !s.events.includes('swap') && !s.events.includes('open'));
  assert.match(s.err.text(), /Quit Uoink from the menu bar/);
});

for (const options of [{ noToken: true }, { quitRejected: true }]) {
  test(`mac update: falls back to AppleScript when ${options.noToken ? 'the token is missing' : 'the quit endpoint fails'}`, async (t) => {
    const s = await macInstallSetup(t, options);
    assert.equal(await main(['update', '--yes', '--no-connect'], s.deps), 0, s.err.text());
    assert.ok(s.events.includes('quit-applescript'));
    assert.ok(s.events.indexOf('status:9.9.8:false') < s.events.indexOf('swap'));
    const quit = s.calls.capture.find((c) => c.cmd === '/usr/bin/osascript');
    assert.ok(quit.opts.timeoutMs > 0 && quit.opts.timeoutMs <= 15000);
  });
}

for (const afterQuit of [false, true]) {
  test(`mac update: unreadable status ${afterQuit ? 'after quitting' : 'before quitting'} never permits a swap`, async (t) => {
    const s = await macInstallSetup(t, { badStatus: true, badStatusAfterQuit: afterQuit });
  assert.equal(await main(['update', '--version', '9.9.9', '--allow-downgrade', '--yes'], s.deps), 1);
    assert.equal(s.marker(), 'old');
    assert.ok(!s.events.includes('move-old') && !s.events.includes('swap') && !s.events.includes('open'));
    assert.match(s.err.text(), /Quit Uoink from the menu bar/);
  });
}

for (const [name, options] of [
  ['open fails', { openFails: true }],
  ['the helper stays stopped', { startFails: true }],
  ['status still reports the old version', { startVersion: '9.9.8' }],
]) {
  // 3.18.1: a relaunch that does not come back is a failure (exit 1), not a
  // success with a hint. These used to expect exit 0 and the hint on stdout.
  test(`mac update: fails honestly and says to open Uoink from Applications when ${name}`, async (t) => {
    const s = await macInstallSetup(t, options);
    assert.equal(await main(['update', '--yes', '--no-connect'], s.deps), 1, s.err.text());
    assert.equal(s.marker(), 'new', 'the install itself succeeded');
    if (options.openFails) {
      assert.match(s.err.text(), /could not (open|launch|start).*Launch failed/is);
      assert.doesNotMatch(s.err.text(), /90 seconds/);
      assert.ok(s.elapsed() < 15000);
    } else if (options.startVersion) {
      assert.match(s.err.text(), /reports version 9\.9\.8/);
    } else {
      assert.match(s.err.text(), /within 90 seconds/);
    }
    assert.match(s.err.text(), /Open Uoink from Applications/);
    assert.match(s.err.text(), /npx uoink serve doctor/);
    assert.doesNotMatch(s.out.text(), /Started Uoink/);
    assert.ok(s.elapsed() <= 90000 + 1000, `bounded wait, waited ${s.elapsed()} ms`);
  });
}

// ---- download counter ----

function counterHandler(rel, mode = {}) {
  return (req, res) => {
    if (!req.url.startsWith('/get/')) return false;
    if (mode.status) { res.writeHead(mode.status).end(); return true; }
    if (mode.hang) return true;
    const u = new URL(req.url, 'http://x');
    const v = u.searchParams.get('v');
    const name = mode.name || `Uoink-Setup-${v}.exe`;
    res.writeHead(302, { location: `${rel.base()}/download/v${v}/${name}` }).end();
    return true;
  };
}

async function counterRelease(mode, extra) {
  let ref = null;
  const rel = await fakeRelease(exeFiles(), {
    handler(req, res, files) {
      if (extra && extra(req, res, files)) return true;
      return counterHandler({ base: () => ref.base }, mode)(req, res);
    },
  });
  ref = rel;
  return rel;
}

test('counter: downloads through /get/windows with explicit version and from=npm, then GitHub URL', async (t) => {
  const rel = await counterRelease({});
  t.after(rel.close);
  const s = setup(t, { base: rel.base, counterBase: rel.base });
  assert.equal(await main(['--yes'], s.deps), 0, s.err.text());
  const get = rel.hits.filter((h) => h.url.startsWith('/get/'));
  assert.equal(get.length, 1);
  assert.equal(get[0].url, '/get/windows?v=9.9.9&from=npm');
  assert.ok(rel.hits.some((h) => h.url === '/download/v9.9.9/Uoink-Setup-9.9.9.exe'));
  assert.equal(s.calls.run.length, 1);
  // checksums come straight from the release, never the counter
  assert.ok(rel.hits.some((h) => h.url === '/latest/download/SHA256SUMS.txt'));
});

test('counter: sends a browser-like uoink-npm user agent with the OS label', async (t) => {
  const rel = await counterRelease({});
  t.after(rel.close);
  const s = setup(t, { base: rel.base, counterBase: rel.base });
  await main(['--yes'], s.deps);
  const { PKG_VERSION } = require('../lib/main.js');
  const get = rel.hits.find((h) => h.url.startsWith('/get/'));
  assert.equal(get.ua, `uoink-npm/${PKG_VERSION} (Windows NT 10.0)`);
  const mac = require('../lib/main.js');
  assert.ok(mac);
});

test('counter: a Range retry goes to the GitHub URL, never back through the counter', async (t) => {
  let first = true;
  const rel = await counterRelease({}, (req, res, files) => {
    if (!req.url.endsWith('.exe')) return false;
    const body = files['Uoink-Setup-9.9.9.exe'];
    if (first) {
      first = false;
      res.writeHead(200, { 'content-length': body.length });
      res.write(body.subarray(0, 500));
      setTimeout(() => res.destroy(), 20);
      return true;
    }
    const start = Number(/bytes=(\d+)-/.exec(req.headers.range || '')?.[1] ?? 0);
    res.writeHead(206, { 'content-length': body.length - start, 'content-range': `bytes ${start}-${body.length - 1}/${body.length}` });
    res.end(body.subarray(start));
    return true;
  });
  t.after(rel.close);
  const s = setup(t, { base: rel.base, counterBase: rel.base });
  assert.equal(await main(['--yes'], s.deps), 0, s.err.text());
  assert.equal(rel.hits.filter((h) => h.url.startsWith('/get/')).length, 1);
  assert.ok(rel.hits.some((h) => h.range === 'bytes=500-' && h.url.startsWith('/download/v9.9.9/')));
});

test('counter: 5xx falls back to the direct GitHub URL', async (t) => {
  const rel = await counterRelease({ status: 503 });
  t.after(rel.close);
  const s = setup(t, { base: rel.base, counterBase: rel.base });
  assert.equal(await main(['--yes'], s.deps), 0, s.err.text());
  assert.ok(rel.hits.some((h) => h.url === '/latest/download/Uoink-Setup-9.9.9.exe'));
  assert.match(s.err.text(), /GitHub directly/);
});

test('counter: no redirect within the timeout falls back', async (t) => {
  const rel = await counterRelease({ hang: true });
  t.after(rel.close);
  const s = setup(t, { base: rel.base, counterBase: rel.base, counterTimeoutMs: 150 });
  assert.equal(await main(['--yes'], s.deps), 0, s.err.text());
  assert.ok(rel.hits.some((h) => h.url === '/latest/download/Uoink-Setup-9.9.9.exe'));
});

test('counter: an unreachable counter falls back', async (t) => {
  const rel = await fakeRelease(exeFiles());
  t.after(rel.close);
  const s = setup(t, { base: rel.base, counterBase: 'http://127.0.0.1:9' });
  assert.equal(await main(['--yes'], s.deps), 0, s.err.text());
});

test('counter: a redirect to a different file than the verified one aborts', async (t) => {
  const rel = await counterRelease({ name: 'Uoink-Setup-1.0.0.exe' });
  t.after(rel.close);
  const s = setup(t, { base: rel.base, counterBase: rel.base });
  assert.equal(await main(['--yes'], s.deps), 1);
  assert.match(s.err.text(), /checksum list names/);
  assert.equal(s.calls.run.length, 0);
  assert.ok(!rel.hits.some((h) => h.url.endsWith('.exe')));
});

// ---- 3.18.1: honest words for update, reinstall and downgrade ----

function fakeWindowsInstall(s) {
  for (const file of ['cli/uoink.cmd', 'python/python.exe', 'uoink_cli.py', 'server.py']) {
    const p = path.join(s.deps.env.LOCALAPPDATA, 'Uoink', file);
    fs.mkdirSync(path.dirname(p), { recursive: true });
    fs.writeFileSync(p, '');
  }
}

// The installed CLI reports `before` until the installer runs, then `after`.
function versionedCapture(s, before, after = '9.9.9', running = true) {
  s.deps.capture = async (cmd, args) => {
    s.calls.capture.push({ cmd, args });
    if (args.includes('status')) {
      const version = s.calls.run.length ? after : before;
      return { code: 0, stdout: JSON.stringify({ ok: true, version, helper_running: running }), stderr: '' };
    }
    return { code: 0, stdout: 'claude-code\n', stderr: '' };
  };
}

test('planAction names install, update, reinstall, downgrade and unknown', () => {
  const { planAction } = require('../lib/main.js');
  assert.equal(planAction('3.18.1', null, null, null).title, 'Install Uoink 3.18.1');
  assert.equal(planAction('3.18.1', {}, '3.17.0', 1).title, 'Update Uoink to 3.18.1 (you have 3.17.0)');
  assert.equal(planAction('3.18.1', {}, '3.18.1', 0).title, 'Reinstall Uoink 3.18.1 (the version you have)');
  const down = planAction('3.17.0', {}, '3.18.1', -1);
  assert.equal(down.title, 'Downgrade Uoink to 3.17.0 (you have 3.18.1)');
  assert.match(down.note, /library stays in place/);
  assert.match(planAction('3.18.1', {}, null, null).title, /could not be read/);
  for (const a of [planAction('3.18.1', {}, '3.17.0', 1), planAction('3.17.0', {}, '3.18.1', -1)]) {
    assert.doesNotMatch(a.title + (a.note || ''), /[—;]/, 'no em dashes or semicolons in UI copy');
  }
});

test('prerelease ordering drives the words: an rc of the same version is a downgrade', () => {
  const { planAction } = require('../lib/main.js');
  const order = cmpVersion('3.18.1-rc.1', '3.18.1');
  assert.equal(order, -1);
  assert.match(planAction('3.18.1-rc.1', {}, '3.18.1', order).title, /^Downgrade Uoink to 3\.18\.1-rc\.1 \(you have 3\.18\.1\)/);
  assert.match(planAction('3.18.1', {}, '3.18.1-rc.1', cmpVersion('3.18.1', '3.18.1-rc.1')).title, /^Update Uoink to 3\.18\.1/);
});

test('update from an older version says Update ... (you have ...)', async (t) => {
  const rel = await fakeRelease(exeFiles());
  t.after(rel.close);
  const s = setup(t, { base: rel.base });
  fakeWindowsInstall(s);
  versionedCapture(s, '9.9.8');
  assert.equal(await main(['update', '--yes', '--no-connect'], s.deps), 0, s.err.text());
  assert.match(s.out.text(), /Update Uoink to 9\.9\.9 \(you have 9\.9\.8\)/);
  assert.match(s.out.text(), /Started Uoink 9\.9\.9/);
});

test('installing the version you have says Reinstall, never Update', async (t) => {
  const rel = await fakeRelease(exeFiles());
  t.after(rel.close);
  const s = setup(t, { base: rel.base });
  fakeWindowsInstall(s);
  assert.equal(await main(['install', '--version', '9.9.9', '--dry-run'], s.deps), 0, s.err.text());
  assert.match(s.out.text(), /Reinstall Uoink 9\.9\.9 \(the version you have\)/);
  assert.doesNotMatch(s.out.text(), /Update Uoink/);
});

test('an unreadable installed version is said plainly, not called an update', async (t) => {
  const rel = await fakeRelease(exeFiles());
  t.after(rel.close);
  const s = setup(t, { base: rel.base, capture: async () => ({ code: 1, stdout: '', stderr: 'broken' }) });
  fakeWindowsInstall(s);
  assert.equal(await main(['update', '--dry-run'], s.deps), 0, s.err.text());
  assert.match(s.out.text(), /Install Uoink 9\.9\.9 over your current copy \(its version could not be read\)/);
  assert.doesNotMatch(s.out.text(), /Update Uoink/);
});

test('a downgrade without --allow-downgrade keeps your copy and says how to go back', async (t) => {
  const rel = await fakeRelease(exeFiles());
  t.after(rel.close);
  const s = setup(t, { base: rel.base });
  fakeWindowsInstall(s);
  versionedCapture(s, '9.12.0');
  assert.equal(await main(['install', '--version', '9.9.9', '--yes'], s.deps), 1, s.err.text());
  assert.match(s.out.text(), /Keeping your copy/);
  assert.match(s.out.text(), /npx uoink install --version 9\.9\.9 --allow-downgrade/);
  assert.doesNotMatch(s.out.text(), /Update Uoink|Downgrade Uoink/);
  assert.equal(s.calls.run.length, 0);
  assert.ok(rel.hits.every((h) => h.url.endsWith('SHA256SUMS.txt')));
});

test('a downgrade with --allow-downgrade says Downgrade ... (you have ...) and still asks first', async (t) => {
  const rel = await fakeRelease(exeFiles());
  t.after(rel.close);
  const asked = [];
  const s = setup(t, { base: rel.base, isTTY: true, ask: async (q) => { asked.push(q); return 'n'; } });
  fakeWindowsInstall(s);
  versionedCapture(s, '9.12.0');
  assert.equal(await main(['install', '--version', '9.9.9', '--allow-downgrade'], s.deps), 1, s.err.text());
  assert.match(s.out.text(), /Downgrade Uoink to 9\.9\.9 \(you have 9\.12\.0\)/);
  assert.match(s.out.text(), /older Uoink may not understand changes 9\.12\.0 made/);
  assert.equal(asked.length, 1, 'the confirmation question is asked');
  assert.match(s.out.text(), /Cancelled/);
  assert.equal(s.calls.run.length, 0);
});

test('a confirmed downgrade installs and checks the helper came back on the old version', async (t) => {
  const rel = await fakeRelease(exeFiles());
  t.after(rel.close);
  const s = setup(t, { base: rel.base });
  fakeWindowsInstall(s);
  versionedCapture(s, '9.12.0');
  assert.equal(await main(['install', '--version', '9.9.9', '--allow-downgrade', '--yes', '--no-connect'], s.deps), 0, s.err.text());
  assert.equal(s.calls.run.length, 1);
  assert.match(s.out.text(), /Downgrade Uoink to 9\.9\.9/);
  assert.match(s.out.text(), /Started Uoink 9\.9\.9/);
  assert.ok(s.calls.health.length >= 1);
});

// ---- 3.18.1: the helper must really come back after an install ----

function fakeClock(s) {
  let now = 0;
  s.deps.now = () => now;
  s.deps.sleep = async (ms) => { now += ms; };
  return () => now;
}

test('windows: a helper that never answers after the install is a failure, with next steps, in bounded time', async (t) => {
  const rel = await fakeRelease(exeFiles());
  t.after(rel.close);
  const s = setup(t, { base: rel.base });
  fakeWindowsInstall(s);
  versionedCapture(s, '9.9.8');
  const elapsed = fakeClock(s);
  s.deps.helperHealth = async (timeoutMs) => { s.calls.health.push(timeoutMs); return null; };
  assert.equal(await main(['update', '--yes'], s.deps), 1);
  assert.equal(s.calls.run.length, 1, 'the installer did run');
  assert.match(s.err.text(), /installer error.*version/i);
  assert.doesNotMatch(s.err.text(), /include what it prints/);
  assert.match(s.err.text(), /9\.9\.9 is installed, but its helper did not answer within 90 seconds/);
  assert.match(s.err.text(), /Open Uoink from the Start menu/);
  assert.match(s.err.text(), /npx uoink serve doctor/);
  assert.doesNotMatch(s.out.text(), /Started Uoink/);
  assert.doesNotMatch(s.out.text(), /Connect your AI agent/, 'no cheerful next steps after a failure');
  assert.equal(elapsed(), 90000, 'gives up at the deadline');
  assert.ok(s.calls.health.length > 10, 'kept polling');
  assert.ok(s.calls.health.every((ms) => ms > 0 && ms <= 5000), 'every probe is bounded');
});

test('windows: the old helper still answering with the old version does not count as back', async (t) => {
  const rel = await fakeRelease(exeFiles());
  t.after(rel.close);
  const s = setup(t, { base: rel.base });
  fakeWindowsInstall(s);
  versionedCapture(s, '9.9.8');
  fakeClock(s);
  s.deps.helperHealth = async () => ({ ok: true, version: '9.9.8' });
  assert.equal(await main(['update', '--yes'], s.deps), 1);
  assert.match(s.err.text(), /reports version 9\.9\.8/);
});

test('windows: a helper that takes a few seconds to come back is reported started', async (t) => {
  const rel = await fakeRelease(exeFiles());
  t.after(rel.close);
  const s = setup(t, { base: rel.base });
  fakeWindowsInstall(s);
  versionedCapture(s, '9.9.8');
  const elapsed = fakeClock(s);
  s.deps.helperHealth = async () => (elapsed() >= 7000 ? launched : null);
  assert.equal(await main(['update', '--yes', '--no-connect'], s.deps), 0, s.err.text());
  assert.match(s.out.text(), /Started Uoink 9\.9\.9/);
  assert.ok(elapsed() >= 7000 && elapsed() < 90000);
});

test('windows: a helper that was stopped before the update stays stopped and that is not a failure', async (t) => {
  const rel = await fakeRelease(exeFiles());
  t.after(rel.close);
  const s = setup(t, { base: rel.base });
  fakeWindowsInstall(s);
  versionedCapture(s, '9.9.8', '9.9.9', false);
  const elapsed = fakeClock(s);
  s.deps.helperHealth = async (timeoutMs) => { s.calls.health.push(timeoutMs); return { listening: false }; };
  assert.equal(await main(['update', '--yes', '--no-connect'], s.deps), 0, s.err.text());
  assert.match(s.out.text(), /not running before, so it was left stopped/);
  assert.equal(s.calls.health.length, 1, 'only the pre-install probe runs');
  assert.equal(elapsed(), 0);
});

test('windows: an installer that left the old version in place is reported, not called installed', async (t) => {
  const rel = await fakeRelease(exeFiles());
  t.after(rel.close);
  const s = setup(t, { base: rel.base });
  fakeWindowsInstall(s);
  versionedCapture(s, '9.9.8', '9.9.8');
  assert.equal(await main(['update', '--yes'], s.deps), 1);
  assert.match(s.err.text(), /still reports version 9\.9\.8, not 9\.9\.9/);
  assert.doesNotMatch(s.out.text(), /9\.9\.9 is installed/);
});

test('mac: the process is up but /health never answers, so the update is not called started', async (t) => {
  const s = await macInstallSetup(t);
  s.deps.helperHealth = async () => null;
  assert.equal(await main(['update', '--yes', '--no-connect'], s.deps), 1);
  assert.equal(s.marker(), 'new');
  assert.match(s.err.text(), /did not answer within 90 seconds/);
  assert.doesNotMatch(s.out.text(), /Started Uoink/);
  assert.ok(s.elapsed() <= 91000);
});

test('gate the destination when the readonly system bundle is older than the writable user bundle', async (t) => {
  const s = await macInstallSetup(t, { otherInstall: true, oldVersion: '10.0.0' });
  assert.equal(await main(['install', '--version', '9.9.9', '--yes'], s.deps), 1);
  assert.equal(s.marker(), 'old');
  assert.match(s.out.text(), /10\.0\.0.*newer/);
  assert.ok(!s.events.includes('swap'));
});

for (const unreadable of [null, '0.0.0-unknown']) {
  test(`unknown target version (${unreadable}) needs explicit permission even with --yes`, async (t) => {
    const rel = await fakeRelease(exeFiles());
    t.after(rel.close);
    const s = setup(t, { base: rel.base });
    fakeWindowsInstall(s);
    versionedCapture(s, unreadable);
    const args = ['install', '--version', '9.9.9', '--yes', '--no-connect'];
    assert.equal(await main(args, s.deps), 1);
    assert.equal(s.calls.run.length, 0);
    assert.match(s.out.text() + s.err.text(), /--allow-downgrade/);
    assert.equal(await main([...args, '--allow-downgrade'], s.deps), 0, s.err.text());
  });
}

test('a broken CLI still protects the target version on disk', async (t) => {
  const rel = await fakeRelease(exeFiles());
  t.after(rel.close);
  const s = setup(t, { base: rel.base, capture: async () => ({ code: 1, stdout: '' }) });
  const root = path.join(s.deps.env.LOCALAPPDATA, 'Uoink');
  fs.mkdirSync(root, { recursive: true });
  fs.writeFileSync(path.join(root, 'VERSION'), '10.0.0');
  assert.equal(await main(['install', '--version', '9.9.9', '--yes'], s.deps), 1);
  assert.match(s.out.text(), /10\.0\.0.*newer/);
  assert.equal(s.calls.run.length, 0);
});

for (const [cliRunning, preflight] of [[false, { ok: true, pid: 92 }], [undefined, null], [false, { listening: true }]]) {
  test(`Windows must verify restart for status ${cliRunning} and probe ${JSON.stringify(preflight)}`, async (t) => {
    const rel = await fakeRelease(exeFiles());
    t.after(rel.close);
    const s = setup(t, { base: rel.base });
    fakeWindowsInstall(s);
    s.deps.capture = async () => ({ code: 0, stdout: JSON.stringify({
      version: s.calls.run.length ? '9.9.9' : '9.9.8', helper_running: cliRunning }) });
    let probes = 0;
    s.deps.helperHealth = async () => { probes++; return s.calls.run.length ? null : preflight; };
    fakeClock(s);
    assert.equal(await main(['update', '--yes'], s.deps), 1);
    assert.ok(probes > 1);
    assert.doesNotMatch(s.out.text(), /left stopped|Started Uoink/);
  });
}

for (const override of [{ pid: 1401 }, { supervisor_run_id: 'other' }, { supervisor_run_id: null }]) {
  test(`matching version from another process or run is refused: ${JSON.stringify(override)}`, async (t) => {
    const rel = await fakeRelease(exeFiles());
    t.after(rel.close);
    const s = setup(t, { base: rel.base, helperHealth: async (_ms, preinstall) =>
      preinstall ? { listening: false } : { ...launched, ...override } });
    fakeWindowsInstall(s);
    fakeClock(s);
    assert.equal(await main(['install', '--version', '9.9.9', '--yes'], s.deps), 1);
    assert.doesNotMatch(s.out.text(), /Started Uoink/);
  });
}

test('failed CLI status with a readable VERSION and a live port still requires a new helper', async (t) => {
  const rel = await fakeRelease(exeFiles());
  t.after(rel.close);
  const s = setup(t, { base: rel.base, capture: async () => ({ code: 1, stdout: '' }) });
  fakeWindowsInstall(s);
  const stamp = path.join(s.deps.env.LOCALAPPDATA, 'Uoink', 'VERSION');
  fs.writeFileSync(stamp, '9.9.8');
  const setupRun = s.deps.run;
  s.deps.run = async (...args) => {
    const result = await setupRun(...args);
    fs.writeFileSync(stamp, '9.9.9');
    return result;
  };
  const probes = [];
  s.deps.helperHealth = async () => {
    const after = s.calls.run.length > 0;
    probes.push(after);
    return after ? null : { ok: true, version: '9.9.8' };
  };
  fakeClock(s);
  assert.equal(await main(['update', '--yes', '--no-connect'], s.deps), 1);
  assert.ok(probes[0] === false && probes.slice(1).includes(true));
  assert.doesNotMatch(s.out.text(), /left stopped|Started Uoink/);
});

test('the Windows status read and health polling share one post-install deadline', async (t) => {
  const rel = await fakeRelease(exeFiles());
  t.after(rel.close);
  const s = setup(t, { base: rel.base });
  fakeWindowsInstall(s);
  const elapsed = fakeClock(s);
  let statusBudget;
  s.deps.capture = async (cmd, args, opts) => {
    if (s.calls.run.length) { statusBudget = opts.timeoutMs; await s.deps.sleep(87000); }
    return { code: 0, stdout: JSON.stringify({ version: s.calls.run.length ? '9.9.9' : '9.9.8', helper_running: true }) };
  };
  const budgets = [];
  s.deps.helperHealth = async (ms) => { if (s.calls.run.length) budgets.push(ms); return null; };
  assert.equal(await main(['update', '--yes', '--no-connect'], s.deps), 1);
  assert.equal(elapsed(), 90000);
  assert.ok(statusBudget > 0 && statusBudget <= 90000);
  assert.ok(budgets.length && budgets[0] <= 3000);
  assert.match(s.err.text(), /installer error.*version/i);
  assert.doesNotMatch(s.err.text(), /include what it prints/);
});

test('a partial installation is fresh for Windows setup even when its CLI says stopped', async (t) => {
  const rel = await fakeRelease(exeFiles());
  t.after(rel.close);
  const s = setup(t, { base: rel.base, helperHealth: async () => ({ listening: false }) });
  fakeWindowsInstall(s);
  fs.unlinkSync(path.join(s.deps.env.LOCALAPPDATA, 'Uoink', 'server.py'));
  versionedCapture(s, '9.9.8', '9.9.9', false);
  fakeClock(s);
  assert.equal(await main(['update', '--yes'], s.deps), 1);
  assert.doesNotMatch(s.out.text(), /left stopped/);
});

test('gate a registered Windows destination even if the default CLI is older', async (t) => {
  const rel = await fakeRelease(exeFiles());
  t.after(rel.close);
  const s = setup(t, { base: rel.base });
  fakeWindowsInstall(s);
  const custom = path.join(s.root, 'Custom Uoink');
  fs.mkdirSync(custom);
  fs.writeFileSync(path.join(custom, 'VERSION'), '10.0.0');
  s.deps.env.SystemRoot = path.join(s.root, 'Windows');
  s.deps.capture = async (cmd) => cmd.endsWith('reg.exe')
    ? { code: 0, stdout: '    Inno Setup: App Path    REG_SZ    ' + custom }
    : { code: 0, stdout: '{"version":"9.9.8"}' };
  assert.equal(await main(['update', '--version', '9.9.9', '--yes'], s.deps), 1);
  assert.match(s.out.text(), /10\.0\.0.*newer/);
  assert.equal(s.calls.run.length, 0);
});

test('a helper that was already answering with this PID and run does not prove a reinstall', async (t) => {
  const rel = await fakeRelease(exeFiles());
  t.after(rel.close);
  const s = setup(t, { base: rel.base, helperHealth: async () => launched });
  fakeWindowsInstall(s);
  fakeClock(s);
  assert.equal(await main(['install', '--version', '9.9.9', '--yes'], s.deps), 1);
  assert.doesNotMatch(s.out.text(), /Started Uoink/);
});

test('a downgrade can verify an older supervisor that only records the ready PID', async (t) => {
  const rel = await fakeRelease(exeFiles());
  t.after(rel.close);
  const s = setup(t, { base: rel.base });
  fakeWindowsInstall(s);
  versionedCapture(s, '10.0.0');
  const state = path.join(s.deps.env.LOCALAPPDATA, 'Uoink', 'helper-recovery.json');
  const old = { supervisor_run_id: 'previous', helper_pid: 317, status: 'running' };
  fs.writeFileSync(state, JSON.stringify(old));
  const run = s.deps.run;
  s.deps.run = async (...args) => {
    const result = await run(...args);
    // Older supervisors preserve extra fields from the previous release.
    fs.writeFileSync(state, JSON.stringify({ ...old, helper_pid: launched.pid, ready_at: '2026-01-02T12:00:00Z' }));
    return result;
  };
  fakeClock(s);
  assert.equal(await main(['install', '--version', '9.9.9', '--allow-downgrade', '--yes'], s.deps), 0, s.err.text());
});

test('the changelog describes the ordinary confirmation skipped by --yes', () => {
  const changes = fs.readFileSync(path.join(__dirname, '../../..', 'CHANGELOG.md'), 'utf8').split('## [3.18.0]')[0];
  assert.match(changes, /--allow-downgrade[^\n]+--yes[^\n]+skip/i);
});

test('numeric core and prerelease fields reject leading zeroes in args, precedence and assets', () => {
  const { parseOwnArgs } = require('../lib/main.js');
  for (const v of ['03.1.0', '3.01.0', '3.1.00', '3.1.0-01', '3.1.0-rc.01.a']) {
    assert.throws(() => parseOwnArgs(['--version', v]));
    assert.equal(cmpVersion(v, '3.1.0'), null);
    assert.equal(pickAsset('win32', 'x64', [[`Uoink-Setup-${v}.exe`, 'hash']]), null);
  }
  assert.equal(cmpVersion('3.1.0-01a+01', '3.1.0-01a+02'), 0);
});

test('the default health probe reads /health on the helper port, follows no redirects and is bounded', async (t) => {
  const { defaultDeps, HELPER_PORT } = require('../lib/main.js');
  assert.equal(HELPER_PORT, 5179);
  let reply = { status: 200, body: JSON.stringify({ ok: true, version: '9.9.9' }) };
  const server = http.createServer((req, res) => {
    if (reply.hang) return;
    res.writeHead(reply.status, reply.status === 302 ? { location: 'http://127.0.0.1:1/health' } : {});
    res.end(reply.body || '');
  });
  await new Promise((r) => server.listen(0, '127.0.0.1', r));
  t.after(() => new Promise((r) => { server.closeAllConnections(); server.close(r); }));
  const seen = [];
  const port = server.address().port;
  const realGet = http.get;
  // Send the request to the local test server, never the real helper port.
  t.mock.method(http, 'get', (opts, cb) => {
    seen.push({ ...opts });
    return realGet({ ...opts, port }, cb);
  });
  const deps = defaultDeps();
  assert.deepEqual(await deps.helperHealth(2000), { ok: true, version: '9.9.9' });
  assert.deepEqual(seen[0], { hostname: '127.0.0.1', port: 5179, path: '/health' });
  reply = { status: 302 };
  assert.equal(await deps.helperHealth(2000), null);
  reply = { status: 200, body: 'not json' };
  assert.equal(await deps.helperHealth(2000), null);
  reply = { hang: true };
  const start = Date.now();
  assert.equal(await deps.helperHealth(100), null);
  assert.ok(Date.now() - start < 2000, 'times out');
  assert.equal(seen.length, 4, 'a redirect does not create another request');
  assert.deepEqual(await deps.helperHealth(100, true), { listening: true }, 'a silent listener is still bound');
  server.closeAllConnections();
  await new Promise(resolve => server.close(resolve));
  assert.deepEqual(await deps.helperHealth(1000, true), { listening: false }, 'connection refused');
});
