"""Dispatch a frozen source/receipt review through subscription Control Room."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

root = Path(r"E:\AI\projects\uoink\checkouts\Yoink-library")
brief = root / "docs/library/proof/notices-operations-adapter-council-supplement-brief-2026-09-13/SUPPLEMENT-BRIEF.md"
assert os.environ.get("IG_FORBIDDEN_LIVE") == r"C:\Users\hello\AppData\Local\Uoink\index.db"
assert len(sys.argv) == 3
assert hashlib.sha256(brief.read_bytes()).hexdigest() == sys.argv[2]
source = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
assert source == sys.argv[1]
assert not subprocess.check_output(["git", "status", "--porcelain"], cwd=root, text=True).strip()
out = root / "_scratch/notices-operations-adapter-council-supplement01-dispatch"
out.mkdir(exist_ok=False)
env = os.environ.copy()
for key in list(env):
    upper = key.upper()
    if any(part in upper for part in ("API_KEY", "AUTH_TOKEN", "ACCESS_TOKEN", "BASE_URL", "OAUTH_TOKEN")) or upper.startswith(("ANTHROPIC_", "OPENAI_", "GOOGLE_API_", "GEMINI_API_", "XAI_", "GROK_", "CLAUDE_CODE_USE_")):
        env.pop(key, None)
env["PYTHONDONTWRITEBYTECODE"] = "1"
goal = ("Open " + brief.as_posix() + " first and read its companion COVERAGE.json and the catalog it names. "
        "Resolve all selected repository-relative proof roots under your assigned worktree. "
        "Complete all 39 omitted file reads in the three bounded source/receipt review groups. "
        "Write docs/library/GEMINI-NOTICES-OPERATIONS-ADAPTER-COUNCIL-SUPPLEMENT-2026-09-13.md early and complete it; this is the only allowed write. "
        "No subagents, tests, code/native/model execution, artifact/archive reads, network, source edits, staging, commits or pushes. "
        "Give a verdict for the observed scope of each group, concrete findings and a 39-file read checklist. Aim for about 1000 words plus the checklist; state any unread sections. Website/marketing remain paused; no overall release acceptance.")
command = ["node", "bin/control-room.mjs", "run", "uoink-library", goal, "--mode", "work", "--strategy", "parallel", "--agents", "gemini", "--lead", "gemini", "--approve"]
(out / "command.json").write_text(json.dumps({"source": source, "brief_sha256": sys.argv[2], "command": command}, indent=2) + "\n", encoding="utf-8")
with (out / "dispatch.log").open("x", encoding="utf-8") as stream:
    result = subprocess.run(command, cwd=r"E:\AI\projects\agent-control-room", env=env, stdout=stream, stderr=subprocess.STDOUT)
(out / "exit.json").write_text(json.dumps({"exit": result.returncode}) + "\n", encoding="utf-8")
print((out / "dispatch.log").read_text(encoding="utf-8")[-10000:])
raise SystemExit(result.returncode)
