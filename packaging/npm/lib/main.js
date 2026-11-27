'use strict';
// npx uoink: install Uoink (download, verify, install, set up) or pass
// arguments to the installed CLI. Everything with side effects is behind the
// `deps` object so tests can inject fakes.

const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const cp = require('node:child_process');
const http = require('node:http');
const readline = require('node:readline');
const net = require('./net.js');

const REPO = 'ryanbiddy/uoink';
const BASE = `https://github.com/${REPO}/releases`;
const LINUX_DOCS = `https://github.com/${REPO}/blob/main/docs/linux.md`;
const MAC_DOCS = `https://github.com/${REPO}/blob/main/docs/mac/INSTALL.md`;
const CONNECT_DOCS = `https://github.com/${REPO}/blob/main/docs/connect-your-agent.md`;
const PKG_VERSION = require('../package.json').version;
const PKG_DIR = path.resolve(__dirname, '..');
// Set on every child process. If a launcher starts with it already set, an
// earlier launcher started it, so it must not pass through again.
const LAUNCHER_ENV = 'UOINK_NPM_LAUNCHER';
// The port an installed Uoink helper listens on (server.py PORT).
const HELPER_PORT = 5179;
// How long to wait for a freshly installed helper to answer /health. First
// start after an update can run library migrations, so this is generous.
const HELPER_START_WAIT_MS = 90000;

const HELP = `uoink: install Uoink, or run the installed Uoink CLI

Usage
  npx uoink                    install Uoink (asks first), or show the installed version
  npx uoink update             install the latest version if it is newer
  npx uoink <command> ...      run the installed CLI, e.g. connect claude-code, search "..."

Options (install and update only)
  --yes             skip the confirmation question
  --dry-run         print the plan and URLs, download nothing
  --version <v>     install a specific version, e.g. 3.16.3
  --allow-downgrade permit replacing a newer copy or one whose version is unknown
  --no-connect      skip the agent connection hints at the end
  --help            show this help

Uoink: https://uoink.app
`;

class UserError extends Error {}

// ---------- platform ----------

function assetFor(platform, arch, version) {
  const v = version.replace(/^v/, '');
  if (platform === 'win32' && arch === 'x64') return { name: `Uoink-Setup-${v}.exe`, kind: 'exe' };
  if (platform === 'darwin' && arch === 'arm64') return { name: `Uoink-${v}-macos-arm64.dmg`, kind: 'dmg' };
  return null;
}

const NUMBER = '(?:0|[1-9][0-9]*)';
const PRE_ID = `(?:${NUMBER}|[0-9]*[A-Za-z-][0-9A-Za-z-]*)`;
const VERSION_PATTERN = String.raw`(${NUMBER})\.(${NUMBER})\.(${NUMBER})(?:-(${PRE_ID}(?:\.${PRE_ID})*))?(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?`;
const VERSION_RE = new RegExp(`^${VERSION_PATTERN}$`);

// Find the asset for this platform in a parsed SHA256SUMS map. Returns
// { name, kind, version, sha } or null.
function pickAsset(platform, arch, sums) {
  let re;
  let kind;
  if (platform === 'win32' && arch === 'x64') {
    re = new RegExp(`^Uoink-Setup-(${VERSION_PATTERN})\\.exe$`);
    kind = 'exe';
  } else if (platform === 'darwin' && arch === 'arm64') {
    re = new RegExp(`^Uoink-(${VERSION_PATTERN})-macos-arm64\\.dmg$`);
    kind = 'dmg';
  } else {
    return null;
  }
  for (const [name, sha] of sums) {
    const m = re.exec(name);
    if (m) return { name, kind, version: m[1], sha };
  }
  return null;
}

function unsupportedMessage(platform, arch) {
  if (platform === 'linux') {
    return `Uoink on Linux is set up from source, not by this command.\nFollow the Linux guide: ${LINUX_DOCS}`;
  }
  if (platform === 'darwin') {
    return `The Uoink Mac app is for Apple silicon (M1 or newer). This Mac is ${arch}.\nSee the Mac guide: ${MAC_DOCS}`;
  }
  if (platform === 'win32') {
    return `The Uoink installer is for 64-bit Intel or AMD Windows. This machine is ${arch}.\nDownload options: https://uoink.app/get`;
  }
  return `Uoink does not have an installer for ${platform}/${arch}. See https://uoink.app/get`;
}

function cmpVersion(a, b) {
  const left = VERSION_RE.exec(a.replace(/^v/, ''));
  const right = VERSION_RE.exec(b.replace(/^v/, ''));
  if (!left || !right) return null;
  function compare(x, y) {
    return x < y ? -1 : x > y ? 1 : 0;
  }
  for (let i = 1; i <= 3; i++) {
    const order = compare(BigInt(left[i]), BigInt(right[i]));
    if (order) return order;
  }
  if (!left[4] || !right[4]) return compare(!left[4], !right[4]);
  const pa = left[4].split('.');
  const pb = right[4].split('.');
  for (let i = 0; i < Math.min(pa.length, pb.length); i++) {
    if (pa[i] === pb[i]) continue;
    const na = /^\d+$/.test(pa[i]);
    const nb = /^\d+$/.test(pb[i]);
    if (na && nb) return compare(BigInt(pa[i]), BigInt(pb[i]));
    if (na !== nb) return na ? -1 : 1;
    return compare(pa[i], pb[i]);
  }
  return compare(pa.length, pb.length);
}

// ---------- finding an installed Uoink ----------

function isExecutableFile(p, deps) {
  try {
    return deps.fs.statSync(p).isFile();
  } catch {
    return false;
  }
}

function realPath(p, deps) {
  try {
    return deps.fs.realpathSync(p);
  } catch {
    return null;
  }
}

function isInside(child, dir) {
  const rel = path.relative(dir, child);
  return rel === '' || (rel !== '..' && !rel.startsWith(`..${path.sep}`) && !path.isAbsolute(rel));
}

