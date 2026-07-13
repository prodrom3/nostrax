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

## Hardening model and known limitations

nostrax ships several protections on by default. Understanding what they
do - and where they stop - is part of using it safely against untrusted
input.

Built-in protections:

- **SSRF / DNS-rebinding**: `validate_target_url` rejects targets that
  resolve to loopback, private, link-local, reserved, multicast,
  unspecified, or cloud-metadata addresses, and `SafeResolver` re-applies
  that classifier at *every* DNS resolution the crawl performs, closing
  the TTL=0 rebinding window.
- **XXE / XML bombs**: sitemap parsing goes through `defusedxml` with an
  additional DOCTYPE/ENTITY string reject.
- **ReDoS**: `--pattern` / `--exclude` run through the `regex` package
  with a per-URL match timeout.
- **Path traversal**: file and cache writes are confined to the current
  working directory via a fully-resolved, case-normalised containment
  check.
- **Resource limits**: response, robots.txt, and sitemap sizes are
  capped; the frontier queue is bounded; the read cap applies to
  *decompressed* bytes, so a gzip bomb is caught after inflation.
- **Credential hygiene**: userinfo is stripped from emitted URLs and
  redacted from logs; redirects are disabled on every request.

Known limitations (by design):

- **A proxy voids SSRF protection.** When `--proxy` is set, the proxy,
  not nostrax, resolves the target hostname, so `SafeResolver` never
  sees the target's address and cannot reject an internal one. Do not
  point a proxied crawl at untrusted targets unless the proxy itself
  enforces an egress policy.
- **robots.txt is advisory.** `--respect-robots` is opt-in; the default
  is to ignore robots.txt. When enabled, an unreachable or malformed
  robots.txt fails open (crawling is allowed).
- **Running without `SafeResolver`.** The library-level `crawl_async`
  installs `SafeResolver` itself, but a caller who supplies a custom
  `Fetcher` or their own `aiohttp` session is responsible for their own
  egress safety.

## Non-security bugs

Non-security bug reports belong on the public
[issue tracker](https://github.com/prodrom3/nostrax/issues).
