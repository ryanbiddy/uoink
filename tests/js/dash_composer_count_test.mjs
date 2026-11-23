// The writing composer counts like X: every link is 23 characters, the rest
// are Unicode code points. Same rule as the helper's own check
// (writing_studio.tweet_length, used by POST /writing/compose/validate).
// Run: node tests/js/dash_composer_count_test.mjs
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

const html = readFileSync('assets/dashboard/index.html', 'utf8');
const server = readFileSync('writing_studio.py', 'utf8');
const start = html.indexOf('const X_URL_WEIGHTED_LENGTH');
const end = html.indexOf('function splitDraftIntoTweets(');
assert.ok(start > 0 && end > start, 'composer counter not found in the dashboard');
const context = vm.createContext({});
vm.runInContext(html.slice(start, end) + '\nthis.tweetLength = tweetLength;', context);
const {tweetLength} = context;

// One weight on both sides.
const serverWeight = Number(/^URL_WEIGHTED_LEN = (\d+)$/m.exec(server)[1]);
assert.equal(vm.runInContext('X_URL_WEIGHTED_LENGTH', context), serverWeight);
assert.equal(serverWeight, 23);
assert.match(server, /^_URL_RE = re\.compile\(r"https\?:\/\/\\S\+"\)$/m,
  'the helper changed its link rule: update the dashboard counter to match');

const longUrl = 'https://example.com/' + 'a'.repeat(80);
const cases = [
  ['', 0],
  ['hello', 5],
  [longUrl, 23],
  [`read this ${longUrl} now`, 'read this '.length + 23 + ' now'.length],
  ['two http://a.test/x and https://b.test/' + 'y'.repeat(60), 'two '.length + 23 + ' and '.length + 23],
  ['a 👍🏽 and é', Array.from('a 👍🏽 and é').length],  // code points, like Python len()
  [`${longUrl}\n${longUrl}`, 23 + 1 + 23],
];
for (const [text, expected] of cases) {
  assert.equal(tweetLength(text), expected, JSON.stringify(text).slice(0, 60));
}
// The bug: a 280-character tweet with a long link must not read as over 280.
const tweet = 'x'.repeat(250) + ' ' + longUrl;
assert.equal(tweet.length > 280, true);
assert.equal(tweetLength(tweet), 250 + 1 + 23);
console.log('PASS: composer counts links as 23 characters, matching the helper');
