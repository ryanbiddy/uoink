from __future__ import annotations

import pytest

import server


@pytest.mark.parametrize(
    "argv",
    [
        [],
        ["--show-dashboard"],
        ["--doctor"],
        ["--migrate-dry-run"],
        ["--heal-paths"],
        ["--heal-paths", "C:/corpus"],
        ["--export-corpus"],
        ["--import-corpus"],
        ["--import-corpus", "C:/backup.json"],
        ["--rebuild-index"],
        ["--rebuild-index", "C:/corpus"],
        ["--backfill-authors"],
        ["--backfill-authors", "--dry-run"],
    ],
)
def test_documented_server_cli_shapes_remain_valid(argv):
    assert server._cli_arguments_valid(argv) is True


@pytest.mark.parametrize(
    "argv",
    [
        ["--unknown"],
        ["--show-dashboard", "--unknown"],
        ["--doctor", "--migrate-dry-run"],
        ["--doctor", "--unknown"],
        ["--dry-run", "--backfill-authors"],
        ["--import-corpus", "backup.json", "--unknown"],
        ["--rebuild-index", "--unknown"],
    ],
)
def test_unsupported_server_cli_shapes_fail_validation(argv):
    assert server._cli_arguments_valid(argv) is False


def test_documented_service_launch_shapes_still_reach_main(monkeypatch):
    calls = []
    monkeypatch.setattr(
        server,
        "main",
        lambda **kwargs: calls.append(kwargs),
    )

    assert server.run_cli([]) == 0
    assert server.run_cli(["--show-dashboard"]) == 0
    assert calls == [
        {"show_dashboard": False},
        {"show_dashboard": True},
    ]


def test_unknown_and_help_arguments_never_start_the_service(
    monkeypatch, capsys
):
    def unexpected_main(**kwargs):
        pytest.fail(f"unsupported CLI arguments started the service: {kwargs}")

    monkeypatch.setattr(server, "main", unexpected_main)

    assert server.run_cli(["--unknown"]) == 2
    unknown = capsys.readouterr()
    assert "unknown argument '--unknown'" in unknown.err

    assert server.run_cli(["--help"]) == 0
    help_output = capsys.readouterr()
    assert "usage: python server.py" in help_output.out
    assert help_output.err == ""


def test_maintenance_commands_reject_trailing_flags(
    monkeypatch, capsys
):
    def unexpected_doctor():
        pytest.fail("invalid doctor arguments reached doctor_payload")

    monkeypatch.setattr(server, "doctor_payload", unexpected_doctor)

    assert server.run_cli(["--doctor", "--unknown"]) == 2
    output = capsys.readouterr()
    assert "unknown argument '--unknown'" in output.err
