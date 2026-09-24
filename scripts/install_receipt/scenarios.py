"""Executable AS-7 C22 scenarios. Unexpected failure ends that scenario.

Production helper routes and measured persisted-state oracles are required.
`/c22/snapshot` is stub-only and is never the acceptance oracle. `/extract`
on an RSS feed is not an actual podcast publication. Missing evidence fails
or remains unexecuted. A browser protocol without an image is unexecuted
in every mode, including synthetic.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable

from .constants import (
    CAPTURE_PROFILE_NAMES,
    CURRENT_SCHEMA_TARGET,
    INNO_NOCLOSE_FLAG,
    INNO_NORESTARTAPPS_FLAG,
    LEGACY_FIXTURE_VERSION,
    SCENARIO_IDS,
    SYNTHETIC_HOSTNAME,
)
from .fixtures import (
    FEED_VARIANTS,
    FixtureFeed,
    build_empty_profile,
    build_populated_legacy,
)
from .http_client import HelperClient
from .launcher import (
    InstalledHelperLauncher,
    inventory_installed,
    read_token_with_note,
    run_provenance_command,
)
from .manifest import load_candidate_package_02, load_manifest, upgrade_kind
from .oracles import (
    capture_ledger,
    child_ownership_records,
    child_recovery_oracles,
    derive_phase2_allowed,
    extract_is_not_publication,
    file_bytes_unchanged,
    helper_ownership_state,
    interrupt_oracle,
    ledger_delta,
    measured_legacy_ids,
    modules_inside_app,
    parse_provenance_json,
    phase2_compare,
    registration_failure_oracle,
    require_schema,
    settings_and_pins_unchanged,
    snapshot_with_measured_ids,
)
from .process_identity import created_ms_for_pid, executable_for_pid, liveness
from .receipt_integrity import child_transition_integrity, probe_released_capture_lock, unresolved_restart_integrity, guard_event_summary
from .runner import OperatorRunner
from .validation import C22ValidationError


CHILD_INSTRUMENT = Path(__file__).resolve().parent / "child_instrument.py"


def scenario_table() -> list[dict[str, str]]:
    return [
        {"id": "install",
         "as7": "actual isolated Inno command and exit",
         "notes": "operator step; kit records argv and refuses auto-exec"},
        {"id": "installed_provenance",
         "as7": "bundled interpreter, module paths, 0028/schema 30",
         "notes": "inventory plus executed provenance command"},
        {"id": "empty_migration_replay",
         "as7": "empty profile migrate, stop, reopen, no invented rows",
         "notes": "executable against isolated helper"},
        {"id": "populated_legacy_replay",
         "as7": "versioned populated legacy fixture then replay",
         "notes": f"fixture {LEGACY_FIXTURE_VERSION}"},
        {"id": "one_off_capture",
         "as7": "unrelated one-off while standing is off; zero standing charges",
         "notes": "synthetic acquisition/transcript; real podcast publish routes"},
        {"id": "manual_first",
         "as7": "manual then standing consent; identities, charges, no dup",
         "notes": "dedupe/charges from persisted ledger"},
        {"id": "standing_first",
         "as7": "consent first, standing capture, then same manual item",
         "notes": "one standing charge, one publication"},
        {"id": "whole_helper_relaunch",
         "as7": "terminate owned helper by held handle; relaunch installed path",
         "notes": "listener restart does not count"},
        {"id": "registered_child_lifetime",
         "as7": "actual registered child lifetime",
         "notes": "original source_subscriptions child methods"},
        {"id": "launch_interruption",
         "as7": "interrupt between launch preparation and child registration",
         "notes": "C22_INJECT=launch_interrupt; unresolved_launch retained"},
        {"id": "registration_failure",
         "as7": "separate registration-failure fixture",
         "notes": "C22_INJECT=registration_failure; surviving child preserved"},
        {"id": "browser_state_checkpoint",
         "as7": "post-restart browser state paired with persisted state",
         "notes": "unexecuted without an actual browser image in all modes"},
        {"id": "protected_phase2_state",
         "as7": "Phase 2 before/after hashes and allowed enqueue changes",
         "notes": "apply remains false; hashes must match or deltas account"},
        {"id": "upgrade_operator_step",
         "as7": "preserve real installed upgrade command",
         "notes": "same-version reinstall is not labeled cross-version"},
    ]


class ScenarioRunner:
    def __init__(self, runner: OperatorRunner, *,
                 fixture_port: int):
        self.runner = runner
        self.fixture_port = fixture_port
        self.outcomes: dict[str, dict[str, Any]] = {}
        self.feed: FixtureFeed | None = None
        self.phase2_baselines: dict[str, dict[str, Any]] = {}

    def prepare_profiles(self, *, refresh: bool = False) -> dict[str, Any]:
        root = self.runner.receipt_root
        empty = root / "profiles" / "empty"
        populated = root / "profiles" / "populated"
        extra_names = tuple(
            name for name in CAPTURE_PROFILE_NAMES
            if name not in {"empty", "populated"}
        )
        prepared_path = root / "fixture_prepare.json"
        full_baseline_path = root / "evidence" / "phase2-baselines.full.json"
        hash_baseline_path = root / "evidence" / "phase2-baselines.json"
        if (not refresh and prepared_path.is_file() and full_baseline_path.is_file()):
            prepared = json.loads(prepared_path.read_text(encoding="utf-8"))
            self.phase2_baselines = json.loads(
                full_baseline_path.read_text(encoding="utf-8"))
            fixtures = root / "fixtures"
            fixtures.mkdir(exist_ok=True)
            if self.feed is None:
                self.feed = FixtureFeed(fixtures, self.fixture_port)
                base = self.feed.start()
                self.feed.state["entry"] = True
                prepared["feed_base"] = base
                prepared["feed_url"] = self.feed.feed_url
            prepared["resumed_without_regeneration"] = True
            return prepared
        empty_meta = build_empty_profile(empty)
        populated_meta = build_populated_legacy(populated)
        extra_meta = {}
        for name in extra_names:
            extra_meta[name] = build_empty_profile(root / "profiles" / name)
        fixtures = root / "fixtures"
        fixtures.mkdir(exist_ok=True)
        self.feed = FixtureFeed(fixtures, self.fixture_port)
        base = self.feed.start()
        self.feed.state["entry"] = True
        # Protected Phase 2 baseline is recorded before any scenario mutates state.
        self.phase2_baselines = {
            "empty": snapshot_with_measured_ids(empty, label="p2-empty-baseline"),
            "populated": snapshot_with_measured_ids(
                populated, label="p2-populated-baseline"),
        }
        for name in extra_names:
            self.phase2_baselines[name] = snapshot_with_measured_ids(
                root / "profiles" / name, label=f"p2-{name}-baseline")
        hash_baseline_path.parent.mkdir(parents=True, exist_ok=True)
        hash_baseline_path.write_text(
            json.dumps({k: v.get("phase2_hash") for k, v in self.phase2_baselines.items()},
                       indent=2) + "\n", encoding="utf-8")
        full_baseline_path.write_text(
            json.dumps(self.phase2_baselines, indent=2, default=str) + "\n",
            encoding="utf-8")
        result = {
            "empty": empty_meta,
            "populated": populated_meta,
            "extra": extra_meta,
            "feed_base": base,
            "feed_url": self.feed.feed_url,
            "synthetic_host": SYNTHETIC_HOSTNAME,
            "phase2_baselines": {k: v.get("phase2_hash") for k, v in self.phase2_baselines.items()},
            "immutable_baselines": True,
            "resumed_without_regeneration": False,
        }
        prepared_path.write_text(
            json.dumps(result, indent=2) + "\n", encoding="utf-8")
        return result

    def close(self) -> None:
        if self.feed is not None:
            self.feed.stop()
            self.feed = None

    def record(self, scenario_id: str, outcome_status: str, **payload: Any) -> dict[str, Any]:
        if scenario_id not in SCENARIO_IDS:
            raise C22ValidationError(f"unknown scenario {scenario_id}")
        dest = self.runner.receipt_root / "evidence" / f"{scenario_id}.json"
        if dest.is_file():
            try:
                existing = json.loads(dest.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                existing = None
            if isinstance(existing, dict) and existing.get("status") in {
                    "pass", "fail", "unexecuted"}:
                raise C22ValidationError(
                    f"refusing to overwrite completed scenario {scenario_id}")
        if "status" in payload:
            payload["helper_status"] = payload.pop("status")
        if "id" in payload:
            payload["helper_id"] = payload.pop("id")
        outcome = {
            "id": scenario_id,
            "status": outcome_status,
            **payload,
        }
        self.outcomes[scenario_id] = outcome
        dest.write_text(json.dumps(outcome, indent=2, default=str) + "\n",
                        encoding="utf-8")
        self.runner.record_event("scenario", **outcome)
        return outcome

    def run_one(self, scenario_id: str) -> dict[str, Any]:
        try:
            handler = {
                "install": self._install,
                "installed_provenance": self._provenance,
                "empty_migration_replay": self._empty_replay,
                "populated_legacy_replay": self._populated_replay,
                "one_off_capture": self._one_off,
                "manual_first": self._manual_first,
                "standing_first": self._standing_first,
                "whole_helper_relaunch": self._relaunch,
                "registered_child_lifetime": self._child_lifetime,
                "launch_interruption": self._launch_interrupt,
                "registration_failure": self._registration_failure,
                "browser_state_checkpoint": self._browser_checkpoint,
                "protected_phase2_state": self._protected,
                "upgrade_operator_step": self._upgrade,
            }[scenario_id]
            return handler()
        except BaseException as exc:
            return self.record(
                scenario_id, "fail",
                error=f"{type(exc).__name__}: {exc}",
                preserved=True,
            )

    def run_all(self, skip_ids: set[str] | None = None) -> dict[str, Any]:
        skip_ids = set(skip_ids or ())
        for scenario_id in SCENARIO_IDS:
            if scenario_id in skip_ids:
                dest = self.runner.receipt_root / "evidence" / f"{scenario_id}.json"
                if dest.is_file():
                    try:
                        self.outcomes[scenario_id] = json.loads(
                            dest.read_text(encoding="utf-8"))
                    except json.JSONDecodeError:
                        self.outcomes[scenario_id] = {
                            "id": scenario_id, "status": "unexecuted",
                            "reason": "completed evidence unreadable",
                        }
                continue
            self.run_one(scenario_id)
        return dict(self.outcomes)

    def _inputs(self) -> dict[str, Any]:
        return self.runner.load_inputs()

    def _profile(self, name: str) -> Path:
        return self.runner.receipt_root / "profiles" / name

    def _synthetic_url(self, variant: str) -> str:
        if self.feed is None:
            return f"http://{SYNTHETIC_HOSTNAME}/{variant}/feed.xml"
        return self.feed.synthetic_feed_url(variant)

    def _wait_standing(self, profile: Path, *, timeout: float = 30.0) -> dict[str, Any]:
        deadline = time.time() + timeout
        last = capture_ledger(profile)
        while time.time() < deadline:
            last = capture_ledger(profile)
            if last.get("standing_charge_count"):
                return last
            time.sleep(0.35)
        return last

    def _wait_publication(self, profile: Path, *, before_count: int,
                          timeout: float = 30.0) -> dict[str, Any]:
        deadline = time.time() + timeout
        last = capture_ledger(profile)
        while time.time() < deadline:
            last = capture_ledger(profile)
            if (last.get("publication_count") or 0) > before_count:
                return last
            time.sleep(0.35)
        return last

    def _identity_for_variant(self, variant: str) -> tuple[str, str]:
        return FEED_VARIANTS.get(variant, FEED_VARIANTS["default"])

    def _with_helper(
        self, profile_name: str,
        fn: Callable[[dict[str, Any], HelperClient | None, InstalledHelperLauncher], dict[str, Any]],
        *, inject: str = "", require_health: bool = True,
        require_token: bool = True,
    ) -> dict[str, Any]:
        inputs = self._inputs()
        profile = self._profile(profile_name)
        port = inputs["isolated_port"]
        launcher = InstalledHelperLauncher(
            self.runner, fixture_ports=[self.fixture_port], inject=inject)
        record = launcher.start(
            profile_name=profile_name, isolated_profile=profile,
            isolated_port=port)
        token_info = read_token_with_note(
            Path(inputs["installed_app"]["path"]), profile)
        token = token_info.get("token")
        client = HelperClient(port, token) if token else None
        body_error: BaseException | None = None
        result: dict[str, Any] | None = None
        try:
            if require_health and not record.get("health", {}).get("ok"):
                raise C22ValidationError(
                    f"helper health failed: {record.get('health')}")
            if require_token and not token:
                raise C22ValidationError(
                    "helper token.txt missing at agreed <profile>/token.txt"
                    + ("; install-dir token is not substituted"
                       if token_info.get("install_token_present") else ""))
            result = fn(record, client, launcher)
        except BaseException as exc:
            body_error = exc
        identity = record.get("child") or {}
        try:
            stop = launcher.stop_owned(
                port=port, identity=identity, token=token, record=record)
            if isinstance(result, dict):
                result["helper_stop"] = stop
            if (stop.get("stopped") is not True or stop.get("port_freed") is not True
                    or stop.get("unknown_not_dead") or stop.get("guard_restore_unknown_failure")
                    or stop.get("guard_restore_deferred")):
                cleanup_error = C22ValidationError(
                    "owned helper cleanup/stop was not affirmatively completed")
                if body_error is None:
                    body_error = cleanup_error
        except Exception as exc:
            record["stop_error"] = f"{type(exc).__name__}: {exc}"
            if body_error is None:
                body_error = exc
        if body_error is not None:
            raise body_error
        return result if result is not None else {}

    def _install(self) -> dict[str, Any]:
        manifest = load_manifest(
            self.runner.receipt_root / "manifest.used.json")
        plan = self.runner.plan_inno(manifest, execute=False)
        joined = " ".join(plan.get("argv") or [])
        shape_ok = (
            "/ISOLATED=1" in joined
            and "/PROFILE=" in joined
            and "/PORT=" in joined
            and "/DIR=" in joined
            and INNO_NOCLOSE_FLAG in joined
            and INNO_NORESTARTAPPS_FLAG in joined
            and str(5179) not in joined
        )
        return self.record(
            "install", "unexecuted",
            reason="Inno is Ryan's throwaway-operator step",
            plan=plan,
            agreed_inno_shape=shape_ok,
        )

    def _provenance(self) -> dict[str, Any]:
        inputs = self._inputs()
        app = Path(inputs["installed_app"]["path"])
        inventory = inventory_installed(app)
        provenance = run_provenance_command(self.runner, app)
        child_health = None
        schema = None

        def probe(record, client, launcher):
            health = client.request("GET", "/health") if client else None
            return {"health": health, "identity": record.get("child")}

        try:
            child_health = self._with_helper("empty", probe)
            body = ((child_health.get("health") or {}).get("body")
                    if isinstance(child_health.get("health"), dict)
                    and "body" in (child_health.get("health") or {})
                    else child_health.get("health"))
            if isinstance(body, dict):
                schema = body.get("migration_version")
            elif isinstance(body, str):
                try:
                    schema = json.loads(body).get("migration_version")
                except json.JSONDecodeError:
                    schema = None
        except C22ValidationError as exc:
            child_health = {"error": str(exc)}
        stdout = ""
        if provenance.get("stdout_path"):
            stdout = Path(provenance["stdout_path"]).read_text(
                encoding="utf-8", errors="replace")
        parsed = provenance.get("structured") or parse_provenance_json(stdout)
        location = modules_inside_app(parsed, app) if parsed else {
            "ok": False, "import_ok": False}
        snap = snapshot_with_measured_ids(self._profile("empty"),
                                          label="provenance")
        schema_ok = require_schema(snap)
        sealed = None
        try:
            sealed = load_candidate_package_02()
        except C22ValidationError as exc:
            sealed = {"error": str(exc), "invented": False}
        source_runtime = not (app / "python" / "python.exe").is_file()
        import_ok = bool(parsed) and location.get("import_ok") and provenance.get("exit") == 0 and bool(parsed.get("mcp_version"))
        if parsed is None:
            status = "fail"
            reason = "provenance command did not emit structured JSON"
        elif not import_ok:
            status = "fail"
            reason = "required import failed; ERROR lines are not installed credit"
        elif source_runtime:
            status = "unexecuted"
            reason = (
                "source-runtime interpreter; structured provenance recorded "
                "but installed credit remains false"
            )
        elif not location.get("ok"):
            status = "fail"
            reason = "module __file__ outside installed app or checkout/user-site present"
        else:
            status = "pass" if schema_ok["ok"] else "fail"
            reason = None if schema_ok["ok"] else "schema 30 missing"
        return self.record(
            "installed_provenance", status,
            inventory=inventory, provenance=provenance,
            provenance_json=parsed,
            location=location,
            sealed_candidate= {
                "installer_source_sha": (sealed or {}).get("installer_source_sha"),
                "package_sha256": (sealed or {}).get("package_sha256"),
                "package_bytes": (sealed or {}).get("package_bytes"),
                "invented": False,
                "schema": (sealed or {}).get("schema"),
            },
            installed_credit=False,
            source_runtime=source_runtime,
            provenance_stdout=stdout[:2000], child_report=child_health,
            schema=schema_ok, health_migration_version=schema, reason=reason,
        )

    def _empty_replay(self) -> dict[str, Any]:
        profile = self._profile("empty")
        before = snapshot_with_measured_ids(profile, label="empty-before")

        def body(record, client, launcher):
            health = client.request("GET", "/health") if client else None
            return {
                "health": health,
                "identity": record.get("child"),
                "migration_version": (health or {}).get("migration_version"),
            }

        first_run = self._with_helper("empty", body)
        after_stop = snapshot_with_measured_ids(profile, label="empty-after-stop")
        second_run = self._with_helper("empty", body)
        after_replay = snapshot_with_measured_ids(profile, label="empty-after-replay")
        first_schema = require_schema(after_stop)
        second_schema = require_schema(after_replay)
        starts_first = (after_stop.get("counts") or {}).get("source_capture_starts", 0)
        starts_second = (after_replay.get("counts") or {}).get("source_capture_starts", 0)
        invented = bool((after_replay.get("legacy_video_ids") or {}).get("yoink_ids"))
        ok = (
            first_schema["ok"] and second_schema["ok"]
            and starts_first == starts_second
            and not invented
            and after_stop.get("integrity", {}).get("integrity") == "ok"
            and after_replay.get("integrity", {}).get("integrity") == "ok"
        )
        return self.record(
            "empty_migration_replay", "pass" if ok else "fail",
            before=before, after_stop=after_stop, after_replay=after_replay,
            first_schema=first_schema, second_schema=second_schema,
            first_run=first_run, second_run=second_run,
            duplicate_starts=starts_second - starts_first,
            invented_rows=invented,
        )

    def _populated_replay(self) -> dict[str, Any]:
        profile = self._profile("populated")
        meta = json.loads((profile / "fixture_meta.json").read_text(
            encoding="utf-8"))
        original_hash = meta["index_sha256"]
        timed_md = profile / "output" / "C22-legacy-timed" / "item.md"
        timed_json = profile / "output" / "C22-legacy-timed" / "item.json"
        before = snapshot_with_measured_ids(profile, label="populated-before")
        ids_before = measured_legacy_ids(profile)

        def body(record, client, launcher):
            health = client.request("GET", "/health") if client else None
            return {"health": health, "identity": record.get("child")}

        opened = self._with_helper("populated", body)
        after = snapshot_with_measured_ids(profile, label="populated-after")
        replay = self._with_helper("populated", body)
        after_replay = snapshot_with_measured_ids(profile, label="populated-replay")
        ids_after = measured_legacy_ids(profile)
        schema_ok = require_schema(after)
        replay_schema = require_schema(after_replay)
        identities_ok = (
            ids_before.get("timed_present")
            and ids_before.get("text_present")
            and ids_after.get("timed_present")
            and ids_after.get("text_present")
        )
        bytes_ok = (
            file_bytes_unchanged(timed_md, meta["markdown_sha256"])
            and file_bytes_unchanged(timed_json, meta["sidecar_sha256"])
        )
        yoinks_before = len((before.get("legacy_video_ids") or {}).get("yoink_ids") or [])
        yoinks_replay = len((after_replay.get("legacy_video_ids") or {}).get("yoink_ids") or [])
        idempotent = yoinks_replay == yoinks_before
        version_ok = meta["fixture_version"] == LEGACY_FIXTURE_VERSION
        ok = (
            version_ok and identities_ok and bytes_ok and idempotent
            and schema_ok["ok"] and replay_schema["ok"]
        )
        return self.record(
            "populated_legacy_replay",
            "pass" if ok else "fail",
            fixture_version=meta["fixture_version"],
            original_index_sha256=original_hash,
            before=before, after=after, after_replay=after_replay,
            opened=opened, replay=replay,
            identities_retained=identities_ok,
            bytes_retained=bytes_ok,
            idempotent_replay=idempotent,
            schema=schema_ok,
            upgrade_kind_note="replay of same package is not a cross-version upgrade",
        )

    def _register_and_consent(self, client: HelperClient, *,
                              url: str, operation_key: str,
                              consent: bool) -> dict[str, Any]:
        sources_post = client.request("POST", "/sources", {
            "kind": "podcast_rss", "url": url,
        })
        feeds_post = client.request("POST", "/podcasts/feeds", {
            "feed_url": url, "poll_interval_min": 15, "auto_ingest": False,
        })
        listed = client.request("GET", "/sources")
        feed_list = client.request("GET", "/podcasts/feeds")
        src = (sources_post.get("source")
               or (listed.get("sources") or [None])[0]
               or feeds_post.get("feed"))
        out: dict[str, Any] = {
            "register_source": sources_post,
            "add_feed": feeds_post,
            "list_sources": listed,
            "list_feeds": feed_list,
            "loopback_register_refused": (
                sources_post.get("ok") is False
                or (sources_post.get("error") or {}).get("code") == "unsupported_source"
            ),
        }
        source_id = None
        if isinstance(src, dict):
            source_id = src.get("source_id") or (src.get("source") or {}).get("source_id")
        if isinstance(feeds_post.get("feed"), dict):
            source_id = source_id or feeds_post["feed"].get("source_id")
            out["feed_id"] = feeds_post["feed"].get("id")
        out["source_id"] = source_id
        if not consent or not source_id:
            out["consent_skipped"] = not source_id
            return out
        src_row = src if isinstance(src, dict) and "revision" in src else None
        if src_row is None and client:
            status = client.request(
                "GET", "/sources/status?source_id=" + str(source_id))
            src_row = status.get("source")
            out["status_before_consent"] = status
        if not src_row:
            out["consent_skipped"] = True
            return out
        intent_body = {
            "operation": {
                "source_id": source_id,
                "consent_state": "on",
                "expected_revision": src_row.get("revision", 0),
                "expected_cursor_revision": (
                    (src_row.get("detection") or {}).get("cursor_revision", 0)
                ),
                "operation_key": operation_key,
            },
            "confirmed": True,
        }
        intent = client.request("POST", "/sources/consent-intent", intent_body)
        out["consent_intent"] = intent
        consent_body = {
            "source_id": source_id,
            "consent_state": "on",
            "expected_revision": src_row.get("revision", 0),
            "expected_cursor_revision": (
                (src_row.get("detection") or {}).get("cursor_revision", 0)
            ),
            "operation_key": operation_key,
            "user_intent_token": intent.get("user_intent_token"),
        }
        out["consent"] = client.request("POST", "/sources/consent", consent_body)
        return out

    def _manual_publish(self, client: HelperClient, *, feed_id: Any,
                        episode_guid: str | None = None,
                        episode_title: str | None = None) -> dict[str, Any]:
        if self.feed is not None:
            self.feed.state["entry"] = True
        poll = None
        if feed_id is not None:
            poll = client.request("POST", "/podcasts/feeds/poll", {"feed_id": feed_id},
                                  timeout=20)
        episodes = client.request("GET", "/podcasts/episodes", timeout=20)
        rows = episodes.get("episodes") or []
        episode = None
        if episode_guid:
            episode = next((e for e in rows if str(e.get("guid") or e.get("entry_id") or "")
                            == str(episode_guid)), None)
        if episode is None and episode_title:
            episode = next((e for e in rows if e.get("title") == episode_title), None)
        if episode is None and (episode_guid or episode_title):
            return {
                "poll": poll,
                "episodes": episodes,
                "episode_id": None,
                "reason": "declared episode identity not found",
                "wanted_guid": episode_guid,
                "wanted_title": episode_title,
            }
        episode_id = (episode or {}).get("id") if episode else (rows[0]["id"] if rows else None)
        download = transcribe = published = None
        if episode_id is not None:
            download = client.request("POST", "/podcasts/episodes/download", {
                "episode_id": episode_id,
            })
            transcribe = client.request("POST", "/podcasts/episodes/transcribe", {
                "episode_id": episode_id,
                "consent_given": True,
                "diarize": False,
            })
            deadline = time.time() + 20
            while time.time() < deadline:
                listed = client.request("GET", "/podcasts/episodes")
                current = next((e for e in (listed.get("episodes") or [])
                                if e.get("id") == episode_id), None)
                if current and current.get("status") in (
                        "transcribed", "downloaded"):
                    if current.get("transcript_local_path") or current.get("status") == "transcribed":
                        break
                time.sleep(0.3)
            published = client.request("POST", "/podcasts/episodes/to-corpus", {
                "episode_id": episode_id,
            })
        return {
            "poll": poll,
            "episodes": episodes,
            "episode_id": episode_id,
            "download": download,
            "transcribe": transcribe,
            "to_corpus": published,
        }

    def _one_off(self) -> dict[str, Any]:
        if self.feed is not None:
            self.feed.state["entry"] = True
        profile = self._profile("one-off")
        guid, title = self._identity_for_variant("one-off")
        before = capture_ledger(profile)

        def body(record, client, launcher):
            url = self._synthetic_url("one-off")
            extract = client.request("POST", "/extract", {
                "url": url, "one_off": True,
            })
            registered = self._register_and_consent(
                client, url=url, operation_key="c22-one-off", consent=False)
            published = self._manual_publish(
                client, feed_id=registered.get("feed_id"),
                episode_guid=guid, episode_title=title)
            status = None
            if registered.get("source_id"):
                status = client.request(
                    "GET", "/sources/status?source_id=" + str(registered["source_id"]))
            return {
                "extract": extract,
                "registered": registered,
                "published": published,
                "status": status,
                "synthetic_url": url,
                "episode_guid": guid,
            }

        result = self._with_helper("one-off", body)
        after = capture_ledger(profile)
        delta = ledger_delta(before, after)
        extract_note = extract_is_not_publication(
            result.get("extract"), before, after)
        standing = after.get("standing_starts") or []
        pubs = after.get("publication_count") or 0
        consent_off = all(
            s.get("consent_state") == "off"
            for s in (after.get("subscriptions") or [])
        ) or not after.get("subscriptions")
        ok = (
            not standing
            and delta["standing_charge_delta"] == 0
            and consent_off
            and extract_note["ok"]
            and pubs >= 1
            and SYNTHETIC_HOSTNAME in str(result.get("synthetic_url") or "")
        )
        return self.record(
            "one_off_capture", "pass" if ok else "fail",
            **result, ledger_after=after, ledger_delta=delta,
            extract_is_not_publication=extract_note,
            standing_charges=standing, publication_count=pubs,
        )

    def _manual_first(self) -> dict[str, Any]:
        if self.feed is not None:
            self.feed.state["entry"] = True
        profile = self._profile("manual-first")
        guid, title = self._identity_for_variant("manual-first")
        before = capture_ledger(profile)

        def body(record, client, launcher):
            url = self._synthetic_url("manual-first")
            registered = self._register_and_consent(
                client, url=url, operation_key="c22-manual-first-on",
                consent=False)
            published = self._manual_publish(
                client, feed_id=registered.get("feed_id"),
                episode_guid=guid, episode_title=title)
            after_manual = capture_ledger(profile)
            consented = self._register_and_consent(
                client, url=url, operation_key="c22-manual-first-consent",
                consent=True)
            if consented.get("source_id"):
                client.request("POST", "/sources/refresh", {
                    "source_id": consented["source_id"],
                }, timeout=30)
            standing_after_consent = self._wait_standing(profile, timeout=20)
            after_consent = capture_ledger(profile)
            status = None
            if consented.get("source_id") or registered.get("source_id"):
                sid = consented.get("source_id") or registered.get("source_id")
                status = client.request("GET", "/sources/status?source_id=" + str(sid))
            return {
                "registered": registered,
                "published": published,
                "consented": consented,
                "after_manual": after_manual,
                "after_consent": after_consent,
                "standing_after_consent": standing_after_consent,
                "status": status,
                "synthetic_url": url,
                "episode_guid": guid,
            }

        result = self._with_helper("manual-first", body)
        after = capture_ledger(profile)
        delta = ledger_delta(before, after)
        keys = after.get("capture_keys") or []
        pubs = after.get("publication_count") or 0
        receipts = after.get("receipts") or []
        standing_after_manual = (result.get("after_manual") or {}).get("standing_starts") or []
        standing_after_consent = (
            (result.get("after_consent") or {}).get("standing_charge_count") or 0
        )
        pubs_after_manual = (result.get("after_manual") or {}).get("publication_count") or 0
        extra_charge = standing_after_consent - len(standing_after_manual)
        ok = (
            pubs == 1
            and pubs_after_manual == 1
            and extra_charge == 0
            and len(delta["new_yoinks"]) == 1
            and not standing_after_manual
            and (result.get("published") or {}).get("to_corpus", {}).get("ok")
            and (result.get("registered") or {}).get("register_source", {}).get("ok") is True
            and (result.get("consented") or {}).get("consent", {}).get("ok") is True
            and receipts
            and SYNTHETIC_HOSTNAME in str(result.get("synthetic_url") or "")
        )
        return self.record(
            "manual_first", "pass" if ok else "fail",
            **result, ledger=after, ledger_delta=delta, unique_keys=keys,
            publication_count=pubs, receipt_count=len(receipts),
            standing_after_manual=len(standing_after_manual),
            extra_standing_charge=extra_charge,
        )

    def _standing_first(self) -> dict[str, Any]:
        if self.feed is not None:
            self.feed.state["entry"] = True
        profile = self._profile("standing-first")
        guid, title = self._identity_for_variant("standing-first")
        before = capture_ledger(profile)

        def body(record, client, launcher):
            url = self._synthetic_url("standing-first")
            consented = self._register_and_consent(
                client, url=url, operation_key="c22-standing-first-on",
                consent=True)
            if consented.get("source_id"):
                client.request("POST", "/sources/refresh", {
                    "source_id": consented["source_id"],
                }, timeout=30)
            standing_ledger = self._wait_standing(profile, timeout=35)
            standing_ledger = self._wait_publication(
                profile, before_count=0, timeout=35)
            pubs_before_manual = standing_ledger.get("publication_count") or 0
            if pubs_before_manual < 1:
                raise C22ValidationError(
                    "standing-first did not observe publication before the manual action")
            published = self._manual_publish(
                client, feed_id=consented.get("feed_id"),
                episode_guid=guid, episode_title=title)
            after_manual = capture_ledger(profile)
            status = None
            if consented.get("source_id"):
                status = client.request(
                    "GET", "/sources/status?source_id=" + str(consented["source_id"]))
            return {
                "consented": consented,
                "published": published,
                "status": status,
                "standing_before_manual": standing_ledger,
                "after_manual": after_manual,
                "pubs_before_manual": pubs_before_manual,
                "synthetic_url": url,
                "episode_guid": guid,
            }

        result = self._with_helper("standing-first", body)
        after = capture_ledger(profile)
        delta = ledger_delta(before, after)
        standing = after.get("standing_starts") or []
        pubs = after.get("publication_count") or 0
        standing_before_manual = (
            (result.get("standing_before_manual") or {}).get("standing_charge_count") or 0
        )
        prior_mutated = bool(delta.get("mutated_prior_starts"))
        ok = (
            standing_before_manual == 1
            and len(standing) == 1
            and pubs == 1
            and (result.get("pubs_before_manual") or 0) == 1
            and len(delta.get("new_yoinks") or []) == 1
            and not prior_mutated
            and (result.get("consented") or {}).get("consent", {}).get("ok") is True
            and (result.get("consented") or {}).get("register_source", {}).get("ok") is True
            and SYNTHETIC_HOSTNAME in str(result.get("synthetic_url") or "")
        )
        if (result.get("pubs_before_manual") or 0) < 1:
            ok = False
            result["manual_counted_as_standing"] = True
        return self.record(
            "standing_first", "pass" if ok else "fail",
            **result, ledger=after, ledger_delta=delta,
            standing_charges=len(standing), publication_count=pubs,
            deduped=pubs == 1 and len(delta["new_capture_keys"]) <= 1,
        )

    def _relaunch(self) -> dict[str, Any]:
        inputs = self._inputs()
        profile = self._profile("relaunch")
        port = inputs["isolated_port"]

        def body(record, client, launcher):
            first_id = record["child"]
            snap_before = snapshot_with_measured_ids(profile, label="relaunch-before")
            ownership_before = helper_ownership_state(profile)
            health_before = client.request("GET", "/health") if client else None
            stopped = launcher.terminate_owned(first_id, record=record)
            live = liveness(first_id["pid"], first_id.get("created_ms"))
            if live == "unknown":
                raise C22ValidationError(
                    "first helper liveness is unknown after terminate; unknown is not dead")
            second = launcher.start(
                profile_name="relaunch-2", isolated_profile=profile,
                isolated_port=port)
            token_info = read_token_with_note(
                Path(inputs["installed_app"]["path"]), profile)
            client2 = HelperClient(port, token_info["token"] or (client.token if client else ""))
            health_after = client2.request("GET", "/health")
            snap_after = snapshot_with_measured_ids(profile, label="relaunch-after")
            new_id = second["child"]
            same_process = (
                new_id["pid"] == first_id["pid"]
                and new_id.get("created_ms") == first_id.get("created_ms")
            )
            launcher.stop_owned(
                port=port, identity=new_id,
                token=token_info.get("token"), record=second)
            return {
                "first_identity": first_id,
                "second_identity": new_id,
                "terminated": stopped,
                "first_liveness_after_kill": live,
                "same_process": same_process,
                "before": snap_before,
                "after": snap_after,
                "ownership_before": ownership_before,
                "ownership_after": helper_ownership_state(profile),
                "health_before": health_before,
                "health_after": health_after,
                "dashboard": f"http://127.0.0.1:{port}/dashboard",
            }

        result = self._with_helper("relaunch", body)
        ok = (
            result.get("first_liveness_after_kill") != "alive"
            and result.get("first_liveness_after_kill") != "unknown"
            and not result.get("same_process")
            and result.get("second_identity", {}).get("pid")
            and (result.get("terminated") or {}).get("stopped")
        )
        return self.record("whole_helper_relaunch", "pass" if ok else "fail",
                           **result)

    def _helper_product_module(self) -> str | None:
        inputs = self._inputs()
        app = Path(inputs["installed_app"]["path"])
        path = app / "source_subscriptions.py"
        return str(path) if path.is_file() else None

    def _drive_helper_capture(self, client: HelperClient, profile: Path,
                              *, variant: str, operation_key: str) -> dict[str, Any]:
        """Standing capture through original helper routes, not child_instrument."""
        url = self._synthetic_url(variant)
        guid, title = self._identity_for_variant(variant)
        consented = self._register_and_consent(
            client, url=url, operation_key=operation_key, consent=True)
        refresh = None
        if consented.get("source_id"):
            refresh = client.request("POST", "/sources/refresh", {
                "source_id": consented["source_id"],
            }, timeout=30)
        standing = self._wait_standing(profile, timeout=40)
        if consented.get("source_id") and not standing.get("standing_charge_count"):
            refresh = client.request("POST", "/sources/refresh", {
                "source_id": consented["source_id"],
            }, timeout=30)
            standing = self._wait_standing(profile, timeout=20)
        deadline = time.time() + 25
        ownership = child_ownership_records(profile)
        while time.time() < deadline:
            ownership = child_ownership_records(profile)
            if ownership:
                break
            if (profile / "c22-inject-child.json").is_file():
                break
            time.sleep(0.3)
        return {
            "consented": consented,
            "refresh": refresh,
            "standing": standing,
            "synthetic_url": url,
            "episode_guid": guid,
            "episode_title": title,
            "ownership": ownership,
            "helper_state": helper_ownership_state(profile),
            "inject_child_file": (
                json.loads((profile / "c22-inject-child.json").read_text(encoding="utf-8"))
                if (profile / "c22-inject-child.json").is_file() else None
            ),
        }

    def _child_identity(self, child: dict[str, Any]) -> dict[str, Any]:
        pid = child.get("pid")
        created = child.get("created_ms")
        exe = child.get("executable")
        live = "unknown"
        if type(pid) is int and pid > 0:
            live = liveness(pid, created if type(created) is int else None)
        resolved_created = created if type(created) is int else None
        resolved_exe = exe
        if type(pid) is int:
            if resolved_created is None:
                resolved_created = created_ms_for_pid(pid)
            if not resolved_exe:
                resolved_exe = executable_for_pid(pid)
        return {
            **child,
            "liveness": live,
            "executable": resolved_exe,
            "created_ms": resolved_created,
            "unknown_stays_unknown": live == "unknown",
        }

    def _wait_surviving_exit(self, children: list[dict[str, Any]],
                             timeout: float = 20.0) -> list[dict[str, Any]]:
        deadline = time.time() + timeout
        observed = [dict(c) for c in children]
        while time.time() < deadline:
            still = []
            for child in observed:
                pid = child.get("pid")
                created = child.get("created_ms")
                live = liveness(pid, created) if type(pid) is int else "none"
                child["liveness"] = live
                if live == "alive":
                    still.append(child)
            if not still:
                break
            time.sleep(0.25)
        return observed

    def _child_lifetime(self) -> dict[str, Any]:
        profile = self._profile("child-life")
        before_state = helper_ownership_state(profile)
        inputs = self._inputs()
        port = inputs["isolated_port"]

        def body(record, client, launcher):
            driven = self._drive_helper_capture(
                client, profile, variant="child-life",
                operation_key="c22-child-life-on")
            live = []
            for item in driven.get("ownership") or []:
                for child in item.get("children") or []:
                    identity = {
                        **self._child_identity(child),
                        "start_id": item.get("start_id"),
                    }
                    live.append(identity)
                    launcher.register_descendant(identity)
            inject_note = driven.get("inject_child_file") or {}
            if inject_note.get("pid"):
                launcher.register_descendant(self._child_identity({
                    "pid": inject_note["pid"],
                    "executable": inject_note.get("executable"),
                    "unregistered": True,
                }))
            unknown = [c for c in live if c.get("liveness") == "unknown"]
            if unknown:
                raise C22ValidationError(
                    "registered child liveness is unknown; unknown cannot pass")
            alive = [
                c for c in live
                if c.get("liveness") == "alive"
                and type(c.get("pid")) is int
                and type(c.get("created_ms")) is int
                and c.get("executable")
            ]
            if not alive:
                raise C22ValidationError(
                    "registered child lifetime requires an alive exact identity")
            child = alive[0]
            first_id = record["child"]
            ledger_before = capture_ledger(profile)
            ownership_before_kill = helper_ownership_state(profile)
            if liveness(child["pid"], child.get("created_ms")) != "alive":
                raise C22ValidationError(
                    "child was not alive before owned helper terminate")
            stopped = launcher.terminate_owned(first_id, record=record)
            child_during = liveness(child["pid"], child.get("created_ms"))
            if child_during == "unknown":
                raise C22ValidationError(
                    "child liveness unknown after helper terminate")
            helper_killed_while_child_alive = child_during == "alive"
            second = launcher.start(
                profile_name="child-life-2", isolated_profile=profile,
                isolated_port=port)
            token_info = read_token_with_note(
                Path(inputs["installed_app"]["path"]), profile)
            client2 = HelperClient(
                port, token_info["token"] or (client.token if client else ""))
            health_after = client2.request("GET", "/health")
            ledger_after = capture_ledger(profile)
            ownership_after = helper_ownership_state(profile)
            new_id = second["child"]
            duplicate = (
                new_id["pid"] == first_id["pid"]
                and new_id.get("created_ms") == first_id.get("created_ms")
            )
            waited = self._wait_surviving_exit([child], timeout=25)
            child_unknown_after = any(
                c.get("liveness") == "unknown" for c in waited)
            child_exited = all(
                c.get("liveness") == "dead" for c in waited) and not child_unknown_after
            before_settlement_restart = helper_ownership_state(profile)
            launcher.stop_owned(
                port=port, identity=new_id,
                token=token_info.get("token"), record=second)
            if not child_exited:
                raise C22ValidationError("registered child did not reach exact observed death")
            third = launcher.start(profile_name="child-life-settlement", isolated_profile=profile,
                                   isolated_port=port)
            try:
                ledger_settled = capture_ledger(profile)
                settled = helper_ownership_state(profile)
                key = (ledger_before.get("starts") or [{}])[0].get("capture_key")
                lock_probe = probe_released_capture_lock(profile, key) if key else {"acquired_and_released": False}
            finally:
                settlement_stop = launcher.stop_owned(port=port, identity=third["child"],
                    token=token_info.get("token"), record=third)
            product = self._helper_product_module()
            delta = ledger_delta(ledger_before, ledger_after)
            return {
                "driven": driven,
                "children": live,
                "before_state": before_state,
                "ownership_before_kill": ownership_before_kill,
                "ownership_after_relaunch": ownership_after,
                "settled": settled,
                "before_settlement_restart": before_settlement_restart,
                "ledger_after_settlement": ledger_settled,
                "settlement_identity": third["child"],
                "settlement_stop": settlement_stop,
                "settled_lock_probe": lock_probe,
                "terminated": stopped,
                "helper_killed_while_child_alive": helper_killed_while_child_alive,
                "child_during_helper_stop": child_during,
                "first_identity": first_id,
                "second_identity": new_id,
                "duplicate_launch": duplicate,
                "ledger_before_kill": ledger_before,
                "ledger_after_relaunch": ledger_after,
                "charge_delta": delta.get("standing_charge_delta"),
                "publication_delta": delta.get("publication_delta"),
                "health_after": health_after,
                "surviving_until_exit": waited,
                "child_exited": child_exited,
                "instrument": {
                    "instrument": {
                        "product_module": product,
                        "helper_driven": True,
                        "inject": "spawn_child",
                    },
                    "ownership": driven.get("ownership"),
                },
            }

        result = self._with_helper("child-life", body, inject="spawn_child")
        unknown = [c for c in (result.get("children") or [])
                   if c.get("liveness") == "unknown"]
        recovery = child_recovery_oracles(
            children=result.get("children") or [],
            helper_terminated_while_child_alive=bool(
                result.get("helper_killed_while_child_alive")),
            relaunched=bool((result.get("second_identity") or {}).get("pid")),
            charge_delta=result.get("charge_delta"),
            publication_delta=result.get("publication_delta"),
            unknown=unknown,
            child_exited=bool(result.get("child_exited")),
            duplicate_launch=bool(result.get("duplicate_launch")),
        )
        product = ((result.get("instrument") or {}).get("instrument") or {}).get(
            "product_module")
        transition = child_transition_integrity(result)
        ok = recovery["ok"] and transition["ok"] and product and "source_subscriptions" in str(product)
        result["raw_transition_oracle"] = transition
        result["recovery"] = recovery
        return self.record("registered_child_lifetime", "pass" if ok else "fail",
                           **result)

    def _observe_unresolved_restart(self, profile_name, profile, launcher, record, client):
        inputs = self._inputs()
        port = inputs["isolated_port"]
        before = helper_ownership_state(profile)
        ledger_before = capture_ledger(profile)
        terminated = launcher.terminate_owned(record["child"], record=record)
        second = launcher.start(profile_name=profile_name + "-restart", isolated_profile=profile, isolated_port=port)
        try:
            after = helper_ownership_state(profile)
            ledger_after = capture_ledger(profile)
        finally:
            stopped = launcher.stop_owned(port=port, identity=second["child"], token=client.token, record=second)
        return {"before": before, "after": after, "ledger_before": ledger_before,
                "ledger_after": ledger_after, "first_identity": record["child"],
                "second_identity": second["child"], "terminated": terminated, "stop": stopped}

    def _launch_interrupt(self) -> dict[str, Any]:
        profile = self._profile("child-interrupt")

        def body(record, client, launcher):
            driven = self._drive_helper_capture(
                client, profile, variant="child-interrupt",
                operation_key="c22-interrupt-on")
            unresolved = [
                item for item in driven.get("ownership") or []
                if item.get("unresolved_launch") is True
            ]
            restart = self._observe_unresolved_restart("child-interrupt", profile, launcher, record, client)
            product = self._helper_product_module()
            return {
                "restart_observation": restart,
                "injection": "launch_interrupt",
                "driven": driven,
                "unresolved": unresolved,
                "helper_state": driven.get("helper_state"),
                "instrument": {
                    "instrument": {
                        "product_module": product,
                        "helper_driven": True,
                        "inject": "launch_interrupt",
                    },
                    "ownership": driven.get("ownership"),
                },
            }

        result = self._with_helper(
            "child-interrupt", body, inject="launch_interrupt")
        unresolved = result.get("unresolved") or []
        spawned_alive = []
        unknown = []
        for item in result.get("driven", {}).get("ownership") or []:
            for child in item.get("children") or []:
                identity = self._child_identity(child)
                if identity.get("liveness") == "unknown":
                    unknown.append(identity)
                elif identity.get("liveness") == "alive":
                    spawned_alive.append(identity)
        inject_note = (result.get("driven") or {}).get("inject_child_file") or {}
        if inject_note.get("pid"):
            identity = self._child_identity({
                "pid": inject_note["pid"],
                "executable": inject_note.get("executable"),
            })
            if identity.get("liveness") == "unknown":
                unknown.append(identity)
            elif identity.get("liveness") == "alive":
                spawned_alive.append(identity)
        oracle = interrupt_oracle(
            unresolved=unresolved,
            spawned_alive=spawned_alive,
            unknown=unknown,
            injection="launch_interrupt",
        )
        result["interrupt_oracle"] = oracle
        restart = unresolved_restart_integrity(result.get("restart_observation") or {})
        result["restart_oracle"] = restart
        return self.record("launch_interruption", "pass" if oracle["ok"] and restart["ok"] else "fail",
                           **result)

    def _registration_failure(self) -> dict[str, Any]:
        profile = self._profile("child-regfail")

        def body(record, client, launcher):
            driven = self._drive_helper_capture(
                client, profile, variant="child-regfail",
                operation_key="c22-regfail-on")
            unresolved = [
                item for item in driven.get("ownership") or []
                if item.get("unresolved_launch") is True
            ]
            surviving = []
            for item in unresolved:
                for child in item.get("children") or []:
                    if child.get("pid"):
                        surviving.append(self._child_identity(child))
            inject_note = driven.get("inject_child_file") or {}
            if inject_note.get("pid"):
                pid = inject_note["pid"]
                created = created_ms_for_pid(pid)
                exe = inject_note.get("executable") or executable_for_pid(pid)
                identity = self._child_identity({
                    "pid": pid,
                    "created_ms": created,
                    "executable": exe,
                    "unregistered": True,
                })
                surviving.append(identity)
                launcher.register_descendant(identity)
            restart = self._observe_unresolved_restart("child-regfail", profile, launcher, record, client)
            product = self._helper_product_module()
            return {
                "restart_observation": restart,
                "injection": "registration_failure",
                "distinct_from": "launch_interrupt",
                "driven": driven,
                "unresolved": unresolved,
                "surviving_unregistered": surviving,
                "instrument": {
                    "instrument": {
                        "product_module": product,
                        "helper_driven": True,
                        "inject": "registration_failure",
                    },
                    "ownership": driven.get("ownership"),
                },
            }

        result = self._with_helper(
            "child-regfail", body, inject="registration_failure")
        surviving = result.get("surviving_unregistered") or []
        unknown = [c for c in surviving if c.get("liveness") == "unknown"]
        if unknown:
            result["unknown_cannot_pass"] = True
            waited = surviving
            child_exited = False
        else:
            waited = self._wait_surviving_exit(surviving, timeout=25)
            child_exited = bool(waited) and all(
                c.get("liveness") == "dead" for c in waited)
        result["surviving_until_exit"] = waited
        oracle = registration_failure_oracle(
            unresolved=result.get("unresolved") or [],
            surviving=surviving,
            unknown=unknown,
            injection="registration_failure",
            child_exited=child_exited,
        )
        result["registration_failure_oracle"] = oracle
        restart = unresolved_restart_integrity(result.get("restart_observation") or {})
        result["restart_oracle"] = restart
        return self.record("registration_failure", "pass" if oracle["ok"] and restart["ok"] else "fail",
                           **result)

    def _browser_checkpoint(self) -> dict[str, Any]:
        inputs = self._inputs()
        profile = self._profile("empty")
        port = inputs["isolated_port"]
        snap = snapshot_with_measured_ids(profile, label="browser-checkpoint")
        protocol = {
            "dashboard_url": f"http://127.0.0.1:{port}/dashboard",
            "required_observation": [
                "UTC time",
                "visible consent/revision",
                "starts charged vs allowance",
                "in-flight or uncertain item if any",
            ],
            "pair_with": str(self.runner.receipt_root / "evidence" /
                             "browser-checkpoint.snapshot.json"),
            "screenshot": None,
            "screenshot_note": (
                "Ryan records the actual browser image. This kit will not "
                "synthesize a screenshot or process-completion image. A "
                "browser protocol without an image is unexecuted in all modes."
            ),
        }
        dest = self.runner.receipt_root / "evidence" / "browser_observation_protocol.json"
        dest.write_text(json.dumps(protocol, indent=2) + "\n", encoding="utf-8")
        (self.runner.receipt_root / "evidence" /
         "browser-checkpoint.snapshot.json").write_text(
            json.dumps(snap, indent=2, default=str) + "\n", encoding="utf-8")
        return self.record(
            "browser_state_checkpoint", "unexecuted",
            protocol=protocol, snapshot=snap,
            reason="browser protocol without an image is unexecuted in all modes",
        )

    def _protected(self) -> dict[str, Any]:
        if not self.phase2_baselines:
            raise C22ValidationError(
                "protected Phase 2 baseline was not recorded before scenarios")
        admitted_by_profile = {
            "one-off": self.outcomes.get("one_off_capture"),
            "manual-first": self.outcomes.get("manual_first"),
            "standing-first": self.outcomes.get("standing_first"),
            "child-life": self.outcomes.get("registered_child_lifetime"),
            "child-interrupt": self.outcomes.get("launch_interruption"),
            "child-regfail": self.outcomes.get("registration_failure"),
            "relaunch": self.outcomes.get("whole_helper_relaunch"),
            "empty": None,
            "populated": None,
        }
        compares = {}
        settings_cmp = {}
        all_ok = True
        for name in CAPTURE_PROFILE_NAMES:
            before = self.phase2_baselines.get(name)
            after = snapshot_with_measured_ids(
                self._profile(name), label=f"p2-{name}-after")
            allowed = derive_phase2_allowed(
                before=before, after=after,
                admitted=admitted_by_profile.get(name),
                profile_name=name,
            )
            cmp = phase2_compare(before, after, allowed)
            files_cmp = settings_and_pins_unchanged(before, after)
            compares[name] = cmp
            settings_cmp[name] = files_cmp
            all_ok = all_ok and cmp["ok"] and files_cmp["ok"]
        empty_cmp = compares.get("empty") or {}
        populated_cmp = compares.get("populated") or {}
        extra_compares = {
            name: compares[name]
            for name in CAPTURE_PROFILE_NAMES
            if name not in {"empty", "populated"}
        }
        apply_off = all(
            (settings_cmp.get(name) or {}).get("apply_off")
            for name in CAPTURE_PROFILE_NAMES
        )
        events = guard_event_summary({name: self._profile(name) for name in CAPTURE_PROFILE_NAMES})
        ok = all_ok and apply_off and events["ok"]
        return self.record(
            "protected_phase2_state", "pass" if ok else "fail",
            empty_compare=empty_cmp, populated_compare=populated_cmp,
            extra_compares=extra_compares,
            all_profile_compares=compares,
            runtime_guard_events=events,
            settings_and_pins=settings_cmp,
            compared_profiles=list(CAPTURE_PROFILE_NAMES),
            empty=(snapshot_with_measured_ids(
                self._profile("empty"), label="p2-empty-after-record").get("phase2")),
            populated=(snapshot_with_measured_ids(
                self._profile("populated"), label="p2-populated-after-record").get("phase2")),
            baseline_recorded_before_scenarios=True,
            librarian_apply_enabled=False,
            self_authorized_after_state=False,
        )

    def _upgrade(self) -> dict[str, Any]:
        manifest = load_manifest(
            self.runner.receipt_root / "manifest.used.json")
        kind = upgrade_kind(
            manifest,
            installed_version=None,
            package_version=None,
        )
        plan = self.runner.plan_inno(manifest, execute=False)
        labeled = upgrade_kind(
            manifest, installed_version="3.8.0", package_version="3.8.0")
        joined = " ".join(plan.get("argv") or [])
        return self.record(
            "upgrade_operator_step", "unexecuted",
            reason="real installed upgrade/reinstall is Ryan's operator step",
            planned_argv=plan["argv"],
            unspecified_kind=kind,
            same_version_label=labeled,
            agreed_inno_shape=(
                "/ISOLATED=1" in joined and "/PROFILE=" in joined
                and "/PORT=" in joined and "/DIR=" in joined
                and INNO_NOCLOSE_FLAG in joined
                and INNO_NORESTARTAPPS_FLAG in joined
            ),
            mislabel_guard="same-version reinstall is not a cross-version upgrade",
        )
