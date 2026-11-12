'use strict';
// Network helpers: HTTPS only, redirects only to an allowlist, Range resume,
// SHA-256 verification. No dependencies.

const fs = require('node:fs');
const https = require('node:https');
const http = require('node:http');
const crypto = require('node:crypto');
const { Transform } = require('node:stream');
const { pipeline } = require('node:stream/promises');

const DEFAULT_HOSTS = [
  'github.com',
  'objects.githubusercontent.com',
  'release-assets.githubusercontent.com',
  'usage.uoink.app',
];

class HttpError extends Error {
  constructor(status, url) {
    super(`HTTP ${status} from ${url}`);
    this.name = 'HttpError';
    this.status = status;
    this.url = url;
  }
}

class SecurityError extends Error {
  constructor(message) {
    super(message);
    this.name = 'SecurityError';
  }
}

class DiskSpaceError extends Error {
  constructor(needed, free) {
    super(`Not enough free disk space: need about ${formatBytes(needed)}, have ${formatBytes(free)}.`);
    this.name = 'DiskSpaceError';
    this.needed = needed;
    this.free = free;
  }
}

function formatBytes(n) {
  if (n >= 1e9) return `${(n / 1e9).toFixed(1)} GB`;
  if (n >= 1e6) return `${Math.round(n / 1e6)} MB`;
  return `${Math.max(1, Math.round(n / 1e3))} KB`;
}

// Throws SecurityError unless the URL is https (or http for an injected test
// config) and its host is on the allowlist.
function checkUrl(raw, opts = {}) {
  let u;
  try {
    u = new URL(raw);
  } catch {
    throw new SecurityError(`Refusing an invalid URL: ${raw}`);
  }
  const hosts = opts.allowedHosts || DEFAULT_HOSTS;
  const schemeOk = u.protocol === 'https:' || (opts.allowHttp === true && u.protocol === 'http:');
  if (!schemeOk) throw new SecurityError(`Refusing a non-HTTPS URL: ${raw}`);
  if (!hosts.includes(u.hostname)) {
    throw new SecurityError(`Refusing to follow a link to ${u.hostname}, which is not on the allowed list.`);
  }
  return u;
}

// One request with manual redirect following. Resolves to { res, url }.
// The caller must consume or destroy res.
function request(rawUrl, opts = {}) {
  const maxRedirects = opts.maxRedirects ?? 6;
  const headers = { 'user-agent': 'uoink-npm-installer', ...(opts.headers || {}) };
  return new Promise((resolve, reject) => {
    const go = (target, left) => {
      let u;
      try {
        u = checkUrl(target, opts);
      } catch (e) {
        reject(e);
        return;
      }
      const mod = u.protocol === 'http:' ? http : https;
      const req = mod.get(u, { headers }, (res) => {
        const status = res.statusCode || 0;
        if ([301, 302, 303, 307, 308].includes(status) && res.headers.location) {
          res.resume();
          if (left <= 0) {
            reject(new Error('Too many redirects.'));
            return;
          }
          go(new URL(res.headers.location, u).toString(), left - 1);
          return;
        }
        resolve({ res, url: u.toString() });
      });
      req.setTimeout(opts.timeoutMs ?? 30000, () => req.destroy(new Error('Connection timed out.')));
      req.on('error', reject);
    };
    go(rawUrl, maxRedirects);
  });
}

// GET url without following redirects and return the validated Location of a
// 3xx answer. Throws on anything else (so callers can fall back).
function firstRedirect(rawUrl, opts = {}) {
  return new Promise((resolve, reject) => {
    let u;
    try {
      u = checkUrl(rawUrl, opts);
    } catch (e) {
      reject(e);
      return;
    }
    const mod = u.protocol === 'http:' ? http : https;
    const req = mod.get(u, { headers: { 'user-agent': 'uoink-npm-installer', ...(opts.headers || {}) } }, (res) => {
      res.resume();
      const status = res.statusCode || 0;
      if (![301, 302, 303, 307, 308].includes(status) || !res.headers.location) {
        reject(new HttpError(status, u.toString()));
        return;
      }
      try {
        resolve(checkUrl(new URL(res.headers.location, u).toString(), opts).toString());
      } catch (e) {
        reject(e);
      }
    });
    req.setTimeout(opts.timeoutMs ?? 10000, () => req.destroy(new Error('Timed out waiting for a redirect.')));
    req.on('error', reject);
  });
}

