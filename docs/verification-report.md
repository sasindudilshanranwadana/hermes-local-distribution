# Verification report

Verified locally on Linux x86_64 and with native GitHub runners on 2026-09-21:

- Core suite: 65/65 passed.
- Branch-aware coverage: 83.05% (required minimum: 80%).
- Portable pre-classifier regression suite: 47/47 passed.
- Routing accuracy gates retained: 96% fallback corpus, 95% semantic challenge
  corpus with zero critical under-routes, and 200+ exact expanded cases.
- Pre-classifier Docker `test` stage: passed all 47 tests.
- Ruff formatting and lint: passed.
- Mypy strict mode: passed with no issues across 23 source files.
- Python compilation: passed.
- Docker Compose validation with the example environment: passed.
- Pinned Mem0 archive: real download, checksum, safe extraction, and required
  server-file checks passed.
- Bundled Hermes installer checksums matched the component manifest.
- PyInstaller Linux artifact: built successfully (13,195,184 bytes).
- Frozen GUI smoke test: remained open under Xvfb for 5 seconds with no exception.
- Gitleaks working-tree scan: no leaks found.
- Gitleaks full-history scan through code commit `cfe1f28`: no leaks found.
- AgentShield: grade A, no findings. It reported zero recognized agent-config
  files, so this is not treated as a general source-code security scan.
- `git diff --check`: passed for the final working tree.
- Native CI run `35601494774`: all Windows, macOS, and Linux jobs passed on
  Python 3.11 and 3.12; repository hygiene also passed.
- Private-alpha installer run `35601508666`: Windows, macOS, and Linux builds,
  tests, checksum generation, and artifact uploads passed.
- Downloaded release artifacts had the expected native formats: Windows x86-64
  PE, macOS arm64 Mach-O app, and Linux x86-64 ELF.
- Every downloaded `SHA256SUMS.txt` entry verified. Manifests used relative
  paths, excluded generated manifest files, and covered all five macOS payload
  files, including nested app contents.
- Release artifact sizes: Windows executable 11,944,267 bytes; macOS executable
  10,571,568 bytes; Linux executable 21,888,064 bytes.

Pending external acceptance gates:

- Clean-machine Windows and macOS install/repair/credential-rotation runs.
- Windows code signing and Apple signing/notarization.
- Repository-level public distribution license selection.

The repository is suitable for a private engineering alpha. It is not yet a
signed, public, novice-facing release.
