"""D-17 (2026-09-04): "the server performs no LLM reasoning on the user's
behalf except through named, default-off, metered feature flags."

Two closing changes, both tested here:

1. ``entity_extraction_enabled`` -- the third background model call gets the
   same named default-off flag as Comment Intelligence and Hook Type. The
   gate is on the *spawn*; ``extract_entities`` itself stays key-gated so a
   user-initiated call still works.
2. The real ``usage`` block of every response is metered into the KV rollup
   (``usage_meter``), per feature / model / month, atomically.

Exit evidence from REPAIR-BRIEF-2026-09-04.md: a saved key plus all
background flags off produces zero background model calls through the real
capture path with ``_anthropic_messages`` faked; usage rows appear for a
flagged call.
"""
from __future__ import annotations

import json
import tempfile
import threading
import types
from datetime import datetime, timezone
from pathlib import Path

import pytest

import index as index_mod
import server
import usage_meter


FAKE_KEY = "sk-ant-test-fake-key"


def _settings_with(monkeypatch, **flags):
    data = server._normalize_settings(dict(flags))
    monkeypatch.setattr(server, "_read_settings", lambda: dict(data))
    return data


def _saved_key(monkeypatch, key: str = FAKE_KEY):
    monkeypatch.setattr(server, "_get_saved_anthropic_key", lambda: key)


# ---- 1. the flag is named, default-off, writable ---------------------------

def test_entity_extraction_flag_default_off():
    defaults = server._default_settings()
    assert "entity_extraction_enabled" in defaults
    assert defaults["entity_extraction_enabled"] is False


def test_entity_extraction_flag_normalizes_and_is_public():
    assert server._normalize_settings({})["entity_extraction_enabled"] is False
    assert server._normalize_settings(
        {"entity_extraction_enabled": 1})["entity_extraction_enabled"] is True
    # An existing settings.json that predates the flag resolves to OFF
    # (clean default-off, no grandfathering).
    legacy = server._normalize_settings({"hook_type_enabled": True})
    assert legacy["entity_extraction_enabled"] is False
    assert server._public_settings({})["entity_extraction_enabled"] is False
    assert server._public_settings(
        {"entity_extraction_enabled": True})["entity_extraction_enabled"] is True


def test_entity_extraction_flag_settable_via_settings_post(monkeypatch):
    written: list[dict] = []
    monkeypatch.setattr(server, "_read_settings", lambda: server._default_settings())
    monkeypatch.setattr(server, "_write_settings", written.append)
    _saved_key(monkeypatch, "")

    class Probe:
        def __init__(self):
            self.responses = []

        def _send_json(self, status, payload):
            self.responses.append((status, payload))

    probe = Probe()
    server.Handler._handle_settings_post(probe, {"entity_extraction_enabled": True})
    status, payload = probe.responses[-1]
    assert status == 200, payload
    assert written and written[-1]["entity_extraction_enabled"] is True
    assert payload["settings"]["entity_extraction_enabled"] is True

    probe = Probe()
    server.Handler._handle_settings_post(
        probe, {"entity_extraction_enabled": "yes"})
    status, payload = probe.responses[-1]
    assert status == 400, payload


# ---- 2. the spawn gate reads the flag, not the key -------------------------

def test_entity_extraction_thread_respects_flag(monkeypatch, tmp_path):
    def boom(*_a, **_k):
        raise AssertionError("background model call with the flag off")
    monkeypatch.setattr(server, "_anthropic_messages", boom)
    _saved_key(monkeypatch)
    _settings_with(monkeypatch)  # every flag off, key present
    assert server._start_entity_extraction_thread(
        tmp_path, "vid-1", {"video_id": "vid-1"}) is None

    # Flag on: the worker starts (and is fully stubbed so it does nothing).
    _settings_with(monkeypatch, entity_extraction_enabled=True)
    started = threading.Event()
    monkeypatch.setattr(server, "_extract_entities",
                        lambda *_a, **_k: started.set())
    thread = server._start_entity_extraction_thread(
        tmp_path, "vid-1", {"video_id": "vid-1"})
    assert thread is not None
    thread.join(timeout=5)
    assert started.is_set()

    # Flag on but the key was marked invalid: still no spawn.
    _settings_with(monkeypatch, entity_extraction_enabled=True,
                   anthropic_key_invalid=True)
    assert server._start_entity_extraction_thread(
        tmp_path, "vid-1", {"video_id": "vid-1"}) is None


