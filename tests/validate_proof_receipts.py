"""Offline run-P receipt contract and run-Q auditor. Never starts a client/helper.

Export JSON Schema with --schema; check frozen files with --verify-inputs.
The schema checks shape; validate_receipts also checks hashes, evidence, accounting,
retry history, isolation declarations, and unchanged projection snapshots.
"""
from __future__ import annotations

import argparse
import base64
import copy
import hashlib
import json
import math
import random
import re
import shutil
import sqlite3
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path, PurePosixPath, PureWindowsPath
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import library_cards
from jsonschema import Draft202012Validator

MANIFEST = ROOT / "docs/library/proof/manifest-2026-09-05.json"
ARCHIVE = ROOT / "docs/library/proof/run-2026-09-05/receipts.json"
ARCHIVE_SHA256 = "2b4e824ea9f93999de6c5108406e60a5c81f108de0b279c52fee2e96d622469c"
HOLDOUT_V2 = ROOT / "docs/library/proof/holdout-v2-2026-09-05.json"
INDUCTION_MANIFEST = ROOT / "docs/library/proof/induction-manifest-2026-09-05.json"
MANIFEST_STAGE2 = ROOT / "docs/library/proof/manifest-stage2-2026-09-05.json"
# Stage-specific frozen inputs. Every other frozen file (card builder, service, migrations)
# is shared. Stage 2 binds the approved taxonomy v2, hold-out v2, the sealed adjudicated
# labels (as the gold file) and the adjudicated mapping table.
STAGE_FILES = {
    1: dict(taxonomy="docs/library/taxonomy-v1-2026-09-04.json", holdout="docs/library/holdout-split-2026-09-04.json",
            gold="docs/library/gold-set-2026-09-04.json"),
    2: dict(taxonomy="docs/library/taxonomy-v2-2026-09-05.json", parent_taxonomy="docs/library/taxonomy-v1-2026-09-04.json",
            holdout="docs/library/proof/holdout-v2-2026-09-05.json",
            gold="docs/library/proof/labels/holdout-v2-gold-2026-09-05.json",
            mapping="docs/library/proof/labels/holdout-v2-mapping-2026-09-05.json"),
}
SOURCE_SHA256 = "2765cc359805fb12f7a90aecd3dd0b34d884aa8cb3015785011bf400da3b4dfc"
CONTRACT = "phase2-v1.2-2026-09-04"
OUTCOMES = ["accepted", "rejected", "unmapped", "unsupported", "pinned", "deleted", "changed"]
PROFILE = dict(profile="librarian", schema_version=1, selection_version="spread-longest-v1",
               n_clips=6, clip_chars=240, byte_budget=8192, corpus_read_bytes=8192,
               serialization="library_cards.card_text UTF-8")
HASH_KEYS = ["manifest_hash", "source_sha256", "taxonomy_file_sha256", "taxonomy_revision_hash",
             "prompt_file_sha256", "prompt_sha256", "card_profile_hash", "card_builder_sha256",
             "holdout_file_sha256", "holdout_ids_hash", "gold_file_sha256", "cards_hash", "corpus_heads_hash", "implementation_hash"]


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def digest(value):
    return sha(canonical(value).encode("utf-8"))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def decode_json(raw):
    def pairs(entries):
        result = {}
        for key, value in entries:
            require(key not in result, f"Duplicate JSON key: {key}")
            result[key] = value
        return result

    def nonfinite(value):
        raise ValueError(f"Non-finite JSON number: {value}")

    return json.loads(raw, object_pairs_hook=pairs, parse_constant=nonfinite)


def read_json(path):
    return decode_json(Path(path).read_text(encoding="utf-8"))


def normalize_quote(text):
    """Service convention: NFC, collapse whitespace, retain case and punctuation."""
    return " ".join(unicodedata.normalize("NFC", text).split())


def stage2_freezes():
    """Reproduce reservations 3/4 from archived bytes only; never dereference paths."""
    raw = ARCHIVE.read_bytes()
    require(sha(raw) == ARCHIVE_SHA256, "Induction source archive changed")
    archived, manifest = decode_json(raw), read_json(MANIFEST)
    old_path = ROOT / "docs/library/holdout-split-2026-09-04.json"
    require(sha(old_path.read_bytes()) == manifest["files"]["holdout"]["sha256"], "Old holdout changed")
    old_ids = {r["video_id"] for rows in read_json(old_path)["strata"].values() for r in rows}
    ids = [pair[0] for pair in manifest["items"]]
    require(archived["target_ids"] == ids and len(ids) == len(set(ids)) == 548, "Archive target mismatch")
    last = {}
    for attempt in archived["attempts"]:
        vid = attempt["video_id"]
        require(vid in ids and attempt["attempt_number"] == last.get(vid, {}).get("attempt_number", 0) + 1,
                "Archive attempts are not consecutive")
        card = attempt["packet"]["card"]
        require(card["video_id"] == vid and card["source_revision"] == manifest["cards"][vid]["source_revision"] and
                card["card_hash"] == manifest["cards"][vid]["card_hash"] ==
                library_cards._hash({k: v for k, v in card.items() if k != "card_hash"}), "Archive card binding mismatch")
        last[vid] = attempt
    require(set(last) == set(ids), "Archive is missing an attempted target")
    require(all(t["outcome"] == last[t["video_id"]]["outcome"] for t in archived["targets"]), "Terminal outcome mismatch")
    induction_ids = sorted(vid for vid in ids if last[vid]["outcome"] == "unmapped")
    require(len(induction_ids) == 225 and len(set(induction_ids) & old_ids) == 23, "Induction scope changed")

    def row(vid):
        card = last[vid]["packet"]["card"]
        return dict(video_id=vid, source_revision=card["source_revision"], card_hash=card["card_hash"],
                    stratum="timed_evidence" if any(e["evidence_kind"] == "timed_clip" for e in card["excerpts"]) else "text_only")

    common = dict(schema_version=1, freeze_status="frozen", archived_receipts_sha256=ARCHIVE_SHA256,
                  source_sha256=SOURCE_SHA256, source_manifest_sha256=sha(MANIFEST.read_bytes()))
    induction = dict(common, kind="induction-manifest", version="induction-v1-2026-09-05",
                     selection="Last reasoning attempt per archived target; terminal outcome equals unmapped; video_id ascending",
                     target_count=225, old_holdout_overlap_count=23,
                     items=[dict(row(vid), old_holdout=vid in old_ids) for vid in induction_ids])
    pool = sorted(set(ids) - set(induction_ids) - old_ids)
    pools = {s: [vid for vid in pool if row(vid)["stratum"] == s] for s in ("timed_evidence", "text_only")}
    counts = {s: len(v) for s, v in pools.items()}
    require(len(pool) == 286 and counts == dict(timed_evidence=105, text_only=181), "Evaluation pool changed")
    seed = int(ARCHIVE_SHA256[:16], 16)
    rng = random.Random(seed)
    strata = {s: [row(vid) for vid in sorted(rng.sample(pools[s], n))]
              for s, n in [("timed_evidence", 47), ("text_only", 13)]}
    infeasible = []
    for rows in strata.values():
        for entry in rows:
            card = last[entry["video_id"]]["packet"]["card"]
            usable = [e for e in card["excerpts"] if normalize_quote(e["text"]) and
                      (e["evidence_kind"] == "timed_clip" or card.get("source_type") in
                       {"page", "x_article", "x_thread", "reddit_thread", "note"})]
            if not usable:
                infeasible.append(entry["video_id"])
    holdout = dict(common, kind="holdout", version="holdout-v2-2026-09-05", labels_status="sealed-labels-pending",
                   selection=dict(algorithm="CPython random.Random(seed).sample; one RNG; timed_evidence then text_only; sort each pool and selected stratum by video_id (Unicode code-point order)",
                                  seed_hex="0x" + ARCHIVE_SHA256[:16], seed_integer=seed,
                                  pool_count=286, pool_counts=counts, pool_ids_sha256=digest(pool),
                                  excluded_induction_count=225, excluded_old_holdout_count=60,
                                  old_holdout_sha256=sha(old_path.read_bytes())),
                   target_count=60, strata=strata,
                   feasibility=dict(ineligible_source_ids=sorted(infeasible),
                       rule="Nonempty timed evidence, or nonempty original prose from page/x_article/x_thread/reddit_thread/note; this is only an evidence-availability ceiling",
                       eligible_counts={s: sum(r["video_id"] not in infeasible for r in rows) for s, rows in strata.items()}))
    return holdout, induction


def verify_stage2_freezes():
    holdout, induction = stage2_freezes()
    require(read_json(HOLDOUT_V2) == holdout, "Holdout v2 differs from deterministic reservation")
    require(read_json(INDUCTION_MANIFEST) == induction, "Induction freeze differs from archive")
    return dict(status="STAGE2_FREEZES_VALID", holdout_count=60, induction_count=225,
                holdout_sha256=sha(HOLDOUT_V2.read_bytes()), induction_sha256=sha(INDUCTION_MANIFEST.read_bytes()),
                feasibility=holdout["feasibility"])


def normalized_taxonomy(document):
    """The documented approve_taxonomy input conversion; mirrors service ordering."""
    nodes = copy.deepcopy(document["nodes"])
    for node in nodes:
        require(node.get("retired", False) in (0, 1, False, True), "Invalid retired flag")
        node["retired"] = bool(node.get("retired", False))
        node["path"] = [unicodedata.normalize("NFC", part) for part in node["path"]]
        node["name"] = node["path"][-1]
    by_path = {tuple(node["path"]): node["shelf_id"] for node in nodes}
    for node in nodes:
        node["parent_shelf_id"] = by_path.get(tuple(node["path"][:-1]))
    nodes.sort(key=lambda node: (len(node["path"]), node["path"], node["shelf_id"]))
    return dict(schema_version=1, version_id=document["version_id"], nodes=nodes,
                parent_version_id=document.get("parent_version_id"), revision_hash=digest(nodes))


def object_schema(properties):
    return dict(type="object", properties=properties, required=list(properties), additionalProperties=False)


def array_schema(items, **options):
    return dict(type="array", items=items, **options)


def with_optional(schema, optional):
    """A closed object schema plus optional properties (contract v1.3 provenance fields);
    required keys and additionalProperties=False are unchanged."""
    out = copy.deepcopy(schema)
    out["properties"].update(optional)
    return out


TEXT = dict(type="string")
ID = dict(type="string", minLength=1)
HASH = dict(type="string", pattern="^[a-f0-9]{64}$")
COUNT = dict(type="integer", minimum=0)
NULL_ID = dict(anyOf=[ID, dict(type="null")])
JSON_OBJECT = dict(type="object")
OUTCOME = dict(enum=OUTCOMES)
STATE_SCHEMA = object_schema(dict(
    projection_revision=COUNT, memberships=array_schema(JSON_OBJECT), pins=array_schema(JSON_OBJECT),
    item_policies=array_schema(JSON_OBJECT), active_version_id=NULL_ID,
    taxonomy_revision_hash=HASH, librarian_apply_enabled=dict(const=False),
    applied_label_count=dict(const=0), proof_apply_count=dict(const=0)))
USAGE_SCHEMA = dict(oneOf=[
    object_schema(dict(status=dict(const="unavailable"), reason=ID)),
    object_schema(dict(status=dict(const="reported"), source=dict(const="claude_cli_json"),
                       model=ID, input_tokens=COUNT, output_tokens=COUNT,
                       cache_read_tokens=COUNT, cache_create_tokens=COUNT))])
ATTEMPT_SCHEMA = object_schema(dict(
    attempt_id=ID, video_id=ID, work_id=ID,
    attempt_token=dict(type="string", pattern="^[A-Za-z0-9_-]{43,128}$"),
    attempt_number=dict(type="integer", minimum=1, maximum=2),
    packet_hash=HASH, packet=JSON_OBJECT, card_text=ID, card_bytes=COUNT,
    prompt_text=ID, prompt_bytes=COUNT, response_text=TEXT, response_bytes=COUNT,
    serialized_input_bytes=COUNT, wall_ms=COUNT, outcome=OUTCOME,
    rejection_reason=NULL_ID, result=dict(anyOf=[JSON_OBJECT, dict(type="null")]),
    submit_response=dict(anyOf=[JSON_OBJECT, dict(type="null")]),
    usage=USAGE_SCHEMA,
    estimates=object_schema(dict(total_cost_usd=dict(type=["number", "null"], minimum=0),
                                  source=dict(enum=["claude_cli_estimate", "unavailable"])))))
TRANSPORT_SCHEMA = object_schema(dict(
    event_id=ID, attempt_id=NULL_ID, video_id=NULL_ID,
    stage=dict(enum=["claim", "reason", "submit", "preview"]), reason=ID,
    request_bytes=COUNT, response_bytes=COUNT, wall_ms=COUNT))
