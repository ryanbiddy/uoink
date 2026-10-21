# FFmpeg in the macOS bundle

Build on the `macos-15` arm64 runner, or a disposable native arm64 Mac:

```sh
python3 -B scripts/mac/build_ffmpeg.py --output "$RUNNER_TEMP/mac-ffmpeg"
bash build-mac.sh --wheels "$RUNNER_TEMP/mac-wheels" \
  --ffmpeg-output "$RUNNER_TEMP/mac-ffmpeg" --output "$RUNNER_TEMP/mac-app"
python3 -B scripts/mac/bundle_smoke.py --app "$RUNNER_TEMP/mac-app/Uoink.app" \
  --output "$RUNNER_TEMP/mac-smoke"
```

The CLI build installs `ffmpeg` and `ffprobe` 8.1.2 in `Contents/Helpers`.
FFmpeg 7.1.5 supplies the shared ABI for TorchCodec 0.7.0, subject to a real
decode test. No Homebrew binaries, headers, libraries or pkg-config are used.
Windows keeps its BtbN n8.1.2 static CLI and n7.1.5 DLLs; Linux is unchanged.

## Verified source inputs

`payload.json` is authoritative. The orchestrator verified both upstream GPG
signatures before supplying these pins. CI checks size and SHA-256 before
opening either archive; it does not repeat the GPG check.

| Role | Exact corresponding source | Bytes | SHA-256 |
| --- | --- | ---: | --- |
| Static CLI 8.1.2 | https://ffmpeg.org/releases/ffmpeg-8.1.2.tar.xz | 11710924 | `464beb5e7bf0c311e68b45ae2f04e9cc2af88851abb4082231742a74d97b524c` |
| Shared 7.1.5 | https://ffmpeg.org/releases/ffmpeg-7.1.5.tar.xz | 11050340 | `de668509caf9e35e3cd162473441fdb29538c6d96ed080292b3cf9e6fc5d558f` |

Both signatures used FFmpeg release key
`FCF9 86EA 15E6 E293 A564 4F10 B432 2F04 D676 58D8` and were reported as
“Good signature.” The upstream sources are built without source patches.
Extraction rejects traversal, escaping links and special files.

## Configure policy and component inventory

Both builds start with:

```text
--arch=aarch64 --target-os=darwin
--cc=<xcrun clang> --sysroot=<xcrun macosx SDK>
--extra-cflags='-arch arm64 -mmacosx-version-min=15.0'
--extra-ldflags='-arch arm64 -mmacosx-version-min=15.0 -Wl,-headerpad_max_install_names'
--disable-gpl --disable-nonfree --disable-autodetect
--disable-doc --disable-debug --disable-everything --disable-programs
--enable-zlib
```

The CLI adds `--enable-static --disable-shared --enable-ffmpeg
--enable-ffprobe --enable-network --enable-securetransport`. Network is
necessary: `server.py` sends `--download-sections` to yt-dlp for chunked
video capture, which invokes FFmpeg against remote media URLs. HTTP/HTTPS,
TCP/TLS and encrypted HLS use explicitly enabled Apple Secure Transport;
no external TLS package is linked. The shared build keeps networking disabled
and adds `--disable-network --enable-shared --disable-static --enable-pic
--install-name-dir=@rpath`.

System zlib is explicitly enabled for native PNG decoding and compressed
container metadata. It comes from the selected Apple SDK. These system
dependencies are allowed by the native inventory's `/usr/lib` and
`/System/Library` rules. Compiler search paths and build flags are cleared
from the environment, and subprocess PATH contains only system directories.

Each row below becomes a comma-separated `--enable-<kind>=...` argument.
Before configuring, the builder checks every requested component against the
hash-verified source's `configure --list-<kind>s` output for that version.
It also checks generated configuration headers for disabled dependencies and
GPL/nonfree/version3 code. Configure and make failures print the final 150 lines
of both `ffbuild/config.log` and `build.log` to CI output and preserve the logs.
FFmpeg may enable internal dependencies; the generated `config_components.h`
and `enabled-components.json` record the actual result for each version.