// A pnpm or yarn global install puts a small shell script on PATH instead of
// a symlink. It names this package's bin/uoink.js.
function namesThisPackage(file, deps) {
  let fd;
  try {
    fd = deps.fs.openSync(file, 'r');
    const buf = Buffer.alloc(4096);
    const n = deps.fs.readSync(fd, buf, 0, buf.length, 0);
    return /node_modules[\\/]+uoink[\\/]+bin[\\/]+uoink\.js/i.test(buf.subarray(0, n).toString('utf8'));
  } catch {
    return false;
  } finally {
    if (fd !== undefined) {
      try {
        deps.fs.closeSync(fd);
      } catch {
        /* already closed */
      }
    }
  }
}

// True when a resolved candidate is this npm launcher (or another copy of it)
// rather than the Uoink desktop CLI. A global `npm i -g uoink` puts a uoink
// symlink on PATH that points at bin/uoink.js, and running that would start
// this launcher again.
function isNpmLauncher(real, deps) {
  const own = deps.pkgDir || PKG_DIR;
  for (const dir of new Set([own, realPath(own, deps)].filter(Boolean))) {
    if (isInside(real, dir)) return true;
  }
  if (/\.[cm]?js$/i.test(real)) return true;
  return namesThisPackage(real, deps);
}

// The candidate's real path when it is a usable file and not this launcher.
function usableCli(p, deps) {
  if (!isExecutableFile(p, deps)) return null;
  const real = realPath(p, deps);
  if (!real || isNpmLauncher(real, deps)) return null;
  return real;
}

// Returns { kind: 'win'|'posix', cli, python?, script? } or null.
function findInstalled(deps) {
  const { platform, env } = deps;
  const home = deps.homedir;
  const seen = new Set();
  const cands = [];
  const add = (p) => {
    if (p && !seen.has(p)) {
      seen.add(p);
      cands.push(p);
    }
  };
  const pathDirs = (env.PATH || env.Path || '').split(path.delimiter).filter(Boolean);
  const notOurs = (dir) => !/node_modules|[\\/]_npx[\\/]|[\\/]npm-cache[\\/]/i.test(dir);
  if (platform === 'win32') {
    if (env.LOCALAPPDATA) add(path.join(env.LOCALAPPDATA, 'Uoink', 'cli', 'uoink.cmd'));
    for (const d of pathDirs.filter(notOurs)) add(path.join(d, 'uoink.cmd'));
    for (const c of cands) {
      if (!usableCli(c, deps)) continue;
      const root = path.resolve(path.dirname(c), '..');
      const python = path.join(root, 'python', 'python.exe');
      const script = path.join(root, 'uoink_cli.py');
      if (isExecutableFile(python, deps) && isExecutableFile(script, deps)) {
        return { kind: 'win', cli: c, python, script };
      }
    }
    return null;
  }
  if (platform === 'darwin') {
    add('/Applications/Uoink.app/Contents/Helpers/uoink');
    add(path.join(home, 'Applications', 'Uoink.app', 'Contents', 'Helpers', 'uoink'));
  }
  add(path.join(home, '.local', 'bin', 'uoink'));
  for (const d of pathDirs.filter(notOurs)) add(path.join(d, 'uoink'));
  for (const c of cands) if (usableCli(c, deps)) return { kind: 'posix', cli: c };
  return null;
}

function macDestination(deps) {
  const apps = writable('/Applications', deps) ? '/Applications' : path.join(deps.homedir, 'Applications');
  return path.join(apps, 'Uoink.app');
}

async function installTarget(deps) {
  if (deps.platform === 'darwin') {
    const dir = macDestination(deps);
    return { dir, exists: lexists(dir, deps), resources: path.join(dir, 'Contents', 'Resources'),
      inst: { kind: 'posix', cli: path.join(dir, 'Contents', 'Helpers', 'uoink') },
      data: path.join(deps.homedir, 'Library', 'Application Support', 'Uoink') };
  }
  if (!deps.env.LOCALAPPDATA) throw new UserError('Could not locate the per-user Uoink installation folder.');
  const data = path.join(deps.env.LOCALAPPDATA, 'Uoink');
  let dir = data;
  // Inno remembers a custom directory in this ordinary per-user uninstall key.
  if (deps.env.SystemRoot) {
    const key = String.raw`HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\{1CCDA47D-2347-43D1-99F4-BD6E7C231288}_is1`;
    const reg = path.join(deps.env.SystemRoot, 'System32', 'reg.exe');
    const result = await deps.capture(reg, ['query', key, '/v', 'Inno Setup: App Path', '/reg:64']);
    const saved = result.code === 0 && /^\s*Inno Setup: App Path\s+REG_SZ\s+(.+)$/im.exec(result.stdout);
    if (saved && path.isAbsolute(saved[1].trim())) dir = saved[1].trim();
  }
  const inst = { kind: 'win', cli: path.join(dir, 'cli', 'uoink.cmd'),
    python: path.join(dir, 'python', 'python.exe'), script: path.join(dir, 'uoink_cli.py') };
  // Match the native installer's FreshInstall test in PrepareToInstall.
  const hasHelper = ['server.py', 'uoink_supervisor.py'].some(file => isExecutableFile(path.join(dir, file), deps));
  const exists = hasHelper || [inst.cli, inst.python, inst.script, path.join(dir, 'VERSION')].some(file => lexists(file, deps));
  return { dir, data, resources: dir, inst, exists, hasHelper };
}

function knownVersion(value) {
  return typeof value === 'string' && value !== '0.0.0-unknown' && VERSION_RE.test(value);
}