RECEIPT_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "urn:uoink:proof-receipts:2026-09-05:v1",
    **object_schema(dict(
        schema_version=dict(const=1), contract_version=dict(const=CONTRACT), run_id=ID,
        mode=dict(enum=["mock", "subscription"]), status=dict(enum=["completed", "aborted"]),
        abort_reason=NULL_ID, inputs=object_schema({key: HASH for key in HASH_KEYS}),
        target_ids=array_schema(ID, minItems=1, uniqueItems=True), target_manifest_hash=HASH,
        config=object_schema(dict(
            client=dict(const="proof_run.py"), transport=dict(const="http_registry"), model=ID,
            base_url=ID, isolation_root=ID, index_path=ID, token_path=ID,
            environment=object_schema({key: ID for key in ("LOCALAPPDATA", "APPDATA", "TEMP", "TMP", "UOINK_OUTPUT_DIR")}),
            anthropic_api_key_unset=dict(const=True), tools=dict(const=[]),
            concurrency=dict(type="integer", minimum=1, maximum=4),
            max_retries=dict(const=1), wall_budget_ms=dict(const=7200000),
            error_rate_limit=dict(const=0.10), error_rate_min_attempts=dict(const=20),
            output_schema_text=ID, output_schema_sha256=HASH)),
        database=object_schema(dict(copy_before_upgrade_sha256=HASH, copy_after_upgrade_sha256=HASH,
                                    source_after_sha256=HASH, schema_before=COUNT, schema_after=COUNT)),
        before=STATE_SCHEMA, after=STATE_SCHEMA,
        attempts=array_schema(ATTEMPT_SCHEMA), transport_failures=array_schema(TRANSPORT_SCHEMA),
        targets=array_schema(object_schema(dict(video_id=ID, work_id=NULL_ID, outcome=OUTCOME,
                                                reason=NULL_ID, last_attempt_id=NULL_ID))),
        preview=object_schema(dict(request=JSON_OBJECT, response=JSON_OBJECT)),
        totals=object_schema(dict(serialized_input_bytes=COUNT, card_bytes=COUNT, prompt_bytes=COUNT,
                                 response_bytes=COUNT, wall_ms=COUNT, retries=COUNT, model_calls=COUNT,
                                 rejected_attempts=COUNT, transport_failures=COUNT)),
        audit_extensions=JSON_OBJECT))}

# Version 1 remains readable for offline regression fixtures only. All measured
# runs use v2: byte totals and usage belong to processes, not derived item views.
LEGACY_RECEIPT_SCHEMA = RECEIPT_SCHEMA
ARTIFACT_SCHEMA = dict(oneOf=[
    object_schema(dict(path=ID, sha256=HASH, bytes=COUNT)),
    object_schema(dict(base64=TEXT, sha256=HASH, bytes=COUNT))])
CALL_SCHEMA = object_schema(dict(
    call_id=ID, attempt_ids=array_schema(ID, minItems=1, uniqueItems=True),
    argv=array_schema(TEXT, minItems=1), schema_text=ID, schema_sha256=HASH,
    stdin=ARTIFACT_SCHEMA, stdout=ARTIFACT_SCHEMA, stderr=ARTIFACT_SCHEMA,
    start_monotonic_ns=COUNT, end_monotonic_ns=COUNT,
    exit_status=dict(type=["integer", "null"]), timed_out=dict(type="boolean"),
    cancellation=dict(anyOf=[ID, dict(type="null")]),
    usage=dict(anyOf=[JSON_OBJECT, dict(type="null")]),
    modelUsage=dict(anyOf=[JSON_OBJECT, dict(type="null")]),
    cli_estimated_cost_usd=dict(type=["number", "null"], minimum=0)))
# Contract v1.3: per-process provenance recorded by the induction runner (audit B8).
CALL_SCHEMA = with_optional(CALL_SCHEMA, dict(cwd=TEXT, environment_policy=TEXT))
COMPLETION_SCHEMA = object_schema(dict(attempt_id=ID, completed_monotonic_ns=COUNT))
HTTP_SCHEMA = object_schema(dict(
    event_id=ID, operation=dict(enum=["claim", "submit", "release", "cancel", "renew", "preview"]),
    request=ARTIFACT_SCHEMA, response=ARTIFACT_SCHEMA,
    status_code=dict(type=["integer", "null"]), error=NULL_ID,
    start_monotonic_ns=COUNT, end_monotonic_ns=COUNT, resend_of=NULL_ID))
EXECUTION_SCHEMA = object_schema(dict(
    checkout_root=ID, git_sha=dict(type="string", pattern="^[a-f0-9]{40}$"),
    start_monotonic_ns=COUNT, end_monotonic_ns=COUNT,
    fingerprints=object_schema({name: ARTIFACT_SCHEMA for name in
        ("runner", "scorer", "validator", "service", "prompt", "card_builder")}),
    cleanup=object_schema(dict(owned_processes_remaining=dict(const=0), helper_stopped=dict(const=True),
                               errors=array_schema(ID)))))
V2_RECEIPT_SCHEMA = copy.deepcopy(LEGACY_RECEIPT_SCHEMA)
V2_RECEIPT_SCHEMA["$id"] = "urn:uoink:proof-receipts:2026-09-05:v2"
V2_RECEIPT_SCHEMA["properties"]["schema_version"] = dict(const=2)
v2_attempt = V2_RECEIPT_SCHEMA["properties"]["attempts"]["items"]
v2_attempt["properties"].update(call_id=ID, model_result=dict(anyOf=[JSON_OBJECT, dict(type="null")]),
                                  claim_event_id=ID, submit_event_ids=array_schema(ID, uniqueItems=True))
v2_attempt["required"] += ["call_id", "model_result", "claim_event_id", "submit_event_ids"]
v2_target = V2_RECEIPT_SCHEMA["properties"]["targets"]["items"]
v2_target["properties"]["terminal_service_state"] = ID
v2_target["required"].append("terminal_service_state")
v2_transport = V2_RECEIPT_SCHEMA["properties"]["transport_failures"]["items"]
v2_transport["properties"].update(http_event_id=NULL_ID, occurred_monotonic_ns=COUNT)
v2_transport["required"] += ["http_event_id", "occurred_monotonic_ns"]
v2_totals = V2_RECEIPT_SCHEMA["properties"]["totals"]
v2_totals["properties"].update(item_attempts=COUNT, schema_bytes=COUNT, stderr_bytes=COUNT)
v2_totals["required"] += ["item_attempts", "schema_bytes", "stderr_bytes"]
V2_RECEIPT_SCHEMA["properties"].update(
    calls=array_schema(CALL_SCHEMA), completion_order=array_schema(COMPLETION_SCHEMA),
    http_history=array_schema(HTTP_SCHEMA), execution=EXECUTION_SCHEMA,
    state_artifacts=object_schema({name: ARTIFACT_SCHEMA for name in
        ("registry", "before_snapshot", "after_snapshot", "before_db", "after_db", "apply_journal",
         "source", "upgraded", "corpus_heads")}),
    accounting=JSON_OBJECT)
V2_RECEIPT_SCHEMA["required"] += ["calls", "completion_order", "http_history", "execution", "state_artifacts", "accounting"]
RECEIPT_SCHEMA = dict(oneOf=[LEGACY_RECEIPT_SCHEMA, V2_RECEIPT_SCHEMA],
                      **{"$schema": "https://json-schema.org/draft/2020-12/schema"})


def artifact_bytes(record, artifact_root):
    """Only open portable, contained archive paths; historical paths are data."""
    Draft202012Validator(ARTIFACT_SCHEMA).validate(record)
    if "base64" in record:
        raw = base64.b64decode(record["base64"], validate=True)
    else:
        name = record["path"]
        require(not PureWindowsPath(name).drive and not PureWindowsPath(name).is_absolute() and
                not PurePosixPath(name).is_absolute() and "\\" not in name and
                ".." not in PurePosixPath(name).parts, "Artifact path must be portable and relative")
        base = Path(artifact_root).resolve()
        path = (base / name).resolve()
        require(path.is_relative_to(base) and path != base, "Artifact escapes archive")
        raw = path.read_bytes()
    require(len(raw) == record["bytes"] and sha(raw) == record["sha256"], "Artifact bytes/hash mismatch")
    return raw


def inline_artifact(raw):
    """Lossless fixture/export representation; never reserialize captured stdout."""
    return dict(base64=base64.b64encode(raw).decode("ascii"), sha256=sha(raw), bytes=len(raw))


def call_accounting(calls):
    """Null counters stay null. modelUsage is preserved by call, without merging models."""
    keys = ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")
    counters = {}
    for key in keys:
        values = [c["usage"].get(key) if isinstance(c["usage"], dict) else None for c in calls]
        counters[key] = sum(values) if values and all(type(v) is int and v >= 0 for v in values) else None
    estimates = [c["cli_estimated_cost_usd"] for c in calls]
    return dict(process_count=len(calls), counters=counters,
                modelUsage_by_call={c["call_id"]: c["modelUsage"] for c in calls},
                cli_estimated_cost_usd=math.fsum(estimates) if estimates and all(v is not None for v in estimates) else None,
                estimate_source="claude_cli_estimate" if estimates and all(v is not None for v in estimates) else "unavailable",
                paid_cost_usd=None, paid_cost_source="unavailable")


def _check_calls(calls, artifact_root):
    seen, attempts, outputs, inputs = set(), set(), {}, {}
    for call in calls:
        Draft202012Validator(CALL_SCHEMA).validate(call)
        cid = call["call_id"]
        require(cid not in seen, "Duplicate call ID")
        seen.add(cid)
        require(not (attempts & set(call["attempt_ids"])), "Attempt belongs to multiple calls")
        attempts.update(call["attempt_ids"])
        require(call["end_monotonic_ns"] >= call["start_monotonic_ns"], "Call ends before it starts")
        require(call["exit_status"] is not None or call["timed_out"] or call["cancellation"], "Missing process exit status")
        schema = call["schema_text"]
        require(sha(schema.encode("utf-8")) == call["schema_sha256"], "Call schema hash mismatch")
        Draft202012Validator.check_schema(decode_json(schema))
        argv = call["argv"]
        require("-p" in argv and "--json-schema" in argv and
                argv.index("--json-schema") + 1 < len(argv) and argv[argv.index("--json-schema") + 1] == schema,
                "Exact CLI argv must bind the output schema")
        stdin, stdout, stderr = [artifact_bytes(call[name], artifact_root) for name in ("stdin", "stdout", "stderr")]
        inputs[cid] = stdin
        try:
            envelope = decode_json(stdout)
        except (ValueError, UnicodeError):
            envelope = None
        envelope = envelope if isinstance(envelope, dict) else {}
        require(call["usage"] == envelope.get("usage"), "Call usage differs from original stdout")
        require(call["modelUsage"] == envelope.get("modelUsage"), "Missing or invented modelUsage entry")
        require(call["cli_estimated_cost_usd"] == envelope.get("total_cost_usd"), "CLI estimate differs from original stdout")
        outputs[cid] = envelope
    return inputs, outputs


def _check_completion_guard(receipts):
    attempts = {a["attempt_id"]: a for a in receipts["attempts"]}
    order = receipts["completion_order"]
    require(len(order) == len(attempts) and {e["attempt_id"] for e in order} == set(attempts), "Completion order missing/duplicate attempt")
    times = [e["completed_monotonic_ns"] for e in order]
    require(times == sorted(times), "Completion order is not monotonic")
    calls = {c["call_id"]: c for c in receipts["calls"]}
    rejected, seen = 0, set()
    for n, event in enumerate(order, 1):
        attempt = attempts[event["attempt_id"]]
        seen.add(attempt["attempt_id"])
        require(event["completed_monotonic_ns"] >= calls[attempt["call_id"]]["end_monotonic_ns"], "Completion precedes call exit")
        rejected += attempt["outcome"] == "rejected"
        failures = sum(e["occurred_monotonic_ns"] <= event["completed_monotonic_ns"] and
                       (e["attempt_id"] is None or e["attempt_id"] in seen) for e in receipts["transport_failures"])
        # Integer comparison makes equality at 10% unambiguous.
        require(n < 20 or 10 * (rejected + failures) <= n,
                f"Error-rate abort threshold exceeded at completion {n}: {rejected + failures}/{n}")


def redact_http(value):
    """Apply to exported request/response JSON, including nested lease secrets."""
    secret_keys = {"authorization", "proxy-authorization", "cookie", "set-cookie", "token", "attempt_token", "api_key"}
    if isinstance(value, dict):
        return {k: "[REDACTED]" if k.lower() in secret_keys else redact_http(v) for k, v in value.items()}
    if isinstance(value, list):
        return [redact_http(v) for v in value]
    return value


def _check_http(receipts, artifact_root):
    events, bodies = {}, {}
    for event in receipts["http_history"]:
        eid = event["event_id"]
        require(eid not in events, "Duplicate HTTP event")
        require(event["end_monotonic_ns"] >= event["start_monotonic_ns"], "HTTP ends before it starts")
        request, response = [decode_json(artifact_bytes(event[k], artifact_root)) for k in ("request", "response")]
        require(redact_http(request) == request and redact_http(response) == response, "HTTP export contains an unredacted secret")
        encoded = canonical([request, response])
        require(not re.search(r"Bearer\s+(?!\[REDACTED\])[^\s\"]+|sk-ant-[A-Za-z0-9_-]+", encoded), "HTTP export contains credential text")
        require(isinstance(request, dict) and {"method", "url", "headers", "body"} <= set(request), "HTTP request wrapper incomplete")
        require(isinstance(response, dict) and {"headers", "body"} <= set(response), "HTTP response wrapper incomplete")
        parsed, base = urlsplit(request["url"]), urlsplit(receipts["config"]["base_url"])
        require((parsed.scheme, parsed.netloc) == (base.scheme, base.netloc) and not parsed.query and not parsed.fragment, "HTTP request outside isolated endpoint")
        require(event["status_code"] is not None or event["error"], "HTTP failure lacks status/error")
        if event["resend_of"] is not None:
            previous = event["resend_of"]
            require(previous in events and events[previous]["operation"] == event["operation"] and
                    bodies[previous][0] == request, "Identical resend lacks matching earlier request")
        events[eid], bodies[eid] = event, (request, response)
    for attempt in receipts["attempts"]:
        claim = attempt["claim_event_id"]
        require(claim in events and events[claim]["operation"] == "claim", "Attempt lacks claim history")
        work = bodies[claim][1]["body"].get("work", [])
        require(any(w.get("work_id") == attempt["work_id"] and w.get("video_id") == attempt["video_id"] for w in work), "Claim does not contain attempted work")
        submitted = attempt["submit_event_ids"]
        require(submitted or attempt["submit_response"] is None, "Submitted attempt lacks HTTP history")
        for pos, eid in enumerate(submitted):
            require(eid in events and events[eid]["operation"] == "submit", "Attempt lacks submit history")
            body = bodies[eid][0]["body"]
            require(body.get("work_id") == attempt["work_id"] and body.get("video_id") == attempt["video_id"] and
                    body.get("result") == attempt["result"], "Submit differs from retained submission")
            require(pos == 0 or events[eid]["resend_of"] == submitted[pos - 1], "Resend must be distinct from reasoning retry")
        if submitted and attempt["submit_response"] is not None:
            require(bodies[submitted[-1]][1]["body"] == redact_http(attempt["submit_response"]), "Submit response was overwritten")
    for event in receipts["transport_failures"]:
        eid = event["http_event_id"]
        require(event["stage"] == "reason" or eid in events, "Transport event lacks HTTP history")
    require(any(e["operation"] == "preview" and bodies[eid][0]["body"] == receipts["preview"]["request"] and
                bodies[eid][1]["body"] == receipts["preview"]["response"] for eid, e in events.items()), "Preview absent from HTTP history")
    return events, bodies


