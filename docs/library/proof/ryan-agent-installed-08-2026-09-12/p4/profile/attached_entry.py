"""P4 application fixture: attach the real Phase 2 service before stdio.

Separately labeled. Never a silent substitute for the original installed
uoink_mcp.py route.
"""
import os
import sys
from pathlib import Path

installed = Path(os.environ["P4_INSTALLED_APP"]).resolve(strict=True)
root = Path(os.environ["P4_FIXTURE_ROOT"]).resolve(strict=True)
profile = Path(os.environ["P4_ISOLATED_PROFILE"]).resolve(strict=True)
sys.path.insert(0, str(installed))
isolation = installed / "uoink_install_isolation.py"
if isolation.is_file():
    import uoink_install_isolation as _iso
    _iso.apply_from_process()
import index
import library_work
import uoink_mcp

database = profile / "index.db"
idx = index.Index.open(database)
try:
    service = library_work.LibraryWorkService(
        idx, librarian_apply_enabled=False)
    if service.librarian_apply_enabled or not service.startup_status.get("ok"):
        raise RuntimeError("P4 report-only service did not attach safely")
    uoink_mcp.server._index_singleton = idx
    uoink_mcp.mcp.run(transport="stdio")
finally:
    idx.close()
