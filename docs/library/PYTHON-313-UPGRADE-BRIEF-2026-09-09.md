# Qualified Python 3.13 build repair

The old Python 3.11.9 binary predates security-only source releases. Gemini's
metadata check establishes available Python 3.13 wheels, but --no-deps cannot
establish the build's final graph. Astra's actual official Python 3.13.15
resolver completed with exit zero. The same direct requirements and constraints
resolve 139 runtime packages with zero version changes or additions. Three
compatibility packages are absent: backports.tarfile, importlib-metadata, zipp.
Build-only setuptools is separately bootstrapped at 83.0.0 and removed later;
--ignore-installed's selection of 84.0.0 is not the real installed build version.
The first collector failed decoding pip's UTF-8 report as cp1252. A separate
reader processes the same retained successful report; no resolver rerun occurred.

Update only Python's version/hash and current build documentation; remove those
three no-longer-required pins and notice rows, with provenance of the real graph.
Preserve the FFmpeg repair. No original acceptance test or fixture changes.
Author the bounded diff in the completed qualification worker, independently
verify the seven native-pin build/doc/lock suites there, integrate by raw diff
and three-way apply, and repeat those suites in checkout. Astra may author this
integrator supplement; Gemini's original read-only report remains unchanged.

Before building, install the same direct requirements with unchanged constraints
into the already prepared disposable Python 3.13 directory, using the same exact
build tooling and no build isolation. Record real versions, dependency closure
and synthetic native runtime checks. Deny model downloads, source media,
diarization, external runtime network, paid API, credentials, live index and
5179. Tensor arithmetic, codec imports and generated media are in scope; model
inference from Gemini's proposed plan is not authorized. Do not launch ordinary
tray/dashboard defaults: use the reviewed isolated installed routes afterward.

Preserve package-04 and old Python/FFmpeg caches. Build the changed committed
candidate, verify its actual 139 distribution inventory and every source/byte
binding, run the full accounted two-process tree and then actual isolated Setup.
Any runtime incompatibility is a new defect requiring a repair brief; do not
reinterpret the 3.14 development test tree as complete Python 3.13 acceptance.
