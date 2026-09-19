# Privacy model

## Always local

- Application configuration and generated internal tokens
- Conversation/session databases
- Built-in Hermes memory
- Self-hosted Mem0 data when enabled
- Files and terminal execution
- Routing decisions and operational logs

## Leaves the computer only when selected

- Prompts and tool context sent to configured cloud model providers
- Requests sent to explicitly enabled remote MCP services
- Downloads of pinned installation components

Local-only mode rejects non-loopback model endpoints. The installer never
contains or contacts an author-owned VPS endpoint. Support bundles use an
allowlist and contain only health and version summaries.

