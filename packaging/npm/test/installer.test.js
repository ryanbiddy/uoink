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
    const m = /\/download\/(?:v[\d.]+\/)?([^/]+)$/.exec(req.url);
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

function setup(t, extra = {}) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'uoink-npm-test-'));
  const tmpRoot = path.join(root, 'tmp');
  const home = path.join(root, 'home');
  fs.mkdirSync(tmpRoot);
  fs.mkdirSync(home);
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const out = sink();
  const err = sink();
  const calls = { run: [], capture: [] };
  const deps = {
    platform: 'win32',
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
  assert.equal(cmpVersion('3.17.0', '3.17.0'), 0);
  assert.equal(cmpVersion('3.10.0', '3.9.9'), 1);
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
  assert.deepEqual(s.calls.run[0].args, ['/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/SP-']);
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

test('--help works and unknown options are rejected', async (t) => {
  const s = setup(t);
  assert.equal(await main(['--help'], s.deps), 0);
  assert.match(s.out.text(), /--dry-run/);
  const s2 = setup(t);
  assert.equal(await main(['--wat'], s2.deps), 1);
});

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
