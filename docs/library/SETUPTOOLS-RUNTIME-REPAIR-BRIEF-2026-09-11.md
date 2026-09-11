# Retain the declared runtime dependency

The full metadata traversal after Lightning qualification finds 283 active edges,
with two unsatisfied: CTranslate2 requires setuptools and Torch requires it on
Python 3.12+. build.ps1 deliberately removes the package after installing it.
This predates the current repair. Preserve the diagnostic and correct packaging.

Retain the already pinned bootstrap setuptools 83.0.0 in the shipped runtime and
add its exact pin to the final lock. Keep pip, wheel and transient notice tools
out. Retain setuptools' own startup support files so its declared package works;
do not remove distutils support while retaining only the distribution metadata.
Review the wheel's primary metadata, license and current advisory response. Add
the exact license/notice from the wheel to the source notice inventory; the
final build will regenerate it from the actual runtime.

Add a separate packaging regression covering the retained runtime package and
startup support, without editing any existing assertion. Execute the existing
installer lock, file-completeness, download-accuracy and decoder-loader suites
plus the new tests in a detached worktree and the checkout. Export raw diff and
apply three-way. The final build must independently prove the 140-package set
and all declared active dependencies, then undergo the fresh audit and scan.

No live index, port 5179, paid API, model inference/checkpoint download, ordinary
installation or main merge. The compatible dependency wheel and its public
metadata may be downloaded; no application source-media scope changes.
