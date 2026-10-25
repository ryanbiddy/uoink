# 3.11 submission checklist

The account, fee, upload and submission are Ryan's actions. Start with
[SUBMIT-NOW.md](SUBMIT-NOW.md) for the click sequence.

## Prepared in this worktree

- [x] MV3 upload zip from `extension/` only, with a strict file allowlist.
- [x] Development key omitted from the zip and retained in the source manifest.
- [x] Mock API excluded; production mock switch is false; no source maps.
- [x] Version checked against VERSION without editing version fields.
- [x] Shared store ID/URL config, developer ID retained, exact origin tests.
- [x] Unused host grants removed and remaining permissions explained.
- [x] Listing, privacy form, reviewer instructions and website copy prepared.
- [x] Offline Chrome smoke and requested static/security/setup checks recorded.
- [x] Existing screenshot and tile inventory inspected.

## Ryan's gates before Submit for review

- [ ] Register/pay the one-time developer fee and enable 2-Step Verification.
- [ ] Create the draft item by uploading `dist/uoink-extension-3.11.0-cws.zip`.
- [ ] **Paste the store ID here:** `extension/store-config.json`, value of
  `chrome_web_store_id`. Keep `chrome_web_store_url` empty until the link is live.
- [ ] Release a helper containing that config and `uoink_store.py`.
  Public users must get a helper that recognizes the store ID without manual edits.
- [ ] Confirm the helper download used by setup includes the store ID. The public
  v3.11.0 installer exists, but it predates this pass; this pass did not replace it.
- [ ] Verify a real capture and clipboard copy with the store identity in a
  disposable profile, using permitted source material.
- [ ] Publish the Limited Use statement from `privacy-practices.md` on `/privacy`.
- [ ] Recapture the images in `SCREENSHOTS.md`. Upload at least one current shot.
- [ ] Verify `hi@uoink.app` receives mail and the support URL works.
- [ ] Fill out all fields and choose Public or Unlisted distribution.
- [ ] Paste the reviewer test instructions. Leave usage sharing off for testing.
- [ ] Submit for review with deferred publication until the helper is ready.

## After approval

- [ ] Publish the item and verify the public install link.
- [ ] Paste that link into `chrome_web_store_url` in the same JSON file.
- [ ] Run `python scripts/sync_store_links.py`, then its `--check` mode.
- [ ] Ship the updated helper/bundled extension and apply `website-copy-notes.md`.
  The shipped setup and splash now offer Add to Chrome, with Advanced sideloading.
- [ ] A store extension update is optional for this link-only change; if uploading
  another package, follow the normal release process and increase its version.
