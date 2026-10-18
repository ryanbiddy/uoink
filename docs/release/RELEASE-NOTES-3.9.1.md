# Uoink 3.9.1

Writing warnings now say "canned-phrase warnings". Voice DNA remains the
voice spec's name. This patch makes no data or settings changes. Installing
over 3.9.0 keeps your library and saved captures.

## Reliability

- The Windows/Ubuntu CI test baseline is fixed: Windows-only Library mirror
  and installer-receipt tests skip on other systems, and portable tests pass on both.
- Linux isolated-install stop recognizes processes that have already exited.
- The YouTube pacing test checks process event order without relying on clock resolution.

## Installing

1. Download `Uoink-Setup-3.9.1.exe` from this release. Windows 10/11 is supported.
   The installer is unsigned, so SmartScreen may warn. Check the file's SHA-256
   against the value on this release page, then choose **More info -> Run anyway**.
2. Run the installer. It defaults to `%LOCALAPPDATA%\Uoink\` with no admin
   required. The finish page can launch the helper, and autostart runs it on login.
3. On first launch, use the setup splash to open `chrome://extensions` and copy
   the installed extension path. Turn on **Developer mode**, click **Load unpacked**,
   and select that folder. The Chrome Web Store listing is pending.
4. Click Chrome's puzzle-piece **Extensions** icon and pin **Uoink** so its
   button stays visible.

Chrome (tested); other Chromium browsers such as Edge and Brave may work but are not tested.

## After updating

Open `chrome://extensions` and reload the Uoink extension. If its ID changes,
reapply its preferences; your helper library and captures stay in place.

## Checksums

| File | SHA-256 |
| --- | --- |
| `Uoink-Setup-3.9.1.exe` | `1b5b8b82b6137f3bc6d7f3a899cde9a641302f5d525f46da5f1f4a4c7cd16c2a` |
| `uoink-3.9.1.mcpb` | `4c8df098ddb66144fcc78302595f4e62fc1ead2d321fc634d3a5617cff4efbc7` |