async function targetStatus(target, deps, timeoutMs) {
  const inst = target.inst;
  let result = { version: null, status: null };
  if (inst.kind === 'posix' || (isExecutableFile(inst.python, deps) && isExecutableFile(inst.script, deps))) {
    result = await installedVersion(inst, deps, timeoutMs);
  }
  if (!knownVersion(result.version)) {
    try {
      result.version = deps.fs.readFileSync(path.join(target.resources, 'VERSION'), 'utf8').trim();
    } catch {
      result.version = null;
    }
    if (!knownVersion(result.version)) result.version = null;
  }
  return result;
}

function cliInvocation(inst) {
  if (inst.kind === 'win') {
    return { cmd: inst.python, args: [inst.script], env: { PYTHONIOENCODING: 'utf-8', PYTHONUTF8: '1', [LAUNCHER_ENV]: '1' } };
  }
  return { cmd: inst.cli, args: [], env: { [LAUNCHER_ENV]: '1' } };
}

// The environment for every child process: ours, plus the recursion guard.
function childEnv(extra) {
  return { ...process.env, ...(extra || {}), [LAUNCHER_ENV]: '1' };
}

async function installedVersion(inst, deps, timeoutMs) {
  const inv = cliInvocation(inst);
  try {
    const r = await deps.capture(inv.cmd, [...inv.args, 'status'], { env: inv.env, timeoutMs });
    if (r.code !== 0) return { version: null, status: null };
    const status = JSON.parse(r.stdout.slice(r.stdout.indexOf('{')));
    return { version: typeof status.version === 'string' ? status.version : null, status };
  } catch {
    return { version: null, status: null };
  }
}

// ---------- default deps ----------

function defaultDeps() {
  const out = process.stdout;
  const err = process.stderr;
  return {
    platform: process.platform,
    arch: process.arch,
    env: process.env,
    homedir: os.homedir(),
    osRelease: os.release(),
    fs,
    tmpRoot: os.tmpdir(),
    base: BASE,
    netOpts: {},
    counterBase: 'https://usage.uoink.app',
    stdout: out,
    stderr: err,
    isTTY: Boolean(process.stdin.isTTY && err.isTTY),
    now: () => performance.now(),
    sleep: (ms) => new Promise((r) => setTimeout(r, ms)),
    // The same token-gated local endpoint used by the menu bar's Quit action.
    // Never follow redirects or put the token in a URL or process arguments.
    quitHelper: (token, timeoutMs) =>
      new Promise((resolve) => {
        const req = http.request({
          hostname: '127.0.0.1', port: HELPER_PORT, path: '/helper/quit', method: 'POST',
          headers: { 'X-Uoink-Token': token, 'Content-Type': 'application/json', 'Content-Length': 2 },
        }, (res) => {
          res.resume();
          resolve(res.statusCode === 200);
        });
        const timer = setTimeout(() => req.destroy(new Error('Quit request timed out.')), timeoutMs);
        req.on('close', () => { clearTimeout(timer); resolve(false); });
        req.on('error', () => resolve(false));
        req.end('{}');
      }),
    // The helper's public liveness probe on the port the installed app uses.
    // Resolves to the parsed JSON body, or null when nothing answers in time.
    // Sends nothing but the request line; follows no redirects.
    helperHealth: (timeoutMs, preinstall = false) =>
      new Promise((resolve) => {
        let done = false;
        let listening = null;
        const finish = (value) => {
          if (!done) {
            done = true;
            resolve(preinstall && !value ? { listening } : value);
          }
        };
        const req = http.get({ hostname: '127.0.0.1', port: HELPER_PORT, path: '/health' }, (res) => {
          listening = true;
          if (res.statusCode !== 200) {
            res.resume();
            finish(null);
            return;
          }
          const chunks = [];
          let size = 0;
          res.on('data', (c) => {
            size += c.length;
            if (size > 1024 * 1024) req.destroy(new Error('Health reply too large.'));
            else chunks.push(c);
          });
          res.on('end', () => {
            try {
              finish(JSON.parse(Buffer.concat(chunks).toString('utf8')));
            } catch {
              finish(null);
            }
          });
        });
        const timer = setTimeout(() => req.destroy(new Error('Health check timed out.')), timeoutMs);
        req.on('close', () => { clearTimeout(timer); finish(null); });
        req.on('socket', socket => socket.once('connect', () => { listening = true; }));
        req.on('error', (error) => {
          if (error.code === 'ECONNREFUSED') listening = false;
          finish(null);
        });
      }),
    ask: (question) =>
      new Promise((resolve) => {
        const rl = readline.createInterface({ input: process.stdin, output: err });
        rl.question(question, (a) => {
          rl.close();
          resolve(a);
        });
        rl.on('close', () => resolve(''));
      }),
    // Run a program and wait. Never uses a shell.
    run: (cmd, args, opts = {}) =>
      new Promise((resolve) => {
        const c = cp.spawn(cmd, args, { stdio: 'inherit', env: childEnv(opts.env), windowsHide: false });
        c.on('error', (e) => resolve({ code: -1, error: e }));
        c.on('exit', (code, sig) => resolve({ code: code === null ? 128 : code, signal: sig }));
      }),
    capture: (cmd, args, opts = {}) =>
      new Promise((resolve) => {
        cp.execFile(
          cmd,
          args,
          { env: childEnv(opts.env), maxBuffer: 16 * 1024 * 1024, timeout: opts.timeoutMs ?? 60000, windowsHide: true },
          (e, stdout, stderr) => resolve({ code: e ? (typeof e.code === 'number' ? e.code : 1) : 0, stdout: String(stdout || ''), stderr: String(stderr || '') })
        );
      }),
  };
}

// ---------- output ----------

function makeUi(deps) {
  const color = !deps.env.NO_COLOR && deps.stdout.isTTY;
  const wrap = (code) => (s) => (color ? `\u001b[${code}m${s}\u001b[0m` : s);
  const bold = wrap('1');
  const dim = wrap('2');
  const red = wrap('31');
  return {
    bold,
    dim,
    say: (s = '') => deps.stdout.write(`${s}\n`),
    warn: (s) => deps.stderr.write(`${s}\n`),
    fail: (s) => deps.stderr.write(`${red('uoink:')} ${s}\n`),
  };
}

