# Migration Step 0 characterization

These fixtures freeze the current HTTP payloads for the surfaces that will
move during the suite split:

- `tests/fixtures/migration_step0/workspace-assembly.json` covers workspace
  create/list/get, assembly ranking and persistence, and both critique phases.
- `tests/fixtures/migration_step0/scripts.json` covers both script-generation
  phases, shot-list derivation, reads, and both revision phases.
- `tests/fixtures/migration_step0/writing.json` covers style anchors, writing
  grounding and persistence, piece reads, composer validation, draft recovery,
  revision persistence, and the creator-credit rejection.

The scenarios use a temporary migrated SQLite database, synthetic corpus rows,
the real `server.Handler`, and loopback HTTP. Clocks, generated workspace IDs,
and the local taste read are fixed. There are no model calls, external requests,
or user corpus reads.

Each JSON file carries its own regeneration and check commands under
`_fixture`. To regenerate all three:

```powershell
python tests/regenerate_migration_step0_fixtures.py
```

To verify that the checked-in payloads still match the current implementation
without rewriting them:

```powershell
python tests/regenerate_migration_step0_fixtures.py --check
```

Fixture changes are behavior changes. Review the JSON diff before accepting a
regeneration; do not update a fixture only to make a failing test green.
