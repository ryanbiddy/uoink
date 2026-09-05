"""Offline run-P receipt contract and run-Q auditor. Never starts a client/helper.

Export JSON Schema with --schema; check frozen files with --verify-inputs.
The schema checks shape; validate_receipts also checks hashes, evidence, accounting,
retry history, isolation declarations, and unchanged projection snapshots.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import shutil
import sqlite3
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import library_cards
from jsonschema import Draft202012Validator

MANIFEST = ROOT / "docs/library/proof/manifest-2026-09-05.json"
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


def freeze_inputs(source, *, allow_install_corpus=False):
    """Freeze the named copy and bounded Markdown heads; no helper/index defaults.

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
    for name, relative in dict(taxonomy="docs/library/taxonomy-v1-2026-09-04.json",
                               prompt="scripts/librarian/prompts/assign.md", card_builder="library_cards.py",
                               holdout="docs/library/holdout-split-2026-09-04.json",
                               gold="docs/library/gold-set-2026-09-04.json", index="index.py", clips="clips.py",
                               provenance="provenance.py", service="library_work.py",
                               migration26="migrations/0026_provenance_precedence.sql",
                               migration27="migrations/0027_library_substrate.sql").items():
        files[name] = dict(path=relative, sha256=sha((ROOT / relative).read_bytes()))
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


def _check_isolation(config, mode):
    parsed = urlsplit(config["base_url"])
    require(parsed.scheme == "http" and parsed.hostname == "127.0.0.1" and
            parsed.port is not None and parsed.port != 5179 and not parsed.username and
            not parsed.password and parsed.path in ("", "/") and not parsed.query and not parsed.fragment,
            "Expected isolated loopback HTTP endpoint; port 5179 is forbidden")
    require(0 < parsed.port < 65536, "Invalid helper port")
    if mode == "subscription":
        require(parsed.port == 5180, "Subscription proof requires port 5180")
    scratch = (ROOT / "_scratch/proof").resolve()
    isolated = Path(config["isolation_root"]).resolve()
    require(isolated.is_relative_to(scratch) and isolated != scratch, "Isolation root must be below _scratch/proof")
    for name, raw in {**config["environment"], "index_path": config["index_path"], "token_path": config["token_path"]}.items():
        require(Path(raw).resolve().is_relative_to(isolated), f"{name} escapes isolated root")
    require(Path(config["index_path"]).resolve() == isolated / "Uoink/index.db", "Unexpected isolated index path")


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
        require(isinstance(quote, str) and quote.strip() and len(quote.split()) < 25 and quote in excerpt["text"],
                "Evidence quote is not a verbatim substring under 25 words")
        if evidence["kind"] == "text_only":
            require(card.get("source_type") in {"page", "x_article", "x_thread", "reddit_thread", "note"},
                    "Source origin does not support original-prose evidence")


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


def validate_receipts(receipts, manifest, *, require_real=False, root=ROOT):
    canonical(receipts)  # Reject NaN/infinity even when called directly from Python.
    Draft202012Validator(RECEIPT_SCHEMA).validate(receipts)
    require(manifest.get("freeze_status") == "frozen", "Input freeze is incomplete")
    require(not require_real or receipts["mode"] == "subscription", "Mock receipts are fixture evidence only")
    require(receipts["inputs"] == manifest["hashes"], "Receipt input hashes differ from frozen inputs")
    require(receipts["status"] == "completed", f"Run aborted: {receipts['abort_reason']}")
    require(receipts["abort_reason"] is None, "Completed run has abort reason")
    ids = receipts["target_ids"]
    frozen_ids = [entry[0] for entry in manifest["items"]]
    require(ids == [video_id for video_id in frozen_ids if video_id in set(ids)], "Targets are unknown or out of frozen order")
    require(receipts["mode"] == "mock" or ids == frozen_ids, "Real proof must cover the entire manifest")
    target_payload = dict(items=[entry for entry in manifest["items"] if entry[0] in set(ids)],
                          exclusions={key: value for key, value in manifest["exclusions"].items() if key in ids})
    require(receipts["target_manifest_hash"] == digest(target_payload), "Target manifest hash mismatch")
    config = receipts["config"]
    _check_isolation(config, receipts["mode"])
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
    for key in ("serialized_input_bytes", "card_bytes", "prompt_bytes", "response_bytes"):
        require(totals[key] == sums[key], f"Total {key} mismatch")
    require(totals["retries"] == sum(max(0, len(attempts) - 1) for attempts in by_item.values()), "Retry total mismatch")
    require(totals["model_calls"] == (0 if receipts["mode"] == "mock" else len(receipts["attempts"])), "Model call count mismatch")
    rejected = sum(attempt["outcome"] == "rejected" for attempt in receipts["attempts"])
    require(totals["rejected_attempts"] == rejected and totals["transport_failures"] == len(failures), "Error counts mismatch")
    require(totals["wall_ms"] <= config["wall_budget_ms"], "Wall-time budget exceeded")
    require(sums["attempt_wall_ms"] <= totals["wall_ms"] * config["concurrency"], "Attempt wall times exceed concurrency capacity")
    n = len(receipts["attempts"])
    require(n < 20 or (rejected + len(failures)) / n <= 0.10, "Error-rate abort threshold exceeded")
    require(not any(t["outcome"] in {"changed", "deleted", "pinned"} for t in targets), "Source or projection invalidation blocks proof")
    return dict(status="FIXTURE_VALID" if receipts["mode"] == "mock" else "RECEIPTS_VALID_AUDIT_REQUIRED",
                target_count=len(ids), attempt_count=n, retries=totals["retries"],
                measured_quality_items=0 if receipts["mode"] == "mock" else len(manifest["holdout"]["ids"]),
                product_proof_pass=False)


