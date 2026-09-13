# WhisperX owned source draft is ready for text review

2026-09-13. This proposal contains actual source changes and an explicit
22-member wheel recipe for `whisperx==3.8.6+uoink.owned1`. It has not been
imported, tested, built or installed. The owned runtime port remains None; no
real model route is enabled. The recipe has 21 fixed text payloads totaling
130,120 bytes and one future generated RECORD. It contains no binary assets.

All 16 upstream Python files, LICENSE, README and pyproject are present. Their
exact sizes and computed Git blob SHA-1 values match the previously captured,
nontruncated release tree at `3ccc17b8de34f305300f8a3fd3c9f76ba820c0d0`.
The original 14 Python files came from a prior installer extraction; the new
blob comparison establishes that their retained bytes match the release tree.
SHA256 bindings separately protect the local before-files. This used only
retained source/metadata; no new request or artifact read was made.

The ASR patch checks the closed runtime before heavy imports and requires an
admitted absolute model path plus an owned fixed VAD before construction. Every
load parameter is passed to the trusted profile check. Automatic compute
selection, default VAD construction and path-based audio decoding are removed.
The original Pipeline initializer bypass, batching and generator processing
remain. This preserves source structure; the earlier 23-case generator result
is not a fresh pass for this changed derivative.

The Pyannote wrapper accepts only an injected Model that the runtime recognizes
as its fixed plain-state instance. Its legacy loader and automatic constructor
refuse. Alignment, diarization, Silero and upstream CLI/task modules refuse
before their legacy imports; the retained code below those refusals is
unreachable through ordinary import. The tiny Segment record moves unchanged
to the VAD helper so ASR no longer imports the disabled diarization module.

Waveforms must be exact contiguous mono native-F32 arrays, nonempty, finite and
within a qualified sample bound. The owned decoder must separately establish
16 kHz and waveform ownership. The default NPZ filter loader and global tensor
cache are replaced by an unavailable owned filter-bank port, supporting the
same 80/128 bands. No filter values, source, notice, accepted hash or decoder
are invented here. These are required before useful execution is possible.

The metadata draft changes exactly the five conflicting requirements to
Hub 1.31.0, Torch 2.13.0, TorchAudio 2.11.0, TorchVision 0.28.0 and TorchCodec
0.16.0. It retains the TorchCodec platform marker in both the dependency and
uv override, binds faster-whisper 1.2.1+uoink.localassets2 and preserves
`>=3.10, <3.14`. The separate candidate02 graph remains failed; none of these
declarations proves a compatible native stack. Frozen lock/notice tests remain
unchanged and their four proposed version decisions still belong to Ryan.

The original MANIFEST.in body is unavailable. This does not require guessing
it: the proposed owned recipe uses only enumerated text members, the unchanged
BSD license and a change notice. It omits original model/NPZ assets and console
entry points. The original README stays in the source review; a separate owned
README supplies accurate package metadata. The builder and its qualification
have not been written or run.

The remaining implementation gaps are specific: complete accepted ASR asset
manifests (twenty missing SHA256 values); a Windows snapshot/native-reopen lease
and crash recovery; process bootstrap and all owned-port methods; validated
waveform decoding and a measured bound; admitted filter banks and their decoder;
the approved plain-state VAD artifact and strict tensor bridge; a deterministic
recipe implementation; and combined imports/DLLs/inference qualification. A
global active port cannot stop reuse of stale models in another session. A real
worker/facade must enforce object lifetime and consume lazy results before
cleanup. Do not treat this source draft as those implementations or as model,
runtime, installation, release, website or marketing acceptance.
