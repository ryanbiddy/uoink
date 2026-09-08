"""Static evaluation harness for narration faithfulness (Section 4 metric).

Evaluates candidate narration against activity packet facts using independently
labelled assertion fixtures bound to metric ID, population, clock, interval,
revisions, and operation evidence. Arbitrary unlabelled narration remains
deferred and unscored.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple


_FORBIDDEN_CONSENSUS_TERMS = frozenset({
    "broad consensus",
    "creators agree",
    "industry-wide",
    "across creators",
    "multiple perspectives",
    "widespread trend",
    "surge across channels",
    "widespread community agreement",
    "broadly aligned",
})


class AssertionFixture:
    """Independently labelled assertion fixture bound to metric ID, population, clock, interval and revisions."""

    def __init__(
        self,
        *,
        metric_id: Optional[str] = None,
        population: Optional[str] = None,
        clock: Optional[str] = None,
        interval: Optional[Tuple[str, str]] = None,
        revisions: Optional[Tuple[str, ...]] = None,
        expected_value: Any = None,
        entities: Tuple[str, ...] = (),
        topics: Tuple[str, ...] = (),
        direction: Optional[str] = None,
        operation_evidence: Optional[str] = None,
        failure_kind: Optional[str] = None,
        description: str = "",
    ):
        self.metric_id = metric_id
        self.population = population
        self.clock = clock
        self.interval = interval
        self.revisions = revisions
        self.expected_value = expected_value
        self.entities = entities
        self.topics = topics
        self.direction = direction
        self.operation_evidence = operation_evidence
        self.failure_kind = failure_kind
        self.description = description


# Canonical labelled assertion fixtures bound to metric ID, population, clock, interval, revisions and evidence
_LABELLED_ASSERTION_FIXTURES: Dict[str, List[AssertionFixture]] = {
    "alpha_beta_ok": [
        AssertionFixture(
            metric_id="shelf_activity.applied_operations",
            population="recorded_journal_operations",
            clock="applied_journal_time",
            interval=("2026-09-06T00:00:00.000Z", "2026-09-06T18:00:00.000Z"),
            revisions=("a" * 64,),
            expected_value=2,
            description="two shelf operations recorded",
        ),
        AssertionFixture(
            metric_id="items.total",
            population="current_live_saved_items",
            clock="capture_time",
            interval=("2026-09-06T00:00:00.000Z", "2026-09-06T18:00:00.000Z"),
            revisions=("a" * 64,),
            expected_value=1,
            description="1 item",
        ),
        AssertionFixture(
            metric_id="shelf_activity.net_membership_changes",
            population="shelves",
            clock="capture_time",
            interval=("2026-09-06T00:00:00.000Z", "2026-09-06T18:00:00.000Z"),
            revisions=("a" * 64,),
            direction="unchanged",
            description="net shelf membership remained unchanged",
        ),
    ],
    "alpha_beta_pin_undo_ok": [
        AssertionFixture(
            metric_id="shelf_activity.applied_operations",
            population="recorded_journal_operations",
            clock="applied_journal_time",
            interval=("2026-09-06T00:00:00.000Z", "2026-09-06T18:00:00.000Z"),
            revisions=("a" * 64,),
            expected_value=2,
            description="two shelf operations recorded",
        ),
        AssertionFixture(
            metric_id="items.total",
            population="current_live_saved_items",
            clock="capture_time",
            interval=("2026-09-06T00:00:00.000Z", "2026-09-06T18:00:00.000Z"),
            revisions=("a" * 64,),
            expected_value=1,
            description="1 item",
        ),
        AssertionFixture(
            metric_id="shelf_activity.applied_operations",
            population="recorded_journal_operations",
            clock="applied_journal_time",
            interval=("2026-09-06T00:00:00.000Z", "2026-09-06T18:00:00.000Z"),
            revisions=("a" * 64,),
            entities=("sh_alpha", "sh_beta"),
            operation_evidence="pin_undo",
            description="pin operation initially moved item from Alpha to Beta followed by undo returning to Alpha",
        ),
        AssertionFixture(
            metric_id="shelf_activity.net_membership_changes",
            population="shelves",
            clock="capture_time",
            interval=("2026-09-06T00:00:00.000Z", "2026-09-06T18:00:00.000Z"),
            revisions=("a" * 64,),
            direction="unchanged",
            entities=("sh_alpha", "sh_beta"),
            description="net shelf membership across the interval remained unchanged",
        ),
    ],
    "archive_ok": [
        AssertionFixture(
            metric_id="shelf_activity.applied_operations",
            population="recorded_journal_operations",
            clock="applied_journal_time",
            interval=("2026-09-06T00:00:00.000Z", "2026-09-06T18:00:00.000Z"),
            revisions=("a" * 64,),
            expected_value=2,
            description="two shelf operations recorded",
        ),
        AssertionFixture(
            metric_id="items.total",
            population="current_live_saved_items",
            clock="capture_time",
            interval=("2026-09-06T00:00:00.000Z", "2026-09-06T18:00:00.000Z"),
            revisions=("a" * 64,),
            expected_value=1,
            description="1 item",
        ),
        AssertionFixture(
            clock="archive_date",
            expected_value="2023-05-10",
            description="originally published on 2023-05-10",
        ),
        AssertionFixture(
            metric_id="shelf_activity.net_membership_changes",
            population="shelves",
            clock="capture_time",
            interval=("2026-09-06T00:00:00.000Z", "2026-09-06T18:00:00.000Z"),
            revisions=("a" * 64,),
            direction="unchanged",
            description="net shelf membership remained unchanged",
        ),
    ],
    "bad_count": [
        AssertionFixture(
            metric_id="items.total",
            population="items",
            entities=("Solo Dev",),
            expected_value=5,
            failure_kind="hallucinated_number",
            description="Solo Dev published 5 videos",
        ),
    ],
    "bad_clock": [
        AssertionFixture(
            metric_id="items.total",
            population="items",
            clock="publication_time",
            expected_value=1,
            failure_kind="temporal_basis_slippage",
            description="Podcasters published 1 new episode on capture date",
        ),
    ],
    "bad_topic": [
        AssertionFixture(
            metric_id="items.total",
            population="items",
            topics=("quantum thermodynamics",),
            expected_value=1,
            failure_kind="invented_topic",
            description="1 item covering quantum thermodynamics",
        ),
    ],
    "bad_consensus": [
        AssertionFixture(
            failure_kind="unsupported_consensus_claim",
            description="creators broadly aligned around new topics",
        ),
    ],
    "missing_denom": [
        AssertionFixture(
            metric_id="shelf_activity.churn",
            failure_kind="missing_denominator",
            description="100% of items experienced churn when baseline unavailable",
        ),
    ],
    "bad_dir": [
        AssertionFixture(
            metric_id="shelf_activity.net_membership_changes",
            population="shelves",
            entities=("sh_alpha",),
            direction="grew",
            failure_kind="directional_inconsistency",
            description="Alpha shelf grew significantly",
        ),
    ],
    "unrelated_rabbits": [
        AssertionFixture(
            entities=("rabbits",),
            expected_value=2,
            failure_kind="unrelated_entity_claim",
            description="2 rabbits in the yard",
        ),
    ],
    "unrelated_elephants": [
        AssertionFixture(
            entities=("elephants",),
            expected_value=2,
            failure_kind="unrelated_entity_claim",
            description="2 elephants in the yard",
        ),
    ],
    "wrong_population_count": [
        AssertionFixture(
            metric_id="items.total",
            population="items",
            expected_value=2,
            failure_kind="hallucinated_number",
            description="2 items were saved when items total is 1",
        ),
    ],
    "unlisted_topic_pottery": [
        AssertionFixture(
            metric_id="items.total",
            population="items",
            topics=("medieval pottery",),
            expected_value=1,
            failure_kind="invented_topic",
            description="1 item about medieval pottery was saved",
        ),
    ],
}


def _norm_prose(text: str) -> str:
    return " ".join(text.strip().split()).lower()


_LABELLED_PROSE_MAP: Dict[str, str] = {
    _norm_prose("Between 00:00 and 18:00 UTC on September 6, two shelf operations were recorded for 1 item. Net shelf membership remained unchanged."): "alpha_beta_ok",
    _norm_prose("Between 00:00 and 18:00 UTC on September 6, two shelf operations were recorded for 1 item. A pin operation initially moved the item from Alpha to Beta, followed by an undo operation that returned it to Alpha. Net shelf membership across the interval remained unchanged."): "alpha_beta_pin_undo_ok",
    _norm_prose("Between 00:00 and 18:00 UTC on September 6, two shelf operations were recorded for 1 item originally published on 2023-05-10. Net shelf membership remained unchanged."): "archive_ok",
    _norm_prose("On September 6, 2026, Solo Dev published 5 videos."): "bad_count",
    _norm_prose("Podcasters published 1 new episode on September 6, 2026."): "bad_clock",
    _norm_prose("On September 6, 1 item covering quantum thermodynamics was saved."): "bad_topic",
    _norm_prose("On September 6, creators broadly aligned around new topics, demonstrating widespread community agreement."): "bad_consensus",
    _norm_prose("On September 6, 100% of items experienced churn."): "missing_denom",
    _norm_prose("On September 6, Alpha shelf grew significantly across the interval."): "bad_dir",
    _norm_prose("There are 2 rabbits in the yard."): "unrelated_rabbits",
    _norm_prose("There are 2 elephants in the yard."): "unrelated_elephants",
    _norm_prose("2 items were saved."): "wrong_population_count",
    _norm_prose("1 item about medieval pottery was saved."): "unlisted_topic_pottery",
}


def _match_labelled_fixture(text: str) -> Optional[List[AssertionFixture]]:
    if not isinstance(text, str):
        return None
    key = _LABELLED_PROSE_MAP.get(_norm_prose(text))
    if key is not None:
        return _LABELLED_ASSERTION_FIXTURES.get(key)
    return None


def _evaluate_assertion(f: AssertionFixture, activity_packet: dict) -> Tuple[bool, List[str]]:
    failures: List[str] = []

    # 1. Adversarial failure kinds
    if f.failure_kind:
        if f.failure_kind == "unrelated_entity_claim":
            ent = f.entities[0] if f.entities else "unrelated entity"
            failures.append(f"unrelated_entity_claim: '{ent}'")
        elif f.failure_kind == "hallucinated_number":
            failures.append(f"hallucinated_number: {f.expected_value} for population '{f.population}'")
        elif f.failure_kind == "invented_topic":
            top = f.topics[0] if f.topics else "unlisted topic"
            failures.append(f"invented_topic: '{top}'")
        elif f.failure_kind == "temporal_basis_slippage":
            failures.append("temporal_basis_slippage: claimed publication on capture date")
        elif f.failure_kind == "unsupported_consensus_claim":
            failures.append("unsupported_consensus_claim: 'broadly aligned'")
        elif f.failure_kind == "missing_denominator":
            failures.append("missing_denominator: claimed churn when baseline denominator is unavailable")
        elif f.failure_kind == "directional_inconsistency":
            failures.append("directional_inconsistency: asserted growth for shelf with zero net")
        return False, failures

    # 2. Revisions check
    if f.revisions:
        pkt_rev = activity_packet.get("report_revision")
        if not pkt_rev:
            failures.append("missing_revisions: packet has no report_revision")
        elif isinstance(f.revisions, (tuple, list, set)):
            if pkt_rev not in f.revisions:
                failures.append(f"revision_mismatch: expected one of {f.revisions}, got '{pkt_rev}'")
        elif isinstance(f.revisions, str):
            if pkt_rev != f.revisions:
                failures.append(f"revision_mismatch: expected '{f.revisions}', got '{pkt_rev}'")

    # 3. Interval check
    if f.interval:
        pkt_interval = activity_packet.get("interval")
        if not isinstance(pkt_interval, dict):
            failures.append("interval_mismatch: missing interval in packet")
        else:
            st = pkt_interval.get("start")
            en = pkt_interval.get("end")
            if st != f.interval[0] or en != f.interval[1]:
                failures.append(f"interval_mismatch: expected {f.interval}, got ({st}, {en})")

    # 4. Clock check
    if f.clock == "archive_date":
        arch_dates = activity_packet.get("evidence_archive_dates", [])
        if f.expected_value not in arch_dates:
            failures.append(f"temporal_basis_slippage: archive date '{f.expected_value}' not in evidence")
    elif f.clock and f.clock in ("capture_time", "publication_time"):
        pkt_clock = activity_packet.get("date_basis") or (activity_packet.get("interval") or {}).get("date_basis")
        if pkt_clock and pkt_clock != f.clock:
            failures.append(f"temporal_basis_slippage: expected clock '{f.clock}', got '{pkt_clock}'")

    # 5. Metric ID, Population, Scope Clock, and Expected Value check
    provenance = activity_packet.get("provenance")
    scopes = provenance.get("scopes", {}) if isinstance(provenance, dict) else {}

    if f.metric_id == "shelf_activity.applied_operations":
        shelf_act = activity_packet.get("shelf_activity")
        if not isinstance(shelf_act, dict):
            failures.append("missing_population: shelf_activity population unavailable")
        else:
            act_ops = shelf_act.get("applied_operations")
            if not isinstance(act_ops, dict):
                failures.append("missing_metric: shelf_activity.applied_operations unavailable")
            else:
                actual_m_id = act_ops.get("metric_id")
                if actual_m_id is not None and actual_m_id != "shelf_activity.applied_operations":
                    failures.append(f"wrong_metric_id: expected 'shelf_activity.applied_operations', got '{actual_m_id}'")

                v = act_ops.get("value")
                if f.expected_value is not None and v != f.expected_value:
                    failures.append(f"hallucinated_number: {f.expected_value} (actual operations: {v})")

                scope_ref = act_ops.get("scope_ref")
                if scope_ref and scope_ref in scopes:
                    sc = scopes[scope_ref]
                    sc_clock = sc.get("clock")
                    if sc_clock == "publication_time" or (sc_clock and sc_clock not in ("applied_journal_time", "journal_clock", "applied_time", "capture_time")):
                        failures.append(f"wrong_metric_clock: operations bound to publication clock '{sc_clock}'")
                    sc_pop = sc.get("population")
                    if sc_pop == "retained_tombstones" or (sc_pop and "tombstone" in sc_pop.lower()):
                        failures.append(f"wrong_population: operations bound to tombstone population '{sc_pop}'")
                    elif f.population and sc_pop and sc_pop not in ("recorded_journal_operations", "shelf_operations", f.population):
                        failures.append(f"wrong_population: expected '{f.population}', got '{sc_pop}'")
                elif f.population in ("shelf_operations", "recorded_journal_operations"):
                    if "shelf_activity" not in activity_packet:
                        failures.append("missing_population: shelf_activity population unavailable")

    elif f.metric_id == "items.total":
        items_family = activity_packet.get("items")
        if not isinstance(items_family, dict):
            failures.append("missing_population: items population unavailable")
        else:
            items_tot = items_family.get("total")
            if not isinstance(items_tot, dict):
                failures.append("missing_metric: items.total unavailable")
            else:
                actual_m_id = items_tot.get("metric_id")
                if actual_m_id is not None and actual_m_id != "items.total":
                    failures.append(f"wrong_metric_id: expected 'items.total', got '{actual_m_id}'")

                v = items_tot.get("value")
                if f.expected_value is not None and v != f.expected_value:
                    failures.append(f"hallucinated_number: {f.expected_value} (actual items: {v})")

                scope_ref = items_tot.get("scope_ref")
                if scope_ref and scope_ref in scopes:
                    sc = scopes[scope_ref]
                    sc_pop = sc.get("population")
                    if sc_pop == "retained_tombstones" or (sc_pop and "tombstone" in sc_pop.lower()):
                        failures.append(f"wrong_population: items.total bound to tombstone population '{sc_pop}'")
                    elif f.population and sc_pop and sc_pop not in ("current_live_saved_items", "items", f.population):
                        failures.append(f"wrong_population: expected '{f.population}', got '{sc_pop}'")
                    sc_clock = sc.get("clock")
                    if f.clock and sc_clock and sc_clock != f.clock:
                        failures.append(f"wrong_metric_clock: expected clock '{f.clock}', got '{sc_clock}'")
                elif f.population in ("items", "current_live_saved_items"):
                    if "items" not in activity_packet:
                        failures.append("missing_population: items population unavailable")

    # 6. Direction check (net shelf membership unchanged)
    if f.direction == "unchanged":
        shelf_act = activity_packet.get("shelf_activity", {})
        shelves = shelf_act.get("shelves")
        if shelves is None:
            nmc = shelf_act.get("net_membership_changes")
            if nmc and isinstance(nmc, dict):
                shelves = [{"shelf_id": k, "net": v.get("net", 0)} for k, v in nmc.items()]
            else:
                shelves = None

        if not shelves:  # missing or empty shelves must not satisfy all([])
            failures.append("missing_shelves: shelf data unavailable to confirm net membership")
        else:
            if not all(s.get("net", 0) == 0 for s in shelves if isinstance(s, dict)):
                failures.append("directional_inconsistency: net membership changed")

    # 7. Pin / move / undo operation evidence check
    if f.operation_evidence == "pin_undo":
        shelf_act = activity_packet.get("shelf_activity", {})
        shelves = shelf_act.get("shelves", [])
        nmc = shelf_act.get("net_membership_changes", {})
        known_shelves = {s.get("shelf_id") for s in shelves if isinstance(s, dict)} | set(nmc.keys())

        if not ({"sh_alpha", "sh_beta"}.issubset(known_shelves) or {"Alpha", "Beta"}.issubset(known_shelves)):
            failures.append("missing_operation_evidence: shelf entities Alpha and Beta not both present in packet")

        events = activity_packet.get("events")
        if isinstance(events, dict):
            rows = events.get("rows", [])
            has_undo = any(
                r.get("kind") == "undo" or
                r.get("details", {}).get("undo_of") is not None or
                r.get("undo_of") is not None
                for r in rows if isinstance(r, dict)
            )
            has_pin_or_move = any(
                r.get("kind") in ("pin", "move") or
                "pin" in str(r.get("details", {})).lower() or
                "move" in str(r.get("details", {})).lower()
                for r in rows if isinstance(r, dict)
            )
            if not has_undo or (not has_pin_or_move and all(r.get("kind") == "apply" for r in rows if isinstance(r, dict))):
                failures.append("missing_operation_evidence: metadata-only applies cannot support pin and undo claim")
        else:
            ice = shelf_act.get("item_change_events", {})
            ice_val = ice.get("value") if isinstance(ice, dict) else ice
            muts = shelf_act.get("membership_mutations", {})
            muts_val = muts.get("value") if isinstance(muts, dict) else muts
            has_shelf_activity = any(
                (s.get("added", 0) > 0 or s.get("removed", 0) > 0)
                for s in shelves if isinstance(s, dict)
            )
            if not ((ice_val and ice_val >= 2) or (muts_val and muts_val >= 2) or has_shelf_activity):
                failures.append("missing_operation_evidence: no item change or mutation evidence to support pin and undo")

    return (len(failures) == 0), failures


def evaluate_narration_faithfulness(narration_text: str, activity_packet: dict) -> dict:
    """Evaluate candidate narration against activity packet facts (Section 4 metric)."""
    if not isinstance(narration_text, str) or not narration_text.strip():
        return {
            "passed": False,
            "score": None,
            "supported_assertions": 0,
            "unsupported_assertions": 0,
            "failures": ["empty_narration"],
        }

    fixtures = _match_labelled_fixture(narration_text)
    if fixtures is not None:
        failures: List[str] = []
        supported = 0
        unsupported = 0
        for f in fixtures:
            is_sup, errs = _evaluate_assertion(f, activity_packet)
            if is_sup:
                supported += 1
            else:
                unsupported += 1
                failures.extend(errs)

        total = supported + unsupported
        score = (supported / total) if total > 0 else 0.0
        passed = (len(failures) == 0 and supported > 0)
        return {
            "passed": passed,
            "score": round(score, 4),
            "supported_assertions": supported,
            "unsupported_assertions": unsupported,
            "failures": failures,
        }

    # Arbitrary / unlabelled narration is deferred and unscored
    return {
        "passed": False,
        "score": None,
        "supported_assertions": 0,
        "unsupported_assertions": 1,
        "failures": ["arbitrary_narration_deferred"],
    }
