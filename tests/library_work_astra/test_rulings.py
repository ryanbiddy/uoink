"""Run L: one focused check for each assigned ruling, R2 through R5."""

import library_work
from test_projection import accepted, intent
from test_substrate import claim, fixture, submission


def test_r2_ready_reports_stored_recovery_state_across_endpoints():
    root, index, service, context, clock = fixture()
    try:
        work = claim(service, context)
        lease = dict(work_id=work["work_id"], attempt_token=work["attempt_token"],
                     client_id="client")
        calls = [
            (service.approve_taxonomy, dict(version_id="v2", nodes=[dict(
                shelf_id="s3", path=["Third"], definition="Third shelf",
                include=["third"], exclude=["other"],
            )])),
            (service.prepare_run, dict(run_id="r2", version_id="v1",
                                      video_ids=["fixture"], prompt_hash="0" * 64)),
            (service.refresh_run_item, dict(run_id="r1", video_id="fixture", reason="refresh")),
            (service.claim_work, dict(action="claim", run_id="r1", client_id="client")),
            (service.renew_attempt, dict(lease, action="renew", lease_seconds=60)),
            (service.release_attempt, dict(lease, action="release", reason="release")),
            (service.cancel_attempt, dict(lease, action="cancel", reason="cancel")),
            (service.submit_result, submission(work)),
            (service.preview_apply, dict(run_id="r1", expected_projection_revision=0)),
            (service.approve_preview, dict(preview_id="missing", delta_hash="0" * 64,
                                          operation_key="approve", expected_projection_revision=0)),
            (service.expire_attempts, {}),
        ]
        for state in ("conflict", "pending"):
            with index.write_transaction() as connection:
                connection.execute("UPDATE library_meta SET recovery_state=?", (state,))
            before = list(index._conn.iterdump())
            responses = [method(context, args) for method, args in calls]
            for (method, _), response in zip(calls, responses):
                assert response == dict(ok=False, schema_version=1, error=dict(
                    code=f"recovery_{state}",
                    message="Recover authoritative records before mutation",
                    retryable=state == "pending", details={},
                )), (method.__name__, response)
            assert list(index._conn.iterdump()) == before
    finally:
        index.close()


def test_r3_pending_recovery_freezes_list_and_expiry(monkeypatch):
    root, index, service, context, clock = fixture()
    try:
        work = claim(service, context)
        pin = intent(service, context, "pin", dict(
            video_id="fixture", shelf_id="s1", action="pin",
            expected_projection_revision=0, operation_key="pending-pin",
        ))
        project_record = service._project_record

        def interrupted_projection(*args):
            raise OSError("Injected projection failure after durable publication")

        monkeypatch.setattr(service, "_project_record", interrupted_projection)
        pending = service.pin_shelf(context, pin)
        assert pending["error"]["code"] == "recovery_pending", pending
        monkeypatch.setattr(service, "_project_record", project_record)
        clock[0] = work["lease_expires_ms"]
        before = list(index._conn.iterdump())
        files_before = {p.relative_to(root): p.read_bytes()
                        for p in (root / "library").rglob("*") if p.is_file()}
        expire = service._expire
        expire_calls = []

        def record_expiry(connection):
            expire_calls.append(True)
            return expire(connection)

        monkeypatch.setattr(service, "_expire", record_expiry)
        listed = service.list_work(context, dict(run_id="r1"))
        assert listed["ok"] and listed["recovery_state"] == "pending", listed
        assert listed["counts"] == {"leased": 1}
        assert listed["items"][0]["state"] == "leased"
        expired = service.expire_attempts(context, {})
        assert expired["error"]["code"] == "recovery_pending", expired
        assert expire_calls == []
        assert list(index._conn.iterdump()) == before
        assert {p.relative_to(root): p.read_bytes()
                for p in (root / "library").rglob("*") if p.is_file()} == files_before

        # After replay and reconsideration, new leases expire normally.
        assert service.recover_operations(context, {})["ok"]
        assert service.pin_shelf(context, pin)["after_revision"] == 1
        unpin = intent(service, context, "pin", dict(
            video_id="fixture", shelf_id="s1", action="unpin",
            expected_projection_revision=1, operation_key="unpin-after-replay",
        ))
        assert service.pin_shelf(context, unpin)["ok"]
        assert service.refresh_run_item(context, dict(
            run_id="r1", video_id="fixture", reason="reconsider after unpin",
        ))["ok"]
        for method, args in ((service.list_work, dict(run_id="r1")),
                             (service.expire_attempts, {})):
            work = claim(service, context)
            clock[0] = work["lease_expires_ms"]
            result = method(context, args)
            assert result["ok"], result
            assert index._conn.execute(
                "SELECT state FROM library_attempts WHERE attempt_token=?",
                (work["attempt_token"],),
            ).fetchone()[0] == "expired"
    finally:
        index.close()


