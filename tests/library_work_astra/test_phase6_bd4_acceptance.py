"""BD-4: a bound capture dependency must be checked inside publication."""
import json
from pathlib import Path

from tests.test_phase6_evaluation import media, sandbox
from tests.test_phase6_bc2 import _open_index, _server_namespace, _youtube_sidecar


def test_bd4_capture_dependency_changed_at_publish_entry_is_preserved(sandbox):
    idx = _open_index(sandbox)
    try:
        item = _youtube_sidecar(sandbox, "bd4-capture", transcript=[(0.0, 10.0, "Held caption A.")])
        item.corpus_path.write_text("# Held capture\n", encoding="utf-8")
        item.sidecar_path.write_text(json.dumps(item.sidecar), encoding="utf-8")
        owner = _server_namespace(idx)["_index_yoink"]
        assert owner(item.folder, item.sidecar, item.corpus_path, item.sidecar_path) is True
        original_publish = idx.publish_media_snapshot
        edited = []

        def change_dependency_at_entry(*args, **kwargs):
            # All standalone checks in the owner have completed. A held
            # caption correction arrives before the publisher takes its
            # storage boundary; this is still mutable capture input.
            disk = json.loads(item.sidecar_path.read_text(encoding="utf-8"))
            disk["transcript"][0]["text"] = "Independent pending caption correction B."
            item.sidecar_path.write_text(json.dumps(disk), encoding="utf-8")
            edited.append(item.sidecar_path.read_bytes())
            return original_publish(*args, **kwargs)

        sandbox.patch.setattr(idx, "publish_media_snapshot", change_dependency_at_entry)
        try:
            owner(item.folder, item.sidecar, item.corpus_path, item.sidecar_path)
        except media.MediaError as exc:
            assert exc.code in {"revision_unavailable", "invalid_request"}
        assert len(edited) == 1
        assert json.loads(Path(item.sidecar_path).read_text(encoding="utf-8"))["transcript"][0]["text"] == \
            "Independent pending caption correction B.", "The pending corrected caption was overwritten"
        assert Path(item.sidecar_path).read_bytes() == edited[0], \
            "A check before publish did not protect the changed capture dependency inside publication"
    finally:
        idx.close()
