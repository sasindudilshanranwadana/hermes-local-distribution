# TDD evidence

## Foundation

- RED commit `f027850`: package, model, path, secret, redaction, command, and
  capability tests failed because implementations were absent.
- GREEN commit `13a601c`: 20 foundation tests passed.

## Provider and installation planning

- RED commit `fac1a20`: provider, renderer, state, installer, and diagnostic
  modules were absent.
- GREEN commit `40f0719`: 31 unit tests and 4 integration tests passed.

## Sanitized services and policy

- RED commit `798da95`: Hermes policy, OmniRoute client, and Compose artifacts
  were absent; the hygiene test also identified literal host markers.
- GREEN commit `bad441e`: Compose validation, policy tests, hygiene tests, and
  pre-classifier compilation passed.

## Wizard and CLI

- RED commit `4f37085`: configuration loader, wizard state, and CLI were absent.
- GREEN commit `fab7ba8`: all seven new journeys passed.

## Applied installation

- RED commit `40acc81`: installer lacked runner/resource/token/provisioning inputs.
- GREEN commit `ee9a361`: a fully mocked applied installation passed, including
  owner-only secrets, Compose/Hermes actions, routing pools, and saved state.

## Verified plugin installation

- RED commit `6dce5c0`: component archive installer was absent.
- GREEN: checksum, path-traversal, allowlisted extraction, and installation tests
  passed before packaging integration.

## Portable pre-classifier regression corpus

- RED commit `1846fdd`: the imported corpus ran 47 tests with 7 failures caused
  by inherited host settings and concrete pool assumptions.
- GREEN commit `4761c42`: all 47 tests passed with the original 96% and 95%
  accuracy thresholds unchanged.
- RED commit `d339914` and GREEN commit `557ba83`: added a Docker test stage and
  Linux CI gate; the container ran all 47 tests successfully.

## Optional Mem0 source installation

- RED commit `ee712d6`: enabling Mem0 exposed the missing pinned-source fetch.
- GREEN commit `164ffec`: checksum-verified extraction and Compose wiring passed
  8 focused tests.
- RED commit `2a1a123` and GREEN commit `5392f43`: the real pinned archive's
  documentation symlink was reproduced and is now safely skipped rather than
  followed.

## Clean-install ordering and curated plugin

- RED commit `5859941` and GREEN commit `e18e2af`: startup now waits for
  OmniRoute, installs providers and pools, then starts the readiness-gated full
  stack.
- RED commit `a5826ee` and GREEN commit `a11752b`: Superpowers is installed and
  enabled by default through its pinned, checksum-verified archive.

## Provider and privacy completion

- RED commit `192f4ff` and GREEN commit `70feb36`: provider-specific credential
  headers and selected-model validation pass 5 focused tests.
- RED commit `073bd65` and GREEN commit `86a8360`: fully local mode rejects the
  alpha Mem0 cloud dependency and keeps built-in memory local.
- RED commit `ffbf9f5` and GREEN commit `944e760`: a generic
  OpenAI-compatible provider option is present in the wizard catalog.
