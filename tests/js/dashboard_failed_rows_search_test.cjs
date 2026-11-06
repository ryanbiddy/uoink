// A failed capture row obeys the Library search; running captures stay.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const page = fs.readFileSync(require('node:path').join(__dirname, '../../assets/dashboard/index.html'), 'utf8');
const start = page.indexOf('    function captureRowsForQuery(');
const code = page.slice(start, page.indexOf('    function libraryCaptureItems()'));
const context = vm.createContext({});
vm.runInContext(code, context);
const rows = [
  { title: 'https://x.com/i/status/xxxxxxxxxx0', source: 'X', detail: 'Could not fetch', tone: 'fail' },
  { title: 'Pressurized rover brief', source: 'YouTube', detail: 'Could not fetch', tone: 'fail' },
  { title: 'Something running', source: 'YouTube', detail: '', tone: 'now' },
];
const keep = (q) => context.captureRowsForQuery(rows, q).map(r => r.title);
assert.equal(keep('').length, 3);
assert.deepEqual(keep('pressurized rover'), ['Pressurized rover brief', 'Something running']);
assert.deepEqual(keep('  '), rows.map(r => r.title));
assert.match(page, /return captureRowsForQuery\(items, state\.filters && state\.filters\.q\)/);
console.log('ok');
