# Security Policy

## Supported versions

| Version | Security fixes |
|---------|----------------|
| `2.x`   | Supported      |
| `1.x`   | Not supported - please upgrade |

## Reporting a vulnerability

Please do **not** file public GitHub issues for suspected vulnerabilities.
The project prefers coordinated disclosure:

1. Open a private [GitHub security advisory](https://github.com/prodrom3/nostrax/security/advisories/new)
   on this repository, **or**
2. Contact the maintainers privately with a minimal reproduction and an
   impact assessment.

A valid report includes:

- The vulnerable versions.
- A proof-of-concept (code, request, payload, target URL, etc.).
- Your assessment of impact (confidentiality / integrity / availability)
  and any mitigations you have already considered.

## What to expect

- **Acknowledgement** within 5 business days of receipt.
- **Triage and remediation plan** within 10 business days, proportional
  to severity (CVSS v3.1).
- **Fix** released as a patch version (`2.0.X`) out of the regular
  cadence for confirmed high- or critical-severity issues. Lower-severity
  issues ride the next scheduled release.
- **Advisory** published on the repository with the affected version
  range, mitigation instructions, and credit to the reporter (unless the
  reporter prefers anonymity).

## Scope

In scope:

- All code under `nostrax/` in this repository.
- The published `nostrax` wheel on PyPI (once released).
- The CI workflow configuration at `.github/workflows/`.

Out of scope:

- Vulnerabilities in direct or transitive dependencies. Please report
  those upstream to the respective projects (`aiohttp`, `lxml`,
  `beautifulsoup4`, `defusedxml`, `regex`, `packaging`, `tomli`).
- Bugs in callers that use the library incorrectly (e.g., running the
  crawler without the shipped `SafeResolver` against an untrusted
  target and then complaining about SSRF).
- Social-engineering attacks on the maintainers.

## Non-security bugs

Non-security bug reports belong on the public
[issue tracker](https://github.com/prodrom3/nostrax/issues).