// ---------- args ----------

function parseOwnArgs(argv) {
  const o = { yes: false, dryRun: false, noConnect: false, help: false, version: null, versionFlag: false, command: null, allowDowngrade: false };
  const rest = [...argv];
  if (rest[0] === 'update' || rest[0] === 'install') o.command = rest.shift();
  while (rest.length) {
    const a = rest.shift();
    if (a === '--yes' || a === '-y') o.yes = true;
    else if (a === '--allow-downgrade') o.allowDowngrade = true;
    else if (a === '--dry-run') o.dryRun = true;
    else if (a === '--no-connect') o.noConnect = true;
    else if (a === '--help' || a === '-h') o.help = true;
    else if (a === '--version') {
      if (rest.length && !rest[0].startsWith('-')) o.version = rest.shift();
      else o.versionFlag = true;
    } else if (a.startsWith('--version=')) o.version = a.slice(10);
    else throw new UserError(`Unknown option: ${a}. Try: npx uoink --help`);
  }
  if (o.version !== null) {
    const v = o.version.replace(/^v/, '');
    if (!VERSION_RE.test(v)) throw new UserError(`"${o.version}" is not a version like 3.16.3.`);
    o.version = v;
  }
  return o;
}

// Our own flags apply only to a bare invocation, update, or install.
function isOwnInvocation(argv) {
  if (argv.length === 0) return true;
  if (argv[0] === 'update' || argv[0] === 'install') return true;
  return argv.every((a, i) => a.startsWith('-') || argv[i - 1] === '--version');
}

// ---------- plan ----------

async function resolvePlan(opts, deps) {
  const netOpts = deps.netOpts;
  const dl = opts.version ? `${deps.base}/download/v${opts.version}` : `${deps.base}/latest/download`;
  const sumsUrl = `${dl}/SHA256SUMS.txt`;
  let text;
  try {
    text = await net.fetchText(sumsUrl, netOpts);
  } catch (e) {
    if (e instanceof net.HttpError && e.status === 404) {
      throw new UserError(opts.version ? `Uoink ${opts.version} was not found. See ${deps.base}` : `Could not find the latest Uoink release at ${deps.base}`);
    }
    throw e;
  }
  const sums = net.parseSums(text);
  const asset = pickAsset(deps.platform, deps.arch, sums);
  if (!asset) {
    throw new UserError(`The release has no installer for ${deps.platform}/${deps.arch} in its SHA256SUMS.txt.`);
  }
  if (opts.version && asset.version !== opts.version) {
    throw new UserError(`Release v${opts.version} lists ${asset.name}, which does not match the version.`);
  }
  const os = asset.kind === 'exe' ? 'windows' : 'mac';
  const counterUrl = deps.counterBase ? `${deps.counterBase}/get/${os}?v=${asset.version}&from=npm` : null;
  return { ...asset, sumsUrl, url: `${dl}/${asset.name}`, counterUrl };
}

// ---------- download with progress ----------

function makeProgress(deps, ui) {
  const quiet = !deps.stderr.isTTY || Boolean(deps.env.CI);
  let nextPct = 10;
  return {
    start(name) {
      ui.warn(`Downloading ${name}`);
    },
    update(got, total) {
      if (quiet || !total) return;
      const pct = Math.floor((got / total) * 100);
      if (pct >= nextPct) {
        ui.warn(`  ${pct}% (${net.formatBytes(got)} of ${net.formatBytes(total)})`);
        nextPct = Math.floor(pct / 10) * 10 + 10;
      }
    },
  };
}

function explainError(e, deps) {
  const code = e && e.code;
  if (e instanceof UserError) return e.message;
  if (e instanceof net.DiskSpaceError) return `${e.message} Free some space and run the command again.`;
  if (e instanceof net.SecurityError) return `Stopped for safety. ${e.message}`;
  if (e instanceof net.HttpError) {
    if (e.status === 403 || e.status === 429) return `GitHub is rate limiting this connection (HTTP ${e.status}). Wait a few minutes and try again.`;
    if (e.status === 404) return `Not found: ${e.url}`;
    return `${e.message}. Try again in a moment.`;
  }
  if (['ENOTFOUND', 'EAI_AGAIN', 'ECONNREFUSED', 'ENETUNREACH', 'ETIMEDOUT', 'ECONNRESET'].includes(code)) {
    return `Could not reach GitHub. Check your internet connection and try again.`;
  }
  if (code === 'ENOSPC') return 'The disk is full. Free some space and run the command again.';
  if (code === 'EACCES' || code === 'EPERM') return `Permission denied: ${e.path || e.message}`;
  return e && e.message ? e.message : String(e);
}

// ---------- download source ----------

function userAgent(deps) {
  const os = deps.platform === 'win32' ? 'Windows NT 10.0' : 'Macintosh; Mac OS X';
  return `uoink-npm/${PKG_VERSION} (${os})`;
}

// Ask the download counter once for the GitHub URL it redirects to. Returns
// that final GitHub URL, so a retry never goes back through the counter. Any
// counter failure falls back to GitHub directly. A redirect to a different
// file than the one we verify is a hard error.
async function chooseSource(plan, deps, ui) {
  if (!plan.counterUrl) return plan.url;
  let target;
  try {
    target = await net.firstRedirect(plan.counterUrl, {
      ...deps.netOpts,
      headers: { 'user-agent': userAgent(deps) },
      timeoutMs: deps.counterTimeoutMs ?? 10000,
    });
  } catch {
    ui.warn('Download counter unavailable, downloading from GitHub directly.');
    return plan.url;
  }
  const name = decodeURIComponent(new URL(target).pathname.split('/').pop());
  if (name !== plan.name) {
    throw new UserError(`The download link points to ${name}, but the checksum list names ${plan.name}. Nothing was downloaded.`);
  }
  return target;
}