| Components | Enabled names | Reason |
| --- | --- | --- |
| Common demuxers | `mov,matroska,mp3,aac,ogg,wav,flac,mpegts,image2,image_jpeg_pipe,image_png_pipe,image_webp_pipe` | MP4/M4A/QuickTime, WebM/MKV, podcast audio, transport streams and downloaded thumbnails |
| Common audio decoders | `aac,aac_latm,mp3float,opus,vorbis,flac,alac,pcm_u8,pcm_s16le,pcm_s16be,pcm_s24le,pcm_s32le,pcm_f32le,pcm_f64le` | AAC/M4A, MP3, WebM/Opus, Ogg and PCM/lossless podcast inputs |
| Common image/video decoders | `h264,vp8,vp9,mjpeg,png,webp,ppm` | Selected video formats, JPEG/PNG/WebP thumbnails; PPM supplies the generated smoke video |
| Common parsers | `aac,aac_latm,mpegaudio,opus,vorbis,flac,h264,vp8,vp9,mjpeg,png` | Packet parsing for enabled codecs |
| Common filters | `aformat,anull,aresample,atrim,format,null,scale,trim,transpose,hflip,vflip` | TorchCodec graphs, audio/pixel conversion and automatic rotation |
| Common protocols | `file,pipe` | Local media, generated test input and decoded samples |
| CLI demuxers | `hls,concat,srt,webvtt,ass,lrc` | Section downloads, concatenation and yt-dlp subtitle conversion |
| CLI subtitle decoders | `srt,subrip,webvtt,ass,text` | Convert downloaded captions to SRT |
| CLI encoders | `pcm_s16le,pcm_f32le,mjpeg,srt` | WAV podcasts, 16 kHz Whisper samples, JPEG screenshots and SRT captions |
| CLI muxers | `wav,s16le,f32le,image2,srt,mp4,mov,ipod,matroska,webm,mpegts,adts,mp3,ogg` | Audio outputs, screenshots, subtitles and yt-dlp stream-copy fixups/sections |
| CLI filters | `fps` | Periodic screenshots in `server.py` and `yt_extract.py` |
| CLI bitstream filters | `aac_adtstoasc,h264_mp4toannexb,vp9_superframe,extract_extradata` | Container fixups and stream-copy remuxing |
| CLI protocols | `http,https,tcp,tls,crypto` | Remote section input and encrypted HLS |

`buffer`, `buffersink`, `abuffer` and `abuffersink` are built-in libavfilter
endpoints, so they are not requested as configurable filters. Protocols are
listed explicitly after `--disable-everything`. The default LGPL version is
retained; the header check rejects `CONFIG_VERSION3`. SDK dependency probes
use configure's normal fallback checks, without a forced failing pkg-config.

`server.py` also converts downloaded thumbnails to JPEG and probes FFmpeg in
diagnostics. `podcasts.py` delegates extraction to yt-dlp's FFmpeg postprocessor;
ffprobe inspects the input audio codec. `whisper_runner.py` decodes Darwin
input through the bundled CLI and passes NumPy samples to transcription,
alignment and diarization, avoiding WhisperX's bare `ffmpeg` string loader.
`uoink_reliability.py` uses faster-whisper/PyAV rather than a separate CLI call.
`clips.py` derives text clips; `media_handoff.py` resolves retained files.
Neither launches FFmpeg. No current frame command uses the `select` filter.
The legacy Tk GUI `youtube_extractor.pyw` also invokes yt-dlp subtitle
conversion and FFmpeg's `fps`/JPEG path. It is absent from the reviewed macOS
payload and remains unchanged. The Windows installer invokes its separately
pinned BtbN tools; the macOS build and smoke scripts use explicit paths.

Bundled Darwin video selectors accept only H.264/AVC, VP8 and VP9, including codec
prefix variants. There is no unknown-codec or unrestricted fallback. An
AV1-only or HEVC-only source fails format selection. No libdav1d is included.
Audio-only reliability downloads do not decode video frames.