def test_extract_entities_itself_stays_key_gated(monkeypatch):
    """The flag belongs on the spawn. A user-initiated call with a saved
    key still runs (D-17 rows 2b/3b pattern)."""
    _saved_key(monkeypatch)
    _settings_with(monkeypatch)  # flag OFF
    calls: list[dict] = []

    def fake(*_a, **kwargs):
        calls.append(kwargs)
        return {"content": [{"type": "text",
                             "text": '{"entities": [{"name": "Ada", "type": "person", "mentions": []}]}'}],
                "usage": {"input_tokens": 10, "output_tokens": 5}}
    monkeypatch.setattr(server, "_anthropic_messages", fake)
    monkeypatch.setattr(server, "_record_anthropic_usage", lambda *_a: None)
    out = server.extract_entities("[0.0] Ada wrote the first program",
                                  title="t", channel="c")
    assert calls and out[0]["name"] == "Ada"


# ---- 3. end-to-end: key saved, every flag off, zero model calls ------------

def _fake_run_subprocess(cmd, **kwargs):
    parts = [str(c) for c in cmd]
    is_ffmpeg = parts and parts[0].endswith("ffmpeg")
    out = None
    if "-o" in parts:
        out = parts[parts.index("-o") + 1]
    elif is_ffmpeg:
        out = parts[-1]
    if is_ffmpeg and out:
        shot = Path(out.replace("%04d", "0001"))
        shot.parent.mkdir(parents=True, exist_ok=True)
        shot.write_bytes(b"\xff\xd8\xff\xe0jpg")
    elif out:
        base_dir = Path(out).parent
        base_dir.mkdir(parents=True, exist_ok=True)
        (base_dir / "video.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp4")
        (base_dir / "video.en.srt").write_text(
            "1\n00:00:00,000 --> 00:00:02,000\nAda Lovelace wrote it\n\n"
            "2\n00:00:02,000 --> 00:00:04,000\nabout ai agents\n",
            encoding="utf-8")
    return types.SimpleNamespace(returncode=0, stdout="", stderr=b"")


_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
_METADATA = {
    "id": "dQw4w9WgXcQ",
    "title": "D-17 capture",
    "description": "a normal long-form video",
    "channel": "somechannel",
    "duration": 212,
    "thumbnails": [],
    "webpage_url": _URL,
}


def _capture_with(monkeypatch, *, settings: dict) -> tuple[dict, list]:
    """Run the real capture path (yt-dlp / ffmpeg mocked, no network) with
    the given settings and a saved key. The entity-extraction spawn is NOT
    stubbed. Returns (sidecar, model_calls)."""
    model_calls: list[dict] = []

    def fake_messages(*_a, **kwargs):
        model_calls.append(kwargs)
        raise AssertionError("model egress reached with every flag off")

    tmp = tempfile.TemporaryDirectory()
    idx = index_mod.Index.open(Path(tmp.name) / "index.db")
    root = Path(tmp.name) / "corpus"
    root.mkdir(parents=True)
    try:
        monkeypatch.setattr(server, "DESKTOP_ROOT", root)
        monkeypatch.setattr(server, "_get_index", lambda: idx)
        monkeypatch.setattr(server, "_run_subprocess", _fake_run_subprocess)
        monkeypatch.setattr(server, "_download_thumbnail", lambda *a, **k: None)
        monkeypatch.setattr(server, "_fetch_channel_context", lambda *a, **k: {})
        monkeypatch.setattr(server, "_start_comments_thread", lambda *a, **k: None)
        monkeypatch.setattr(server, "_anthropic_messages", fake_messages)
        _saved_key(monkeypatch)
        _settings_with(monkeypatch, **settings)

        folder = root / "AI" / "d17-case"
        result = server._run_extraction(
            _URL, 30, folder, open_explorer=False, metadata=_METADATA,
            source_type=None, generate_paste=False)
        assert result["ok"] is True, result
        # Let any background thread that *did* spawn run to completion.
        for t in threading.enumerate():
            if t.name.startswith("entity-extraction-"):
                t.join(timeout=10)
        sidecar = json.loads(
            (folder / f"{folder.name}.json").read_text(encoding="utf-8"))
        return sidecar, model_calls
    finally:
        idx.close()
        tmp.cleanup()


