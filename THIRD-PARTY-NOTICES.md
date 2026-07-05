# Third-Party Notices

Uoink is MIT-licensed. It bundles the third-party components below.

**This committed file is the curated fallback.** The shipped file is
regenerated from the actual bundled dependency tree at build time
(`build.ps1` runs `scripts/gen_third_party_notices.py` against the
embeddable Python via pip-licenses), so what ships matches what installs
exactly, transitive deps included. Regenerate locally with:

```
python scripts/gen_third_party_notices.py THIRD-PARTY-NOTICES.md
```

## Directly bundled (pinned in requirements.txt / build.ps1)

| Package | License | Project |
|---|---|---|
| yt-dlp | Unlicense (public domain) | https://github.com/yt-dlp/yt-dlp |
| faster-whisper | MIT | https://github.com/SYSTRAN/faster-whisper |
| whisperx | BSD-2-Clause | https://github.com/m-bain/whisperX |
| mcp | MIT | https://github.com/modelcontextprotocol/python-sdk |
| keyring | MIT | https://github.com/jaraco/keyring |
| Pillow | HPND (MIT-compatible) | https://python-pillow.org |
| pystray | LGPL-3.0 | https://github.com/moses-palmer/pystray |
| pywebview | BSD-3-Clause | https://github.com/r0x0r/pywebview |
| pythonnet | MIT | https://github.com/pythonnet/pythonnet |
| crawl4ai | Apache-2.0 | https://github.com/unclecode/crawl4ai |

## Removed in C-02 (were the false-MIT liability)

- **whisper-timestamped** (AGPL-3.0) and its **dtw-python** dependency
  (GPL-3.0) are gone. Reliability detection now runs on faster-whisper's
  MIT per-word probabilities, which whisperx already pulled in.

## ffmpeg (bundled binary, not a Python package)

- **Component:** ffmpeg / ffprobe, BtbN `win64-lgpl` build (see build.ps1
  `$FFMPEG_URL`).
- **License:** LGPL v2.1+ (this build is compiled without the GPL-only
  encoders such as libx264/libx265). Replaces the gyan.dev "essentials"
  GPLv3 build, which was redistributed without meeting the GPL's
  source-offer and license-text obligations.
- **Source:** https://ffmpeg.org/download.html and
  https://github.com/BtbN/FFmpeg-Builds . Uoink uses ffmpeg only to decode
  and extract audio for transcription.
- LGPL text: https://www.gnu.org/licenses/old-licenses/lgpl-2.1.html

## Note on transitive licenses

faster-whisper and whisperx pull PyTorch (BSD-style) and CTranslate2 (MIT)
plus their own transitive trees. The build-time generated file enumerates
every one with its exact version and license; this curated list names the
direct, load-bearing dependencies and their families.