def _deserializable(image: bytes) -> bytes:
    """A WAL-mode database image cannot be opened after Connection.deserialize
    (SQLite reports "unable to open database file"); the named source copy is
    WAL. Hashes are always checked on the original bytes. Only the in-memory
    copy has header bytes 18-19 (journal mode) set to rollback so the pages can
    be read; page content is untouched. Integrator addition, 2026-09-05."""
    if len(image) > 20 and image[:15] == b"SQLite format 3" and image[18:20] == bytes([2, 2]):
        patched = bytearray(image)
        patched[18] = 1
        patched[19] = 1
        return bytes(patched)
    return image


def _check_state_artifacts(receipts, manifest, artifact_root, http):
    records = receipts["state_artifacts"]
    raw = {key: artifact_bytes(value, artifact_root) for key, value in records.items()}
    require(sha(raw["source"]) == SOURCE_SHA256, "Archived source hash mismatch")
    require(sha(raw["upgraded"]) == receipts["database"]["copy_after_upgrade_sha256"], "Archived upgrade hash mismatch")
    for key, schema_key in [("source", "schema_before"), ("upgraded", "schema_after")]:
        with sqlite3.connect(":memory:") as conn:
            conn.deserialize(_deserializable(raw[key]))
            conn.execute("PRAGMA query_only=ON")
            require(conn.execute("SELECT max(version) FROM schema_version").fetchone()[0] == receipts["database"][schema_key], "Archived database schema mismatch")
    for side in ("before", "after"):
        require(decode_json(raw[side + "_snapshot"]) == receipts[side], "Independent snapshot disagrees with receipt")
        require(raw[side + "_db"].startswith(b"SQLite format 3\0"), "Missing SQLite snapshot")
        with sqlite3.connect(":memory:") as conn:
            conn.deserialize(_deserializable(raw[side + "_db"]))
            conn.execute("PRAGMA query_only=ON")
            conn.row_factory = sqlite3.Row
            meta = conn.execute("SELECT * FROM library_meta WHERE singleton=1").fetchone()
            state = receipts[side]
            require(meta["projection_revision"] == state["projection_revision"] and
                    meta["active_version_id"] == state["active_version_id"], "Database projection/activation differs from snapshot")
            require(conn.execute("SELECT revision_hash FROM shelf_versions WHERE version_id=?", (state["active_version_id"],)).fetchone()[0] == state["taxonomy_revision_hash"], "Database taxonomy differs from snapshot")
            for key, query in [
                ("memberships", "SELECT * FROM item_shelves ORDER BY video_id,shelf_id"),
                ("pins", "SELECT video_id,shelf_id FROM item_shelves WHERE locked=1 ORDER BY video_id,shelf_id"),
                ("item_policies", "SELECT video_id,exclusive_move FROM library_item_policy ORDER BY video_id")]:
                require([dict(r) for r in conn.execute(query)] == state[key], "Database memberships/pins/policies differ from snapshot")
            require(conn.execute("SELECT count(*) FROM library_applies").fetchone()[0] == 0, "Database contains applies")
    require(decode_json(raw["apply_journal"]) == {"entries": []}, "Proof apply journal is not empty")
    heads = decode_json(raw["corpus_heads"])
    require(set(heads) == set(manifest["corpus_heads"]), "Bounded corpus archive is incomplete")
    for vid, record in heads.items():
        head = artifact_bytes(record, artifact_root)
        require(len(head) <= 8192 and sha(head) == manifest["corpus_heads"][vid]["raw_sha256"], "Bounded corpus head mismatch")
    registry = decode_json(raw["registry"])
    required = {"library_work", "library_attempts", "library_submissions", "library_proposals", "library_manifest"}
    require(set(registry) == required and all(isinstance(v, list) for v in registry.values()), "Registry export incomplete")
    with sqlite3.connect(":memory:") as conn:
        conn.deserialize(_deserializable(raw["after_db"]))
        conn.execute("PRAGMA query_only=ON")
        conn.row_factory = sqlite3.Row
        for table in sorted(required):
            if table == "library_submissions":
                query = "SELECT * FROM library_submissions WHERE attempt_token IN (SELECT attempt_token FROM library_attempts WHERE work_id IN (SELECT work_id FROM library_work WHERE run_id=?))"
            elif table == "library_attempts":
                query = "SELECT * FROM library_attempts WHERE work_id IN (SELECT work_id FROM library_work WHERE run_id=?)"
            else:
                query = f"SELECT * FROM {table} WHERE run_id=?"  # table is from the fixed set above
            rows = [dict(r) for r in conn.execute(query, (receipts["run_id"],))]
            require(sorted(map(canonical, rows)) == sorted(map(canonical, registry[table])), "Registry export differs from after database")
    work = {w["work_id"]: w for w in registry["library_work"]}
    attempts = {a["attempt_token"]: a for a in registry["library_attempts"]}
    submissions = {s["attempt_token"]: s for s in registry["library_submissions"]}
    require(len(work) == len(registry["library_work"]) and len(attempts) == len(registry["library_attempts"]) and
            len(submissions) == len(registry["library_submissions"]), "Duplicate registry identity")
    used_submissions, accepted = set(), []
    for a in receipts["attempts"]:
        require(a["work_id"] in work and work[a["work_id"]]["video_id"] == a["video_id"], "Registry work missing/mismatched")
        r = attempts.get(a["attempt_token"], {})
        require(r.get("work_id") == a["work_id"] and r.get("attempt_number") == a["attempt_number"], "Registry attempt missing/mismatched")
        sub = submissions.get(a["attempt_token"])
        if a["submit_response"] is not None and a["submit_response"].get("ok"):
            require(sub is not None and decode_json(sub["result_json"]) == a["result"] and
                    decode_json(sub["response_json"]) == a["submit_response"], "Registry submission missing/overwritten")
            used_submissions.add(a["attempt_token"])
            if a["outcome"] == "accepted":
                for i, member in enumerate(a["result"]["memberships"]):
                    evidence = member["evidence"]
                    excerpt = next(e for e in a["packet"]["card"]["excerpts"] if e["excerpt_id"] == evidence["excerpt_id"])
                    enriched = dict(evidence, **{k: excerpt[k] for k in ("start", "end", "timing", "truncated")})
                    accepted.append((a["video_id"], member["shelf_id"], sub["submission_key"], int(i == 0),
                                     member["confidence"], canonical(enriched), manifest["taxonomy"]["version_id"]))
    require(used_submissions == set(submissions), "Unaccounted registry submission")
    proposals = registry["library_proposals"]
    require(sorted(accepted) == sorted((p["video_id"], p["shelf_id"], p["submission_key"], p["is_primary"],
                                       p["confidence"], canonical(decode_json(p["evidence_json"])), p["version_id"]) for p in proposals), "Registry proposals differ from accepted memberships")
    require(sorted(r["video_id"] for r in registry["library_manifest"]) == receipts["target_ids"], "Registry manifest differs from targets")
    for target in receipts["targets"]:
        if target["work_id"] is not None:
            require(work[target["work_id"]]["state"] == target["terminal_service_state"], "Terminal service state differs from model disposition")
    # Third claims are service history, never a third reasoning attempt.
    reasoning_tokens = {a["attempt_token"] for a in receipts["attempts"]}
    events, bodies = http
    for token, a in attempts.items():
        if token not in reasoning_tokens:
            require(a["state"] == "cancelled" and any(e["operation"] == "claim" and
                isinstance(bodies[eid][1]["body"], dict) and any(w.get("work_id") == a["work_id"] and
                w.get("attempt_number") == a["attempt_number"] for w in bodies[eid][1]["body"].get("work", []))
                for eid, e in events.items()), "Unaccounted extra claim in registry")
            require(any(e["operation"] == "cancel" and bodies[eid][0]["body"].get("work_id") == a["work_id"] and
                bodies[eid][1]["body"].get("state") == "cancelled" for eid, e in events.items()), "Unaccounted claim/cancel in registry")