def test_saved_key_with_all_flags_off_makes_zero_background_model_calls(monkeypatch):
    sidecar, model_calls = _capture_with(monkeypatch, settings={})
    assert model_calls == []
    assert sidecar["entity_extraction_status"] == "skipped"
    assert sidecar.get("hook_type") is None
    assert sidecar.get("comment_intelligence") is None


def test_sidecar_entity_status_matches_gate_when_flag_on(monkeypatch):
    """Flag on + key: the sidecar says pending and the worker does run
    (its model call is the one the fake refuses, so it lands as failed --
    the point is that it *spawned* and that it went through the gate)."""
    sidecar, model_calls = _capture_with(
        monkeypatch, settings={"entity_extraction_enabled": True})
    assert len(model_calls) == 1
    assert sidecar["entity_extraction_status"] in {"pending", "failed"}


# ---- 4. usage is read, per feature / model / month, atomically -------------

@pytest.fixture
def idx(tmp_path):
    handle = index_mod.Index.open(tmp_path / "index.db")
    try:
        yield handle
    finally:
        handle.close()


def _resp(text="ok", **usage):
    return {"model": "claude-haiku-4-5-20251001",
            "content": [{"type": "text", "text": text}],
            "usage": usage}


def test_usage_recorded_and_summed(idx):
    when = datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc)
    first = usage_meter.record_usage(
        idx, "hook_type", _resp(input_tokens=1200, output_tokens=80,
                                cache_read_input_tokens=100),
        now=when, price=server._anthropic_estimated_cost)
    second = usage_meter.record_usage(
        idx, "hook_type", _resp(input_tokens=800, output_tokens=20),
        now=when, price=server._anthropic_estimated_cost)
    assert first["calls"] == 1 and second["calls"] == 2
    assert second["input_tokens"] == 2000
    assert second["output_tokens"] == 100
    assert second["cache_read"] == 100
    assert second["last_usage"] == {"input_tokens": 800, "output_tokens": 20,
                                    "cache_read": 0, "cache_create": 0}
    assert second["est_usd"] == server._anthropic_estimated_cost(2000, 100)

    key = usage_meter.usage_key("hook_type", "claude-haiku-4-5-20251001", "2026-09")
    assert key == "usage.anthropic.hook_type.claude-haiku-4-5-20251001.2026-09"
    row = idx._conn.execute(
        "SELECT value FROM memory_layer WHERE key=?", (key,)).fetchone()
    assert row is not None
    stored = json.loads(row[0])
    assert stored["calls"] == 2 and stored["input_tokens"] == 2000
    assert stored["month"] == "2026-09"


def test_usage_is_model_specific(idx):
    when = datetime(2026, 9, 4, tzinfo=timezone.utc)
    usage_meter.record_usage(idx, "hook_type", _resp(input_tokens=10, output_tokens=1), now=when)
    other = {**_resp(input_tokens=5, output_tokens=1), "model": "claude-sonnet-5"}
    usage_meter.record_usage(idx, "hook_type", other, now=when)
    buckets = usage_meter.read_buckets(idx, month="2026-09")
    assert {b["model"] for b in buckets} == {"claude-haiku-4-5-20251001", "claude-sonnet-5"}
    assert all(b["calls"] == 1 for b in buckets)
    summary = usage_meter.month_summary(idx, month="2026-09",
                                        price=server._anthropic_estimated_cost)
    assert summary["by_feature"]["hook_type"]["calls"] == 2
    assert summary["by_feature"]["hook_type"]["input_tokens"] == 15
    assert sorted(summary["by_feature"]["hook_type"]["models"]) == [
        "claude-haiku-4-5-20251001", "claude-sonnet-5"]