// ---------- install steps ----------

async function installWindows(file, deps, ui, dir) {
  ui.say('Running the Uoink installer (per user, no admin needed). This can take a minute.');
  const r = await deps.run(file, ['/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/SP-', `/DIR=${dir}`]);
  if (r.error) throw new UserError(`Could not start the installer: ${r.error.message}`);
  if (r.code !== 0) {
    throw new UserError(`The installer exited with code ${r.code}. Close any running Uoink and try again, or download it from https://uoink.app/get.`);
  }
}

function pathDirs(deps) {
  return (deps.env.PATH || '').split(path.delimiter).filter(Boolean);
}

function writable(dir, deps) {
  try {
    deps.fs.accessSync(dir, deps.fs.constants.W_OK);
    return true;
  } catch {
    return false;
  }
}

function lexists(p, deps) {
  try {
    deps.fs.lstatSync(p);
    return true;
  } catch {
    return false;
  }
}

const reason = (e) => (e && (e.code || e.message)) || String(e);

const MAC_HELPER_WAIT_MS = 15000;
const MAC_QUIT_MESSAGE = 'Quit Uoink from the menu bar, then run npx uoink update again.';

async function waitForMacStatus(inst, deps, deadline, matches) {
  while (deps.now() < deadline) {
    const result = await installedVersion(inst, deps, Math.max(1, Math.ceil(deadline - deps.now())));
    if (matches(result)) return true;
    const remaining = deadline - deps.now();
    if (remaining <= 0) break;
    await deps.sleep(Math.min(500, remaining));
  }
  return false;
}

async function stopMacHelper(appDir, deps, ui) {
  const installed = findInstalled(deps);
  const target = lexists(appDir, deps)
    ? { kind: 'posix', cli: path.join(appDir, 'Contents', 'Helpers', 'uoink') } : null;
  const checked = new Set();
  // /Applications and ~/Applications can both contain an app. An idle copy
  // found first must not hide a running helper in the bundle being replaced.
  for (const inst of [installed, target]) {
    if (!inst) continue;
    const cli = realPath(inst.cli, deps) || inst.cli;
    if (checked.has(cli)) continue;
    checked.add(cli);
    await stopMacInstance(inst, deps, ui);
  }
}

async function stopMacInstance(inst, deps, ui) {
  const { status } = await installedVersion(inst, deps, MAC_HELPER_WAIT_MS);
  if (status && status.helper_running === false) return;
  // A failed status command does not prove that it is safe to replace the app.
  if (!status || status.helper_running !== true) throw new UserError(MAC_QUIT_MESSAGE);

  ui.say('Quitting Uoink before replacing the app...');
  const deadline = deps.now() + MAC_HELPER_WAIT_MS;
  let requested = false;
  // The installed CLI has no stop command. Its status supplies the data folder
  // containing the local token used by the helper's graceful quit endpoint.
  try {
    if (typeof status.data_dir === 'string' && path.isAbsolute(status.data_dir)) {
      const token = deps.fs.readFileSync(path.join(status.data_dir, 'token.txt'), 'utf8').trim();
      if (token) requested = await deps.quitHelper(token, 3000);
    }
  } catch {
    /* An older or inaccessible install can still receive an AppleScript Quit. */
  }
  if (!requested && deps.now() < deadline) {
    try {
      await deps.capture('/usr/bin/osascript', ['-e', 'quit app "Uoink"'], { timeoutMs: Math.ceil(deadline - deps.now()) });
    } catch {
      /* Only an explicit helper_running: false below permits the swap. */
    }
  }
  if (!await waitForMacStatus(inst, deps, deadline, ({ status }) => status && status.helper_running === false)) {
    throw new UserError(MAC_QUIT_MESSAGE);
  }
}

// Replace appDir with the staged copy so there is never a moment with no
// Uoink.app: move the old one aside, move the new one in, and only then
// delete the old one. If the new one can't go in, the old one goes back.
function swapIntoPlace(staged, appDir, deps, ui) {
  const old = path.join(path.dirname(appDir), `.Uoink.app.old-${process.pid}`);
  const dropStaged = () => {
    try {
      deps.fs.rmSync(staged, { recursive: true, force: true });
    } catch {
      /* a hidden leftover; the next install removes it */
    }
  };
  try {
    deps.fs.rmSync(old, { recursive: true, force: true });
  } catch {
    /* if it is still there, the move aside below fails and says so */
  }
  const hadOld = lexists(appDir, deps);
  if (hadOld) {
    try {
      deps.fs.renameSync(appDir, old);
    } catch (e) {
      dropStaged();
      throw new UserError(`Could not move the current Uoink.app aside to replace it (${reason(e)}). Your current Uoink was not changed. Quit Uoink and try again.`);
    }
  }
  try {
    deps.fs.renameSync(staged, appDir);
  } catch (e) {
    let restored = !hadOld;
    if (hadOld) {
      try {
        deps.fs.renameSync(old, appDir);
        restored = true;
      } catch {
        /* reported below */
      }
    }
    dropStaged();
    if (!restored) {
      throw new UserError(
        `Could not move the new Uoink.app into place (${reason(e)}), and could not put the current one back.\n` +
          `Your current Uoink is at ${old}\nTo put it back, run: mv "${old}" "${appDir}"`
      );
    }
    throw new UserError(
      `Could not move the new Uoink.app into place (${reason(e)}). ` +
        (hadOld ? 'Your current Uoink was put back unchanged. Quit Uoink and try again.' : 'Try again.')
    );
  }
  if (hadOld) {
    try {
      deps.fs.rmSync(old, { recursive: true, force: true });
    } catch (e) {
      ui.warn(`Uoink is updated, but the previous copy could not be removed (${reason(e)}). You can delete ${old}`);
    }
  }
}