def _check_v2(receipts, manifest, template, artifact_root):
    calls = receipts["calls"]
    inputs, outputs = _check_calls(calls, artifact_root)
    by_id = {a["attempt_id"]: a for a in receipts["attempts"]}
    require(set(by_id) == {aid for c in calls for aid in c["attempt_ids"]}, "Call/attempt accounting mismatch")
    for call in calls:
        selected = [by_id[aid] for aid in call["attempt_ids"]]
        require(all(a["call_id"] == call["call_id"] for a in selected), "Attempt references wrong call")
        prefix, suffix = template.split("{{CARDS}}")
        prompt = prefix.replace("{{TAXONOMY}}", library_cards.serialize_card(manifest["taxonomy"])) + "\n\n".join(
            library_cards.card_text(a["packet"]["card"]) for a in selected) + suffix
        require(inputs[call["call_id"]] == prompt.encode("utf-8"), "Modified batch input or reordered cards")
        require(call["schema_text"] == receipts["config"]["output_schema_text"], "Call output schema differs from freeze")
        envelope = outputs[call["call_id"]]
        structured = envelope.get("structured_output", envelope)
        if any(a["outcome"] in {"accepted", "unmapped", "unsupported"} for a in selected):
            require(Draft202012Validator(decode_json(call["schema_text"])).is_valid(structured), "Schema-invalid model reply cannot be successful")
        result_rows = envelope.get("structured_output", envelope)
        result_rows = result_rows.get("results", []) if isinstance(result_rows, dict) else []
        result_rows = result_rows if isinstance(result_rows, list) else []
        for a in selected:
            matches = [r.get("result") for r in result_rows if isinstance(r, dict) and r.get("video_id") == a["video_id"]]
            original = matches[0] if len(matches) == 1 and isinstance(matches[0], dict) else None
            require(a["model_result"] == original, "Original model result was overwritten")
            if a["outcome"] in {"accepted", "unmapped", "unsupported"}:
                require(original == a["result"] and call["exit_status"] == 0 and not call["timed_out"] and not call["cancellation"], "Successful attempt lacks unique successful process result")
            require(a["usage"]["status"] == "unavailable" and a["estimates"]["total_cost_usd"] is None, "Item views must not duplicate call usage/estimates")
    totals = receipts["totals"]
    expected = dict(model_calls=len(calls), item_attempts=len(by_id),
        prompt_bytes=sum(c["stdin"]["bytes"] for c in calls), response_bytes=sum(c["stdout"]["bytes"] for c in calls),
        stderr_bytes=sum(c["stderr"]["bytes"] for c in calls), schema_bytes=sum(len(c["schema_text"].encode("utf-8")) for c in calls))
    expected["serialized_input_bytes"] = expected["prompt_bytes"] + expected["schema_bytes"]
    require(all(totals[k] == v for k, v in expected.items()), "Process/byte totals mismatch")
    require(receipts["accounting"] == call_accounting(calls), "Invented or double-counted usage/cost totals")
    execution = receipts["execution"]
    start, end = execution["start_monotonic_ns"], execution["end_monotonic_ns"]
    require(end >= start and totals["wall_ms"] == (end - start) // 1_000_000, "Run monotonic timeline mismatch")
    points = []
    for c in calls:
        require(start <= c["start_monotonic_ns"] <= c["end_monotonic_ns"] <= end, "Call outside run timeline")
        if c["start_monotonic_ns"] != c["end_monotonic_ns"]:
            points.extend([(c["start_monotonic_ns"], 1), (c["end_monotonic_ns"], -1)])
    active = 0
    for _, delta in sorted(points):
        active += delta
        require(active <= receipts["config"]["concurrency"], "Concurrent process limit exceeded")
    for event in receipts["completion_order"]:
        require(start <= event["completed_monotonic_ns"] <= end, "Completion outside run timeline")
    require(not execution["cleanup"]["errors"], "Cleanup errors require audit/repair")
    for artifact in execution["fingerprints"].values():
        artifact_bytes(artifact, artifact_root)
    require(execution["fingerprints"]["prompt"]["sha256"] == manifest["hashes"]["prompt_file_sha256"] and
            execution["fingerprints"]["card_builder"]["sha256"] == manifest["hashes"]["card_builder_sha256"], "Execution fingerprints differ from frozen inputs")
    _check_completion_guard(receipts)
    http = _check_http(receipts, artifact_root)
    _check_state_artifacts(receipts, manifest, artifact_root, http)
    response = receipts["preview"]["response"]
    require(response.get("can_apply") is False, "Preview did not refuse application")


SUPPORT_SCHEMA = object_schema(dict(video_id=ID, source_revision=HASH, card_hash=HASH,
                                   excerpt_id=HASH, quote=dict(type="string", minLength=1, maxLength=1000)))
CARD_KEY = dict(type="string", pattern=r"^c[0-9]{3}$")
SUPPORT_REFERENCE_SCHEMA = object_schema(dict(support_key=dict(type="string", pattern=r"^c[0-9]{3}-[1-9][0-9]*$")))
INDUCTION_NODE_SCHEMA = object_schema(dict(
    shelf_id=ID, path=array_schema(ID, minItems=1, maxItems=3), definition=ID,
    include=array_schema(ID, minItems=1), exclude=array_schema(ID, minItems=1),
    sibling_cues=array_schema(object_schema(dict(include_cue=ID, confusing_alternative=ID, evidence_needed=ID)), minItems=1),
    supporting_evidence=array_schema(SUPPORT_SCHEMA)))
EXPANDED_PROPOSAL_SCHEMA = object_schema(dict(
    version_id=ID, parent_version_id=ID, nodes=array_schema(INDUCTION_NODE_SCHEMA, minItems=1),
    coverage_ledger=array_schema(object_schema(dict(video_id=ID,
        disposition=dict(enum=["proposed_concept", "existing_concept", "still_unmapped", "unsupported"]),
        shelf_ids=array_schema(ID, uniqueItems=True), evidence=array_schema(SUPPORT_SCHEMA, uniqueItems=True),
        reason=dict(type="string", minLength=1, maxLength=160)))),
    diff=object_schema(dict(preserved=array_schema(ID, uniqueItems=True), added=array_schema(ID, uniqueItems=True),
        renamed=array_schema(JSON_OBJECT), merged=array_schema(JSON_OBJECT), split=array_schema(JSON_OBJECT),
        retired=array_schema(ID, uniqueItems=True))),
    pin_impact_report=JSON_OBJECT, rejected_proposals=array_schema(object_schema(dict(proposal=ID, reason=ID)))))
PROPOSAL_SCHEMA = copy.deepcopy(EXPANDED_PROPOSAL_SCHEMA)
PROPOSAL_SCHEMA["properties"]["nodes"]["items"]["properties"]["supporting_evidence"] = array_schema(SUPPORT_REFERENCE_SCHEMA)
_ledger_schema = PROPOSAL_SCHEMA["properties"]["coverage_ledger"]["items"]
_ledger_schema["properties"].pop("video_id")
_ledger_schema["properties"]["card_key"] = CARD_KEY
_ledger_schema["required"] = ["card_key" if key == "video_id" else key for key in _ledger_schema["required"]]
_ledger_schema["properties"]["evidence"] = array_schema(SUPPORT_REFERENCE_SCHEMA, uniqueItems=True)
INDUCTION_RECEIPT_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "urn:uoink:induction-receipts:2026-09-05:v1",
    **object_schema(dict(kind=dict(const="induction-receipts"), schema_version=dict(const=1),
        run_id=ID, mode=dict(enum=["mock", "subscription"]), status=dict(enum=["completed", "aborted"]), abort_reason=NULL_ID,
        inputs=object_schema(dict(induction_manifest_sha256=HASH, archived_receipts_sha256=HASH,
            taxonomy_file_sha256=HASH, batch_prompt_sha256=HASH, consolidation_prompt_sha256=HASH)),
        batch_prompt=ARTIFACT_SCHEMA, consolidation_prompt=ARTIFACT_SCHEMA, taxonomy=ARTIFACT_SCHEMA,
        calls=array_schema(CALL_SCHEMA, minItems=1),
        batches=array_schema(object_schema(dict(call_id=ID, video_ids=array_schema(ID, minItems=1, maxItems=25, uniqueItems=True)))),
        consolidation_call_id=ID, proposal=PROPOSAL_SCHEMA, proposal_artifact=ARTIFACT_SCHEMA,
        accounting=JSON_OBJECT, execution=with_optional(object_schema(dict(git_sha=dict(type="string", pattern="^[a-f0-9]{40}$"),
            start_monotonic_ns=COUNT, end_monotonic_ns=COUNT,
            fingerprints=object_schema({name: ARTIFACT_SCHEMA for name in ("runner", "validator", "card_builder")}))),
            # Contract v1.3 isolation and provenance evidence (audit B8, B2-H).
            dict(checkout_root=TEXT, cwd=TEXT, model=ID, effort=JSON_OBJECT, concurrency=COUNT, call_timeout_s=COUNT,
                 environment=JSON_OBJECT, database_opened=dict(const=False), helper_opened=dict(const=False),
                 network_egress=TEXT, input_paths=JSON_OBJECT, output_root=TEXT,
                 resume=dict(anyOf=[JSON_OBJECT, dict(type="null")])))))}
INDUCTION_RECEIPT_SCHEMA = with_optional(INDUCTION_RECEIPT_SCHEMA, dict(
    induction_state=object_schema(dict(source=TEXT, archived_receipts_sha256=HASH, pins=COUNT, memberships=COUNT,
                                       item_policies=COUNT, active_version_id=dict(anyOf=[ID, dict(type="null")])))))


def _check_support(support, cards, frozen):
    vid = support["video_id"]
    require(vid in frozen and vid in cards, "Support outside induction manifest")
    card = cards[vid]
    require(card["video_id"] == vid and support["source_revision"] == card["source_revision"] == frozen[vid]["source_revision"] and
            support["card_hash"] == card["card_hash"] == frozen[vid]["card_hash"] ==
            library_cards._hash({k: v for k, v in card.items() if k != "card_hash"}), "Support source/card binding mismatch")
    excerpt = next((e for e in card["excerpts"] if e["excerpt_id"] == support["excerpt_id"]), None)
    require(excerpt is not None, "Support must name an original excerpt, not title/summary")
    quote = normalize_quote(support["quote"])
    require(1 <= len(quote.split()) <= 24 and len(support["quote"]) <= 1000 and
            quote in normalize_quote(excerpt["text"]), "Support quote must occur in one excerpt and contain 1 to 24 words")
    require(excerpt["evidence_kind"] == "timed_clip" or
            (excerpt["evidence_kind"] == "text_only" and card.get("source_type") in
             {"page", "x_article", "x_thread", "reddit_thread", "note"}), "Ineligible original source evidence")


def _recorded_induction_supports(batch_outputs, video_id, *, candidates):
    """Read only the batch recorded for this card, and only its evidence fields."""
    output = batch_outputs.get(video_id)
    require(isinstance(output, dict), "Missing recorded batch output for induction card")
    rows = output.get("candidates" if candidates else "dispositions", [])
    require(isinstance(rows, list), "Recorded batch candidates/dispositions must be arrays")
    supports = []
    for row in rows:
        require(isinstance(row, dict), "Recorded batch candidate/disposition must be an object")
        if not candidates and row.get("video_id") != video_id:
            continue
        evidence = row.get("supporting_evidence" if candidates else "evidence", [])
        require(isinstance(evidence, list), "Recorded batch evidence must be an array")
        supports.extend(s for s in evidence if isinstance(s, dict) and s.get("video_id") == video_id)
    return supports


def derive_induction_keys(induction, batches, batch_proposals):
    """Assign occurrence keys from manifest order and recorded batch array order.

    Per batch, visit candidates/supporting_evidence before dispositions/evidence.
    Identical objects at different locations get distinct keys; their origin is
    retained so ledger and node references cannot borrow each other's evidence.
    This helper derives identities, not source validity; selected supports still
    pass the complete evidence checks after expansion.
    """
    items = induction["items"]
    ids = [row["video_id"] for row in items]
    require(len(ids) == len(set(ids)) == 225, "Induction keys require 225 distinct manifest cards")
    require(len(batches) == len(batch_proposals), "Induction key batches/output count mismatch")
    selected = [vid for batch in batches for vid in batch["video_ids"]]
    require(len(selected) == len(set(selected)) == 225 and set(selected) == set(ids),
            "Induction key batches must cover the manifest once")
    card_keys = {vid: f"c{index:03d}" for index, vid in enumerate(ids, 1)}
    table = dict(cards={card_keys[row["video_id"]]: {k: row[k] for k in ("video_id", "source_revision", "card_hash")}
                        for row in items}, supports={})
    counts = Counter()
    skipped = []
    for batch, output in zip(batches, batch_proposals):
        require(isinstance(output, dict), "Recorded batch output must be an object")
        for kind, field, evidence_field in (("candidate", "candidates", "supporting_evidence"),
                                            ("disposition", "dispositions", "evidence")):
            rows = output.get(field, [])
            require(isinstance(rows, list), "Recorded batch candidates/dispositions must be arrays")
            for row_index, row in enumerate(rows):
                require(isinstance(row, dict), "Recorded batch candidate/disposition must be an object")
                evidence = row.get(evidence_field, [])
                require(isinstance(evidence, list), "Recorded batch evidence must be an array")
                for support_index, support in enumerate(evidence):
                    require(isinstance(support, dict), "Recorded batch support must be an object")
                    vid = support.get("video_id")
                    # Contract v1.3: a support whose identity does not belong to its batch
                    # (a model-transcribed 19-digit id, typically) gets no key and cannot
                    # be referenced; it is listed, in output order, so the omission is
                    # reproducible from the recorded bytes. It is never fatal.
                    if vid not in batch["video_ids"]:
                        skipped.append(dict(call_id=batch["call_id"], kind=kind, row=row_index, support=support_index,
                                            video_id=vid if isinstance(vid, str) else None,
                                            reason="support video_id is not a card of its batch"))
                        continue
                    if kind == "disposition" and row.get("video_id") != vid:
                        skipped.append(dict(call_id=batch["call_id"], kind=kind, row=row_index, support=support_index,
                                            video_id=vid, reason="disposition evidence names a different card than its row"))
                        continue
                    counts[vid] += 1
                    key = card_keys[vid]
                    table["supports"][f"{key}-{counts[vid]}"] = dict(card_key=key, kind=kind, support=copy.deepcopy(support))
    if skipped:  # absent when empty so contract v1.2 renderings stay byte-identical
        table["skipped"] = skipped
    return table


def render_induction_consolidation(template, batch_proposals, keys):
    """Fill both slots once, without interpreting placeholder text in evidence."""
    require(template.count("{{PROPOSALS}}") == template.count("{{KEYS}}") == 1,
            "Consolidation requires exactly one PROPOSALS and one KEYS placeholder")
    values = {"{{PROPOSALS}}": library_cards.serialize_card(batch_proposals),
              "{{KEYS}}": library_cards.serialize_card(keys)}
    return re.sub(r"\{\{(?:PROPOSALS|KEYS)\}\}", lambda match: values[match.group()], template)


def expand_induction_proposal(proposal, keys):
    """Return a separate full-support document; never mutate recorded model output.

    Receipt validation always re-derives keys from checked batch stdout. Standalone
    callers must provide that same table; this helper alone proves no provenance.
    """
    Draft202012Validator(PROPOSAL_SCHEMA).validate(proposal)
    expanded = copy.deepcopy(proposal)

    def resolve(reference, kind, card_key=None):
        key = reference["support_key"]
        require(key in keys["supports"], f"Unknown induction support key: {key}")
        entry = keys["supports"][key]
        require(entry["kind"] == kind, f"Support key must name recorded batch {kind} evidence: {key}")
        require(card_key is None or entry["card_key"] == card_key, "Ledger support key belongs to another card")
        return copy.deepcopy(entry["support"])

    for node in expanded["nodes"]:
        node["supporting_evidence"] = [resolve(ref, "candidate") for ref in node["supporting_evidence"]]
    for row in expanded["coverage_ledger"]:
        key = row.pop("card_key")
        require(key in keys["cards"], f"Unknown induction card key: {key}")
        row["video_id"] = keys["cards"][key]["video_id"]
        row["evidence"] = [resolve(ref, "disposition", key) for ref in row["evidence"]]
    return expanded


