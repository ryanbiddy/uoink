# D1 admission preparation repair

The data-only admission preparation returned exit 1 (c27355) before writing the root review or admission and before any D1 invocation or checkpoint operation. Nine source rows and four references had matched their byte and hash bindings. The next check incorrectly used PSObject.Properties.Count directly, which does not produce the intended scalar count in this PowerShell environment.

Repair: explicitly materialize that property collection with @(...) before checking Count. Retain all hash and membership checks. The fresh preparation may write the previously absent review and ROOT-ADMISSION.json only after every check passes. No payload, binding, owner decision, test or D1 execution source changes. This is a preparation repair; the one approved inspection has not run.