@pytest.fixture(autouse=True)
def _fresh_meter_status():
    usage_meter.reset_status()
    yield
    usage_meter.reset_status()


class _BrokenIndex:
    def write_transaction(self):
        raise RuntimeError("locked")


def test_usage_missing_is_not_fatal_and_not_silent(idx):
    """Metering stays best-effort (never raises, never fails the call) but
    a response without usage is counted, not dropped."""
    when = datetime(2026, 9, 4, tzinfo=timezone.utc)
    no_block = usage_meter.record_usage(idx, "hook_type", {"content": []}, now=when)
    assert no_block["calls"] == 0 and no_block["unavailable_calls"] == 1
    malformed = usage_meter.record_usage(idx, "hook_type", {"usage": "nope"}, now=when)
    assert malformed["calls"] == 0 and malformed["unavailable_calls"] == 2
    assert malformed["last_unavailable_at"] == "2026-09-04T00:00:00Z"
    assert malformed["last_call_at"] is None and malformed["last_usage"] is None
    # Not a response at all: nothing happened, nothing to count.
    assert usage_meter.record_usage(idx, "hook_type", None) is None
    (bucket,) = usage_meter.read_buckets(idx)
    assert bucket["unavailable_calls"] == 2 and bucket["calls"] == 0
    assert usage_meter.meter_status()["write_failures"] == 0
    # Usage that was available but could not be stored is a visible write
    # failure, not a silent None.
    assert usage_meter.record_usage(None, "hook_type", _resp(input_tokens=1)) is None
    assert usage_meter.record_usage(_BrokenIndex(), "hook_type", _resp(input_tokens=1)) is None
    status = usage_meter.meter_status()
    assert status["write_failures"] == 2 and status["ok"] is False
    assert status["last_error"] == "RuntimeError"
    assert status["last_failed_feature"] == "hook_type"
    assert status["last_failure_at"]


# ---- 5. run F acceptance, case 3: missing usage is visible -----------------

def test_missing_usage_is_visible_in_the_public_meter(monkeypatch, idx):
    """Astra's reproduction (tests/acceptance_run_f_probe.py): the real
    ``_record_anthropic_usage`` with a successful-looking response that has
    model and text but no ``usage``. Before: 0 rows, ``total_usd`` 0.0, no
    marker. Now the call is counted as unavailable everywhere the meter is
    read."""
    monkeypatch.setattr(server, "_get_index", lambda: idx)
    server._record_anthropic_usage("entity_extraction", {
        "model": "fixture-model",
        "content": [{"type": "text", "text": "ok"}]})
    (bucket,) = usage_meter.read_buckets(idx)
    assert bucket["feature"] == "entity_extraction"
    assert bucket["model"] == "fixture-model"
    assert bucket["calls"] == 0 and bucket["unavailable_calls"] == 1
    assert bucket["input_tokens"] == 0 and bucket["est_usd"] == 0.0

    actual = server._anthropic_actual_usage_payload()
    assert "error" not in actual
    assert actual["unavailable_calls"] == 1
    feature = actual["by_feature"]["entity_extraction"]
    assert feature["unavailable_calls"] == 1 and feature["calls"] == 0
    assert feature["models"] == ["fixture-model"]
    assert actual["total_usd"] == 0.0 and actual["estimate"] is True
    assert actual["status"]["ok"] is True

    # A later metered call on the same bucket keeps both counts.
    server._record_anthropic_usage("entity_extraction", {
        "model": "fixture-model", "usage": {"input_tokens": 7, "output_tokens": 3}})
    feature = server._anthropic_actual_usage_payload()["by_feature"]["entity_extraction"]
    assert feature["calls"] == 1 and feature["unavailable_calls"] == 1
    assert feature["input_tokens"] == 7


