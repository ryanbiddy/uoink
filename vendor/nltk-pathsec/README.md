# NLTK path-policy source backport

This patch targets the six artifact APIs named by GHSA-8mgp-746c-j5xp in
NLTK 3.10.3. Read docs/library/ASTRA-NLTK-PATHSEC-VERDICT-2026-09-12.md for
the integration verdict, test counts and limits. It is source preparation,
not a packaged dependency or a cleared installer advisory.

TransitionParser.train/parse and AveragedPerceptron.save/load now check their
paths and use NLTK's guarded file operations. Tagger saves validate filename
components and the destination; they retain POSIX descriptor-based writes.
Maxent output uses the path policy for its four files. Implicitly registering
new caller directories as trusted roots is removed. Existing serialization
code remains downstream; the tests intercept it rather than qualify models.

On Windows, directory creation is checked before and after by pathname. This
does not establish general race protection against another process with the
same user's rights. The Windows symlink test is skipped when the OS refuses
link creation. POSIX-specific behavior was inspected, not executed here.

Prepare into a new directory with:

```powershell
python scripts/prepare_nltk_pathsec_backport.py --src <pristine-nltk-package> --dst <new-destination>
```

The utility checks the exact three input hashes, fixed patch hash, every patch
output and the complete copied file map. The receipt stays inside the new
destination and uses exclusive creation. No expected-hash override is accepted.
No package is imported and no resource is fetched. Retained-byte comparison
does not independently authenticate upstream material or eliminate every
concurrent filesystem race.

The original source files under original/ are portable preparation fixtures,
copied without modification from the staged upstream package. Their copyrights
remain in the files; the upstream distribution licence is in original/LICENSE.txt.
Full import/routing tests require the matching staged Python/native libraries.
UOINK_NLTK_BASE_SOURCE may point to preserved pristine source after the runtime
is patched; it is separate from the runtime used to execute those tests.

Before installer use, build an explicitly labelled local wheel, update its
distribution version/metadata and RECORD, record the wheel hash and notices,
and qualify the staged runtime and full candidate. Keep the original advisory
visible alongside any later backport disposition. Do not patch staging in place.