def validate_induction_proposal(proposal, induction, cards, taxonomy, *, batch_outputs):
    """Validate an expanded proposal containing exact full support objects.

    batch_outputs maps each card ID to its own recorded batch's decoded output.
    Receipt validation constructs this binding from checked calls; a standalone
    proposal check cannot authenticate supplied batch bytes or process provenance.
    """
    Draft202012Validator(EXPANDED_PROPOSAL_SCHEMA).validate(proposal)
    frozen = {r["video_id"]: r for r in induction["items"]}
    require(len(frozen) == len(induction["items"]) == 225, "Induction requires all 225 distinct cards")
    nodes = {n["shelf_id"]: n for n in proposal["nodes"]}
    require(len(nodes) == len(proposal["nodes"]), "Duplicate proposed shelf ID")
    paths = {tuple(unicodedata.normalize("NFC", p).strip() for p in n["path"]) for n in nodes.values()}
    require(len(paths) == len(nodes) and all(all(p) for p in paths), "Duplicate/empty proposed path")
    require(all(len(p) == 1 or p[:-1] in paths for p in paths), "Proposed path has no parent")
    old = {n["shelf_id"]: n for n in taxonomy["nodes"] if not n.get("retired")}
    require(proposal["parent_version_id"] == taxonomy["version_id"] and proposal["version_id"] != taxonomy["version_id"], "Proposal revision/parent mismatch")
    require(set(proposal["diff"]["added"]) == set(nodes) - set(old), "Taxonomy additions differ from diff")
    require(set(proposal["diff"]["preserved"]) <= set(nodes) & set(old), "Preserved shelf absent from base/proposal")
    fields = ("path", "definition", "include", "exclude")
    for sid, node in nodes.items():
        for support in node["supporting_evidence"]:
            _check_support(support, cards, frozen)
            require(support in _recorded_induction_supports(batch_outputs, support["video_id"], candidates=True),
                    "Node support differs from recorded batch candidate evidence")
        if sid not in old:
            require(len({e["video_id"] for e in node["supporting_evidence"]}) >= 5, "New concept requires five distinct supporting cards")
            require(not any(all(node[k] == prior[k] for k in fields) for prior in old.values()), "Unchanged concept must preserve its shelf ID")
        if sid in proposal["diff"]["preserved"]:
            require(all(node[k] == old[sid][k] for k in fields), "Preserved concept changed without diff")
        require(set(node["include"]) <= {c["include_cue"] for c in node["sibling_cues"]}, "Include cue lacks confusing alternative and distinguishing evidence")
    removed = set(old) - set(nodes)
    accounted = set(proposal["diff"]["retired"])
    for operation in ("renamed", "merged", "split"):
        for mapping in proposal["diff"][operation]:
            require(set(mapping) == {"from_shelf_ids", "to_shelf_ids", "reason"} and mapping["from_shelf_ids"] and
                    mapping["to_shelf_ids"] and isinstance(mapping["reason"], str) and mapping["reason"].strip(), "Explicit taxonomy mapping required")
            require(set(mapping["from_shelf_ids"]) <= set(old) and set(mapping["to_shelf_ids"]) <= set(nodes), "Taxonomy mapping references unknown shelf")
            accounted.update(mapping["from_shelf_ids"])
    require(removed <= accounted and set(proposal["diff"]["retired"]) <= removed, "Removed shelves lack explicit mapping")
    changed = {sid for sid in set(old) & set(nodes) if any(nodes[sid][k] != old[sid][k] for k in fields)}
    require(changed <= accounted, "Changed concepts lack explicit mapping")
    require(proposal["pin_impact_report"].get("silent_redirects") is False and
            isinstance(proposal["pin_impact_report"].get("items"), list), "Pin-impact report must prohibit silent redirects")
    ledger = proposal["coverage_ledger"]
    require(len(ledger) == 225 and {r["video_id"] for r in ledger} == set(frozen), "Coverage ledger missing/duplicate induction ID")
    for row in ledger:
        require(set(row["shelf_ids"]) <= set(nodes), "Ledger references unknown concept")
        mapped = row["disposition"] in {"proposed_concept", "existing_concept"}
        require(bool(row["shelf_ids"]) == mapped and bool(row["evidence"]) == mapped, "Ledger disposition lacks evidence/concept or falsely maps refusal")
        if row["disposition"] == "existing_concept":
            require(set(row["shelf_ids"]) <= set(old), "Existing-concept ledger names a new shelf")
        require(len({s["excerpt_id"] for s in row["evidence"]}) == len(row["evidence"]), "Duplicate ledger excerpt reference")
        for support in row["evidence"]:
            require(support["video_id"] == row["video_id"], "Ledger support belongs to another card")
            _check_support(support, cards, frozen)
            require(support in _recorded_induction_supports(batch_outputs, row["video_id"], candidates=False),
                    "Ledger support differs from recorded batch disposition evidence")


def validate_induction_receipts(receipts, induction=None, *, artifact_root=ROOT, require_real=False):
    canonical(receipts)
    Draft202012Validator(INDUCTION_RECEIPT_SCHEMA).validate(receipts)
    require(not require_real or receipts["mode"] == "subscription", "Mock induction is fixture evidence only")
    require(receipts["status"] == "completed" and receipts["abort_reason"] is None, "Aborted induction is retained, not accepted")
    verify_stage2_freezes()
    frozen_induction = read_json(INDUCTION_MANIFEST)
    require(induction is None or induction == frozen_induction, "Induction input differs from freeze")
    induction = frozen_induction
    inputs = receipts["inputs"]
    require(inputs["induction_manifest_sha256"] == sha(INDUCTION_MANIFEST.read_bytes()) and
            inputs["archived_receipts_sha256"] == ARCHIVE_SHA256, "Induction provenance mismatch")
    taxonomy_raw = artifact_bytes(receipts["taxonomy"], artifact_root)
    require(sha(taxonomy_raw) == inputs["taxonomy_file_sha256"] == read_json(MANIFEST)["files"]["taxonomy"]["sha256"], "Induction baseline taxonomy changed")
    taxonomy = decode_json(taxonomy_raw)
    prompts = {}
    for name in ("batch_prompt", "consolidation_prompt"):
        raw = artifact_bytes(receipts[name], artifact_root)
        require(sha(raw) == inputs[name + "_sha256"], "Induction prompt freeze mismatch")
        prompts[name] = raw.decode("utf-8")
    archived = read_json(ARCHIVE)
    wanted = {r["video_id"] for r in induction["items"]}
    cards = {a["video_id"]: a["packet"]["card"] for a in archived["attempts"] if a["video_id"] in wanted}
    call_inputs, outputs = _check_calls(receipts["calls"], artifact_root)
    calls = {c["call_id"]: c for c in receipts["calls"]}
    final_id = receipts["consolidation_call_id"]
    batch_ids = [b["call_id"] for b in receipts["batches"]]
    require(len(set(batch_ids)) == len(batch_ids) and final_id not in batch_ids and
            set(calls) == set(batch_ids) | {final_id}, "Missing/duplicate/unaccounted induction call")
    selected = [vid for b in receipts["batches"] for vid in b["video_ids"]]
    require(len(selected) == len(set(selected)) == 225 and set(selected) == wanted, "Induction batches must cover 225 identities once")
    batch_proposals, batch_outputs = [], {}
    for batch in receipts["batches"]:
        call = calls[batch["call_id"]]
        require(call["attempt_ids"] == batch["video_ids"], "Induction call attempt IDs must be its ordered card IDs")
        template = prompts["batch_prompt"]
        require(template.count("{{TAXONOMY}}") == template.count("{{CARDS}}") == 1, "Induction batch placeholders changed")
        prefix, suffix = template.split("{{CARDS}}")
        expected = prefix.replace("{{TAXONOMY}}", library_cards.serialize_card(taxonomy)) + "\n\n".join(
            library_cards.card_text(cards[vid]) for vid in batch["video_ids"]) + suffix
        require(call_inputs[call["call_id"]] == expected.encode("utf-8"), "Induction prompt contains modified cards or extra material")
        output = outputs[call["call_id"]].get("structured_output", outputs[call["call_id"]])
        batch_proposals.append(output)
        batch_outputs.update({vid: output for vid in batch["video_ids"]})
    template = prompts["consolidation_prompt"]
    keys = derive_induction_keys(induction, receipts["batches"], batch_proposals)
    require(call_inputs[final_id] == render_induction_consolidation(template, batch_proposals, keys).encode("utf-8"),
            "Consolidation input differs from original batch proposals or derived keys")
    require(calls[final_id]["attempt_ids"] == ["consolidation"], "Consolidation call identity mismatch")
    require(all(c["exit_status"] == 0 and not c["timed_out"] and not c["cancellation"] for c in calls.values()), "Failed induction call cannot establish a completed proposal")
    proposal = receipts["proposal"]
    require(outputs[final_id].get("structured_output", outputs[final_id]) == proposal and
            decode_json(artifact_bytes(receipts["proposal_artifact"], artifact_root)) == proposal, "Proposal differs from original consolidation output")
    require(receipts["accounting"] == call_accounting(receipts["calls"]), "Induction usage/cost accounting mismatch")
    execution = receipts["execution"]
    require(execution["start_monotonic_ns"] <= min(c["start_monotonic_ns"] for c in calls.values()) and
            max(c["end_monotonic_ns"] for c in calls.values()) <= execution["end_monotonic_ns"], "Induction call outside run timeline")
    require(all(c["end_monotonic_ns"] <= calls[final_id]["start_monotonic_ns"] for cid, c in calls.items() if cid != final_id), "Consolidation precedes a batch completion")
    for record in execution["fingerprints"].values():
        artifact_bytes(record, artifact_root)
    expanded = expand_induction_proposal(proposal, keys)
    validate_induction_proposal(expanded, induction, cards, taxonomy, batch_outputs=batch_outputs)
    return dict(status="INDUCTION_FIXTURE_VALID" if receipts["mode"] == "mock" else "INDUCTION_RECEIPTS_VALID_AUDIT_REQUIRED",
                target_count=225, call_count=len(calls), proposal_approved=False)


def verify_manifest(manifest, root=ROOT):
    """Check the freeze against this checkout, without opening a database or corpus."""
    require(manifest["freeze_status"] == "frozen", "Input freeze is incomplete")
    require(manifest["schema_version"] == 1, "Unknown manifest schema")
    require(manifest["source"]["sha256"] == SOURCE_SHA256, "Wrong named source hash")
    items = manifest["items"]
    require(len(items) == 548 and items == sorted(items), "Expected 548 ordered source pairs")
    require(len({entry[0] for entry in items}) == 548, "Duplicate manifest identity")
    payload = dict(items=items, exclusions=manifest["exclusions"])
    require(digest(payload) == manifest["manifest_hash"], "Manifest hash mismatch")
    require(set(manifest["exclusions"]) <= {entry[0] for entry in items}, "Unknown excluded identity")
    for frozen in manifest["files"].values():
        path = (root / frozen["path"]).resolve()
        require(path.is_relative_to(root.resolve()), "Frozen file escapes checkout")
        require(sha(path.read_bytes()) == frozen["sha256"], f"Frozen file changed: {frozen['path']}")
    taxonomy = normalized_taxonomy(read_json(root / manifest["files"]["taxonomy"]["path"]))
    require(taxonomy == manifest["taxonomy"], "Normalized taxonomy changed")
    require(manifest["card_profile"] == PROFILE, "Card profile changed")
    require(digest(PROFILE) == manifest["hashes"]["card_profile_hash"], "Card profile hash mismatch")
    split = read_json(root / manifest["files"]["holdout"]["path"])
    heldout = sorted(entry["video_id"] for rows in split["strata"].values() for entry in rows)
    require(len(heldout) == len(set(heldout)) == 60, "Holdout requires 60 distinct identities")
    require(heldout == manifest["holdout"]["ids"], "Holdout identities changed")
    require(digest(heldout) == manifest["hashes"]["holdout_ids_hash"], "Holdout ID hash mismatch")
    cards = manifest["cards"]
    require(set(cards) == {entry[0] for entry in items}, "Missing frozen card")
    for video_id, revision in items:
        require(cards[video_id]["source_revision"] == revision, "Frozen card revision mismatch")
    require(digest(cards) == manifest["cards_hash"], "Frozen card index hash mismatch")
    require(set(manifest["corpus_heads"]) == set(cards), "Missing corpus head hash")
    require(digest(manifest["corpus_heads"]) == manifest["corpus_heads_hash"], "Corpus head index hash mismatch")
    expected = dict(manifest_hash=manifest["manifest_hash"], source_sha256=SOURCE_SHA256,
                    taxonomy_revision_hash=taxonomy["revision_hash"], card_profile_hash=digest(PROFILE),
                    holdout_ids_hash=digest(heldout), cards_hash=digest(cards),
                    corpus_heads_hash=digest(manifest["corpus_heads"]), implementation_hash=digest(manifest["files"]))
    for name, key in [("taxonomy", "taxonomy_file_sha256"), ("prompt", "prompt_file_sha256"),
                      ("card_builder", "card_builder_sha256"), ("holdout", "holdout_file_sha256"),
                      ("gold", "gold_file_sha256")]:
        expected[key] = manifest["files"][name]["sha256"]
    expected["prompt_sha256"] = sha((root / manifest["files"]["prompt"]["path"]).read_text(encoding="utf-8").encode("utf-8"))
    require(expected == manifest["hashes"], "Freeze hash aliases disagree")
    return manifest


def render_prompt(template, taxonomy, card):
    require(template.count("{{TAXONOMY}}") == template.count("{{CARDS}}") == 1, "Prompt placeholders changed")
    # Replace placeholders once, before incorporating any untrusted card text.
    prefix, suffix = template.split("{{CARDS}}")
    return (prefix.replace("{{TAXONOMY}}", library_cards.serialize_card(taxonomy))
            + library_cards.card_text(card) + suffix)


