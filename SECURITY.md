# Security policy

## Credential handling

- Credentials are collected only by masked GUI fields or an owner-only secret file.
- Secrets are never accepted as CLI arguments.
- Secret files are atomically replaced and use mode `0600` where supported.
- Command execution never uses a shell and rejects registered secrets in argv.
- Logs, errors, dry-run plans, and support bundles pass through central redaction.
- Provider credentials are sent only to loopback OmniRoute or directly to the
  provider endpoint selected by the owner.

## Local network exposure

All published Docker ports bind to `127.0.0.1`. Redis, Postgres, and internal
service traffic use Docker networks that are not published. Remote MCP servers
are opt-in.

## Supply chain

- Hermes installation scripts are bundled and checksum-verified.
- Hermes source, OmniRoute, Redis, Mem0, and Superpowers are pinned by immutable
  commit or image digest.
- CI runs tests, linting, type checking, Compose validation, and a full-history
  Gitleaks scan.
- A component with unknown redistribution rights is blocked from artifacts.

## Reporting

For the private alpha, report security issues privately to the repository owner.
Do not include real credentials, conversation text, memories, or support bundles
in a public issue.

