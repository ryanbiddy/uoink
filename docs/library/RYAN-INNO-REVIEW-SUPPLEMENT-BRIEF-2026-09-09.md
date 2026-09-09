# Inno integrator correction brief — 2026-09-09

The third worker revision has 118 independent passes / one existing skip,
15.69 seconds. Retain its exact patch before this local source correction.
Five source-review gaps remain. Astra will correct only installer/uoink.iss
in the completed worker tree, preserve every frozen test and verify the same
15-file union there and after three-way integration. No Setup or uninstall
execution; compile the exact corrected script against dummy staging only.

1. Check every SetPreviousData Boolean result and abort on failed persistence.
   The stored AppDir is currently required but not compared; bind it to the
   actual app directory. The parsed marker app_dir must also match that directory.
2. Require exact single valued ISOLATED/PROFILE/PORT/DIR switches, and bare
   negative close/restart switches. Current name-only parsing accepts a value
   on a negative flag. Refuse malformed/duplicated isolation controls before
   ordinary preparation. Positive close/restart switches remain forbidden.
3. Refuse an unresolved existing ancestor. Check the marker leaf as well as
   directory ancestors for reparse points before reading/writing it. Retain
   final-directory revalidation and existing ordinary/legacy data exclusions.
4. JSON strings must reject raw control characters. Write/read the marker as
   explicit UTF-8 because the Python consumer decodes UTF-8; the current ANSI
   conversion cannot preserve arbitrary Unicode Windows profile names.
5. Keep original marker/database bytes and failed observations. Preserve the
   worker's first failed compile, successful compile, and independent union.
   Record a separate corrected compile and union, exact source hashes, review
   verdict and raw patch. No test-only imitation of Pascal runtime is a runtime
   receipt; real Inno persistence, close behavior and uninstall stay Ryan's.

The documented SetPreviousData API returns Boolean, and SaveStringToFile takes
AnsiString. Use Inno's Utf8Encode/Utf8Decode to preserve the JSON encoding.
Sources: [SetPreviousData](https://jrsoftware.org/ishelp/topic_isxfunc_setpreviousdata.htm),
[SaveStringToFile](https://jrsoftware.org/ishelp/topic_isxfunc_savestringtofile.htm),
[encoding functions](https://jrsoftware.org/ishelp/topic_scriptfunctions.htm).