def test_r4_pin_invalidated_preview_names_all_pin_conflicts():
    root, index, service, context, clock = accepted()
    try:
        # Both kinds of pin affect the same preview's target manifest.
        item = index.get_yoink("fixture")
        item.update(video_id="moved", slug="moved")
        index.upsert_yoink(item)
        with index.write_transaction() as connection:
            connection.execute("INSERT INTO clips(video_id,seq,start,end,text) "
                               "VALUES('moved',0,0,10,'Original source evidence.')")
        assert service.prepare_run(context, dict(
            run_id="both", version_id="v1", video_ids=["fixture", "moved"],
            prompt_hash="0" * 64,
        ))["ok"]
        claimed = service.claim_work(context, dict(action="claim", run_id="both", client_id="client"))
        assert claimed["ok"] and len(claimed["work"]) == 2, claimed
        for work in claimed["work"]:
            assert service.submit_result(context, submission(work, "both-" + work["video_id"]))["ok"]
        preview = service.preview_apply(context, dict(run_id="both", expected_projection_revision=0))
        assert preview["ok"], preview
        approval = dict(preview_id=preview["preview_id"], delta_hash=preview["delta_hash"],
                        operation_key="apply-both", expected_projection_revision=0)
        assert service.approve_preview(context, approval)["ok"]
        for revision, (video_id, shelf_id, action) in enumerate([
            ("fixture", "s1", "pin"), ("fixture", "s2", "pin"), ("moved", "s2", "move"),
        ]):
            pin = intent(service, context, "pin", dict(
                video_id=video_id, shelf_id=shelf_id, action=action,
                expected_projection_revision=revision, operation_key=f"pin-{revision}",
            ))
            assert service.pin_shelf(context, pin)["ok"]
        assert index._conn.execute("SELECT COUNT(*) FROM library_previews").fetchone()[0] == 0
        service = library_work.LibraryWorkService(index, root / "library", clock=lambda: clock[0],
                                                  librarian_apply_enabled=True)
        assert service.startup_status["ok"]
        before = list(index._conn.iterdump())
        expected = [dict(video_id="fixture", shelf_id="s1", pin_kind="pin"),
                    dict(video_id="fixture", shelf_id="s2", pin_kind="pin"),
                    dict(video_id="moved", shelf_id="s2", pin_kind="move")]
        for method, args in (
            (service.approve_preview, approval),
            (service.apply_preview, dict(mode="apply", **approval)),
            (service.preview_apply, dict(run_id="both", expected_projection_revision=0)),
        ):
            refused = method(context, args)
            assert not refused["ok"], refused
            details = refused["error"]["details"]
            assert details["conflicts"] == expected
            assert (details["expected_revision"], details["current_revision"]) == (0, 3)
            assert list(index._conn.iterdump()) == before
    finally:
        index.close()


def test_r5_list_reports_contract_version():
    root, index, service, context, clock = fixture()
    try:
        expected = "phase2-v1.2-2026-09-04"
        assert library_work.CONTRACT_VERSION == expected
        for state in ("ready", "pending", "conflict"):
            with index.write_transaction() as connection:
                connection.execute("UPDATE library_meta SET recovery_state=?", (state,))
            for args in ({}, dict(run_id="r1", state="leased", limit=1)):
                listed = service.list_work(context, args)
                assert listed["ok"] and listed["contract_version"] == expected, listed
                assert listed["schema_version"] == 1 and listed["recovery_state"] == state
    finally:
        index.close()
