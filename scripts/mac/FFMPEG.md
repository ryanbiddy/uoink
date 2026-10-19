# FFmpeg in the first macOS CI bundle

FFmpeg and ffprobe are omitted. No macOS binary or source tarball with a
reviewed license, configure flags and checksum was available in the offline
checkout for this pass. Homebrew binaries are not used. No FFmpeg version,
license, flags or hash is claimed for an absent payload.

The bundle reports `media_requires_ffmpeg`: frame extraction, podcast audio
download and audio transcription are unavailable. The app does not use a
machine's FFmpeg installation to conceal this limitation. TorchCodec decoder
libraries are also unqualified. PyAV and other wheels may contain their own
codec libraries; their files remain in the wheel/native inventory and their
upstream license files remain installed. They do not supply the missing CLI
or establish working ASR/alignment.

The next media build should compile a SHA-256-pinned FFmpeg source release in
CI with `--disable-gpl --disable-nonfree --disable-autodetect`, an explicit
reviewed codec/library list, and no Homebrew dependencies. Record the exact
compiler, SDK, configure output, source URL/hash, binary hashes and applicable
LGPL text before shipping it. Qualify TorchCodec's shared-library ABI separately.
Static LGPL redistribution requires a review of the corresponding-source and
relinking obligations; a checksum alone does not settle those obligations.
