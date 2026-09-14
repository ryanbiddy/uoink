import fs from 'node:fs';
const root='E:/AI/projects/uoink/checkouts/Yoink-library';
const file=root+'/docs/library/ORCHESTRATION-HANDOFF-2026-09-08.md';
const before=fs.readFileSync(file);const text=before.toString('utf8');
const old=`documentation. Control Room run19ac6c2d-eaa3-428a-829c-5dc2a2289a40 is active
from CONTROLLER-RESUME-PUBLICATION-IMPLEMENTATION-BRIEF-2026-09-14.md at frozen
basee0bbbd6. Gemini3.8-flash-high/high uses the existing Antigravity subscription
for source-only work in its fresh worktree. Frozen plan2dfb90f8/map00c3e86b
binds eight sources/227,073 bytes and narrows fixed classification, pre-resume
and actual final-publication checks. Preserve generated routing and all accepted
tests. Native bootstrap/transport and child adoption remain later units. Keep
real startup and model entry refusals closed.`;
const replacement=`documentation. Control Room run19ac6c2d-eaa3-428a-829c-5dc2a2289a40 completed
at3c630a/0 from frozen basee0bbbd6, but source review FAILED. Read
ASTRA-CONTROLLER-BOUNDARY01-SOURCE-FAILURE-2026-09-14.md and follow
CONTROLLER-BOUNDARY-CUSTODY-REPAIR-BRIEF-2026-09-14.md next. Freeze7fefb4
retains13 files/227,359 bytes and746 original events, map1679fc8f.
Rootcf4fb8 validates the source pins; factory peer9f85fdc6 and fixture
peer91dc2d1e confirm custody/helper/attempt and fixture-boundary defects.
The ten new proposed tests remain unexecuted. Passive8a07a3/1 records a
malformed adapter diff; it is not a candidate test result. Preserve original
delivery and truncated command evidence. Astra's bounded source and fixture
repairs use separate fresh directories under the committed brief. All accepted
tests and generated gates remain unchanged. Native bootstrap/transport and
child adoption remain later units; real startup and model entry stay closed.`;
const lf=text.replaceAll('\r\n','\n');if(lf.split(old).length!==2)throw Error('Queue match');
const marker='| Authenticated child namespace |';if(lf.split(marker).length!==2)throw Error('State match');
const row='| Controller resume/publication connection | Gemini19ac6c2d source review FAILED; ten proposed cases unexecuted | Exact13-file delivery/map1679fc8f retained; root pins and two peer reviews agree on custody/helper/attempt and fixture reachability gaps. Passive patch check8a07a3 fails the delivered adapter diff | Follow CONTROLLER-BOUNDARY-CUSTODY-REPAIR-BRIEF-2026-09-14.md. Source-only repair; accepted95 and production71d3e70 unchanged |\n';
const log=`
### 2026-09-14 — Fixed-boundary delivery rejected; custody repair follows

Gemini run19ac6c2d finished at3c630a/0. Freeze7fefb4 preserves13 delivered
files/227,359 bytes, original746-event Control Room record and20 command steps.
Rootcf4fb8 verifies all pins, eight origins/227,073 bytes, eleven derivatives,
two before copies and ten source-ordered IDs. Eleven command previews and the
final outer output are truncated; complete command coverage remains unverified.
The report's no-Git claim conflicts with recorded read-only status step254.

Factory peer9f85fdc6 and fixture peer91dc2d1e confirm the missing initial
custody identity, dynamic helper lookup, optional unchecked attempt path and
incorrect negative-hook timing. The generated case never reaches the actual
generated gate. No proposed test ran. Passive8a07a3/1 preserves the malformed
adapter diff; the durable diff reconstructs both directions. The accepted
34,968-byte adapter prefix is unchanged. Preserve these distinct findings:
source failure, documentary patch failure and unexecuted tests.

The new custody repair brief authorizes only corrections to these fresh drafts,
with before copies and reasons, in separate source/fixture directories. It
does not authorize accepted assertion edits or qualification execution. Retain
exact initial custody and fixed helper references through both boundaries;
test the actual post-bind point and actual generated gates with inert services.
Production stays71d3e70. D2 stays complete atd13534f without repeat access.
Runtime, complete-tree, package, installed-client and market gates remain open.
`;
const after=lf.replace(old,replacement).replace(marker,row+marker)+log;
const destination=after.replaceAll('\n',text.includes('\r\n')?'\r\n':'\n');
fs.writeFileSync(root+'/_scratch/CONTROLLER-BOUNDARY01-HANDOFF-BEFORE.md',before,{flag:'wx'});
fs.writeFileSync(file,destination);console.log(JSON.stringify({queue_replacements:1,state_rows_added:1,log_entries_added:1,production_edits:0}));