def test_cache_only_usage_is_priced_with_rate_provenance(idx):
    """Astra's reproduction: 1,000 cache-read tokens and nothing else used
    to price to $0.0 because only input/output had rates. Every counter now
    has its own rate, and the rates used travel with the number."""
    when = datetime(2026, 9, 4, tzinfo=timezone.utc)
    bucket = usage_meter.record_usage(idx, "entity_extraction", {
        "model": "fixture-model",
        "usage": {"input_tokens": 0, "output_tokens": 0,
                  "cache_read_input_tokens": 1000}},
        now=when, rates=server.ANTHROPIC_RATES)
    assert bucket["cache_read"] == 1000
    assert bucket["est_usd"] == pytest.approx(
        1000 / 1_000_000 * server.ANTHROPIC_PRICING_CACHE_READ_PER_MILLION)
    assert bucket["est_usd"] > 0.0
    assert bucket["est_rates"] == {
        "input_per_million": server.ANTHROPIC_PRICING_INPUT_PER_MILLION,
        "output_per_million": server.ANTHROPIC_PRICING_OUTPUT_PER_MILLION,
        "cache_read_per_million": server.ANTHROPIC_PRICING_CACHE_READ_PER_MILLION,
        "cache_create_per_million": server.ANTHROPIC_PRICING_CACHE_CREATE_PER_MILLION,
        "source": server.ANTHROPIC_PRICING_SOURCE,
        "source_checked": server.ANTHROPIC_PRICING_SOURCE_CHECKED,
    }
    assert bucket["est_rates"]["source"].startswith("https://")
    datetime.strptime(bucket["est_rates"]["source_checked"], "%Y-%m-%d")

    # Cache creation is priced at its own (higher) rate.
    bucket = usage_meter.record_usage(idx, "entity_extraction", {
        "model": "fixture-model",
        "usage": {"cache_creation_input_tokens": 1000}},
        now=when, rates=server.ANTHROPIC_RATES)
    assert bucket["cache_create"] == 1000
    assert bucket["est_usd"] == pytest.approx(
        1000 / 1_000_000 * (server.ANTHROPIC_PRICING_CACHE_READ_PER_MILLION
                            + server.ANTHROPIC_PRICING_CACHE_CREATE_PER_MILLION))
    assert server.ANTHROPIC_PRICING_CACHE_CREATE_PER_MILLION > \
        server.ANTHROPIC_PRICING_CACHE_READ_PER_MILLION

    summary = usage_meter.month_summary(idx, month="2026-09",
                                        rates=server.ANTHROPIC_RATES)
    feature = summary["by_feature"]["entity_extraction"]
    assert feature["cache_read"] == 1000 and feature["cache_create"] == 1000
    assert feature["usd"] == pytest.approx(0.00135) and summary["total_usd"] > 0.0
    assert summary["estimate"] is True
    assert summary["rates"]["source"] == server.ANTHROPIC_PRICING_SOURCE
    assert summary["rates"]["source_checked"] == server.ANTHROPIC_PRICING_SOURCE_CHECKED
    # The legacy two-argument pricer still works, and says it priced no cache.
    legacy = usage_meter.month_summary(idx, month="2026-09", price=lambda i, o: i + o)
    assert legacy["by_feature"]["entity_extraction"]["usd"] == 0.0
    assert legacy["rates"] is None and legacy["estimate"] is True


def test_pricing_payload_carries_cache_rates_and_provenance():
    pricing = server._anthropic_pricing_payload()
    assert pricing["cache_read_per_million"] == server.ANTHROPIC_PRICING_CACHE_READ_PER_MILLION
    assert pricing["cache_create_per_million"] == server.ANTHROPIC_PRICING_CACHE_CREATE_PER_MILLION
    assert pricing["source"] == server.ANTHROPIC_RATES["source"]
    assert pricing["source_checked"] == server.ANTHROPIC_RATES["source_checked"]
    assert server.ANTHROPIC_RATES["cache_read_per_million"] < \
        server.ANTHROPIC_RATES["input_per_million"] < \
        server.ANTHROPIC_RATES["cache_create_per_million"]