def self_test():
    """Positive and adversarial fixtures; all data is synthetic, no SQLite or HTTP."""
    from jsonschema.exceptions import ValidationError

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
    require(validate_receipts(real, manifest, require_real=True)["product_proof_pass"] is False, "Auditor declared quality PASS")
    checked += 1
    real_attempt["usage"]["input_tokens"] = 11
    try:
        validate_receipts(real, manifest, require_real=True)
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
    print(json.dumps(dict(status="SELF_TEST_VALID", cases=checked, model_calls=0, helper_calls=0)))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipts", type=Path)
    parser.add_argument("--manifest", type=Path, default=MANIFEST)
    parser.add_argument("--schema", action="store_true", help="Print the machine-readable JSON Schema")
    parser.add_argument("--verify-inputs", action="store_true")
    parser.add_argument("--require-real", action="store_true", help="Reject mock evidence; never executes a model")
    parser.add_argument("--mock", action="store_true", help="Require fixture receipts")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--freeze", action="store_true", help="Rebuild the freeze from the named copy; requires --mock")
    parser.add_argument("--source", type=Path)
    parser.add_argument("--check-source", action="store_true", help="Remeasure source heads and compare with freeze; requires --mock")
    parser.add_argument("--allow-install-corpus", action="store_true", help="Read only explicit source Markdown heads in the install root")
    args = parser.parse_args(argv)
    try:
        Draft202012Validator.check_schema(RECEIPT_SCHEMA)
        if args.schema:
            print(json.dumps(RECEIPT_SCHEMA, indent=2))
            return 0
        if args.self_test:
            require(args.mock, "Self-tests require --mock")
            self_test()
            return 0
        if args.freeze:
            require(args.mock and args.source is not None, "Freeze requires --mock --source <named-copy>")
            require(args.manifest.resolve() == MANIFEST.resolve(), "Freeze writes only the assigned manifest file")
            manifest = freeze_inputs(args.source, allow_install_corpus=args.allow_install_corpus)
            MANIFEST.parent.mkdir(parents=True, exist_ok=True)
            MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
            print(json.dumps(dict(status=manifest["freeze_status"], targets=len(manifest["items"]),
                                 frozen_cards=len(manifest["cards"]), unresolved=len(manifest["unresolved_targets"]),
                                 manifest_hash=manifest["manifest_hash"])))
            return 1 if manifest["unresolved_targets"] else 0
        manifest = verify_manifest(read_json(args.manifest))
        if args.check_source:
            require(args.mock and args.source is not None, "Source check requires --mock --source <named-copy>")
            current = freeze_inputs(args.source, allow_install_corpus=args.allow_install_corpus)
            require(current["freeze_status"] == "frozen", "Source check has unresolved corpus heads")
            require({k: v for k, v in current.items() if k != "upgrade"} ==
                    {k: v for k, v in manifest.items() if k != "upgrade"}, "Current source evidence differs from freeze")
            require(current["upgrade"]["schema_version"] == manifest["upgrade"]["schema_version"], "Upgrade schema changed")
            print(json.dumps(dict(status="FROZEN_SOURCE_VALID", targets=len(current["items"]))))
        elif args.receipts:
            receipts = read_json(args.receipts)
            require(not args.mock or receipts.get("mode") == "mock", "--mock requires fixture receipts")
            print(json.dumps(validate_receipts(receipts, manifest, require_real=args.require_real), indent=2))
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
