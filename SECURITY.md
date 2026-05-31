# Security Policy

## Scope

This project is a local-first BLE integration and dashboard for H59 smart bands.

The primary security concerns are:
- accidental disclosure of local device data
- accidental disclosure of personal device identifiers
- introduction of unsafe BLE write behavior
- introduction of secrets into the repository

## Reporting

If you find a security issue, do not open a public issue with exploit details first.

Report it privately to the maintainer through a private channel and include:
- a short description of the issue
- affected files or commands
- reproduction steps
- impact assessment

## Repository Hygiene

Contributors must not commit:
- API keys, tokens, passwords, certificates, or private keys
- local SQLite databases
- BLE packet captures, logs, or generated traces containing personal data
- real device addresses, nicknames, or other personal identifiers in examples or tests
- generated build/runtime directories such as virtualenvs, `node_modules`, `dist`, caches, or local dashboard runtime state

Use generic placeholders in examples:
- `left-wrist`
- `demo-band`
- `11111111-2222-3333-4444-555555555555`

## Operational Safety

BLE write behavior should remain conservative.

Before exposing new write commands in the CLI:
1. confirm the packet shape from live evidence or vendor documentation
2. verify round-trip behavior where possible
3. document whether the command is read-only, configuration-changing, or state-changing
4. add tests and research notes

Particular care is required for:
- device clock writes
- measurement scheduling settings
- reboot or reset commands
- any command that may alter on-device history retention or measurement state

## Disclosure Boundaries

This repository is intended to be shared as source, not as a full zipped working tree.

If you share it with third parties:
- share the git repository
- do not include local ignored directories such as `data/`, `misc/artifacts/`, `captures/`, or `traces/`
- scrub any exported screenshots or reports if they contain personal health data
