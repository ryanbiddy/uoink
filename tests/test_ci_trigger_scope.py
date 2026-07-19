from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"


def _yaml_block(lines: list[str], header: str) -> list[str]:
    start = lines.index(header)
    indent = len(header) - len(header.lstrip())
    block: list[str] = []
    for line in lines[start + 1:]:
        if line and len(line) - len(line.lstrip()) <= indent:
            break
        block.append(line)
    return block


def test_feature_branches_run_once_via_pull_request():
    lines = WORKFLOW.read_text(encoding="utf-8").splitlines()
    on_block = _yaml_block(lines, "on:")
    push_block = _yaml_block(on_block, "  push:")
    pull_request_block = _yaml_block(on_block, "  pull_request:")

    assert "    branches:" in push_block
    assert "      - v2-integration" in push_block
    assert "      - main" in push_block
    assert "    tags:" in push_block
    assert '      - "v*"' in push_block

    assert "    branches:" in pull_request_block
    assert "      - v2-integration" in pull_request_block
    assert "      - main" in pull_request_block


def test_stale_runs_cancel_within_each_pull_request_or_ref():
    lines = WORKFLOW.read_text(encoding="utf-8").splitlines()
    concurrency_block = _yaml_block(lines, "concurrency:")

    assert (
        "  group: ci-${{ github.event.pull_request.number || github.ref }}"
        in concurrency_block
    )
    assert "  cancel-in-progress: true" in concurrency_block
