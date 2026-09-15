#!/usr/bin/env python3
"""Compare weighted and unweighted item search on the Living Library copy.

The 20 cases are hand-scored against a known relevant item or channel. Title
cases use words from that item's title, channel cases use the channel name,
and body cases use a phrase read from the stored corpus text. The database is
always opened read-only.

Run:
    PYTHONPATH=. python scripts/library/bm25_eval.py
    PYTHONPATH=. python scripts/library/bm25_eval.py --db path/to/index-copy.db
"""

from __future__ import annotations

import argparse
import os
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from index import Index, _fts_query


DEFAULT_INDEX = (
    Path(os.environ.get("LOCALAPPDATA", "."))
    / "AgentControlRoom"
    / "uoink-index-copy-2026-09-04.db"
)


@dataclass(frozen=True)
class QueryCase:
    kind: str
    query: str
    target: str
    reason: str

    def relevant(self, row: sqlite3.Row) -> bool:
        if self.kind == "channel":
            return row["channel"] == self.target
        return row["video_id"] == self.target


CASES = (
    QueryCase(
        "title", "object detection computer vision", "WgPbbWmnXJ8",
        "All four words occur in the target course title.",
    ),
    QueryCase(
        "title", "training LLMs CERN lecture", "2094362669444648960",
        "The target title names a CERN lecture on training LLMs.",
    ),
    QueryCase(
        "title", "Codex 10M Users ChatGPT Work", "episode_9ddb44f98b2",
        "The podcast title contains this exact identifying phrase.",
    ),
    QueryCase(
        "title", "AI Time Something Fixable", "647pSnX5H_Y",
        "The target title says AI time is being wasted on something fixable.",
    ),
    QueryCase(
        "title", "Every Level Claude Explained", "ZRb7D6R64hM",
        "The words reproduce the target's title.",
    ),
    QueryCase(
        "title", "Clone Youtube channel Claude Code", "MJmoSxSPeRY",
        "The target title contains every query term.",
    ),
    QueryCase(
        "title", "Hedge Fund Implosion AI", "episode_ee13d34d83c",
        "The podcast title contains the full identifying phrase.",
    ),
    QueryCase(
        "channel", "Alex Volkov ThursdAI", "Alex Volkov from ThursdAI",
        "Any item from the exact channel is relevant.",
    ),
    QueryCase(
        "channel", "Nous Research", "Nous Research",
        "Any item from the exact channel is relevant.",
    ),
    QueryCase(
        "channel", "MIT OpenCourseWare", "MIT OpenCourseWare",
        "Any item from the exact channel is relevant.",
    ),
    QueryCase(
        "channel", "OpenAI Developers", "OpenAI Developers",
        "Any item from the exact channel is relevant.",
    ),
    QueryCase(
        "channel", "The All-In Podcast", "The All-In Podcast",
        "Any item from the exact channel is relevant.",
    ),
    QueryCase(
        "body", "blue line purple detector tracker", "WgPbbWmnXJ8",
        "The target transcript explains its tracker's blue and purple lines.",
    ),
    QueryCase(
        "body", "multi-head attention purple curve", "2094362669444648960",
        "The target transcript discusses a purple multi-head-attention curve.",
    ),
    QueryCase(
        "body", "site side by side verbose skills", "episode_9ddb44f98b2",
        "The target podcast passage discusses verbose skills beside a site.",
    ),
    QueryCase(
        "body", "giant lava lamp screen saver", "iyVXw-SoUrY",
        "The target transcript compares an artwork to both objects.",
    ),
    QueryCase(
        "body", "supply chain robotics export controls", "2092270658524745728",
        "The target transcript connects export controls to the robotics supply chain.",
    ),
    QueryCase(
        "body", "private state overall state nodes", "2083691176830390272",
        "The target workshop passage contrasts private and overall graph state.",
    ),
    QueryCase(
        "body", "plugins add-ons install", "647pSnX5H_Y",
        "The target transcript warns that calling plugins add-ons undersells them.",
    ),
    QueryCase(
        "body", "voice-based welcome calls insurance products", "2094872636996165632",
        "The target transcript names welcome calls and insurance cross-sells.",
    ),
)


def _weights_sql(raw: str) -> str:
    values = [part.strip() for part in raw.split(",")]
    if len(values) != 7:
        raise ValueError("expected seven yoinks_fts column weights")
    return ", ".join(str(float(value)) for value in values)