async function installMac(file, tmp, deps, ui, appDir = macDestination(deps)) {
  if (Number.parseInt(deps.osRelease, 10) < 24) {
    throw new UserError('Uoink needs macOS 15 or newer.');
  }
  const mnt = path.join(tmp, 'mnt');
  deps.fs.mkdirSync(mnt, { recursive: true });
  ui.say('Opening the disk image...');
  const att = await deps.capture('/usr/bin/hdiutil', ['attach', '-nobrowse', '-readonly', '-noautoopen', '-mountpoint', mnt, file]);
  if (att.code !== 0) throw new UserError(`Could not open the disk image: ${att.stderr.trim() || `hdiutil exit ${att.code}`}`);
  try {
    const src = path.join(mnt, 'Uoink.app');
    if (!deps.fs.existsSync(src)) throw new UserError('Uoink.app was not found inside the disk image.');
    const destDir = path.dirname(appDir);
    deps.fs.mkdirSync(destDir, { recursive: true });
    const staged = path.join(destDir, '.Uoink.app.new');
    deps.fs.rmSync(staged, { recursive: true, force: true });
    ui.say(`Copying Uoink to ${destDir}...`);
    const cpy = await deps.capture('/usr/bin/ditto', [src, staged]);
    if (cpy.code !== 0) {
      deps.fs.rmSync(staged, { recursive: true, force: true });
      throw new UserError(`Copy failed: ${cpy.stderr.trim() || `ditto exit ${cpy.code}`}`);
    }
    try {
      await stopMacHelper(appDir, deps, ui);
    } catch (e) {
      try {
        deps.fs.rmSync(staged, { recursive: true, force: true });
      } catch {
        /* Preserve the quit instruction if cleanup also fails. */
      }
      throw e;
    }
    swapIntoPlace(staged, appDir, deps, ui);
  } finally {
    let d = await deps.capture('/usr/bin/hdiutil', ['detach', mnt]);
    if (d.code !== 0) d = await deps.capture('/usr/bin/hdiutil', ['detach', '-force', mnt]);
  }
  return appDir;
}

function linkMacCli(appDir, deps, ui) {
  const helper = path.join(appDir, 'Contents', 'Helpers', 'uoink');
  const onPath = pathDirs(deps);
  const candidates = [path.join(deps.homedir, '.local', 'bin'), '/opt/homebrew/bin', '/usr/local/bin'];
  for (const dir of candidates) {
    if (!onPath.includes(dir) || !deps.fs.existsSync(dir) || !writable(dir, deps)) continue;
    const link = path.join(dir, 'uoink');
    try {
      let st = null;
      try {
        st = deps.fs.lstatSync(link);
      } catch {
        /* no existing file */
      }
      if (st) {
        if (!st.isSymbolicLink() || !/Uoink\.app/.test(deps.fs.readlinkSync(link))) continue;
        deps.fs.unlinkSync(link);
      }
      deps.fs.symlinkSync(helper, link);
      ui.say(`Linked the uoink command at ${link}`);
      return;
    } catch {
      /* try the next folder */
    }
  }
  ui.say(`The uoink command is at ${helper}`);
  ui.say(`To use it as "uoink", run: mkdir -p ~/.local/bin && ln -s "${helper}" ~/.local/bin/uoink`);
}

// ---------- flows ----------

async function installFlow(opts, deps, ui) {
  const target = await installTarget(deps);
  const before = target.exists ? await targetStatus(target, deps) : { version: null, status: null };
  if (target.exists && opts.command === 'install' && !opts.version) {
    ui.say(`Uoink ${before.version || '(version unknown)'} is already installed. Use "npx uoink update" to get a newer version.`);
    return 0;
  }
  const plan = await resolvePlan(opts, deps);
  const order = before.version ? cmpVersion(plan.version, before.version) : null;
  if (order !== null && order < 0 && !opts.allowDowngrade) {
    ui.say(`Your installed Uoink ${before.version} is newer than the offered version ${plan.version}. Keeping your copy.`);
    ui.say(`To go back to ${plan.version} anyway, run: npx uoink install --version ${plan.version} --allow-downgrade`);
    return opts.version ? 1 : 0;
  }
  if (opts.command === 'update' && !opts.version && order === 0) {
    ui.say(`Uoink ${before.version} is installed and up to date (latest is ${plan.version}).`);
    return 0;
  }
  const where = target.dir;
  const big = deps.platform === 'win32' ? 'about 550 MB' : 'about 515 MB';
  const action = planAction(plan.version, target.exists, before.version, order);

  if (opts.dryRun) {
    ui.say(bannerPlan(ui, plan, where, big, action));
    if (target.exists && order === null && !opts.allowDowngrade) {
      ui.say('Replacing this copy requires --allow-downgrade.');
    }
    ui.say('');
    ui.say('Dry run: nothing was downloaded or installed.');
    return 0;
  }

  ui.say(bannerPlan(ui, plan, where, big, action));
  if (target.exists && order === null && !opts.allowDowngrade) {
    ui.fail('The installed version is unknown. To replace this copy, run again with --allow-downgrade.');
    return 1;
  }
  ui.say('');
  if (!opts.yes) {
    if (!deps.isTTY) {
      ui.fail('This needs your confirmation, but there is no terminal to ask in. Run again with --yes to continue.');
      return 1;
    }
    const a = String(await deps.ask('Continue? [y/N] ')).trim().toLowerCase();
    if (a !== 'y' && a !== 'yes') {
      ui.say('Cancelled. Nothing was downloaded.');
      return opts.version ? 1 : 0;
    }
  }

  let tmp;
  try {
    tmp = deps.fs.mkdtempSync(path.join(deps.tmpRoot, 'uoink-'));
  } catch (e) {
    throw e;
  }
  try {
    const file = path.join(tmp, plan.name);
    const prog = makeProgress(deps, ui);
    prog.start(plan.name);
    const source = await chooseSource(plan, deps, ui);
    await net.download(source, file, {
      ...deps.netOpts,
      headers: { 'user-agent': userAgent(deps) },
      sleep: deps.sleep,
      spaceDir: tmp,
      freeBytes: deps.freeBytes,
      onProgress: prog.update,
      onRetry: (n, max) => ui.warn(`  Connection dropped. Resuming (${n} of ${max})...`),
    });
    ui.warn('Verifying SHA-256...');
    const got = await net.sha256File(file);
    if (got !== plan.sha) {
      deps.fs.rmSync(file, { force: true });
      ui.fail(`SHA-256 mismatch for ${plan.name}.\n  expected ${plan.sha}\n  got      ${got}\nThe download was deleted and nothing was installed. Try again, and if it repeats, report it at https://github.com/${REPO}/issues`);
      return 1;
    }
    ui.say('Checksum matches the official SHA256SUMS.txt.');

    // Sample the listening port just before setup makes its restart decision.
    const previous = await deps.helperHealth(3000, true).catch(() => null);
    const oldRecovery = recoveryState(target, deps);
    const stopped = target.hasHelper && before.status?.helper_running === false && previous?.listening === false;
    if (plan.kind === 'exe') await installWindows(file, deps, ui, target.dir);
    else await installMac(file, tmp, deps, ui, target.dir);
    const deadline = deps.now() + HELPER_START_WAIT_MS;
    deps.fs.rmSync(file, { force: true });
    if (plan.kind === 'dmg') linkMacCli(target.dir, deps, ui);
    return await afterInstall(opts, deps, ui, plan, target, { previous, oldRecovery, stopped }, deadline);
  } finally {
    deps.fs.rmSync(tmp, { recursive: true, force: true });
  }
}

