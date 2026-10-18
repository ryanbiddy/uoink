"""SEC-05 addendum contract: posture is documented, not implemented here."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MEMO = ROOT / "docs" / "library" / "POLICY-MEMO-2026-09-04.md"


def test_sec05_addendum_names_opt_in_key_and_egress():
    text = MEMO.read_text(encoding="utf-8")
    assert "## Addendum: FxTwitter v2 enrichment (SEC-05)" in text
    assert "`fxtwitter_enrichment_enabled`" in text
    assert "Default | **off**" in text or "Default** | **off**" in text
    assert "https://api.fxtwitter.com/2/status/{tweet_id}" in text
    assert "User-Agent: Uoink (+https://uoink.app)" in text
    assert "No code in this increment" in text
    assert "paste-a-URL" in text
