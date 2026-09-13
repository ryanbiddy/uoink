"""Read the completed inert preflight; run no tests or product code."""
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(r"E:\AI\projects\uoink\checkouts\Yoink-library")
HERE = Path(__file__).resolve().parent
OUT = HERE / "native02-contract-result.json"
assert not OUT.exists()
spec = importlib.util.spec_from_file_location("partition_exit_contract", ROOT / "_scratch/partition_exit_contract.py")
helper = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = helper
spec.loader.exec_module(helper)
folder = HERE / "native02-partition"
result = helper.validate_partition(
    selected=json.loads((folder / "membership.json").read_bytes()),
    reports=[json.loads(line) for line in (folder / "reports.jsonl").read_text().splitlines()],
    session=json.loads((folder / "session.json").read_bytes()),
    verifier_results=json.loads((ROOT / "_scratch/partition-subtest-native02/results.json").read_bytes()),
    outer_exit=json.loads((HERE / "native02-launch/result.json").read_text(encoding="utf-8-sig"))["exit"],
    junit_xml=(ROOT / "_scratch/partition-subtest-native02/tests.xml").read_bytes(),
)
OUT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
print(json.dumps({k: v for k, v in result.items() if k not in {"cases", "failed_phases", "failed_subtests"}}, indent=2))
