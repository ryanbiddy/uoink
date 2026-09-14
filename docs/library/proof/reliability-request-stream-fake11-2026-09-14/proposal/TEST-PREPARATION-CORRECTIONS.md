# Corrections before any test execution

The first test draft patched global `Path.is_file`. The instrument reviewer identified that this would replace an installed metadata trap. The preserved draft is `before/test_reliability_request_stream.pre-metadata-review01.py` (49b1b8ff1089da9949960ed30f0df0b3dae3960dc090503bf99d0174ac2b9bb1). The current tests instead replace only the derivative module's `Path` name with an inert class. Its sole file predicate is a fixed fixture value; the actual pathlib and operating-system traps stay installed.

The next draft imported `unittest.mock`, which is outside the accepted preloaded unittest closure and can load unwanted dependencies. It is retained as `before/test_reliability_request_stream.pre-import-review02.py` (fcdf7d3a9ed1e0975bba2c464594b2fe472761f1c09a40393fa3c2fedc075742). The current tests use a small contextmanager that saves/restores one attribute, plus the existing ExitStack. Assertions and candidate source did not change for either correction.

A proposed Word.text concern did not require a source correction: the bound production `_words_from_segments` already uses `.word` followed by `.text`. That entire function is preserved. The positive control uses actual passive Word/Segment instances and checks normalized span text.

My early message counted three affected ordinary-detection tests. The correct count is two: `test_detect_unreliable_spans_does_not_enable_download` and `test_stale_marker_ordinary_path_still_refuses_download`. This is a prospective compatibility conflict, not an observed test failure. No candidate was imported, compiled or executed during preparation.
