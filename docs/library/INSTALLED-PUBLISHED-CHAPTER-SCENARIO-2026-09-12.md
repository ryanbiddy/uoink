# Separate installed publication and chapter-consumer scenario

The original P4 seed has chapter database rows but lacks a matching published
sidecar. Its failed export remains evidence, and the fixture is not edited.
Use a fresh, separately named Phase 6 scenario after the SQLite repair and
replacement-package qualification. All original assertions remain unchanged.

Prepare one new visibly synthetic item under Agent Install 07/p6-published01/
profile. Its stored cue is 34–46 seconds and its supplied chapter is 34–90
seconds. Put SYNTHETIC FIXTURE in the title, cue text and chapter title. These
bytes are generated test data, never a quotation from a fetched source. The
source URL may reuse the already declared P4 target, but keep the synthetic
item id; unsupported player seeking must remain null rather than be invented.
No network source acquisition, transcription, speaker labels or inference.

Use only package-bound installed modules. Store initial source/corpus bytes and
index the synthetic item through the ordinary writer. Call the existing
server._publish_capture_media producer with those consumed bytes. That producer
mints a build-time publication ticket, builds the artifact and complete sidecar,
and calls Index.publish_media_snapshot. Do not call store_snapshot alone, patch
product methods, write media tables directly or bypass input/revision validation.
Record actual publication outcome, source/media revisions and file hashes.

The observer must retain the automatic guard and canary, explicit isolated
profile/port, package/source checks and owned-job cleanup. Authenticated client
configuration may reference the already signed-in isolated namespace; no copied
credentials or new sign-in. Before observation, review a frozen settings overlay
allowing only the existing bounded read tools and export_cited_range, with all
capture, write, shell and network tools denied. Keep apply false.

First read resources, then export the stored range after more than two seconds
on the same original installed stdio process. Retain actual time and frames;
this is the trigger that failed in package-06. The positive criterion is a
successful export with exact stored cue text, current revisions, one overlapping
chapter and no speaker labels. Unsupported seek fields must stay null. Any
failure remains failed and needs diagnosis before another attempt.

Astra review: this is a new operator scenario using the complete production
publication path, not a correction to an acceptance fixture. Generated data and
local publication are within the delegated isolated installation check. A
headless range read cannot supply a GUI click or player screenshot. Keep those
observations separate; do not create a synthetic page and count it as product UI.