async function fetchText(url, opts = {}) {
  const { res, url: finalUrl } = await request(url, opts);
  if ((res.statusCode || 0) >= 400) {
    res.resume();
    throw new HttpError(res.statusCode, finalUrl);
  }
  const chunks = [];
  let size = 0;
  for await (const c of res) {
    size += c.length;
    if (size > 1e6) {
      res.destroy();
      throw new Error('Unexpectedly large response for a text file.');
    }
    chunks.push(c);
  }
  return Buffer.concat(chunks).toString('utf8');
}

// Parse SHA256SUMS.txt lines: "<64 hex>  <name>" (a leading * on the name is allowed).
function parseSums(text) {
  const out = new Map();
  for (const line of text.split(/\r?\n/)) {
    const m = /^([0-9a-fA-F]{64})\s+\*?(\S.*?)\s*$/.exec(line);
    if (m) out.set(m[2], m[1].toLowerCase());
  }
  return out;
}

function sha256File(file) {
  return new Promise((resolve, reject) => {
    const h = crypto.createHash('sha256');
    fs.createReadStream(file)
      .on('error', reject)
      .on('data', (d) => h.update(d))
      .on('end', () => resolve(h.digest('hex')));
  });
}

function freeBytes(dir) {
  try {
    if (typeof fs.statfsSync !== 'function') return null;
    const s = fs.statfsSync(dir);
    return Number(s.bavail) * Number(s.bsize);
  } catch {
    return null;
  }
}

function isFatal(err) {
  return (
    err instanceof HttpError ||
    err instanceof SecurityError ||
    err instanceof DiskSpaceError ||
    (err && (err.code === 'ENOSPC' || err.code === 'EACCES' || err.code === 'EPERM'))
  );
}

// Download url to dest with retry and Range resume. Calls
// onProgress(received, total) and returns the final size.
async function download(url, dest, opts = {}) {
  const retries = opts.retries ?? 5;
  const sleep = opts.sleep || ((ms) => new Promise((r) => setTimeout(r, ms)));
  const onProgress = opts.onProgress || (() => {});
  let got = 0;
  let total = null;
  let spaceChecked = false;
  let attempt = 0;
  for (;;) {
    try {
      const headers = { ...(opts.headers || {}) };
      if (got > 0) headers.range = `bytes=${got}-`;
      const { res, url: finalUrl } = await request(url, { ...opts, headers });
      const status = res.statusCode || 0;
      if (status === 416 && got > 0) {
        res.resume();
        break; // already have every byte
      }
      if (status >= 400) {
        res.resume();
        throw new HttpError(status, finalUrl);
      }
      let append = false;
      if (status === 206 && got > 0) {
        append = true;
        const m = /\/(\d+)$/.exec(res.headers['content-range'] || '');
        if (m) total = Number(m[1]);
      } else {
        got = 0; // server ignored Range (200): start over
        const len = Number(res.headers['content-length']);
        total = Number.isFinite(len) && len > 0 ? len : null;
      }
      if (!spaceChecked && total) {
        const free = (opts.freeBytes || freeBytes)(opts.spaceDir || require('node:path').dirname(dest));
        const needed = total * 2;
        if (free !== null && free < needed) {
          res.destroy();
          throw new DiskSpaceError(needed, free);
        }
        spaceChecked = true;
      }
      const counter = new Transform({
        transform(chunk, _enc, cb) {
          got += chunk.length;
          onProgress(got, total);
          cb(null, chunk);
        },
      });
      await pipeline(res, counter, fs.createWriteStream(dest, { flags: append ? 'a' : 'w' }));
      if (total && got < total) throw new Error('Connection closed early.');
      break;
    } catch (err) {
      if (isFatal(err)) throw err;
      try {
        got = fs.statSync(dest).size;
      } catch {
        got = 0;
      }
      attempt += 1;
      if (attempt > retries) throw err;
      if (opts.onRetry) opts.onRetry(attempt, retries, err);
      await sleep(Math.min(8000, 500 * 2 ** attempt));
    }
  }
  return fs.statSync(dest).size;
}

module.exports = {
  DEFAULT_HOSTS,
  HttpError,
  SecurityError,
  DiskSpaceError,
  checkUrl,
  request,
  fetchText,
  firstRedirect,
  parseSums,
  sha256File,
  freeBytes,
  download,
  formatBytes,
};