def _open_read_only(path: Path) -> sqlite3.Connection:
    resolved = path.resolve()
    if not resolved.is_file():
        raise FileNotFoundError(resolved)
    conn = sqlite3.connect(
        f"file:{resolved.as_posix()}?mode=ro",
        uri=True,
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    return conn


def _search(conn: sqlite3.Connection, query: str,
            weights: str | None) -> list[sqlite3.Row]:
    match = _fts_query(query)
    if not match:
        return []
    rank = "bm25(yoinks_fts)"
    if weights is not None:
        rank = f"bm25(yoinks_fts, {weights})"
    return conn.execute(
        "SELECT y.video_id, y.title, y.channel, "
        f"{rank} AS score "
        "FROM yoinks_fts f "
        "JOIN yoinks y ON y.video_id=f.video_id "
        "WHERE yoinks_fts MATCH ? AND y.deleted_at IS NULL "
        f"ORDER BY {rank}, y.video_id",
        (match,),
    ).fetchall()


def _relevant_rank(case: QueryCase, rows: list[sqlite3.Row]) -> int | None:
    return next(
        (rank for rank, row in enumerate(rows, 1) if case.relevant(row)),
        None,
    )


def _display_row(row: sqlite3.Row | None) -> str:
    if row is None:
        return "—"
    title = re.sub(r"\s+", " ", row["title"] or "(untitled)").strip()
    channel = re.sub(r"\s+", " ", row["channel"] or "unknown").strip()
    if len(title) > 54:
        title = title[:51].rstrip() + "..."
    return f"{title} [{channel}]"


def _rank_label(rank: int | None) -> str:
    return str(rank) if rank is not None else "not found"


def evaluate(conn: sqlite3.Connection, weights: str) -> tuple[int, int, int]:
    weighted_wins = baseline_wins = ties = 0
    summary = []
    for number, case in enumerate(CASES, 1):
        baseline = _search(conn, case.query, None)
        weighted = _search(conn, case.query, weights)
        baseline_rank = _relevant_rank(case, baseline)
        weighted_rank = _relevant_rank(case, weighted)

        baseline_value = baseline_rank if baseline_rank is not None else 10**9
        weighted_value = weighted_rank if weighted_rank is not None else 10**9
        if weighted_value < baseline_value:
            verdict = "weighted"
            weighted_wins += 1
        elif baseline_value < weighted_value:
            verdict = "unweighted"
            baseline_wins += 1
        else:
            verdict = "tie"
            ties += 1
        summary.append((number, case, baseline_rank, weighted_rank, verdict))

        print(f"\n[{number:02}] {case.kind.upper()}: {case.query}")
        print(f"Relevant: {case.reason}")
        print("| rank | unweighted | weighted |")
        print("|---:|---|---|")
        for rank in range(5):
            left = baseline[rank] if rank < len(baseline) else None
            right = weighted[rank] if rank < len(weighted) else None
            print(
                f"| {rank + 1} | {_display_row(left)} | "
                f"{_display_row(right)} |"
            )
        print(
            "Verdict: "
            f"{verdict} (relevant rank {_rank_label(baseline_rank)} -> "
            f"{_rank_label(weighted_rank)})"
        )

    print("\nG2 SCORECARD")
    print("| # | kind | query | unweighted rank | weighted rank | winner |")
    print("|---:|---|---|---:|---:|---|")
    for number, case, baseline_rank, weighted_rank, verdict in summary:
        print(
            f"| {number} | {case.kind} | {case.query} | "
            f"{_rank_label(baseline_rank)} | {_rank_label(weighted_rank)} | "
            f"{verdict} |"
        )
    print(
        f"\nWeighted wins: {weighted_wins}; unweighted wins: "
        f"{baseline_wins}; ties: {ties}."
    )
    outcome = "PASS" if weighted_wins > baseline_wins else "FAIL"
    print(f"G2: {outcome}")
    return weighted_wins, baseline_wins, ties


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=DEFAULT_INDEX)
    parser.add_argument(
        "--weights",
        default=Index._YOINKS_BM25_WEIGHTS,
        help="seven comma-separated yoinks_fts bm25 weights",
    )
    args = parser.parse_args()
    weights = _weights_sql(args.weights)

    print(f"Database: {args.db.resolve()} (read-only)")
    print(f"Weights: {weights}")
    with _open_read_only(args.db) as conn:
        if conn.execute("SELECT COUNT(*) FROM yoinks").fetchone()[0] == 0:
            raise RuntimeError("index copy contains no yoinks")
        weighted_wins, baseline_wins, _ties = evaluate(conn, weights)
    return 0 if weighted_wins > baseline_wins else 1


if __name__ == "__main__":
    raise SystemExit(main())
