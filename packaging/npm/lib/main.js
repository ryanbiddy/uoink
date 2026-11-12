'use strict';
// npx uoink: install Uoink (download, verify, install, set up) or pass
// arguments to the installed CLI. Everything with side effects is behind the
// `deps` object so tests can inject fakes.

const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const cp = require('node:child_process');
const readline = require('node:readline');
const net = require('./net.js');

const REPO = 'ryanbiddy/uoink';
const BASE = `https://github.com/${REPO}/releases`;
const LINUX_DOCS = `https://github.com/${REPO}/blob/main/docs/linux.md`;
const MAC_DOCS = `https://github.com/${REPO}/blob/main/docs/mac/INSTALL.md`;
const CONNECT_DOCS = `https://github.com/${REPO}/blob/main/docs/connect-your-agent.md`;
const PKG_VERSION = require('../package.json').version;

const HELP = `uoink: install Uoink, or run the installed Uoink CLI

Usage
  npx uoink                    install Uoink (asks first), or show the installed version
  npx uoink update             install the latest version if it is newer
  npx uoink <command> ...      run the installed CLI, e.g. connect claude-code, search "..."

Options (install and update only)
  --yes             skip the confirmation question
  --dry-run         print the plan and URLs, download nothing
  --version <v>     install a specific version, e.g. 3.16.3
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

// Find the asset for this platform in a parsed SHA256SUMS map. Returns
// { name, kind, version, sha } or null.
function pickAsset(platform, arch, sums) {
  let re;
  let kind;
  if (platform === 'win32' && arch === 'x64') {
    re = /^Uoink-Setup-(\d+\.\d+\.\d+)\.exe$/;
    kind = 'exe';
  } else if (platform === 'darwin' && arch === 'arm64') {
    re = /^Uoink-(\d+\.\d+\.\d+)-macos-arm64\.dmg$/;
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
  const pa = a.split('.').map(Number);
  const pb = b.split('.').map(Number);
  for (let i = 0; i < 3; i++) {
    const d = (pa[i] || 0) - (pb[i] || 0);
    if (d) return d < 0 ? -1 : 1;
  }
  return 0;
}

// ---------- finding an installed Uoink ----------

function isExecutableFile(p, deps) {
  try {
    return deps.fs.statSync(p).isFile();
  } catch {
    return false;
  }
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
    if (env.LOCALAPPDATA) add(path.win32.join(env.LOCALAPPDATA, 'Uoink', 'cli', 'uoink.cmd'));
    for (const d of pathDirs.filter(notOurs)) add(path.win32.join(d, 'uoink.cmd'));
    for (const c of cands) {
      if (!isExecutableFile(c, deps)) continue;
      const root = path.win32.resolve(path.win32.dirname(c), '..');
      const python = path.win32.join(root, 'python', 'python.exe');
      const script = path.win32.join(root, 'uoink_cli.py');
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
  for (const c of cands) if (isExecutableFile(c, deps)) return { kind: 'posix', cli: c };
  return null;
}

function cliInvocation(inst) {
  if (inst.kind === 'win') return { cmd: inst.python, args: [inst.script], env: { PYTHONIOENCODING: 'utf-8', PYTHONUTF8: '1' } };
  return { cmd: inst.cli, args: [], env: {} };
}

async function installedVersion(inst, deps) {
  const inv = cliInvocation(inst);
  try {
    const r = await deps.capture(inv.cmd, [...inv.args, 'status'], { env: inv.env });
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
    stdout: out,
    stderr: err,
    isTTY: Boolean(process.stdin.isTTY && err.isTTY),
    sleep: (ms) => new Promise((r) => setTimeout(r, ms)),
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
        const c = cp.spawn(cmd, args, { stdio: 'inherit', env: { ...process.env, ...(opts.env || {}) }, windowsHide: false });
        c.on('error', (e) => resolve({ code: -1, error: e }));
        c.on('exit', (code, sig) => resolve({ code: code === null ? 128 : code, signal: sig }));
      }),
    capture: (cmd, args, opts = {}) =>
      new Promise((resolve) => {
        cp.execFile(
          cmd,
          args,
          { env: { ...process.env, ...(opts.env || {}) }, maxBuffer: 16 * 1024 * 1024, timeout: opts.timeoutMs ?? 60000, windowsHide: true },
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
  const o = { yes: false, dryRun: false, noConnect: false, help: false, version: null, versionFlag: false, command: null };
  const rest = [...argv];
  if (rest[0] === 'update' || rest[0] === 'install') o.command = rest.shift();
  while (rest.length) {
    const a = rest.shift();
    if (a === '--yes' || a === '-y') o.yes = true;
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
    if (!/^\d+\.\d+\.\d+$/.test(v)) throw new UserError(`"${o.version}" is not a version like 3.16.3.`);
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
  return { ...asset, sumsUrl, url: `${dl}/${asset.name}` };
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
    deps.fs.rmSync(appDir, { recursive: true, force: true });
    deps.fs.renameSync(staged, appDir);
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
  if (ctx.onlyIfNewer && ctx.installedVersion && cmpVersion(plan.version, ctx.installedVersion) <= 0) {
    ui.say(`Uoink ${ctx.installedVersion} is installed and up to date (latest is ${plan.version}).`);
    return 0;
  }
  const where = deps.platform === 'win32' ? '%LOCALAPPDATA%\\Uoink (per user, no admin needed)' : '/Applications/Uoink.app (or ~/Applications if /Applications is not writable)';
  const big = deps.platform === 'win32' ? 'about 550 MB' : 'about 515 MB';

  if (opts.dryRun) {
    ui.say(bannerPlan(ui, plan, where, big, installed));
    ui.say('');
    ui.say('Dry run: nothing was downloaded or installed.');
    return 0;
  }

  ui.say(bannerPlan(ui, plan, where, big, installed));
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
    await net.download(plan.url, file, {
      ...deps.netOpts,
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
    await afterInstall(opts, deps, ui, plan, appDir);
    return 0;
  } finally {
    deps.fs.rmSync(tmp, { recursive: true, force: true });
  }
}

function bannerPlan(ui, plan, where, big, installed) {
  const lines = [
    `${ui.bold(installed ? `Update Uoink to ${plan.version}` : `Install Uoink ${plan.version}`)}`,
    `  Downloads ${plan.name} (${big}) from GitHub, checks its SHA-256 against the release's SHA256SUMS.txt,`,
    `  then runs the official installer. Installs to ${where}.`,
    `  Needs about twice the download size free in your temp folder while it works.`,
    `  ${ui.dim(`Installer: ${plan.url}`)}`,
    `  ${ui.dim(`Checksums: ${plan.sumsUrl}`)}`,
  ];
  return lines.join('\n');
}

