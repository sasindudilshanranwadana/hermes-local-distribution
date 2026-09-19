# Provider guide

The wizard supports OpenRouter, OpenAI, Anthropic, Gemini, DeepSeek, Ollama,
LM Studio, and additional OpenAI-compatible endpoints.

For every provider, enter:

- the API key when required;
- the model identifier shown by that provider;
- the model context size if it differs from the suggested value.

The wizard validates the credential against the provider's model catalog and
confirms that the selected model is available before accepting it. Credentials
are masked in the UI and stored only in the local owner-only secret file.

The wizard creates roles for fast chat, coding, agentic work, reasoning,
long-context work, and vision. Missing optional roles are shown as degraded.
Installation requires viable fast, coding, agentic, and reasoning routes.

Use at least two independent cloud providers when high availability matters.
For fully local mode, start Ollama or LM Studio before provider validation.
Use built-in Hermes memory in fully local mode. The optional Mem0 profile in
this private alpha currently requires a cloud embedding provider and is kept
off by default.
