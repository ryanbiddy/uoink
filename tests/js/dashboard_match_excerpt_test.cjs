// Search highlights mark whole words only.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const page = fs.readFileSync(require('node:path').join(__dirname, '../../assets/dashboard/index.html'), 'utf8');
const start = page.indexOf('    function matchExcerptHtml(');
const code = page.slice(start, page.indexOf('    // Re-haul list row:'));
const context = vm.createContext({ htmlEscape: (v) => String(v).replace(/&/g, '&amp;').replace(/</g, '&lt;') });
vm.runInContext(code, context);
const mark = (text, q) => context.matchExcerptHtml(text, q);

assert.equal(mark('I was upset, so I set up the rover', 'up'), 'I was upset, so I set <mark>up</mark> the rover');
assert.equal(mark('The setup is fine', 'up'), 'The setup is fine');
assert.equal(mark('Evals, then more evals.', 'evals'), '<mark>Evals</mark>, then more <mark>evals</mark>.');
assert.equal(mark("don't stop", "don't"), "<mark>don't</mark> stop");
assert.equal(mark('Pressurized rover', 'pressurized rover'), '<mark>Pressurized</mark> <mark>rover</mark>');
assert.equal(mark('a <b> tag', ''), 'a &lt;b> tag');
// A long passage centers on the first whole-word hit, not on "upset".
const long = `${'upset '.repeat(40)}and then the rover went up the hill ${'x '.repeat(40)}`;
assert.match(mark(long, 'up'), /<mark>up<\/mark> the hill/);
console.log('ok');