FFmpeg has no native MP3 encoder. Bundled Darwin podcast output is PCM WAV, with a
`.wav` path; Windows/Linux MP3 commands and paths are unchanged. WAV uses
more storage. The MP3 decoder and stream-copy muxer do not imply encoding
support. No libmp3lame, x264, x265 or other external codec library is enabled.

## Loading and capabilities

The embedded interpreter resolves media tools only from `Contents/Helpers`.
Darwin source/dev runs use PATH and retain the Linux media formats and behavior.
yt-dlp gets `--ignore-config --ffmpeg-location <Helpers>` so ambient config
cannot replace the tools. Missing binaries, failed `-version`, or a failed
generated PCM decode retain `media_requires_ffmpeg`. The decode self-test
uses pipes and writes no app files. Results are cached by executable path,
size, modification time and inode.

The shared ABI is `avcodec.61`, `avformat.61`, `avutil.59`, `swresample.5`,
`swscale.8`, `avfilter.10` and `avdevice.61`. Assembly installs these under
`Contents/Frameworks/FFmpeg7`, with `@rpath` IDs and sibling `@loader_path`
dependencies, and patches TorchCodec 7 load commands/rpaths relative to each
wheel binary. Edited binaries are ad-hoc signed.

The bundled Python must use TorchCodec 0.7.0 to decode generated WAV to
16 kHz mono samples. The probe inspects dyld's loaded-image list and rejects
FFmpeg loaded from outside `FFmpeg7`; it runs with no `DYLD_*` variables and
no Homebrew PATH. If loading, patching or decoding fails, assembly restores
the wheel binaries and removes `FFmpeg7`. `notices/torchcodec.json` records
the failure, and `alignment_requires_torchcodec` keeps WhisperX/alignment
unavailable. The CLI media capability can still pass. A decoder probe does
not prove model download, ASR quality or diarization.

## Notices, source and legal review

`Contents/Resources/notices/ffmpeg/` contains this file, `payload.json`,
`build_ffmpeg.py`, `ffmpeg_bundle.py`, and separate `cli/` and `shared/`
records: source version/URL/size/hash/key fingerprint, the exact configure
command, requested and actual components, compiler version, SDK version/path,
build/config logs, configuration headers and upstream `COPYING.LGPLv2.1`
as `LGPL-2.1.txt`. CLI version output is recorded too. `notices/build.json`
states whether the shared runtime was retained. Final native/file inventories
record shipped binary hashes after loader edits and signing.

To obtain corresponding source, download the exact versioned tarball above
and retain these build scripts and the recorded command. The cache also
retains installed static archives and headers; the app includes only the CLI
programs and any qualified shared runtime. FFmpeg is a separate process for
CLI use; TorchCodec loads the separate shared libraries.

The layout and source URLs do not establish complete LGPL redistribution or
relinking compliance. Review the static CLI source/build materials, the
TorchCodec/shared-library replacement path, signing effects and any required
relinking materials before distribution. This pass makes no broader legal
compliance claim.

## Hosted evidence still required

`actions/cache` keys output on both source pins, configure/component choices,
the recipe/installer scripts, compiler and SDK. Cache hits recheck file hashes,
modes and symlink targets. No prefix restore keys allow a different recipe.
Build evidence is uploaded even on failure.

The hosted run must compile both versions, pass arm64/native dependency
inventory, then relocate the app to a path with spaces. Smoke runs both
programs, converts generated audio to a 16 kHz WAV, generates MJPEG/MOV video
and extracts a JPEG through `fps` and `scale`. It repeats TorchCodec decoding
if retained, checks helper/CLI media availability and exact MCP inventories,
and compares the entire app tree before and after execution.

These fixtures do not cover every compressed format or a live HTTPS/HLS
chunk download. Real AAC/Opus/MP3/H.264/VP9 captures and subtitle conversion
remain acceptance checks. Pass 8 sets both deployment flags and the app plist
to macOS 15, the OS used for hosted runtime qualification. The earlier 14.0
FFmpeg target did not establish support for the complete app on macOS 14.