def freeze_inputs(source, *, allow_install_corpus=False, stage=1):
    """Freeze the named copy and bounded Markdown heads; no helper/index defaults.

    stage=2 binds the stage 2 files (STAGE_FILES[2]); the card and head freeze is identical
    because the card builder is shared.

    A blocked head is retained as an unresolved target, never silently excluded.
    --allow-install-corpus permits only the copy's explicit Markdown references,
    never the live database, token, settings, or arbitrary install files.
    """
    source = Path(source).resolve()
    require(source.name == "uoink-index-copy-2026-09-04-upgraded.db", "Use the explicitly named source copy")
    require(sha(source.read_bytes()) == SOURCE_SHA256, "Named source hash mismatch before copying")
    scratch = ROOT / "_scratch/proof/freeze"
    scratch.mkdir(parents=True, exist_ok=True)
    local = scratch / "source.db"
    require(source != local.resolve(), "Source and duplicate must differ")
    shutil.copyfile(source, local)
    require(sha(local.read_bytes()) == SOURCE_SHA256, "Duplicate differs from named source")
    original = sqlite3.connect(local.resolve().as_uri() + "?mode=ro", uri=True)
    original.execute("PRAGMA query_only=ON")
    schema_before = original.execute("SELECT max(version) FROM schema_version").fetchone()[0]
    original.close()
    upgraded = scratch / "upgraded.db"
    shutil.copyfile(local, upgraded)
    from index import Index
    index = Index.open(upgraded)
    index._conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    index.close()
    upgrade_sha256 = sha(upgraded.read_bytes())
    conn = sqlite3.connect(upgraded.resolve().as_uri() + "?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    files = {}
    for name, relative in dict(STAGE_FILES[stage],
                               prompt="scripts/librarian/prompts/assign.md", card_builder="library_cards.py",
                               index="index.py", clips="clips.py",
                               provenance="provenance.py", service="library_work.py",
                               migration26="migrations/0026_provenance_precedence.sql",
                               migration27="migrations/0027_library_substrate.sql").items():
        files[name] = dict(path=relative, sha256=sha((ROOT / relative).read_bytes()))
    if stage == 2:
        stage2_gold = read_json(ROOT / files["gold"]["path"])
        require(isinstance(stage2_gold, list) and len(stage2_gold) == 60 and
                all(item.get("sealed") is True for item in stage2_gold), "Stage 2 gold must be the sealed adjudicated labels")
    taxonomy = normalized_taxonomy(read_json(ROOT / files["taxonomy"]["path"]))
    split = read_json(ROOT / files["holdout"]["path"])
    heldout_ids = sorted(entry["video_id"] for rows in split["strata"].values() for entry in rows)
    install = Path("C:/Users/hello/AppData/Local/Uoink")
    allowed = [Path("E:/Uoink"), Path("C:/Users/hello/OneDrive/Desktop/Uoink")]
    if allow_install_corpus:
        allowed.append(install)
    items, cards, blockers, heads = [], {}, [], {}
    strata = Counter()
    try:
        rows = list(conn.execute("SELECT * FROM yoinks ORDER BY video_id"))
        require(len(rows) == 548, "Named source no longer has 548 targets")
        schema = conn.execute("SELECT max(version) FROM schema_version").fetchone()[0]
        for row in rows:
            item = dict(row)
            video_id = item["video_id"]
            raw_path = Path(item["corpus_path"]) if item.get("corpus_path") else None
            reason = None
            if item.get("deleted_at") is not None:
                reason = "Deleted target in named source"
            elif raw_path is None:
                reason = "Named source has no corpus path"
            elif raw_path.is_relative_to(install) and not allow_install_corpus:
                reason = "Corpus head under protected install root; read permission unresolved"
            elif raw_path.suffix.lower() != ".md" or not any(raw_path.is_relative_to(base) for base in allowed):
                reason = "Corpus path is outside the explicitly allowed document roots"
            raw = None
            if reason is None:
                resolved = raw_path.resolve()
                if not any(resolved.is_relative_to(base.resolve()) for base in allowed):
                    reason = "Corpus symlink escapes allowed document roots"
                elif any((parent / ".git").exists() for parent in resolved.parents if parent != parent.parent):
                    reason = "Corpus path enters a project checkout"
                else:
                    try:
                        with resolved.open("rb") as stream:
                            raw = stream.read(library_cards.CORPUS_READ_BYTES)
                    except OSError as exc:
                        reason = f"Corpus head unavailable: {type(exc).__name__}"
            if reason is not None:
                blockers.append(dict(video_id=video_id, reason=reason))
                items.append([video_id, None])
                continue
            text = raw.decode("utf-8", errors="replace")
            clips = [dict(clip) for clip in conn.execute("SELECT * FROM clips WHERE video_id=? ORDER BY seq", (video_id,))]
            card = library_cards.build_card(item, clips, corpus_text=text, profile="librarian")
            stratum = "timed_evidence" if any(e["evidence_kind"] == "timed_clip" for e in card["excerpts"]) else "text_only"
            strata[stratum] += 1
            entry = dict(source_revision=card["source_revision"], card_hash=card["card_hash"],
                         card_bytes=len(library_cards.card_text(card).encode("utf-8")))
            cards[video_id] = dict(entry, stratum=stratum, source_type=card.get("source_type"), status=card["status"])
            heads[video_id] = dict(raw_sha256=sha(raw), decoded_sha256=sha(text.encode("utf-8")), bytes=len(raw))
            items.append([video_id, card["source_revision"]])
            head_dir = scratch / "heads"
            head_dir.mkdir(exist_ok=True)
            (head_dir / (sha(video_id.encode("utf-8")) + ".bin")).write_bytes(raw)
        require(sha(source.read_bytes()) == SOURCE_SHA256, "Named source changed during freeze")
    finally:
        conn.close()
    manifest_hash = digest(dict(items=items, exclusions={}))
    hashes = dict(manifest_hash=manifest_hash, source_sha256=SOURCE_SHA256,
                  taxonomy_file_sha256=files["taxonomy"]["sha256"], taxonomy_revision_hash=taxonomy["revision_hash"],
                  prompt_file_sha256=files["prompt"]["sha256"],
                  prompt_sha256=sha((ROOT / files["prompt"]["path"]).read_text(encoding="utf-8").encode("utf-8")),
                  card_profile_hash=digest(PROFILE), card_builder_sha256=files["card_builder"]["sha256"],
                  holdout_file_sha256=files["holdout"]["sha256"], holdout_ids_hash=digest(heldout_ids),
                  gold_file_sha256=files["gold"]["sha256"], cards_hash=digest(cards), corpus_heads_hash=digest(heads),
                  implementation_hash=digest(files))
    heldout_strata = {name: sorted(entry["video_id"] for entry in entries) for name, entries in split["strata"].items()}
    remeasured = Counter(cards[video_id]["stratum"] for video_id in heldout_ids if video_id in cards)
    return dict(schema_version=1, freeze_status="blocked" if blockers else "frozen", contract_version=CONTRACT,
                source=dict(name=source.name, sha256=SOURCE_SHA256, bytes=source.stat().st_size, schema_version=schema_before),
                upgrade=dict(sha256=upgrade_sha256, schema_version=schema,
                             hash_note="Measured duplicate only; migration timestamps make file hashes run-specific"),
                ordering="video_id ascending, Unicode code-point order", items=items, exclusions={},
                manifest_hash=manifest_hash, manifest_hash_kind="provisional-unresolved-heads" if blockers else "library_work.manifest-v1",
                hashes=hashes, files=files, card_profile=PROFILE, taxonomy=taxonomy,
                cards=cards, cards_hash=digest(cards), corpus_heads=heads, corpus_heads_hash=digest(heads),
                measured_strata=dict(strata), unresolved_targets=blockers,
                holdout=dict(ids=heldout_ids, declared_strata=heldout_strata, remeasured_strata=dict(remeasured),
                             coverage_floor=0.80, precision_target=0.90,
                             gold_mapping="longest frozen taxonomy path prefix; no match is unscorable and blocks proof"),
                execution=dict(model="claude-sonnet-5", concurrency=4, max_retries=1, wall_budget_ms=7200000,
                               error_rate_limit=0.10, error_rate_min_attempts=20,
                               error_rate_policy="Astra operational abort threshold, additional to Fable's quality thresholds"))


def _check_isolation(config, mode, checkout_root=None):
    parsed = urlsplit(config["base_url"])
    require(parsed.scheme == "http" and parsed.hostname == "127.0.0.1" and
            parsed.port is not None and parsed.port != 5179 and not parsed.username and
            not parsed.password and parsed.path in ("", "/") and not parsed.query and not parsed.fragment,
            "Expected isolated loopback HTTP endpoint; port 5179 is forbidden")
    require(0 < parsed.port < 65536, "Invalid helper port")
    if mode == "subscription":
        require(parsed.port == 5180, "Subscription proof requires port 5180")
    # Historical containment is lexical. Never resolve/open a historical path,
    # including a Windows path when auditing on POSIX (or the reverse).
    flavor = PureWindowsPath if PureWindowsPath(config["isolation_root"]).drive else PurePosixPath
    root = flavor(str(checkout_root or ROOT))
    isolated = flavor(config["isolation_root"])
    require(root.is_absolute() and isolated.is_absolute(), "Isolation declarations must be absolute")
    require(".." not in root.parts and ".." not in isolated.parts, "Historical traversal is forbidden")
    scratch = root / "_scratch/proof"
    require(isolated.is_relative_to(scratch) and isolated != scratch, "Isolation root must be below _scratch/proof")
    for name, raw in {**config["environment"], "index_path": config["index_path"], "token_path": config["token_path"]}.items():
        path = flavor(raw)
        require(path.is_absolute() and ".." not in path.parts and path.is_relative_to(isolated), f"{name} escapes isolated root")
    require(flavor(config["index_path"]) == isolated / "Uoink/index.db", "Unexpected isolated index path")


def _check_evidence(result, card, taxonomy):
    require(result.get("outcome") == "assigned", "Accepted receipt must contain assigned result")
    memberships = result.get("memberships")
    require(isinstance(memberships, list) and 1 <= len(memberships) <= 3, "Expected 1-3 memberships")
    nodes = {node["shelf_id"]: node for node in taxonomy["nodes"] if not node["retired"]}
    seen = set()
    for member in memberships:
        shelf = member.get("shelf_id")
        require(shelf in nodes and shelf not in seen, "Invalid/duplicate shelf identity")
        seen.add(shelf)
        require(member.get("shelf_path") == nodes[shelf]["path"], "Shelf path differs from frozen taxonomy")
        confidence = member.get("confidence")
        require(type(confidence) in (int, float) and math.isfinite(confidence) and 0.60 <= confidence <= 1,
                "Invalid assignment confidence")
        evidence = member.get("evidence", {})
        require(evidence.get("basis") == "packet", "Proof evidence must use the supplied packet")
        require(evidence.get("card_hash") == card["card_hash"], "Evidence card identity mismatch")
        excerpt = next((entry for entry in card["excerpts"] if entry["excerpt_id"] == evidence.get("excerpt_id")), None)
        require(excerpt is not None and evidence.get("kind") == excerpt["evidence_kind"], "Evidence excerpt identity mismatch")
        quote = evidence.get("quote")
        require(isinstance(quote, str) and len(quote) <= 1000 and 1 <= len(normalize_quote(quote).split()) <= 24 and
                normalize_quote(quote) in normalize_quote(excerpt["text"]),
                "Evidence quote must occur in one excerpt and contain 1 to 24 words")
        if evidence["kind"] == "text_only":
            require(card.get("source_type") in {"page", "x_article", "x_thread", "reddit_thread", "note"},
                    "Source origin does not support original-prose evidence")
            require(excerpt.get("start") is None and excerpt.get("end") is None, "Text evidence has timing bounds")
        elif evidence["kind"] == "timed_clip":
            start, end = excerpt.get("start"), excerpt.get("end")
            require(type(start) in (int, float) and type(end) in (int, float) and
                    math.isfinite(start) and math.isfinite(end) and 0 <= start < end, "Invalid timed evidence bounds")
        else:
            raise ValueError("Unknown evidence kind")


def _response_object(attempt):
    try:
        value = decode_json(attempt["response_text"])
    except (ValueError, TypeError):
        return None
    return value if isinstance(value, dict) else None


def _check_usage(attempt, mode):
    usage, estimate = attempt["usage"], attempt["estimates"]
    raw = _response_object(attempt)
    if mode == "mock":
        require(usage["status"] == "unavailable" and estimate["total_cost_usd"] is None,
                "Mock usage/cost cannot be measured")
    if usage["status"] == "reported":
        require(raw is not None and isinstance(raw.get("usage"), dict), "Reported usage lacks CLI JSON usage")
        for public, cli in [("input_tokens", "input_tokens"), ("output_tokens", "output_tokens"),
                            ("cache_read_tokens", "cache_read_input_tokens"),
                            ("cache_create_tokens", "cache_creation_input_tokens")]:
            require(public in usage and raw["usage"].get(cli) == usage[public], f"CLI usage mismatch: {public}")
        models = set(raw.get("modelUsage", {}))
        if isinstance(raw.get("model"), str):
            models.add(raw["model"])
        require(usage["model"] in models, "Reported model lacks CLI provenance")
    if estimate["total_cost_usd"] is not None:
        require(estimate["source"] == "claude_cli_estimate" and raw is not None and
                raw.get("total_cost_usd") == estimate["total_cost_usd"], "Cost estimate lacks CLI provenance")
    else:
        require(estimate["source"] == "unavailable", "Null estimate must be unavailable")


def validate_receipts(receipts, manifest, *, require_real=False, root=ROOT, artifact_root=None,
                      require_whole_manifest=True):
    canonical(receipts)  # Reject NaN/infinity even when called directly from Python.
    Draft202012Validator(RECEIPT_SCHEMA).validate(receipts)
    v2 = receipts["schema_version"] == 2
    require(v2 or receipts["mode"] == "mock", "Measured receipts require schema_version 2; run R is historical diagnostic evidence")
    require(manifest.get("freeze_status") == "frozen", "Input freeze is incomplete")
    require(not require_real or receipts["mode"] == "subscription", "Mock receipts are fixture evidence only")
    require(receipts["inputs"] == manifest["hashes"], "Receipt input hashes differ from frozen inputs")
    require(receipts["status"] == "completed", f"Run aborted: {receipts['abort_reason']}")
    require(receipts["abort_reason"] is None, "Completed run has abort reason")
    ids = receipts["target_ids"]
    frozen_ids = [entry[0] for entry in manifest["items"]]
    require(ids == [video_id for video_id in frozen_ids if video_id in set(ids)], "Targets are unknown or out of frozen order")
    require(not require_whole_manifest or receipts["mode"] == "mock" or ids == frozen_ids, "Real proof must cover the entire manifest")
    target_payload = dict(items=[entry for entry in manifest["items"] if entry[0] in set(ids)],
                          exclusions={key: value for key, value in manifest["exclusions"].items() if key in ids})
    require(receipts["target_manifest_hash"] == digest(target_payload), "Target manifest hash mismatch")
    config = receipts["config"]
    _check_isolation(config, receipts["mode"], receipts["execution"]["checkout_root"] if v2 else None)
    require(sha(config["output_schema_text"].encode("utf-8")) == config["output_schema_sha256"], "Output schema hash mismatch")
    Draft202012Validator.check_schema(decode_json(config["output_schema_text"]))
    require(receipts["database"]["copy_before_upgrade_sha256"] == SOURCE_SHA256 and
            receipts["database"]["source_after_sha256"] == SOURCE_SHA256, "Source/copy hash mismatch")
    require(receipts["database"]["schema_after"] >= receipts["database"]["schema_before"], "Database schema regressed")
    require(receipts["before"] == receipts["after"], "Projection, memberships, pins, policy or activation changed")
    require(receipts["before"]["taxonomy_revision_hash"] == manifest["taxonomy"]["revision_hash"] and
            receipts["before"]["active_version_id"] == manifest["taxonomy"]["version_id"], "Frozen taxonomy was not active before proof")
    require(not receipts["before"]["memberships"] and not receipts["before"]["pins"], "Named copy proof starts with zero labels and pins")
    template = (root / manifest["files"]["prompt"]["path"]).read_text(encoding="utf-8")
    by_item, attempt_ids, tokens, work_ids = defaultdict(list), set(), set(), {}
    schema_bytes = len(config["output_schema_text"].encode("utf-8"))
    sums = Counter()
    for attempt in receipts["attempts"]:
        video_id = attempt["video_id"]
        require(video_id in ids, "Attempt outside target manifest")
        require(attempt["attempt_id"] not in attempt_ids and attempt["attempt_token"] not in tokens,
                "Duplicate attempt ID/token")
        attempt_ids.add(attempt["attempt_id"])
        tokens.add(attempt["attempt_token"])
        require(work_ids.setdefault(attempt["work_id"], video_id) == video_id, "Work identity reused for another item")
        previous = by_item[video_id]
        require(attempt["attempt_number"] == len(previous) + 1, "Attempt numbers must be consecutive per item")
        if previous:
            require(previous[-1]["outcome"] == "rejected" and previous[-1]["work_id"] == attempt["work_id"],
                    "Only rejected results may receive one new reasoning attempt")
        previous.append(attempt)
        packet, frozen = attempt["packet"], manifest["cards"][video_id]
        require(digest(packet) == attempt["packet_hash"], "Packet hash mismatch")
        require(packet.get("schema_version") == 1 and packet.get("video_id") == video_id and
                packet.get("source_revision") == frozen["source_revision"] and
                packet.get("taxonomy_revision") == manifest["taxonomy"]["revision_hash"], "Packet identity/revision mismatch")
        policy = dict(min_confidence=0.60, max_memberships=3, max_churn_percent=15,
                      prompt_hash=manifest["hashes"]["prompt_sha256"], selection_version="spread-longest-v1", card_schema=1)
        require(packet.get("policy_hash") == digest(policy), "Packet policy hash mismatch")
        card = packet["card"]
        require(set(packet) == {"schema_version", "video_id", "source_revision", "taxonomy_revision", "policy_hash", "card"},
                "Packet fields differ from service contract")
        require(card.get("video_id") == video_id and card.get("source_revision") == frozen["source_revision"], "Card identity/revision mismatch")
        require(card.get("card_hash") == frozen["card_hash"] == library_cards._hash({k: v for k, v in card.items() if k != "card_hash"}),
                "Card differs from frozen evidence")
        require(card.get("profile") == "librarian" and card.get("schema_version") == 1 and
                card.get("selection_version") == "spread-longest-v1", "Wrong card profile")
        require(len(card["excerpts"]) <= 6 and all(len(e["text"]) <= 240 for e in card["excerpts"]), "Card profile limits exceeded")
        require(attempt["card_text"] == library_cards.card_text(card), "Card serialization mismatch")
        require(attempt["prompt_text"] == render_prompt(template, manifest["taxonomy"], card), "Prompt differs from frozen template/taxonomy/card")
        for field in ("card", "prompt", "response"):
            require(attempt[field + "_bytes"] == len(attempt[field + "_text"].encode("utf-8")), f"{field} byte count mismatch")
            sums[field + "_bytes"] += attempt[field + "_bytes"]
        require(attempt["card_bytes"] == frozen["card_bytes"] <= 8192, "Frozen card byte budget mismatch")
        require(attempt["serialized_input_bytes"] == attempt["prompt_bytes"] + schema_bytes, "Serialized input byte count mismatch")
        sums["serialized_input_bytes"] += attempt["serialized_input_bytes"]
        sums["attempt_wall_ms"] += attempt["wall_ms"]
        require(attempt["wall_ms"] <= receipts["totals"]["wall_ms"], "Attempt longer than complete run")
        if attempt["outcome"] in {"accepted", "unmapped", "unsupported"}:
            response = attempt["submit_response"]
            require(response is not None and response.get("ok") is True and response.get("outcome") == attempt["outcome"] and
                    response.get("work_id") == attempt["work_id"] and response.get("video_id") == video_id,
                    "Successful outcome lacks matching registry receipt")
            require(attempt["rejection_reason"] is None, "Successful outcome has rejection reason")
            result = attempt["result"]
            raw = _response_object(attempt)
            require(raw is not None, "Successful result lacks parseable model response")
            model_result = raw.get("structured_output", raw)
            if not v2:
                require(model_result == {"results": [{"video_id": video_id, "result": result}]},
                        "Model output does not match submitted single-item result")
            if attempt["outcome"] == "accepted":
                _check_evidence(result, card, manifest["taxonomy"])
            else:
                require(result is not None and result.get("outcome") == attempt["outcome"] and
                        isinstance(result.get("reason"), str) and result["reason"].strip(), "Abstention lacks matching reason")
        else:
            require(attempt["rejection_reason"] is not None, "Failed attempt lacks rejection reason")
        _check_usage(attempt, receipts["mode"])
    failures, event_ids = receipts["transport_failures"], set()
    for event in failures:
        require(event["event_id"] not in event_ids, "Duplicate transport event")
        event_ids.add(event["event_id"])
        require(event["video_id"] is None or event["video_id"] in ids, "Transport event outside manifest")
        require(event["attempt_id"] is None or event["attempt_id"] in attempt_ids, "Transport event references missing attempt")
        require(event["wall_ms"] <= receipts["totals"]["wall_ms"], "Transport event longer than run")
    for attempt in receipts["attempts"]:
        if attempt["submit_response"] is None:
            require(any(e["attempt_id"] == attempt["attempt_id"] for e in failures), "Missing transport-failure receipt")
    targets = receipts["targets"]
    require([target["video_id"] for target in targets] == ids, "Missing, duplicate or reordered target outcomes")
    for target in targets:
        attempts = by_item[target["video_id"]]
        if attempts:
            last = attempts[-1]
            require(target["last_attempt_id"] == last["attempt_id"] and target["work_id"] == last["work_id"] and
                    target["outcome"] == last["outcome"], "Final target disagrees with last attempt")
        else:
            require(target["last_attempt_id"] is None and target["outcome"] in {"unsupported", "pinned", "deleted", "changed"},
                    "Target outcome requires a recorded attempt")
        require(target["outcome"] == "accepted" or target["reason"] is not None, "Nonassignment needs a reason")
    preview = receipts["preview"]
    require(preview["request"].get("mode", "preview") == "preview" and
            preview["request"].get("run_id") == receipts["run_id"] and
            preview["request"].get("expected_projection_revision") == receipts["before"]["projection_revision"] and
            not preview["request"].get("activate_version", False), "Expected preview-only request without activation")
    require(preview["response"].get("ok") is True and preview["response"].get("preview_id"), "Missing successful preview receipt")
    totals = receipts["totals"]
    for key in (("card_bytes",) if v2 else ("serialized_input_bytes", "card_bytes", "prompt_bytes", "response_bytes")):
        require(totals[key] == sums[key], f"Total {key} mismatch")
    require(totals["retries"] == sum(max(0, len(attempts) - 1) for attempts in by_item.values()), "Retry total mismatch")
    if not v2:
        require(totals["model_calls"] == 0, "Legacy fixture cannot report model processes")
    rejected = sum(attempt["outcome"] == "rejected" for attempt in receipts["attempts"])
    require(totals["rejected_attempts"] == rejected and totals["transport_failures"] == len(failures), "Error counts mismatch")
    require(totals["wall_ms"] <= config["wall_budget_ms"], "Wall-time budget exceeded")
    require(sums["attempt_wall_ms"] <= totals["wall_ms"] * config["concurrency"], "Attempt wall times exceed concurrency capacity")
    n = len(receipts["attempts"])
    require(n < 20 or 10 * (rejected + len(failures)) <= n, "Error-rate abort threshold exceeded")
    if v2:
        _check_v2(receipts, manifest, template, artifact_root or root)
    require(not any(t["outcome"] in {"changed", "deleted", "pinned"} for t in targets), "Source or projection invalidation blocks proof")
    return dict(status="FIXTURE_VALID" if receipts["mode"] == "mock" else "RECEIPTS_VALID_AUDIT_REQUIRED",
                target_count=len(ids), attempt_count=n, retries=totals["retries"],
                measured_quality_items=0 if receipts["mode"] == "mock" else len(manifest["holdout"]["ids"]),
                whole_manifest_checked=require_whole_manifest,
                product_proof_pass=False)


def _legacy_fixture():
    taxonomy = normalized_taxonomy(read_json(ROOT / "docs/library/taxonomy-v1-2026-09-04.json"))
    card = library_cards.build_card(dict(video_id="fixture-note", title="Fixture", source_type="note"), [],
                                    corpus_text="A grounded fixture quote with Unicode caf\u00e9.", profile="librarian")
    prompt_path = "scripts/librarian/prompts/assign.md"
    template = (ROOT / prompt_path).read_text(encoding="utf-8")
    pair = [card["video_id"], card["source_revision"]]
    hashes = {key: "a" * 64 for key in HASH_KEYS}
    hashes.update(manifest_hash=digest(dict(items=[pair], exclusions={})),
                  prompt_sha256=sha(template.encode("utf-8")))
    manifest = dict(freeze_status="frozen", items=[pair], exclusions={}, taxonomy=taxonomy, hashes=hashes,
                    files=dict(prompt=dict(path=prompt_path)), holdout=dict(ids=[card["video_id"]]),
                    cards={card["video_id"]: dict(source_revision=card["source_revision"],
                        card_hash=card["card_hash"], card_bytes=len(library_cards.card_text(card).encode("utf-8")))})
    policy = dict(min_confidence=0.60, max_memberships=3, max_churn_percent=15,
                  prompt_hash=hashes["prompt_sha256"], selection_version="spread-longest-v1", card_schema=1)
    packet = dict(schema_version=1, video_id=card["video_id"], source_revision=card["source_revision"],
                  taxonomy_revision=taxonomy["revision_hash"], policy_hash=digest(policy), card=card)
    shelf = next(node for node in taxonomy["nodes"] if node["shelf_id"] == "education")
    result = dict(outcome="assigned", memberships=[dict(shelf_id=shelf["shelf_id"], shelf_path=shelf["path"],
        confidence=0.9, evidence=dict(basis="packet", kind="text_only", card_hash=card["card_hash"],
                                     excerpt_id=card["excerpts"][0]["excerpt_id"], quote="grounded fixture quote"))])
    response = dict(ok=True, schema_version=1, work_id="w", video_id=card["video_id"], outcome="accepted")
    schema_text = '{"type":"object"}'
    attempt = dict(attempt_id="a1", video_id=card["video_id"], work_id="w", attempt_token="t" * 43,
                   attempt_number=1, packet_hash=digest(packet), packet=packet,
                   card_text=library_cards.card_text(card), prompt_text=render_prompt(template, taxonomy, card),
                   response_text=canonical(dict(results=[dict(video_id=card["video_id"], result=result)])),
                   result=result, submit_response=response, wall_ms=5, outcome="accepted", rejection_reason=None,
                   usage=dict(status="unavailable", reason="Mock fixture"),
                   estimates=dict(total_cost_usd=None, source="unavailable"))
    for field in ("card", "prompt", "response"):
        attempt[field + "_bytes"] = len(attempt[field + "_text"].encode("utf-8"))
    attempt["serialized_input_bytes"] = attempt["prompt_bytes"] + len(schema_text.encode("utf-8"))
    isolated = ROOT / "_scratch/proof/self-test"
    state = dict(projection_revision=0, memberships=[], pins=[], item_policies=[],
                 active_version_id=taxonomy["version_id"], taxonomy_revision_hash=taxonomy["revision_hash"],
                 librarian_apply_enabled=False, applied_label_count=0, proof_apply_count=0)
    receipt = dict(schema_version=1, contract_version=CONTRACT, run_id="fixture", mode="mock", status="completed",
        abort_reason=None, inputs=hashes, target_ids=[card["video_id"]], target_manifest_hash=hashes["manifest_hash"],
        config=dict(client="proof_run.py", transport="http_registry", model="fixture", base_url="http://127.0.0.1:5180",
                    isolation_root=str(isolated), index_path=str(isolated / "Uoink/index.db"),
                    token_path=str(isolated / "token.txt"),
                    environment={key: str(isolated) for key in ("LOCALAPPDATA", "APPDATA", "TEMP", "TMP", "UOINK_OUTPUT_DIR")},
                    anthropic_api_key_unset=True, tools=[], concurrency=4, max_retries=1, wall_budget_ms=7200000,
                    error_rate_limit=0.10, error_rate_min_attempts=20,
                    output_schema_text=schema_text, output_schema_sha256=sha(schema_text.encode("utf-8"))),
        database=dict(copy_before_upgrade_sha256=SOURCE_SHA256, copy_after_upgrade_sha256="b" * 64,
                      source_after_sha256=SOURCE_SHA256, schema_before=26, schema_after=27),
        before=state, after=copy.deepcopy(state), attempts=[attempt], transport_failures=[],
        targets=[dict(video_id=card["video_id"], work_id="w", outcome="accepted", reason=None, last_attempt_id="a1")],
        preview=dict(request=dict(mode="preview", run_id="fixture", expected_projection_revision=0),
                     response=dict(ok=True, preview_id="p")),
        totals={**{key: attempt[key] for key in ("serialized_input_bytes", "card_bytes", "prompt_bytes", "response_bytes")},
                "wall_ms": 10, "retries": 0, "model_calls": 0, "rejected_attempts": 0, "transport_failures": 0},
        audit_extensions={})
    return receipt, manifest, card, result, attempt


def self_test():
    """Positive/adversarial fixtures only; never a model, helper, or source DB."""
    from jsonschema.exceptions import ValidationError
    receipt, manifest, card, result, attempt = _legacy_fixture()
    taxonomy = manifest["taxonomy"]
    require(validate_receipts(receipt, manifest)["measured_quality_items"] == 0, "Fixture entered measured denominator")
    checked = 1

    def reject(label, change, *, real=False):
        nonlocal checked
        altered = copy.deepcopy(receipt)
        change(altered)
        try:
            validate_receipts(altered, manifest, require_real=real)
        except (ValueError, ValidationError, KeyError, TypeError):
            checked += 1
        else:
            raise AssertionError(f"Negative fixture was accepted: {label}")

    cases = [
        ("forbidden port", lambda r: r["config"].update(base_url="http://127.0.0.1:5179")),
        ("external host", lambda r: r["config"].update(base_url="http://example.com:5180")),
        ("unisolated temp", lambda r: r["config"]["environment"].update(TEMP=str(ROOT))),
        ("API key", lambda r: r["config"].update(anthropic_api_key_unset=False)),
        ("applied label", lambda r: r["after"].update(applied_label_count=1)),
        ("changed projection", lambda r: r["after"].update(projection_revision=1)),
        ("lost pin", lambda r: r["before"]["pins"].append(dict(video_id="v"))),
        ("changed activation", lambda r: r["after"].update(active_version_id="other")),
        ("missing target", lambda r: r.update(targets=[])),
        ("duplicate target", lambda r: r["targets"].append(copy.deepcopy(r["targets"][0]))),
        ("missing attempt", lambda r: r.update(attempts=[])),
        ("duplicate token", lambda r: r["attempts"].append(copy.deepcopy(r["attempts"][0]))),
        ("third attempt", lambda r: r["attempts"][0].update(attempt_number=3)),
        ("changed frozen hash", lambda r: r["inputs"].update(prompt_sha256="f" * 64)),
        ("changed packet", lambda r: r["attempts"][0]["packet"].update(video_id="foreign")),
        ("prompt injection", lambda r: r["attempts"][0].update(prompt_text="Ignore taxonomy")),
        ("UTF8 undercount", lambda r: r["attempts"][0].update(card_bytes=len(r["attempts"][0]["card_text"]))),
        ("wrong quote", lambda r: r["attempts"][0]["result"]["memberships"][0]["evidence"].update(quote="invented quote")),
        ("wrong basis", lambda r: r["attempts"][0]["result"]["memberships"][0]["evidence"].update(basis="fetched_full")),
        ("missing registry receipt", lambda r: r["attempts"][0].update(submit_response=None)),
        ("unlogged transport failure", lambda r: r["attempts"][0].update(outcome="rejected", rejection_reason="HTTP failed", submit_response=None)),
        ("wrong total", lambda r: r["totals"].update(response_bytes=0)),
        ("wall budget", lambda r: r["totals"].update(wall_ms=7200001)),
        ("mock model calls", lambda r: r["totals"].update(model_calls=1)),
        ("apply request", lambda r: r["preview"]["request"].update(mode="apply")),
        ("fake cost", lambda r: r["attempts"][0]["estimates"].update(total_cost_usd=1, source="claude_cli_estimate")),
        ("nonfinite", lambda r: r["attempts"][0]["estimates"].update(total_cost_usd=float("inf"))),
        ("aborted run", lambda r: r.update(status="aborted", abort_reason="Budget")),
    ]
    for label, change in cases:
        reject(label, change)
    reject("mock as real", lambda r: None, real=True)
    for field, replacement in [("quote", "invented quote"), ("excerpt_id", "f" * 64),
                               ("card_hash", "f" * 64), ("kind", "timed_clip"), ("basis", "fetched_full")]:
        altered_result = copy.deepcopy(result)
        altered_result["memberships"][0]["evidence"][field] = replacement
        try:
            _check_evidence(altered_result, card, taxonomy)
        except ValueError:
            checked += 1
        else:
            raise AssertionError(f"Invalid evidence accepted: {field}")
    unsupported_card = copy.deepcopy(card)
    unsupported_card["source_type"] = "video"
    try:
        _check_evidence(result, unsupported_card, taxonomy)
    except ValueError:
        checked += 1
    else:
        raise AssertionError("Video description accepted as original prose")
    real = copy.deepcopy(receipt)
    real["mode"] = "subscription"
    real["totals"]["model_calls"] = 1
    real_attempt = real["attempts"][0]
    real_attempt["response_text"] = canonical(dict(
        structured_output=dict(results=[dict(video_id=card["video_id"], result=result)]),
        model="synthetic-cli-model", usage=dict(input_tokens=10, output_tokens=5,
            cache_read_input_tokens=2, cache_creation_input_tokens=3), total_cost_usd=0.01))
    real_attempt["usage"] = dict(status="reported", source="claude_cli_json", model="synthetic-cli-model",
                                 input_tokens=10, output_tokens=5, cache_read_tokens=2, cache_create_tokens=3)
    real_attempt["estimates"] = dict(total_cost_usd=0.01, source="claude_cli_estimate")
    real_attempt["response_bytes"] = len(real_attempt["response_text"].encode("utf-8"))
    real["totals"]["response_bytes"] = real_attempt["response_bytes"]
    _check_usage(real_attempt, "subscription")
    checked += 1
    real_attempt["usage"]["input_tokens"] = 11
    try:
        _check_usage(real_attempt, "subscription")
    except ValueError:
        checked += 1
    else:
        raise AssertionError("Fabricated CLI usage was accepted")
    # A rejected reasoning result can be followed by one accepted retry.
    retried = copy.deepcopy(receipt)
    first = retried["attempts"][0]
    first.update(outcome="rejected", rejection_reason="Invalid fixture result",
                 result=None, response_text="not JSON", response_bytes=8,
                 submit_response=dict(ok=True, outcome="rejected"))
    second = copy.deepcopy(attempt)
    second.update(attempt_id="a2", attempt_token="u" * 43, attempt_number=2)
    retried["attempts"].append(second)
    retried["targets"][0]["last_attempt_id"] = "a2"
    for key in ("serialized_input_bytes", "card_bytes", "prompt_bytes", "response_bytes"):
        retried["totals"][key] = sum(entry[key] for entry in retried["attempts"])
    retried["totals"].update(retries=1, rejected_attempts=1)
    require(validate_receipts(retried, manifest)["retries"] == 1, "Valid retry rejected")
    checked += 1
    import importlib.util
    spec = importlib.util.spec_from_file_location("astra_v2_fixtures", ROOT / "tests/library_work_astra/test_receipts_v2.py")
    fixtures = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixtures)
    checked += fixtures.run_offline_checks(sys.modules[__name__])
    fixtures.test_guard_equality_first_breach_and_interleaved_order()
    checked += 4
    sys.path.insert(0, str(ROOT / "tests/library_work_astra"))
    try:
        spec = importlib.util.spec_from_file_location("astra_induction_fixtures", ROOT / "tests/library_work_astra/test_induction_contract.py")
        induction_fixtures = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(induction_fixtures)
        checked += induction_fixtures.run_offline_checks()
    finally:
        sys.path.pop(0)
    print(json.dumps(dict(status="SELF_TEST_VALID", cases=checked, model_calls=0, helper_calls=0)))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipts", type=Path)
    parser.add_argument("--manifest", type=Path, default=MANIFEST)
    parser.add_argument("--schema", action="store_true", help="Print the machine-readable JSON Schema")
    parser.add_argument("--receipt-kind", choices=["proof", "induction"], default="proof")
    parser.add_argument("--freeze-stage2", action="store_true", help="Freeze induction and evaluation identities from archive only")
    parser.add_argument("--verify-stage2-freezes", action="store_true")
    parser.add_argument("--verify-inputs", action="store_true")
    parser.add_argument("--require-real", action="store_true", help="Reject mock evidence; never executes a model")
    parser.add_argument("--mock", action="store_true", help="Require fixture receipts")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--freeze", action="store_true", help="Rebuild the freeze from the named copy; requires --mock")
    parser.add_argument("--stage2", action="store_true",
                        help="Stage 2 execution freeze: taxonomy v2, hold-out v2, sealed labels; writes/validates manifest-stage2")
    parser.add_argument("--source", type=Path)
    parser.add_argument("--check-source", action="store_true", help="Remeasure source heads and compare with freeze; requires --mock")
    parser.add_argument("--allow-install-corpus", action="store_true", help="Read only explicit source Markdown heads in the install root")
    args = parser.parse_args(argv)
    try:
        Draft202012Validator.check_schema(RECEIPT_SCHEMA)
        if args.freeze_stage2:
            require(args.mock, "Identity freeze requires --mock; no model or database is opened")
            for path, value in zip((HOLDOUT_V2, INDUCTION_MANIFEST), stage2_freezes()):
                text = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
                require(not path.exists() or path.read_text(encoding="utf-8") == text, "Existing freeze differs; do not overwrite")
                if not path.exists():
                    path.write_text(text, encoding="utf-8", newline="\n")
            print(json.dumps(verify_stage2_freezes()))
            return 0
        if args.verify_stage2_freezes:
            print(json.dumps(verify_stage2_freezes()))
            return 0
        if args.schema:
            print(json.dumps(INDUCTION_RECEIPT_SCHEMA if args.receipt_kind == "induction" else RECEIPT_SCHEMA, indent=2))
            return 0
        if args.self_test:
            require(args.mock, "Self-tests require --mock")
            self_test()
            return 0
        if args.receipts and args.receipt_kind == "induction":
            receipts = read_json(args.receipts)
            require(not args.mock or receipts.get("mode") == "mock", "--mock requires fixture receipts")
            print(json.dumps(validate_induction_receipts(receipts, artifact_root=args.receipts.resolve().parent,
                                                         require_real=args.require_real), indent=2))
            return 0
        stage = 2 if args.stage2 else 1
        assigned_manifest = MANIFEST_STAGE2 if args.stage2 else MANIFEST
        if args.stage2 and args.manifest.resolve() == MANIFEST.resolve():
            args.manifest = MANIFEST_STAGE2
        if args.freeze:
            require(args.mock and args.source is not None, "Freeze requires --mock --source <named-copy>")
            require(args.manifest.resolve() == assigned_manifest.resolve(), "Freeze writes only the assigned manifest file")
            manifest = freeze_inputs(args.source, allow_install_corpus=args.allow_install_corpus, stage=stage)
            if stage == 2:
                stage1 = read_json(MANIFEST)
                for key in ("items", "cards", "corpus_heads", "cards_hash", "corpus_heads_hash", "measured_strata"):
                    require(manifest[key] == stage1[key], f"Stage 2 card freeze differs from stage 1: {key}")
            assigned_manifest.parent.mkdir(parents=True, exist_ok=True)
            assigned_manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
            print(json.dumps(dict(status=manifest["freeze_status"], targets=len(manifest["items"]),
                                 frozen_cards=len(manifest["cards"]), unresolved=len(manifest["unresolved_targets"]),
                                 manifest_hash=manifest["manifest_hash"])))
            return 1 if manifest["unresolved_targets"] else 0
        manifest = verify_manifest(read_json(args.manifest))
        if args.check_source:
            require(args.mock and args.source is not None, "Source check requires --mock --source <named-copy>")
            current = freeze_inputs(args.source, allow_install_corpus=args.allow_install_corpus, stage=stage)
            require(current["freeze_status"] == "frozen", "Source check has unresolved corpus heads")
            require({k: v for k, v in current.items() if k != "upgrade"} ==
                    {k: v for k, v in manifest.items() if k != "upgrade"}, "Current source evidence differs from freeze")
            require(current["upgrade"]["schema_version"] == manifest["upgrade"]["schema_version"], "Upgrade schema changed")
            print(json.dumps(dict(status="FROZEN_SOURCE_VALID", targets=len(current["items"]))))
        elif args.receipts:
            receipts = read_json(args.receipts)
            require(not args.mock or receipts.get("mode") == "mock", "--mock requires fixture receipts")
            print(json.dumps(validate_receipts(receipts, manifest, require_real=args.require_real,
                                                artifact_root=args.receipts.resolve().parent), indent=2))
        elif args.verify_inputs:
            print(json.dumps(dict(status="FROZEN_INPUTS_VALID", manifest_hash=manifest["manifest_hash"], targets=len(manifest["items"]))))
        else:
            parser.error("Choose --receipts, --verify-inputs, --schema, or --self-test --mock")
        return 0
    except (ValueError, KeyError, TypeError, OSError, json.JSONDecodeError) as exc:
        print(f"INVALID: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        # jsonschema's diagnostics can contain card/prompt contents; print only its message.
        from jsonschema.exceptions import ValidationError, SchemaError
        if isinstance(exc, (ValidationError, SchemaError)):
            path = "/".join(str(part) for part in exc.absolute_path)
            print(f"INVALID schema at {path or '<root>'}: {exc.validator}", file=sys.stderr)
            return 1
        raise


if __name__ == "__main__":
    raise SystemExit(main())
