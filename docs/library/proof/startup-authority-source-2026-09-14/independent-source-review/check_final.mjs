// Passive text/hash comparison only. No subject imports or writes.
import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { resolve, sep } from 'node:path';
const root = 'E:/AI/projects/uoink/checkouts/Yoink-library';
const base = resolve(root, '_scratch/real-startup-authority-repair01');
function need(v, message) { if (!v) throw Error(message); }
function read(relative, parent = base) {
  const path = resolve(parent, relative);
  need(path.startsWith(resolve(parent) + sep), 'relative text path required');
  need(/\.(py|txt|json|md|diff)$/.test(path), 'fixed text extension required');
  return readFileSync(path);
}
const hash = bytes => createHash('sha256').update(bytes).digest('hex');
const mapBytes = read('SOURCE-INPUTS.json');
need(hash(mapBytes) === '23591b4c9fd6d18ee9856c5abb9329ce926ab49553c72bb20b1eaaf8a549d775', 'frozen map');
const map = JSON.parse(mapBytes);
need(map.original_inputs.length === 9 && map.derivatives.length === 12, 'fixed membership');
for (const row of map.original_inputs) {
  const original = read(row.source, root), copy = read(row.copy);
  need(original.length === row.bytes && hash(original) === row.sha256 && original.equals(copy), 'original/copy binding: ' + row.copy);
}
for (const row of map.derivatives) {
  const bytes = read(row.path);
  need(bytes.length === row.bytes && hash(bytes) === row.sha256, 'derivative binding: ' + row.path);
}
const final = read('asr_loading_adapter.py'), baseline = read('before/asr_loading_adapter.py');
need(final.subarray(0, baseline.length).equals(baseline) && baseline.length === 12113, 'exact qualified prefix');
need(final.subarray(baseline.length).equals(read('startup_addition.py.txt')), 'exact addition');
const lines = bytes => bytes.toString('utf8').replaceAll('\r\n', '\n').split('\n');
function reconstruct(beforeName, diffName, afterName) {
  const before = lines(read(beforeName)), after = lines(read(afterName));
  const patch = lines(read(diffName));
  need(patch[0].startsWith('--- ') && patch[1].startsWith('+++ '), 'patch headers');
  let i = 2, oldPos = 0, newPos = 0, hunks = 0;
  const forward = [], reverse = [];
  while (i < patch.length && patch[i] !== '') {
    const match = /^@@ -(\d+),(\d+) \+(\d+),(\d+) @@$/.exec(patch[i++]);
    need(match, 'explicit hunk header');
    const oldStart = Number(match[1]) - 1, newStart = Number(match[3]) - 1;
    forward.push(...before.slice(oldPos, oldStart)); reverse.push(...after.slice(newPos, newStart));
    oldPos = oldStart; newPos = newStart; let oldCount = 0, newCount = 0;
    while (i < patch.length && !patch[i].startsWith('@@ ') && patch[i] !== '') {
      const line = patch[i++], tag = line[0], text = line.slice(1);
      need([' ', '-', '+'].includes(tag), 'patch body');
      if (tag !== '+') { need(before[oldPos++] === text, 'old body'); oldCount++; reverse.push(text); }
      if (tag !== '-') { need(after[newPos++] === text, 'new body'); newCount++; forward.push(text); }
    }
    need(oldCount === Number(match[2]) && newCount === Number(match[4]), 'hunk counts'); hunks++;
  }
  need(patch.slice(i).every(line => line === ''), 'patch trailing content');
  forward.push(...before.slice(oldPos)); reverse.push(...after.slice(newPos));
  need(forward.join('\n') === after.join('\n') && reverse.join('\n') === before.join('\n'), 'complete forward/reverse reconstruction');
  return { diff: diffName, hunks, forward: true, reverse: true, comparison: 'complete LF-normalized text' };
}
const patches = [
  reconstruct('before/asr_loading_adapter.py', 'asr_loading_adapter.diff', 'asr_loading_adapter.py'),
  reconstruct('before/asr_loading_adapter-before-consume01.py', 'review-corrections.diff', 'asr_loading_adapter.py')
];
console.log(JSON.stringify({scope:'passive text only',status:'PASS',source_sha256:hash(final),source_bytes:final.length,map_sha256:hash(mapBytes),original_copy_pairs:9,derivative_rows:12,exact_prefix_bytes:baseline.length,addition_exact:true,patches}, null, 2));
