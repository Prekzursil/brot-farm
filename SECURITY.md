# Security Policy

## Supported versions

Fractal Darkroom is a library/CLI + static docs site, not a deployed service.
Only the latest commit on `main` is supported with security fixes.

| Version | Supported          |
| ------- | ------------------ |
| main    | ✅                 |
| older   | ❌ update first    |

## Reporting a vulnerability

**Please use [private vulnerability reporting]** — click *Report a vulnerability*
in the repository's *Security* tab. Reports there go privately to the maintainer
and allow coordinated disclosure.

- Do **not** open a public issue or PR for anything security-sensitive.
- Include reproduction steps, the module affected, and — for numerical-output
  bugs — the seed and parameters that reproduce them.
- You should get an acknowledgement within **72 hours** and a fix or mitigation
  plan within **14 days**, workload permitting.

## Scope

This project ships:

- **Python code** (`buddhabrot.py`, `cosbrot.py`, `brot_farm.py`, `topup.py`) —
  runs locally on user machines, reads/writes only its own `out/` directory,
  and executes no network calls, no `eval`, and no user-supplied code paths.
- **A static client-side docs site** (`docs/`) — includes a formula sandbox.
  A formula, whether typed or carried by a shared `#exp=` link, a pin or an
  imported experiment file, is parsed by a whitelist arithmetic grammar and
  compiled to closures. It is never evaluated as code (no `eval`, no
  `new Function`), and the playground writes formula errors and imported
  names as text, never as HTML. It is not a server feature and no data leaves
  the page.

In scope: anything in this repository that could crash, corrupt data, or
execute unintended code when a user runs the documented commands with
non-malicious inputs, plus dependency-chain concerns in `requirements.txt`.

Out of scope: rendering performance, aesthetic differences, and findings that
require already-arbitrary code execution on the user's machine.

## Supply chain

Dependencies are `numpy`, `pillow`, `pytest`, and `pytest-cov` from PyPI,
pinned by minimum versions in `requirements.txt`; CI installs them on
GitHub-hosted runners. Report suspected dependency compromises through the
same private channel, and via the package's own advisories.
