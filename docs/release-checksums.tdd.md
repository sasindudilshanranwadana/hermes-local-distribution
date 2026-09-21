# Release checksum TDD evidence

## Source and user journey

No separate plan file was used. The journey was derived from private-alpha
artifact inspection: as a recipient, I need every downloaded release file to
have a stable, portable SHA-256 entry so I can verify the package before
running it.

## Task report

1. A release artifact inspection found that Unix manifests hashed
   `SHA256SUMS.txt` itself, macOS manifests omitted nested app files, and the
   Windows manifest exposed the runner's absolute path.
2. RED: `python -m pytest tests/security/test_release_checksums.py -q` failed
   both tests because `scripts/write_checksums.py` did not exist and the
   workflow still used platform-specific commands. Checkpoint: `0c98f8f`.
3. GREEN: the same target passed 2/2 after adding one portable recursive
   generator and using it for every release runner. Checkpoint: `14bc98c`.
4. Review found that an interrupted run could leave `SHA256SUMS.tmp` and make
   the next manifest invalid. RED: the focused idempotence test failed because
   the first manifest contained the stale temporary file. Checkpoint:
   `1284e80`.
5. GREEN: `python -m pytest tests/security/test_release_checksums.py -q`
   passed 2/2 after excluding both generated manifest paths. Checkpoint:
   `19e2cee`.

## Test specification

| Guarantee | Test or command | Type | Result |
| --- | --- | --- | --- |
| The manifest excludes itself and interrupted temporary output | `test_manifest_is_complete_relative_and_stable` | Security integration | PASS |
| Nested macOS app files are recursively included | `test_manifest_is_complete_relative_and_stable` | Security integration | PASS |
| Paths are portable and relative | `test_manifest_is_complete_relative_and_stable` | Security integration | PASS |
| Repeated runs produce the same manifest | `test_manifest_is_complete_relative_and_stable` | Security integration | PASS |
| All release runners use the same generator | `test_release_workflow_uses_portable_checksum_generator` | Workflow contract | PASS |

## Coverage and merge evidence

- Full suite: 65/65 passed.
- Branch-aware application coverage: 83.05%; required minimum: 80%.
- Ruff formatting/lint and mypy strict mode passed.
- The four RED/GREEN checkpoints are retained on `main`.
- Native Windows, macOS, and Linux workflow evidence is recorded in
  `docs/verification-report.md` after the remote run completes.