async function afterInstall(opts, deps, ui, plan, appDir) {
  const inst = findInstalled(deps) || (appDir ? { kind: 'posix', cli: path.join(appDir, 'Contents', 'Helpers', 'uoink') } : null);
  if (!inst) {
    ui.say('');
    ui.say(`Uoink ${plan.version} is installed. Open a new terminal so the uoink command is on your PATH.`);
    return;
  }
  const { version, status } = await installedVersion(inst, deps);
  ui.say('');
  ui.say(version ? `Uoink ${version} is installed.` : `Uoink ${plan.version} is installed.`);
  if (status && status.helper_running === false) {
    if (deps.platform === 'darwin') {
      await deps.capture('/usr/bin/open', ['-a', appDir ? path.dirname(path.dirname(path.dirname(inst.cli))) : 'Uoink']);
      ui.say('Started Uoink (it runs in the menu bar).');
    } else {
      ui.say('Open Uoink from the Start menu to start it.');
    }
  }
  if (deps.platform === 'win32') ui.say('Open a new terminal so the uoink command is on your PATH.');
  if (!opts.noConnect) {
    ui.say('');
    ui.say(ui.bold('Connect your AI agent'));
    const inv = cliInvocation(inst);
    const r = await deps.capture(inv.cmd, [...inv.args, 'connect', '--list'], { env: inv.env });
    if (r.code === 0 && r.stdout.trim()) ui.say(r.stdout.trimEnd());
    ui.say('Pick one and run, for example: npx uoink connect claude-code');
    ui.say(`More: ${CONNECT_DOCS}`);
  }
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
    if (inst && !own) return await passthrough(inst, argv, deps);

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
      const { version } = await installedVersion(inst, deps);
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

module.exports = { main, pickAsset, assetFor, cmpVersion, findInstalled, parseOwnArgs, isOwnInvocation, unsupportedMessage, PKG_VERSION, BASE };
