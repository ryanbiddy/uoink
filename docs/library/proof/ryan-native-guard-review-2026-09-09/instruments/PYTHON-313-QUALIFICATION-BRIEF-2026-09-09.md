# Python 3.13 qualification, 2026-09-09

Gemini: independent bounded READ-ONLY product review in your worktree. No
subagents, commits, product/test edits, Setup, model execution/download, live
index, port 5179, paid API, credentials or system configuration changes.
Your earlier recommendation to retain Python 3.11.9 did not establish that
the same exact 142 package versions cannot run on a current Python minor.
Test feasibility instead of assuming a major dependency migration is required.

Python.org currently lists Python 3.13.15 (2026-08-05) with an official Windows
amd64 embeddable ZIP. Verify the official page and artifact metadata. Check all
142 requirements-installer-lock.txt pins for cp313-win_amd64 or compatible
abi3/pure wheels, Python Requires-Python and environment-dependent dependencies.
Use only public PyPI/Python metadata; retain inputs, exact JSON, hashes and
commands in your ignored scratch. A pip dry-run with --python-version 3.13,
--platform win_amd64 --implementation cp --abi cp313 --only-binary=:all: is
allowed, with --ignore-installed and no installation. Use a disposable cache,
clear paid/API keys and pip index environment variables. Source-only packages
must be identified separately; don't equate lack of a wheel with incompatibility.

Inspect build.ps1, receipt guards and product source for hardcoded python311,
removed stdlib dependencies and ABI assumptions. Propose the smallest qualified
upgrade, or report exact blockers and their public evidence. No speculative
"severe architectural friction" wording. Do not suggest Python 3.12 as current:
its binary-maintenance phase has also ended. Do not claim full runtime acceptance
from a resolver result. Write docs/library/GEMINI-PYTHON-313-QUALIFICATION-2026-09-09.md
early and give exact runtime/build checks Astra must run if qualification succeeds.