// What this run does to the installed copy, in words for the banner.
// order is cmpVersion(offered, installed), or null when either is unknown.
function planAction(version, installed, installedVersion, order) {
  if (!installed) return { kind: 'install', title: `Install Uoink ${version}` };
  if (order === null) {
    return { kind: 'unknown', title: `Install Uoink ${version} over your current copy (its version could not be read)` };
  }
  if (order > 0) return { kind: 'update', title: `Update Uoink to ${version} (you have ${installedVersion})` };
  if (order === 0) return { kind: 'reinstall', title: `Reinstall Uoink ${version} (the version you have)` };
  return {
    kind: 'downgrade',
    title: `Downgrade Uoink to ${version} (you have ${installedVersion})`,
    note: `Your library stays in place. An older Uoink may not understand changes ${installedVersion} made to it.`,
  };
}

function bannerPlan(ui, plan, where, big, action) {
  const lines = [
    `${ui.bold(action.title)}`,
    ...(action.note ? [`  ${action.note}`] : []),
    `  Downloads ${plan.name} (${big}) from GitHub, checks its SHA-256 against the release's SHA256SUMS.txt,`,
    `  then runs the official installer. Installs to ${where}.`,
    `  Needs about twice the download size free in your temp folder while it works.`,
    `  ${ui.dim(`Installer: ${plan.counterUrl || plan.url}`)}`,
    `  ${ui.dim(`Checksums: ${plan.sumsUrl}`)}`,
  ];
  return lines.join('\n');
}

function recoveryState(target, deps) {
  try {
    return JSON.parse(deps.fs.readFileSync(path.join(target.data, 'helper-recovery.json'), 'utf8')) || {};
  } catch {
    return {};
  }
}

function isNewHelper(health, target, before, deps) {
  const { pid, supervisor_run_id: run } = health;
  if (!Number.isSafeInteger(pid) || pid <= 0 || typeof run !== 'string' || !run) return false;
  const previous = before.oldRecovery;
  if (run === before.previous?.supervisor_run_id || run === previous.supervisor_run_id ||
      (pid === previous.helper_pid && !previous.supervisor_run_id)) return false;
  const state = recoveryState(target, deps);
  if (state.helper_pid !== pid) return false;
  const inheritedRunId = state.supervisor_run_id === previous.supervisor_run_id && pid !== previous.helper_pid;
  if (state.supervisor_run_id && !inheritedRunId) {
    if (state.supervisor_run_id !== run) return false;
  } else if (state.status !== 'running' || !state.ready_at) {
    // Older supervisors only publish "running" after checking this child's
    // PID and run ID twice. They may carry an unused run ID across a downgrade.
    return false;
  }
  try {
    if (target.inst.kind === 'win') {
      return Number(deps.fs.readFileSync(path.join(target.dir, 'server.pid'), 'utf8').trim()) === pid;
    }
    const identity = JSON.parse(deps.fs.readFileSync(path.join(target.data, 'runtime-identity.json'), 'utf8'));
    const script = path.join(target.resources, 'server.py');
    return identity.pid === pid && (identity.script === script ||
      (realPath(script, deps) !== null && realPath(script, deps) === realPath(identity.script, deps)));
  } catch {
    return false;
  }
}

function remaining(deps, deadline) {
  return Math.max(0, Math.ceil(deadline - deps.now()));
}

async function waitForHelper(deps, version, target, before, deadline) {
  let mismatch;
  while (remaining(deps, deadline) > 0) {
    const health = await deps.helperHealth(Math.min(5000, remaining(deps, deadline))).catch(() => null);
    if (health?.ok === true) {
      if (health.version !== version) {
        if (knownVersion(health.version)) mismatch = `the helper reports version ${health.version}. Expected ${version}.`;
      } else if (isNewHelper(health, target, before, deps) && deps.now() <= deadline) {
        return null;
      } else {
        mismatch = 'the responding helper could not be matched to this launch.';
      }
    }
    await deps.sleep(Math.min(1000, remaining(deps, deadline)));
  }
  return mismatch || 'its helper did not answer within 90 seconds.';
}

