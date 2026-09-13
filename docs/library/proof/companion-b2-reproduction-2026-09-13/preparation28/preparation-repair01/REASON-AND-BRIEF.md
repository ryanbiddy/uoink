# Text preparation repair before attempt 02

Attempt 01 of the text-only preparation script exited 1 during Python parsing:
the generated Windows path inside an outer triple-quoted string contained an
unescaped `\u`, yielding `SyntaxError: truncated \uXXXX escape`. Python never
executed the script body. No inputs were copied and no runtime or wheel was
opened. The exact before-source is preserved here.

The repair represents the generated absolute runtime path with forward slashes
and uses forward slashes in its two suffixes. The generated child's existing
normalizer still maps either slash to Windows form before comparing paths.
No behavior assertion, builder, recipe, original seal or runtime is changed.
Attempt 02 may rerun only the corrected text preparer, then statically parse
the proposed scripts. It may not launch the proposed copier, private Python,
guarded child or builder.
