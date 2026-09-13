# Preload the ZIP filename codec — 2026-09-13

Root's source review identified a likely first-use guard conflict: `zipfile` decodes names without the UTF-8 flag using CP437. Loading `encodings.cp437` lazily after the content-read guard is installed could require an unapproved standard-library file read. No inspector or wheel was executed to discover this.

Preload that one standard codec with the other imports before installing the guard. Do not widen the guard's content paths or alter ZIP checks, historical pins, metadata assertions, outputs or launcher behavior. The original inspector and 16-input preparation manifest are preserved under `before-cp437-preload/`; the narrow source diff is retained separately. The updated preparation remains unexecuted and requires root admission.
