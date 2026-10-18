"""Named pytest union for AZ-5g2. Explicit selectors only; never PowerShell $args."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Task-specific named selectors for the AZ-5d2 union plus AZ-5h, AZ-5h2, BA-4,
# BA-5, all three measurement generations, and Phase 4 resources/prompts/briefs.
NAMED_SELECTORS = [
    "tests/test_phase5_az5h.py",
    "tests/test_phase5_az5h2.py",
    "tests/test_phase5_az5d2.py",
    "tests/library_work_astra/test_phase5_ba4_acceptance.py",
    "tests/library_work_astra/test_phase5_ba5_acceptance.py",
    "tests/library_work_astra/test_phase5_acceptance.py",
    "tests/library_work_astra/test_phase5_acceptance2.py",
    "tests/library_work_astra/test_phase5_acceptance3.py",
    "tests/library_work_astra/test_phase5_dashboard.py",
    "tests/library_work_astra/test_phase5_dashboard2.py",
    "tests/library_work_astra/test_phase5_dashboard3.py",
    "tests/library_work_astra/test_phase5_measurements.py",
    "tests/library_work_astra/test_phase5_measurements2.py",
    "tests/library_work_astra/test_phase5_measurements3.py",
    "tests/test_library_analysis_fixtures.py",
    "tests/test_phase0_registry_capture.py",
    "tests/test_source_subscriptions_registry.py",
    "tests/test_c01_mcp_stdio.py",
    "tests/test_phase4_stdio.py",
    "tests/test_stdio_clip_tools.py",
    "tests/test_docs_live_contracts.py",
    "tests/test_current_doc_references.py",
    "tests/test_dashboard_sources_api.py",
    "tests/test_dashboard_sources_ui.py",
    "tests/test_dashboard_v324_ui.py",
    "tests/test_library_adapters.py",
    "tests/test_library_resources.py",
    "tests/test_library_prompts.py",
    "tests/test_library_briefs.py",
]


def main() -> int:
    scratch = ROOT / "_scratch" / "az5g2"
    xml = scratch / "combined.xml"
    basetemp = scratch / "pytest-temp"
    xml.parent.mkdir(parents=True, exist_ok=True)
    argv = [
        sys.executable,
        "-B",
        "-m",
        "pytest",
        "-q",
        "--tb=short",
        "-p",
        "no:cacheprovider",
        f"--junitxml={xml}",
        f"--basetemp={basetemp}",
        *NAMED_SELECTORS,
    ]
    (scratch / "union-command.txt").write_text(" ".join(argv) + "\n", encoding="utf-8")
    print("AZ-5g2 union:", " ".join(argv[3:]), flush=True)
    completed = subprocess.run(argv, cwd=ROOT)
    return int(completed.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
