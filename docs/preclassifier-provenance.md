# Pre-classifier provenance

The portable pre-classifier was imported from the owner's private source
repository at base commit `76547753135b18d0a37ac52120edd46317fb760e` on
2026-09-20. The private repository URL and owner identity are intentionally not
included in this distribution.

Imported runtime and regression material:

- `app.py` and its labeled benchmark corpora;
- the routing, failover, quota, authentication, readiness, logging, and safety
  regression suite;
- dependency declarations required by the service.

Sanitization changes made for this distribution:

- replaced concrete account/provider/model fallbacks with generated capability
  pool names;
- moved service URLs, database paths, internal authentication, prompt budgets,
  and tool-free model restrictions to environment-driven configuration;
- made local classification opt-in so Ollama is not an undeclared dependency;
- removed reliance on the source host's environment and credentials from tests;
- replaced source-account model assertions with synthetic pool membership
  assertions while preserving all accuracy thresholds;
- excluded logs, environment files, databases, request dumps, caches, backups,
  and runtime state.

The imported suite currently contains 47 passing tests. It retains the 96%
fallback-corpus threshold, the 95% semantic challenge threshold with zero
critical under-routes, and the 200+ case expanded corpus requirement.

