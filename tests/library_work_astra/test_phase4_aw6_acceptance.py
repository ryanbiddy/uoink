"""AW-6: failed publication cleanup must preserve a replacement temp file."""
from pathlib import Path

import library_mirror as mirror
from tests.library_work_astra.test_phase4_aw_acceptance import env, export, item_file, mutate_clip


def test_aw6_finally_cleanup_preserves_replacement_at_allocated_temp(env, monkeypatch):
    export(env)
    mutate_clip(env)
    env.mirror.on_committed_event("source_refresh", video_id="a")
    target = item_file(env)
    prior = target.read_bytes()
    original_replace = env.mirror._io_replace
    replacements = []
    personal = b"INDEPENDENT USER FILE AT THE FORMER TEMP PATH"

    def replace_then_fail(src, dst):
        if Path(dst) != target:
            return original_replace(src, dst)
        temp = Path(src)
        moved = temp.with_name(temp.name + ".held")
        temp.rename(moved)
        temp.write_bytes(personal)
        replacements.append((temp, moved))
        raise OSError("publication unavailable after the temp name changed owners")

    monkeypatch.setattr(env.mirror, "_io_replace", replace_then_fail)
    env.mirror.resync()
    assert len(replacements) == 1
    temp, moved = replacements[0]
    assert moved.is_file(), "The original allocation must remain available for identity comparison"
    assert temp.is_file(), "finally cleanup deleted an independently replaced temp pathname"
    assert temp.read_bytes() == personal
    assert target.read_bytes() == prior
