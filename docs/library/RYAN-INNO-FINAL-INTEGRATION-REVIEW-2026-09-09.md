# Isolation and Inno integration: review verdict — 2026-09-09

**Accept the corrected source for candidate integration; installed behavior
remains unexecuted.** The helper, stdio, splash, dashboard, output, credentials,
runtime identity and suite advertisement now share an explicit isolated profile
and loopback port. Ordinary data migration is skipped in this mode. Stop checks
the recorded process identity on the terminating handle and confirms exit;
it neither targets by process name nor probes the resident helper.

Inno requires one explicit isolated app/profile/port binding, plus bare
/NOCLOSEAPPLICATIONS and /NORESTARTAPPLICATIONS. Conflicting positive switches
are refused. It validates paths before preparation and again before file work,
rejects reparse ancestors and marker leaves, and checks a bounded marker against
the selected profile, port and app directory. Uninstall validates persisted
identity and requires the owned stop to succeed before deletion. Missing or
damaged evidence is not permission to use ordinary cleanup.

Astra's final supplement checks failed persistence, exact marker/app binding,
malformed switches, unresolved paths and marker encoding. JSON is explicit UTF-8
and rejects raw control characters. The exact worker source before these
corrections is retained separately. No existing test or fixture changed.

The independent worker observation has **118 passed, one skipped**, 15.69 s.
The corrected worker repeats **118 passed, one skipped**, 15.79 s. After raw
diff export and clean three-way application, checkout verification has **130
passed, one skipped**, 22.09 s, including twelve read-opening/preview and startup
anchor companions. The existing symlink-privilege skip remains. Dummy staging
compiled the exact corrected script with exit **0**; its executable was never
run. Both the worker's earlier compile failure and successful compile remain.

Raw patches, commands, logs, XML, compile receipts, guards and source hashes are
sealed in proof/ryan-inno-final-2026-09-09/SHA256.json. The three-way merge retains
e86bc16 in server.py and uoink_mcp.py. Full committed-tree and real package
verification still follow. These checks do not establish actual Inno registry
persistence, Restart Manager behavior, installation/uninstallation, C22 recovery
or real-client receipts; Ryan supplies those on the final disposable installation.
