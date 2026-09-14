# Exact adapter binding repair before execution

The unexecuted proposal01 cannot reach its intended observation. Its subclass
fails the existing exact GeneratedLifecyclePort checks, and its early hook
compares the incoming adapter _OwnedASRStart with the internal profile sentinel
before the adapter validates that startup object. These are source review
findings, not failed native measurements. Proposal01, its original diffs and its
false admission remain unchanged. ORIGINAL-PROPOSAL01-MEMBERS.json binds all 36
original text files before this repair.

Use the exact GeneratedLifecyclePort. Its new private binding accepts only the
fixed OwnedContender class and the same primitives, monitor and connected primary
journal setup, once, before lease entry. Load the existing journal helper and
contender helper before the adapter; remove the helper's adapter import and
subclass to avoid a circular dependency. This changes no input membership and
adds no native symbol, caller callback, IPC authority or model permission.

Keep the original adapter startup assertion, stored startup and authority event
order verbatim. Invoke the contender only after that validation, passing the
stored _OwnedASRStart and internal sentinel separately. Require exact binding,
record/permit, primary RESERVED token and unchanged unstarted state. The helper
must complete and retain the same primary journal head before the inherited
create_suspended receives the original internal sentinel.

The fixed bootstrap selects this exact class and binding. The source map and
launcher use a fresh proposal02 and writer-exclusion02 output; this is a source
revision, not a rerun. The 18 source inputs, nine retained support bindings,
existing assertion bodies, finite native calls, cleanup rules and receipt
checks retain their original scope. There is no test or native admission here.

After editing, retain exact source deltas and unchanged-source bindings. Root
and the independent reviewer must read the full repaired source before any
separate generated observation is admitted. No candidate import, test, process,
native API, support-binary or model access occurs during this preparation.
