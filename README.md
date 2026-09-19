# Hermes Local Distribution

A private-alpha, novice-friendly distribution of a hardened Hermes Agent system.
It installs Hermes Desktop together with local routing, model classification,
optional self-hosted memory, verification workflows, and conservative security
defaults. Every installation starts with empty memory and credentials belonging
only to its owner.

## Intended experience

1. Download the installer for Windows, macOS, or Linux from GitHub Releases.
2. Open it and choose local, cloud, or hybrid models.
3. Add one or more model providers and the model names available to the account.
4. Optionally enable self-hosted Mem0.
5. Select **Install now**. The wizard installs and verifies the local stack.
6. Open Hermes Desktop.

The user does not edit YAML, run Docker commands, or copy credentials into Git.
The wizard validates credentials and the selected model before installation.

## What is included

- Official Hermes Agent pinned to a tested revision
- Hermes Desktop bootstrap
- OmniRoute 3.8.50 pinned by image digest
- Redis pinned by image digest
- The portable pre-classifier and its routing intelligence
- Generated capability pools for each user's actual models
- Optional self-hosted Mem0 and Postgres
- Golden compression, delegation, verification, approval, and privacy policy
- Checksum-verified Superpowers plugin
- Repair, doctor, uninstall-plan, and redacted support-bundle commands

## Privacy boundary

No credential, conversation, memory, channel identifier, personal `SOUL.md`,
VPS address, session, or database is included. Local-only mode rejects cloud
providers. Cloud and hybrid modes explicitly send prompts to providers selected
by the owner. The distribution never connects to the author's infrastructure.

See [Privacy model](docs/privacy-model.md) and [Security policy](SECURITY.md).

## Requirements

- Windows 10/11, current macOS, or a modern Linux desktop
- Docker Desktop (or Docker Engine with Compose on Linux)
- Internet access during initial installation for pinned upstream components
- At least one local model endpoint or model-provider account

Fully local inference requires enough RAM/VRAM for the selected model. The
installer cannot make a weak local model behave identically to a stronger cloud
model; it preserves the routing and verification architecture, not model weights.
Built-in Hermes memory is used in fully local mode. The optional Mem0 profile is
off by default in this alpha because its upstream server currently needs a cloud
embedding provider.

## Development

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m pytest --cov=hermes_local_setup --cov-fail-under=80
.venv/bin/hermes-local-setup plan --answers tests/fixtures/local_answers.json --json
```

Build the graphical artifact:

```bash
.venv/bin/pyinstaller --noconfirm --clean hermes-local-setup.spec
```

The GitHub workflows build and test on Windows, macOS, and Linux. Public release
is intentionally blocked pending the license decision, platform signing, and a
clean-machine private beta.

## Repository status

This repository is a private alpha. Do not make it public until every item in
[LICENSE-DECISION.md](LICENSE-DECISION.md) is resolved and the private-alpha
runbook has passed on clean Windows and macOS machines.
