# Private-alpha acceptance runbook

Run this on clean Windows and macOS machines before inviting non-technical users.

1. Install and start Docker Desktop.
2. Download the platform artifact and verify `SHA256SUMS.txt`.
3. Launch the wizard without Git or Python installed.
4. Complete one local-only installation and confirm no cloud request occurs.
5. Complete one cloud/hybrid installation with newly created test credentials.
6. Verify all service ports bind only to loopback.
7. Open Hermes Desktop and complete chat, file, tool, coding, and browser tasks.
8. Verify a difficult task reaches a complex pool and a simple task reaches a
   fast/simple pool.
9. Add and retrieve a synthetic Mem0 fact, then confirm a fresh installation
   contains no previous memory.
10. Rerun the installer in repair mode and confirm no provider duplicates.
11. Replace one provider credential and prove the old credential no longer works.
12. Restart the computer and confirm all local services recover.
13. Generate a support bundle and scan it for credentials and test conversation text.
14. Run the preservation-first uninstall plan and confirm memories are retained.

Record OS versions, artifact checksums, outcomes, and screenshots in a private
release issue. Never use personal accounts or production credentials for this run.

