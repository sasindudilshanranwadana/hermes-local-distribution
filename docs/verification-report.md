# Verification report

Verified on Linux x86_64 on 2026-09-20:

- Core suite: 62/62 passed.
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
- PyInstaller Linux artifact: built successfully (13,194,216 bytes).
- Frozen GUI smoke test: remained open under Xvfb for 5 seconds with no exception.
- Gitleaks working-tree scan: no leaks found.
- Gitleaks full-history scan: no leaks found across 32 commits.
- AgentShield: grade A, no findings. It reported zero recognized agent-config
  files, so this is not treated as a general source-code security scan.
- `git diff --check`: passed for the final working tree.

Pending external acceptance gates:

- GitHub Actions Windows and macOS native artifact builds.
- Clean-machine Windows and macOS install/repair/credential-rotation runs.
- Windows code signing and Apple signing/notarization.
- Repository-level public distribution license selection.

The repository is suitable for a private engineering alpha. It is not yet a
signed, public, novice-facing release.
