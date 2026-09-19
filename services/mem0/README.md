# Optional local Mem0 source

The installer downloads the pinned Apache-2.0 Mem0 revision declared in
`manifests/components.toml` into `source/` after checksum/revision verification.
No memories, credentials, or runtime database files are distributed.

The profile is off by default. In this private alpha, Mem0's upstream server
uses a cloud embedding provider, so the installer rejects it in fully local
mode. Built-in Hermes memory remains enabled for local-only installations.
