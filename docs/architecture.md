# Architecture

```text
Hermes Desktop
      |
      | OpenAI-compatible API on loopback
      v
Portable pre-classifier
      |
      | classified capability pool
      v
OmniRoute ---- selected local/cloud providers
      |
      +---- Redis (internal network)

Hermes memory ---- built-in memory
      |
      +---- optional self-hosted Mem0 ---- Postgres (internal network)
```

The golden policy is immutable source input. The wizard creates a separate
environment binding containing provider endpoints, model capability assignments,
and local secret names. Runtime state—conversations, memories, databases, logs,
and caches—is created only on the user's machine.

The pre-classifier owns task and complexity classification. OmniRoute owns
provider selection and fallback within generated capability pools. No portable
source file assumes that a user owns a particular subscription or model.

