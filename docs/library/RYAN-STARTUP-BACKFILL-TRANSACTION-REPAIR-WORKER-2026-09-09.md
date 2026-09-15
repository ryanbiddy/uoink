# Startup backfill transaction ownership — Grok worker

Worker: grok
Worktree: `C:\Users\hello\AppData\Local\AgentControlRoom\worktrees\uoink-library\f9e2c921-de5\grok`
Branch: `control-room/f9e2c921-de5-grok`
Base HEAD: `e23d7821b9967ed7e6bd5cfa2705bb3d68d183c0`

Status: **source complete in this worktree**. Astra independently integrates
with a raw three-way patch, rebuilds, and repeats the original bundled
observation. This worker did not commit, push, run Setup, rebuild, contact
port 5179, open the live index, fetch, enable apply, or call a paid API /
model / client.

No subagents. No existing test, fixture, assertion, skip or parameter edits.
Owned files: `server.py` and new `tests/test_startup_backfill_transaction_ownership.py`.

## Diagnosis

The bundled C22 helper logs at 6632f33 are real shared-connection races, not
erased by scenario success.

One-off (`20260909T200249Z-helper-one-off.stdout.log`):

```
source_subscriptions._Store.read -> self.conn.execute("COMMIT")
sqlite3.OperationalError: cannot commit - no transaction is active
```

Child-life (`20260909T200350Z-helper-child-life.stdout.log`):

```
expire_poll_leases -> Index.write_transaction
RuntimeError: cannot start a write transaction while another transaction is active
```

`server._run_phase2_author_backfill_once` selected and then
`INSERT OR REPLACE` + `idx._conn.commit()` on the process Index connection
without `idx._lock` and without `read_snapshot` / `write_transaction`.
Source-watch `_Store.read` / `write` share that connection and lock. The
unowned `commit()` can end a source-watch `BEGIN` (one-off). The unowned
`INSERT` can leave `in_transaction` true so the next `write_transaction`
refuses (child-life). Swallowing persist errors as a warning also hid a
failed flag write and could leave a foreign transaction open.

Author correction (`page_extractor.backfill_platform_author` /
`Index.update_taxonomy`) already serialises through the Index lock. It was
not changed.

## Repair

Flag lookup uses `Index.read_snapshot` (lock + `BEGIN DEFERRED`, rollback,
refuse if a transaction is already active). Flag persistence uses
`Index.write_transaction` (lock + `BEGIN IMMEDIATE`, owned commit, rollback
on failure). Persist errors propagate; `_start_backfill_thread` already logs
them. The completion flag is not written on failure, so the next startup
retries. Once-per-install early return and idempotent author correction are
unchanged. Source-store transactions were not weakened. The watcher was not
removed. Unrelated work is not globally serialised.

## Regression file

`tests/test_startup_backfill_transaction_ownership.py` uses disposable
`tmp_path` profiles and real SQLite:

- ordinary hostname-channel correction and repeat invocation (flag gates rerun)
- foreign transaction refused, not absorbed or committed
- failed flag write leaves `in_transaction` false, no completion row, retry
  persists the flag
- held source `store.read` / `store.write` block backfill; the held unit still
  owns its transaction and does not see the completion key
- concurrent expire/due tick and backfill keep owned transactions

## Guarded native verifier

Interpreter: `E:/AI/projects/uoink/checkouts/Yoink-library/_scratch/ig-native/Scripts/python.exe`
Script: `docs/library/proof/ryan-corrected-01-2026-09-09/integrator_verify.py`
`IG_FORBIDDEN_LIVE` was a string; that file was not inspected. API keys unset.
`PHASE3_REQUIRE_IMPLEMENTATION=1` is set by the verifier. `test_phase3_s21.py`
was not collected.

| Label | Group | XML | Result |
| --- | --- | --- | --- |
| `g-sbf2` | named suites | `_scratch/g-sbf2/tests.xml` | 23 tests, 22 passed, 1 failed, 0 skipped, 3.20s |
| `g-sbf3` | strict Phase 3 except s21 | `_scratch/g-sbf3/tests.xml` | 182 tests, 181 passed, 1 failed, 0 skipped, 35.53s |
| `g-sbf-ix` | `test_existing_index_read_open.py` alone | `_scratch/g-sbf-ix/tests.xml` | 3 passed |

