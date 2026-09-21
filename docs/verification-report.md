# Verification report

Verified locally on Linux x86_64 and with native GitHub runners on 2026-09-21:

- Core suite: 68/68 passed.
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
- Gitleaks full-history scan through workflow code commit `5452bfc`: no leaks
  found.
- AgentShield: grade A, no findings. It reported zero recognized agent-config
  files, so this is not treated as a general source-code security scan.
- `git diff --check`: passed for the final working tree.
- Native CI run `35602876394`: all Windows, macOS, and Linux jobs passed on
  Python 3.11 and 3.12; repository hygiene also passed.
- Private-alpha installer run `35602419589`: Windows, macOS, and Linux builds,
  tests, checksum generation, and artifact uploads passed.
- Workflows pin current Node 24 releases for checkout, Python setup, artifact
  transfer, and Gitleaks; no Node runtime deprecation warning remains.
- Downloaded release artifacts had the expected native formats: Windows x86-64
  PE, macOS arm64 Mach-O app, and Linux x86-64 ELF.
- Every downloaded `SHA256SUMS.txt` entry verified. Manifests used relative
  paths, excluded generated manifest files, and covered all five macOS payload
  files, including nested app contents.
- Release artifact sizes: Windows executable 11,946,556 bytes; macOS executable
  10,571,904 bytes; Linux executable 21,887,832 bytes.
- Public prerelease `v0.1.0-alpha.2`, workflow `35606318343`: all platform
  builds and the release job passed. The three published ZIPs were downloaded
  from GitHub Releases; every checksum entry verified.
- Extracted `alpha.2` ZIP permissions were verified: Linux and both macOS
  executables are mode `755`; the Windows executable is mode `644` as expected.
- Final `alpha.2` executable sizes: Windows 11,945,971 bytes; macOS 10,572,256
  bytes; Linux 21,887,960 bytes.

Pending external acceptance gates:

- Clean-machine Windows and macOS install/repair/credential-rotation runs.
- Windows code signing and Apple signing/notarization.
- Repository-level public distribution license selection.

The repository is suitable for a private engineering alpha. It is not yet a
signed, public, novice-facing release.
