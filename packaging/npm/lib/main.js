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
  --allow-downgrade allow --version to install an older version than you have
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

const VERSION_PATTERN = String.raw`(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?`;
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
    helperHealth: (timeoutMs) =>
      new Promise((resolve) => {
        let done = false;
        const finish = (value) => {
          if (!done) {
            done = true;
            resolve(value);
          }
        };
        const req = http.get({ hostname: '127.0.0.1', port: HELPER_PORT, path: '/health' }, (res) => {
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
        req.on('error', () => finish(null));
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

async function installWindows(file, deps, ui) {
  ui.say('Running the Uoink installer (per user, no admin needed). This can take a minute.');
  const r = await deps.run(file, ['/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/SP-']);
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

async function installMac(file, tmp, deps, ui) {
  if (Number.parseInt(deps.osRelease, 10) < 24) {
    throw new UserError('Uoink needs macOS 15 or newer.');
  }
  const mnt = path.join(tmp, 'mnt');
  deps.fs.mkdirSync(mnt, { recursive: true });
  ui.say('Opening the disk image...');
  const att = await deps.capture('/usr/bin/hdiutil', ['attach', '-nobrowse', '-readonly', '-noautoopen', '-mountpoint', mnt, file]);
  if (att.code !== 0) throw new UserError(`Could not open the disk image: ${att.stderr.trim() || `hdiutil exit ${att.code}`}`);
  let appDir;
  try {
    const src = path.join(mnt, 'Uoink.app');
    if (!deps.fs.existsSync(src)) throw new UserError('Uoink.app was not found inside the disk image.');
    const systemApps = '/Applications';
    const userApps = path.join(deps.homedir, 'Applications');
    let destDir = systemApps;
    if (!writable(systemApps, deps)) {
      destDir = userApps;
      deps.fs.mkdirSync(userApps, { recursive: true });
    }
    appDir = path.join(destDir, 'Uoink.app');
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

async function installFlow(opts, deps, ui, ctx = {}) {
  const plan = await resolvePlan(opts, deps);
  const installed = ctx.installed || null;
  const order = ctx.installedVersion ? cmpVersion(plan.version, ctx.installedVersion) : null;
  if (order !== null && order < 0 && !opts.allowDowngrade) {
    ui.say(`Your installed Uoink ${ctx.installedVersion} is newer than the offered version ${plan.version}. Keeping your copy.`);
    ui.say(`To go back to ${plan.version} anyway, run: npx uoink install --version ${plan.version} --allow-downgrade`);
    return 0;
  }
  if (ctx.onlyIfNewer && order === 0) {
    ui.say(`Uoink ${ctx.installedVersion} is installed and up to date (latest is ${plan.version}).`);
    return 0;
  }
  const where = deps.platform === 'win32' ? '%LOCALAPPDATA%\\Uoink (per user, no admin needed)' : '/Applications/Uoink.app (or ~/Applications if /Applications is not writable)';
  const big = deps.platform === 'win32' ? 'about 550 MB' : 'about 515 MB';
  const action = planAction(plan.version, installed, ctx.installedVersion, order);

  if (opts.dryRun) {
    ui.say(bannerPlan(ui, plan, where, big, action));
    ui.say('');
    ui.say('Dry run: nothing was downloaded or installed.');
    return 0;
  }

  ui.say(bannerPlan(ui, plan, where, big, action));
  ui.say('');
  if (!opts.yes) {
    if (!deps.isTTY) {
      ui.fail('This needs your confirmation, but there is no terminal to ask in. Run again with --yes to continue.');
      return 1;
    }
    const a = String(await deps.ask('Continue? [y/N] ')).trim().toLowerCase();
    if (a !== 'y' && a !== 'yes') {
      ui.say('Cancelled. Nothing was downloaded.');
      return 0;
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

    let appDir = null;
    if (plan.kind === 'exe') await installWindows(file, deps, ui);
    else appDir = await installMac(file, tmp, deps, ui);
    deps.fs.rmSync(file, { force: true });

    if (appDir) linkMacCli(appDir, deps, ui);
    return await afterInstall(opts, deps, ui, plan, appDir, {
      fresh: !installed,
      wasRunning: ctx.installedStatus ? ctx.installedStatus.helper_running : null,
    });
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

// Poll the helper's /health until it reports the wanted version or the
// deadline passes. Each probe is bounded by the time left.
async function waitForHelper(deps, version, deadline) {
  while (deps.now() < deadline) {
    let health = null;
    try {
      health = await deps.helperHealth(Math.max(1, Math.min(5000, Math.ceil(deadline - deps.now()))));
    } catch {
      health = null;
    }
    if (health && health.ok === true && health.version === version) return true;
    const remaining = deadline - deps.now();
    if (remaining <= 0) break;
    await deps.sleep(Math.min(1000, remaining));
  }
  return false;
}

function notStartedMessage(version, where) {
  return (
    `Uoink ${version} is installed, but its helper did not answer within ${HELPER_START_WAIT_MS / 1000} seconds.\n` +
    `  Open Uoink from ${where} to start it.\n` +
    '  If it still does not start, run: npx uoink serve doctor\n' +
    `  and include what it prints in a report at https://github.com/${REPO}/issues`
  );
}

// Returns the exit code: 0 when Uoink is installed and, if it was meant to
// start, its helper answered /health with the new version. 1 otherwise.
async function afterInstall(opts, deps, ui, plan, appDir, before = {}) {
  // Check the bundle just installed, even if another Uoink CLI is on PATH.
  const inst = appDir ? { kind: 'posix', cli: path.join(appDir, 'Contents', 'Helpers', 'uoink') } : findInstalled(deps);
  if (deps.platform === 'darwin' && appDir) {
    ui.say('');
    ui.say(`Uoink ${plan.version} is installed. Starting it and waiting for it to answer...`);
    const deadline = deps.now() + HELPER_START_WAIT_MS;
    let started = false;
    try {
      const opened = await deps.capture('/usr/bin/open', ['-a', appDir], { timeoutMs: MAC_HELPER_WAIT_MS });
      if (opened.code === 0) {
        started = await waitForMacStatus(inst, deps, deadline,
          ({ version, status }) => version === plan.version && status && status.helper_running === true)
          && await waitForHelper(deps, plan.version, deadline);
      }
    } catch {
      /* The install succeeded, but opening or confirming the helper did not. */
    }
    if (!started) {
      ui.fail(notStartedMessage(plan.version, 'Applications'));
      return 1;
    }
    ui.say(`Started Uoink ${plan.version} (it runs in the menu bar).`);
  } else if (deps.platform === 'win32') {
    const { version } = inst ? await installedVersion(inst, deps) : { version: null };
    if (version && version !== plan.version) {
      ui.fail(
        `The installer finished, but the installed Uoink still reports version ${version}, not ${plan.version}.\n` +
          '  Quit Uoink from the tray icon and run the same command again.'
      );
      return 1;
    }
    ui.say('');
    ui.say(`Uoink ${plan.version} is installed.`);
    // The installer starts the helper on a fresh install, and after an update
    // only when it was running before. A helper that was stopped stays stopped.
    if (before.fresh || before.wasRunning === true) {
      ui.say(`Waiting for Uoink to start (up to ${HELPER_START_WAIT_MS / 1000} seconds)...`);
      if (!await waitForHelper(deps, plan.version, deps.now() + HELPER_START_WAIT_MS)) {
        ui.fail(notStartedMessage(plan.version, 'the Start menu'));
        return 1;
      }
      ui.say(`Started Uoink ${plan.version}.`);
    } else {
      ui.say('Uoink was not running before, so it was left stopped. Open Uoink from the Start menu to start it.');
    }
    ui.say('Open a new terminal so the uoink command is on your PATH.');
  } else {
    ui.say('');
    ui.say(`Uoink ${plan.version} is installed.`);
  }
  if (!opts.noConnect && inst) {
    ui.say('');
    ui.say(ui.bold('Connect your AI agent'));
    const inv = cliInvocation(inst);
    const r = await deps.capture(inv.cmd, [...inv.args, 'connect', '--list'], { env: inv.env });
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

    if (!inst && !pickable(deps)) {
      ui.say(unsupportedMessage(deps.platform, deps.arch));
      return 0;
    }

    if (inst) {
      const { version, status } = await installedVersion(inst, deps);
      if (opts.command !== 'update' && opts.command !== 'install') {
        ui.say(`Uoink ${version || '(version unknown)'} is installed.`);
        ui.say('Run: npx uoink update      to check for a newer version');
        ui.say('     npx uoink <command>   to use the CLI, e.g. npx uoink connect --list');
        return 0;
      }
      if (opts.command === 'install' && !opts.version) {
        ui.say(`Uoink ${version || ''} is already installed. Use "npx uoink update" to get a newer version.`);
        return 0;
      }
      return await installFlow(opts, deps, ui, {
        installed: inst,
        installedVersion: version,
        installedStatus: status,
        onlyIfNewer: opts.command === 'update' && !opts.version,
      });
    }

    if (opts.command === 'update') ui.say('Uoink is not installed yet, so this will install it.');
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