Named-suite pass set: all 6 new tests, 3 `test_startup_anchor_transaction`, 4
`test_cat_p2_taxonomy`, 7 `test_v3_2_3_anchors_lens`, and 2 of 3
`test_existing_index_read_open`.

### Retained named-suite grouping failure

`test_read_open_does_not_migrate_then_explicit_backend_promotes` fails in the
named group (`assert writer is reader`) because
`tests/test_cat_p2_taxonomy.py` assigns `server._get_index = lambda: idx`
without restore. Isolation of that file is 3 passed (`g-sbf-ix`). Existing
test was not edited.

### Retained original AT6 failure

`tests/library_work_astra/test_phase3_acceptance7.py::test_as7_c21_at6_receipt_records_process_exit_status`

```
AssertionError: ('Retained AT6 receipt has no explicit successful process exit status', {})
```

Logs: `_scratch/g-sbf2/tests.log`, `_scratch/g-sbf3/tests.log`.

Original C22 reproduction (untouched):

- `docs/library/proof/ryan-c22-bundled-01-2026-09-09/receipt/commands/20260909T200249Z-helper-one-off.stdout.log`
- `docs/library/proof/ryan-c22-bundled-01-2026-09-09/receipt/commands/20260909T200350Z-helper-child-life.stdout.log`

## Hashes (worktree files)

- `server.py` SHA256 `60302255ee70c125d95ba02e7c90e6255f56d94e9f60c81b90b3189ff39fc646`
- `tests/test_startup_backfill_transaction_ownership.py` SHA256 `ec36cea9696d1912dbfd2581747279df68a3f4bf4887c22ef01baf3bc85b1a98`

Applyable combined patch:
`docs/library/patches/startup-backfill-transaction-ownership-2026-09-09.patch`

## Complete diff

```diff
diff --git a/server.py b/server.py
index db8984b..d1bf0aa 100644
--- a/server.py
+++ b/server.py
@@ -3017,26 +3017,29 @@ def _run_phase2_author_backfill_once() -> None:
     """Run the Phase 2 sidecar author backfill a single time per install.
     The SQL migration (0020) already set platform + the YouTube author; this
     recovers the real X / Reddit author from the sidecars and corrects the
-    hostname `channel` values (Bug 3)."""
+    hostname `channel` values (Bug 3).
+
+    Flag lookup and persistence go through Index's lock/transaction boundary
+    so a source-watch snapshot or write on the shared connection is not
+    committed or entered. A failed flag write does not record completion.
+    """
     idx = _get_index()
-    try:
-        row = idx._conn.execute(
-            "SELECT value FROM memory_layer WHERE key=?",
-            (_PHASE2_BACKFILL_KEY,)).fetchone()
-    except Exception:
-        row = None
+    with idx.read_snapshot() as conn:
+        try:
+            row = conn.execute(
+                "SELECT value FROM memory_layer WHERE key=?",
+                (_PHASE2_BACKFILL_KEY,)).fetchone()
+        except Exception:
+            row = None
     if row is not None:
         return  # already run on this install
     stats = page_extractor.backfill_platform_author(idx)
     log.info("phase 2 author backfill: %s", stats)
-    try:
-        idx._conn.execute(
+    with idx.write_transaction() as conn:
+        conn.execute(
             "INSERT OR REPLACE INTO memory_layer (key, value, updated_at) "
             "VALUES (?, ?, ?)",
             (_PHASE2_BACKFILL_KEY, json.dumps(stats), _now_iso()))
-        idx._conn.commit()
-    except Exception:
-        log.warning("could not record phase 2 backfill completion flag")
```

New file `tests/test_startup_backfill_transaction_ownership.py` (213 lines) is
in the combined patch above.

## Astra

Integrate these two source files with a raw three-way patch. Rebuild the
changed product. Repeat the original bundled C22 observation plus the final
complete tree. This worker does not rebuild.