def test_meter_write_failure_is_visible_status(monkeypatch, idx):
    """A meter write that cannot happen leaves visible accounting status,
    separate from the (successful) inference it was metering."""
    def broken():
        raise RuntimeError("index unavailable")
    monkeypatch.setattr(server, "_get_index", broken)
    server._record_anthropic_usage("hook_type", _resp(input_tokens=5, output_tokens=1))
    status = usage_meter.meter_status()
    assert status["write_failures"] == 1 and status["ok"] is False
    assert status["last_error"] == "RuntimeError"
    assert status["last_failed_feature"] == "hook_type"
    # The public payload shows it even while the index is unreadable ...
    actual = server._anthropic_actual_usage_payload()
    assert actual["error"] == "usage unavailable"
    assert actual["unavailable_calls"] is None
    assert actual["status"]["write_failures"] == 1 and actual["status"]["ok"] is False
    assert actual["rates"]["source"] == server.ANTHROPIC_PRICING_SOURCE
    # ... and once it is readable again, with the rows that did land.
    monkeypatch.setattr(server, "_get_index", lambda: idx)
    server._record_anthropic_usage("hook_type", _resp(input_tokens=5, output_tokens=1))
    actual = server._anthropic_actual_usage_payload()
    assert "error" not in actual
    assert actual["by_feature"]["hook_type"]["calls"] == 1
    assert actual["status"]["write_failures"] == 1 and actual["status"]["ok"] is False

    # A write refused because an unrelated transaction is open (the shared
    # boundary from run E) is a lost write too, and says so.
    idx._conn.execute(
        "INSERT INTO memory_layer(key,value,updated_at) VALUES('pending','1','2026-09-04')")
    try:
        assert usage_meter.record_usage(idx, "hook_type", _resp(input_tokens=1)) is None
        assert idx._conn.in_transaction  # the other caller's work is untouched
    finally:
        idx._conn.rollback()
    assert usage_meter.meter_status()["write_failures"] == 2
    assert usage_meter.read_buckets(idx)[0]["calls"] == 1


def test_usage_writes_are_atomic_across_threads(idx):
    when = datetime(2026, 9, 4, tzinfo=timezone.utc)
    n_threads, per_thread = 8, 25

    def worker():
        for _ in range(per_thread):
            usage_meter.record_usage(
                idx, "entity_extraction",
                _resp(input_tokens=3, output_tokens=2), now=when)

    threads = [threading.Thread(target=worker) for _ in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    (bucket,) = usage_meter.read_buckets(idx, month="2026-09")
    assert bucket["calls"] == n_threads * per_thread
    assert bucket["input_tokens"] == 3 * n_threads * per_thread
    assert bucket["output_tokens"] == 2 * n_threads * per_thread


def test_flagged_call_records_usage_through_server(monkeypatch, idx):
    """A Hook Type call with a stubbed ``_anthropic_messages`` lands a
    usage row via the server's call-site hook."""
    monkeypatch.setattr(server, "_get_index", lambda: idx)
    _saved_key(monkeypatch)
    _settings_with(monkeypatch, hook_type_enabled=True)
    monkeypatch.setattr(server, "_anthropic_messages", lambda *a, **k: _resp(
        text='{"hook_type": "curiosity_gap", "confidence": 4, "reasoning": "x"}',
        input_tokens=1200, output_tokens=80))
    server.analyze_hook_type({"title": "t", "description": "d", "channel": "c"})
    server.analyze_hook_type({"title": "t", "description": "d", "channel": "c"})
    buckets = usage_meter.read_buckets(idx)
    assert len(buckets) == 1
    assert buckets[0]["feature"] == "hook_type"
    assert buckets[0]["calls"] == 2
    assert buckets[0]["input_tokens"] == 2400

    pricing = server._anthropic_pricing_payload()
    actual = pricing["actual"]
    assert actual["month"] == usage_meter.month_of()
    assert actual["by_feature"]["hook_type"]["calls"] == 2
    assert actual["total_usd"] == server._anthropic_estimated_cost(2400, 160)


def test_pricing_payload_survives_missing_index(monkeypatch):
    def broken():
        raise RuntimeError("no index")
    monkeypatch.setattr(server, "_get_index", broken)
    actual = server._anthropic_pricing_payload()["actual"]
    assert actual["by_feature"] == {}
    assert actual["error"] == "usage unavailable"


def test_usage_meter_makes_no_network_or_model_imports():
    source = Path(usage_meter.__file__).read_text(encoding="utf-8")
    for banned in ("urllib", "requests", "httpx", "anthropic", "openai", "socket"):
        assert f"import {banned}" not in source
        assert f"from {banned}" not in source