function startupFailure(ui, version, where, why) {
  ui.fail(`Uoink ${version} is installed, but ${why}\n` +
    `  Open Uoink from ${where} to start it.\n` +
    '  For local diagnostics, run: npx uoink serve doctor\n' +
    `  If you file an issue at https://github.com/${REPO}/issues, include the installer error and Uoink version.`);
  return 1;
}

async function afterInstall(opts, deps, ui, plan, target, before, deadline) {
  const mac = plan.kind === 'dmg';
  const where = mac ? 'Applications' : 'the Start menu';
  ui.say('');
  if (mac) {
    ui.say(`Uoink ${plan.version} is installed. Starting it and waiting for it to answer...`);
    const opened = await deps.capture('/usr/bin/open', ['-a', target.dir],
      { timeoutMs: Math.max(1, Math.min(MAC_HELPER_WAIT_MS, remaining(deps, deadline))) })
      .catch(error => ({ code: 1, stderr: error.message }));
    if (opened.code !== 0) {
      return startupFailure(ui, plan.version, where, `macOS could not open the app (${opened.stderr?.trim() || 'exit ' + opened.code}).`);
    }
  }
  let installed;
  do {
    const budget = remaining(deps, deadline);
    if (!budget) break;
    installed = await targetStatus(target, deps, budget);
    if (installed.version && installed.version !== plan.version) {
      ui.fail(`The installer finished, but the installed Uoink still reports version ${installed.version}, not ${plan.version}.\n` +
        `  Quit Uoink from the ${mac ? 'menu bar' : 'tray icon'} and run the same command again. Open Uoink from ${where} to start it.\n` +
        '  For local diagnostics, run: npx uoink serve doctor');
      return 1;
    }
    if (!mac || installed.status?.helper_running === true) break;
    await deps.sleep(Math.min(500, remaining(deps, deadline)));
  } while (remaining(deps, deadline));
  if (!mac && before.stopped && installed?.status?.helper_running !== true) {
    if (installed?.version !== plan.version) {
      ui.fail(`The installer finished, but the installed version could not be verified. Expected ${plan.version}.`);
      return 1;
    }
    ui.say(`Uoink ${plan.version} is installed.`);
    ui.say('Uoink was not running before, so it was left stopped. Open Uoink from the Start menu to start it.');
  } else {
    const failure = await waitForHelper(deps, plan.version, target, before, deadline);
    if (failure) return startupFailure(ui, plan.version, where, failure);
    ui.say(`Started Uoink ${plan.version}${mac ? ' (it runs in the menu bar)' : ''}.`);
  }
  if (!mac) ui.say('Open a new terminal so the uoink command is on your PATH.');
  const hintBudget = remaining(deps, deadline);
  if (!opts.noConnect && hintBudget > 0) {
    ui.say('');
    ui.say(ui.bold('Connect your AI agent'));
    const inv = cliInvocation(target.inst);
    const r = await deps.capture(inv.cmd, [...inv.args, 'connect', '--list'],
      { env: inv.env, timeoutMs: hintBudget });
    if (r.code === 0 && r.stdout.trim()) ui.say(r.stdout.trimEnd());
    ui.say('Pick one and run, for example: npx uoink connect claude-code');
    ui.say(`More: ${CONNECT_DOCS}`);
  }
  return 0;
}

async function passthrough(inst, args, deps) {
  const inv = cliInvocation(inst);
  const r = await deps.run(inv.cmd, [...inv.args, ...args], { env: inv.env });
  if (r.error) throw new UserError(`Could not run ${inv.cmd}: ${r.error.message}`);
  return r.code;
}

// ---------- main ----------

async function main(argv, injected = {}) {
  const deps = { ...defaultDeps(), ...injected };
  const ui = makeUi(deps);
  try {
    // Installed: everything except our own commands goes to the CLI.
    const own = isOwnInvocation(argv);
    const inst = findInstalled(deps);
    if (inst && !own) {
      if (deps.env[LAUNCHER_ENV]) {
        ui.fail(
          `stopped to avoid a loop. This npx uoink was started by another npx uoink (${LAUNCHER_ENV} is set), so it will not run ${inst.cli} again.\n` +
            'If that file is the npm package and not the Uoink app, remove it with "npm uninstall -g uoink" and try again.'
        );
        return 1;
      }
      return await passthrough(inst, argv, deps);
    }

    if (!own) {
      ui.fail('Uoink is not installed yet, so there is no CLI to run. Install it first with: npx uoink');
      return 1;
    }
    const opts = parseOwnArgs(argv);
    if (opts.help) {
      ui.say(HELP);
      return 0;
    }
    if (opts.versionFlag) {
      ui.say(`uoink npm installer ${PKG_VERSION}`);
      return 0;
    }

    if (inst && !opts.command && !opts.version) {
      const { version } = await installedVersion(inst, deps);
      ui.say(`Uoink ${version || '(version unknown)'} is installed.`);
      ui.say('Run: npx uoink update      to check for a newer version');
      ui.say('     npx uoink <command>   to use the CLI, e.g. npx uoink connect --list');
      return 0;
    }
    if (!pickable(deps)) {
      ui.say(unsupportedMessage(deps.platform, deps.arch));
      return opts.version ? 1 : 0;
    }
    return await installFlow(opts, deps, ui);
  } catch (e) {
    ui.fail(explainError(e, deps));
    return 1;
  }
}

function pickable(deps) {
  return assetFor(deps.platform, deps.arch, '0.0.0') !== null;
}

module.exports = {
  main,
  pickAsset,
  assetFor,
  cmpVersion,
  planAction,
  HELPER_PORT,
  HELPER_START_WAIT_MS,
  findInstalled,
  parseOwnArgs,
  isOwnInvocation,
  unsupportedMessage,
  installMac,
  defaultDeps,
  makeUi,
  LAUNCHER_ENV,
  PKG_DIR,
  PKG_VERSION,
  BASE,
};
