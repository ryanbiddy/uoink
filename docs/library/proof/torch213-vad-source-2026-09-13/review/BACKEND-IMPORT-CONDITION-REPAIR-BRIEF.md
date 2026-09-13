# Future launcher pre-import condition

2026-09-13. Documentary proposal; no launcher, sealed factory, owner draft or production file changed.

The fixed factory currently names `PYANNOTE_METRICS_ENABLED=0` and requires a verified import graph before its imports. Target Torch source at commit `cf30153c4c131c8164ee7798e5022d810682e2cb`, `torch/__init__.py` SHA-256 `cf40c075c95864036e835795756d69b8cccfafa76f3bcde5eba9d06065ccd3d1`, lines 3017–3054 and 3073–3077, discovers the `torch.backends` entrypoint group and both loads and calls each entrypoint when its environment switch is absent or `1`. The retained 2.8 source also has this behavior.

When implementing the separately authorized isolated runtime launcher, add the fixed child environment value `TORCH_DEVICE_BACKEND_AUTOLOAD=0` before the first Torch import. Reject or overwrite an inherited conflicting value in that disposable child; do not alter the user's persistent environment. Record the exact value and startup timing without exposing unrelated environment contents. Keep the metrics setting, independently denied network, pinned dependencies and all existing admission gates.

Before a native run, qualify this launcher delta with an inert child/import seam showing that the flag is present before the first permitted import, an inherited `1` does not survive, and the existing source/asset gates still refuse when absent. This brief does not itself admit that native run. The actual import receipt must still identify selected package/native bytes and observed module/DLL activity.

The switch is limited to automatic external backend entrypoints. It does not suppress target `torch._native` at line 3087, Windows DLL loading, logging initialization, third-party imports, global module hooks or other native behavior. Those remain separate scope and qualification requirements; do not call this a whole-import safety fix.
