"""Run K: reproduce the intended churn case through the frozen service API."""

from test_substrate import fixture, submission


def test_three_of_ten_churn_with_authoritative_taxonomy():
    """P2-3: 30% churn needs approval of that exact delta and ceiling."""
    root, index, service, context, clock = fixture()
    try:
        video_ids = ["fixture"] + [f"churn-{i}" for i in range(9)]
        for video_id in video_ids[1:]:
            item = index.get_yoink("fixture")
            item.update(video_id=video_id, slug=video_id)
            index.upsert_yoink(item)
            with index.write_transaction() as connection:
                connection.execute(
                    "INSERT INTO clips(video_id,seq,start,end,text) VALUES(?,0,0,10,?)",
                    (video_id, "Original source evidence."),
                )

        def stage(run_id, moved):
            prepared = service.prepare_run(context, dict(
                run_id=run_id, version_id="v1", video_ids=video_ids,
                prompt_hash="0" * 64,
            ))
            assert prepared["ok"], prepared
            claimed = service.claim_work(context, dict(
                action="claim", run_id=run_id, client_id="client", max_items=10,
            ))
            assert claimed["ok"], claimed
            assert {work["video_id"] for work in claimed["work"]} == set(video_ids)
            for work in claimed["work"]:
                request = submission(work, f"{run_id}-{work['video_id']}")
                if work["video_id"] in moved:
                    request["result"]["memberships"][0].update(
                        shelf_id="s2", shelf_path=["Other"],
                    )
                result = service.submit_result(context, request)
                assert result["ok"] and result["outcome"] == "accepted", result

        def approval(preview, key, revision):
            return dict(
                preview_id=preview["preview_id"], delta_hash=preview["delta_hash"],
                operation_key=key, expected_projection_revision=revision,
            )

        # Establish the baseline through an approved apply, after taxonomy publication.
        stage("baseline", set())
        service.librarian_apply_enabled = True  # Disposable fixture only.
        initial = service.preview_apply(context, dict(
            run_id="baseline", expected_projection_revision=0, activate_version=True,
        ))
        assert initial["ok"] and initial["initial_filing"], initial
        initial_approval = approval(initial, "baseline-apply", 0)
        assert service.approve_preview(context, initial_approval)["ok"]
        baseline_receipt = service.apply_preview(context, dict(mode="apply", **initial_approval))
        assert baseline_receipt["ok"] and baseline_receipt["after_revision"] == 1, baseline_receipt

        connection = index._conn
        baseline = connection.execute("SELECT * FROM item_shelves ORDER BY video_id").fetchall()
        assert len(baseline) == 10
        moved = set(video_ids[:3])
        stage("change", moved)
        preview = service.preview_apply(context, dict(
            run_id="change", expected_projection_revision=1,
        ))
        assert preview["ok"], preview
        assert (preview["changed_items"], preview["baseline_items"], preview["churn_percent"]) == (3, 10, 30.0)
        assert not preview["initial_filing"] and not preview["can_apply"]
        assert set(preview["summary"]["changed_item_ids"]) == moved
        assert len(preview["summary"]["items"]) == 10
        assert preview["manifest_exclusions"] == []
        assert "churn_approval_required" in {reason["code"] for reason in preview["reasons"]}

        change_approval = approval(preview, "change-apply", 1)
        for ceiling in (None, 29):
            request = dict(change_approval)
            if ceiling is not None:
                request["approved_churn_percent"] = ceiling
            refused = service.approve_preview(context, request)
            assert not refused["ok"] and refused["error"]["code"] == "churn_limit", refused
        unapproved = service.apply_preview(context, dict(mode="apply", **change_approval))
        assert not unapproved["ok"] and unapproved["error"]["code"] == "preview_approval_required", unapproved
        assert connection.execute("SELECT * FROM item_shelves ORDER BY video_id").fetchall() == baseline
        assert connection.execute("SELECT projection_revision FROM library_meta").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM library_operation_receipts").fetchone()[0] == 1

        approved = service.approve_preview(context, dict(change_approval, approved_churn_percent=30))
        assert approved["ok"], approved
        request = dict(mode="apply", **change_approval)
        receipt = service.apply_preview(context, request)
        assert receipt["ok"] and receipt["after_revision"] == 2, receipt
        assert service.apply_preview(context, request) == receipt
        rows = connection.execute("SELECT * FROM item_shelves ORDER BY video_id").fetchall()
        assert len(rows) == 10
        assert {row["video_id"] for row in rows if row["shelf_id"] == "s2"} == moved
        assert all(row["is_primary"] and not row["locked"] for row in rows)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        index.close()
