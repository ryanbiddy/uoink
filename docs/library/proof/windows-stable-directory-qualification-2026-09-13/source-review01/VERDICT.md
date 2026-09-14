# Stable-directory identity source review — 2026-09-13

No blocking defect found in the proposed directory-only repair or its 81-case guarded qualification. This is a source review; I ran no cases, imports, native operations or artifact checks and issued no admission.

The review covers the two product deltas, the complete new test module, qualifier, launcher, protocol and final input map in `_scratch/windows-stable-directory-identity-proposal01`. The earlier failed native observations remain failed. The reported 4096→8192 directory-size change motivates this repair but does not establish that its native rerun will pass.

In `win32_worker_connection.py:169`, `same_directory_identity` accepts exact directory identities with bounded integer sizes and compares final path, volume serial, file ID and link count. Its use in `pin_exact_members:354` is limited to directory expectations. Regular files still require complete `FileIdentity` equality; the dataclass equality itself is unchanged. The existing native identity checks at lines 317–329 continue to refuse reparse points, delete-pending entries and negative sizes. Partial pin failures retain the handle and mark the read set unconfirmed.

In `windows_reservation_port.py:98`, retained ancestor checks use the directory comparator while preserving the physical-path comparison and ownership checks. The original failure diagnostic still records both sizes. Journal-file checks, durability and release conditions are unchanged.

The 11 added methods exercise actual `OwnedWin32Primitives.identity` and `pin_exact_members` against inert FFI/query responses, including positive controls, strict file-size rejection and retained handles after failure. They do not rely on the inherited fake pin override. The ancestor/journal cases use the existing generated Fixture and cover growth through clear/release, each other field changing, invalid size values and flush failure. They do not measure OS exclusion, process death, ABI layout or physical flush.

The qualifier changes only module/suite membership and 70→81 counts. Its ten final guards, closed content reads, 12 metadata traps, 25 registry wrappers and blocked native/model imports remain. The launcher changes only the fresh label and input/case counts. It retains exact original/copy/after control checks, immediate global native-exit capture, bounded output, ordered membership and failure receipts.

The saved data-only tool result `ACTUAL-TEXT-CHECK.json` (chunk 094637, exit 0) verifies every one of the 30 pins, the three original test files byte-for-byte against the qualified 70-case origin, the unchanged first 70 ordered IDs and the exact 11 added IDs. The false admission template binds the final map. The documented six-versus-seven historical-note correction changes prose only.

Final SHA-256 bindings:

| Input | SHA-256 |
| --- | --- |
| win32_worker_connection.py | 60d22036d6827205be5d0657af8e4693aa534605bdfb1b501878eb2a889fe25f |
| windows_reservation_port.py | b93076ab07b8c0567f6608520c99f5e5523be3dd388010a5a49037a4a899f775 |
| test_stable_directory.py | daf8ba2f87a0b6e7805a659abd93a8a79d2fe5830f26ae0986b8867bf5314478 |
| qualify_windows_reservations.py | a52142fdafd7784bdd23362c2798dce113a9f52e4c24c88bee54c8dd93715f4d |
| run_preflight01.ps1 | 48b4fd0cbf81893624a658893e8b80e1ea522be538882e13b045e54bfe872d66 |
| PINS.json | 0462d15628f65591b3fc19dc36e50e19534f0e66db9de84536a90c3d951821df |

Root may decide whether to admit this exact fake-port qualification. This review supplies no native, model, migration or release acceptance.
