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
6. GitHub reported Node 20 deprecation annotations for the workflow action
   versions. RED: the focused repository-hygiene test failed because none of
   the current Node 24 action releases were present. Checkpoint: `bc4f220`.
7. GREEN: `python -m pytest tests/security/test_repository_hygiene.py -q`
   passed 6/6 after pinning the official Node 24 action releases. Checkpoint:
   `92de874`.
8. The native run then isolated one remaining Node 20 annotation from Gitleaks
   v2. RED: the Node 24 workflow contract failed after adding the current
   Gitleaks v3.0.0 requirement. Checkpoint: `4bb3e01`.
9. GREEN: the repository-hygiene target passed 6/6 with Gitleaks v3.0.0, whose
   action runtime is Node 24. Checkpoint: `5452bfc`.
10. Downloading the first tagged prerelease exposed that GitHub artifact
    transfer had stripped Unix executable permissions before ZIP creation.
    RED: both release-archive tests failed because the permission-preserving
    archiver and workflow integration were absent. Checkpoint: `82e57ce`.
11. GREEN: the release-archive and repository-hygiene targets passed 8/8 after
    restoring executable modes before creating each platform ZIP. Checkpoint:
    `0d3b1d2`.

## Test specification

| Guarantee | Test or command | Type | Result |
| --- | --- | --- | --- |
| The manifest excludes itself and interrupted temporary output | `test_manifest_is_complete_relative_and_stable` | Security integration | PASS |
| Nested macOS app files are recursively included | `test_manifest_is_complete_relative_and_stable` | Security integration | PASS |
| Paths are portable and relative | `test_manifest_is_complete_relative_and_stable` | Security integration | PASS |
| Repeated runs produce the same manifest | `test_manifest_is_complete_relative_and_stable` | Security integration | PASS |
| All release runners use the same generator | `test_release_workflow_uses_portable_checksum_generator` | Workflow contract | PASS |
| Workflows use current Node 24 official actions | `test_workflows_use_current_node24_action_releases` | Workflow contract | PASS |
| Linux and macOS executables remain executable after ZIP extraction | `test_archives_restore_platform_executable_permissions` | Release integration | PASS |
| Tagged releases use the permission-preserving archiver | `test_release_workflow_uses_permission_preserving_archiver` | Workflow contract | PASS |

## Coverage and merge evidence

- Full suite: 68/68 passed.
- Branch-aware application coverage: 83.05%; required minimum: 80%.
- Ruff formatting/lint and mypy strict mode passed.
- The ten RED/GREEN checkpoints are retained on `main`.
- Native Windows, macOS, and Linux release workflow `35602419589` passed, and
  every downloaded checksum entry verified. The complete native evidence is
  recorded in `docs/verification-report.md`.
