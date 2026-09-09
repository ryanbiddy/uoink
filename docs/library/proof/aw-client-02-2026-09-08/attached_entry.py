"""AW application fixture: attach the real Phase 2 service before stdio."""
import os
from pathlib import Path
import index
import library_work
import uoink_mcp

root = Path(os.environ["AW_FIXTURE_ROOT"]).resolve(strict=True)
database = root / "profile" / "Uoink" / "index.db"
idx = index.Index.open(database)
try:
    service = library_work.LibraryWorkService(
        idx, root / "prompt-store", librarian_apply_enabled=False)
    if service.librarian_apply_enabled or not service.startup_status.get("ok"):
        raise RuntimeError("AW report-only service did not attach safely")
    uoink_mcp.server._index_singleton = idx
    uoink_mcp.mcp.run(transport="stdio")
finally:
    idx.close()
