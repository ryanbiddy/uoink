# Decision memo: what run A changes about the plan

**For:** Ryan · **From:** Claude (run A) · **2026-09-04** · **One page.**
Covers my four deliverables only. Codex, grok and gemini report their own; the orchestrator integrates.

---

## The plan survives. Four things move, one needs your ruling.

**Nothing about the direction changed.** The wedge (recurring-source follower), the phase
order (clips → substrate → watchers → reach), pure client-run compute, no egress, no vendor
memory: all of it still holds after reading the code closely enough to write the contracts.
The build path in THE-LIVING-LIBRARY §8 does not need editing.

### 1. Your ruling: D-17 is not currently true, and fixing it turns a shipped feature off

Entity extraction fires a Claude Haiku call on **every capture** whenever an API key exists —
no flag, no setting, no way to see it happen (`server.py:3768-3783`). Its two siblings,
Comment Intelligence and Hook Type, are both behind named default-off flags. So decision 3's
"entity extraction gets a named default-off flag" is not a tidy-up; it is the only actual
violation of D-17 in the codebase, and closing it is five one-line edits.

The catch: `_normalize_settings` resolves a missing flag to `False`, so **entity extraction
stops for you and every existing user on the next helper restart.** Two options:

- **(a) Clean default-off** — ships as written, you re-enable it in Settings with one click.
- **(b) Grandfather** — four extra lines that turn it on once for installs that predate the flag.

**I recommend (a)** and a release-note line. "Default-off" that grandfathers itself on is not
default-off, and this is a one-user-in-the-room product where the click is trivial. Say the
word if you'd rather have (b). Full audit and the diff-ready plan: `D-17-2026-09-04.md`.

### 2. "Evidence card" currently means two different things, and it moves the cost number

`uoink_mcp_tools.get_evidence_card` returns **10 clips, untruncated**. `dryrun.py` builds
**6 clips truncated to 240 chars**. On the orchestrator's own measured inputs that is roughly
a **6-10× difference in tokens per card** — which is the denominator of grok's G4 test and the
input format of gemini's gold set. Both are being produced right now against different
definitions.

Not a decision, a spec correction: give `get_evidence_card` a `clip_chars` parameter
(default 240, max 2000) so the Librarian's card and the human's card are one code path at two
settings. Whoever integrates run A should reconcile this **before** trusting the cost model or
the gold set. I flagged the arithmetic but could not measure the real mean clip length —
see the caveat at the bottom.

### 3. Phase 2 needs one more table and one more tool than the brief names

The brief lists four tables and five tools. Reversibility needs a fifth table
(`library_applies`, the apply journal with an inverse patch) and a sixth tool
(`undo_library_apply`), because a nightly assignment pass touches 40 items under the *same*
taxonomy version — so "every apply is a version" does not hold without a journal. Both are
small and both are in the draft SQL. Calling them out rather than smuggling them in.

Also in there: `item_shelves` deliberately has **no foreign key into `clips`**, because
`rebuild_all_clips()` re-issues every `clip_id` and a FK would blank the library's entire
evidence layer the first time anyone runs `--rebuild-index`. Evidence is stored as
quote + timestamp + deep link. Details: `WORK-QUEUE-CONTRACT-2026-09-04.md`.

### 4. The recall hook needs one fix before it goes anywhere near a real session

`scripts/recall_hook.py` prints creator speech — arbitrary third-party text from a captured
video — straight into the model's context on every prompt, with no fence and no "this is
data, not instructions" framing. A YouTuber who says the wrong sentence mid-video ends up
addressing your model. It also has no SQLite timeout and never closes its connection, in
front of every prompt you type.

Both are small fixes, listed with eleven others in `MCP-REACH-2026-09-04.md` §4. The hook is
the single highest-leverage thing in Phase 4 — it works today, in Claude Code, with no
protocol work — which is exactly why it should be hardened before it is installed more widely.

---

## One ordering suggestion

Phase 4 lists MCP resources first. On (reach delivered ÷ work), the order is: **recall-hook
hardening → vault mirror → resources → prompts**. The vault mirror is nearly free —
`memory_layer._maybe_mirror` already mirrors TASTE.md and USER.md to `<vault>/Uoink/`, so
extending it to evidence cards is a template and a writer — and it delivers Obsidian, Basic
Memory *and* the Hermes distribution play in one change. Resources are a week and need a
client that supports them.

---

## Caveat on this run

`python` and `git commit` were both blocked by this session's permission policy, so **I
produced no new measurements and could not commit.** Everything I state is either read
directly from files in the worktree (line numbers, tool counts, the `mcp==1.27.1` pin, the
capability object, the SQL) or cited to the orchestrator's prior verification and labelled as
such. Where a number was needed and I could not produce it — the mean de-overlapped clip
length in §2 above — I said so and pointed at who owns it. The four documents are in the
worktree, uncommitted.

---

**Deliverables:** `D-17-2026-09-04.md` · `WORK-QUEUE-CONTRACT-2026-09-04.md` ·
`MCP-REACH-2026-09-04.md` · this memo. All under `docs/library/`.
