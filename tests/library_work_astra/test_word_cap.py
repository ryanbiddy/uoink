"""Service boundary checks, including a supported full-card submission."""
import copy
import json
import sys
import unicodedata
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from test_library_work_validation import make_validation_environment, make_valid_submission_payload


@pytest.mark.parametrize("basis", ["packet", "fetched_full"])
@pytest.mark.parametrize("words", [23, 24, 25, 26])
def test_quote_boundary_and_retry(tmp_path, basis, words):
    text = "Café " + " ".join(f"w{i}" for i in range(1, 26))
    idx, svc, ctx, work, _ = make_validation_environment(tmp_path, excerpt_text=text)
    try:
        quote = "\t  ".join(unicodedata.normalize("NFD", text).split()[:words])
        payload = make_valid_submission_payload(work, quote=quote)
        if basis == "fetched_full":
            card = svc._card(idx._conn, work["video_id"], "full")
            payload["result"]["memberships"][0]["evidence"].update(
                basis=basis, card_hash=card["card_hash"], excerpt_id=card["excerpts"][0]["excerpt_id"])
        result = svc.submit_result(ctx, payload)
        assert result["outcome"] == ("accepted" if words <= 24 else "rejected"), result
        assert idx._conn.execute("SELECT count(*) FROM item_shelves").fetchone()[0] == 0
        assert idx._conn.execute("SELECT count(*) FROM library_proposals").fetchone()[0] == int(words <= 24)
        if words > 24:
            assert result["rejected"][0]["field"] == "result.memberships[0].evidence.quote"
            assert result["retryable"] is True
            row = idx._conn.execute("SELECT result_json FROM library_submissions").fetchone()
            assert json.loads(row[0]) == payload["result"]
            retry = svc.claim_work(ctx, dict(action="claim", run_id="run_val_01", client_id=ctx.client_id,
                                             max_items=1, lease_seconds=600))["work"][0]
            assert retry["attempt_token"] != work["attempt_token"]
            accepted = svc.submit_result(ctx, make_valid_submission_payload(retry, key="retry", quote="Café w1"))
            assert accepted["outcome"] == "accepted", accepted
    finally:
        idx.close()


def test_secondary_failure_is_atomic(tmp_path):
    text = " ".join(f"w{i}" for i in range(26))
    idx, svc, ctx, work, _ = make_validation_environment(tmp_path, excerpt_text=text)
    try:
        payload = make_valid_submission_payload(work, quote="w0 w1")
        secondary = copy.deepcopy(payload["result"]["memberships"][0])
        secondary.update(shelf_id="shelf_other", shelf_path=["Other Shelf"])
        secondary["evidence"]["quote"] = text
        payload["result"]["memberships"].append(secondary)
        response = svc.submit_result(ctx, payload)
        assert response["outcome"] == "rejected"
        assert response["rejected"][0]["field"] == "result.memberships[1].evidence.quote"
        assert response["accepted_memberships"] == []
        assert idx._conn.execute("SELECT count(*) FROM library_proposals").fetchone()[0] == 0
        assert json.loads(idx._conn.execute("SELECT result_json FROM library_submissions").fetchone()[0]) == payload["result"]
    finally:
        idx.close()
