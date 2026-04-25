# Security Policy

## Supported versions

Only the latest release is actively maintained.

## Reporting a vulnerability

**Please do not open a public GitHub issue for security vulnerabilities.**

Email: **security@eduluma.org**

Include:
- A description of the vulnerability and potential impact
- Steps to reproduce or a proof-of-concept
- Any suggested fix (optional)

We will acknowledge receipt within 48 hours and aim to ship a fix within 14 days
for confirmed critical issues.

## Scope

| In scope                           | Out of scope                              |
| ---------------------------------- | ----------------------------------------- |
| API authentication bypass          | Brute-force of weak user passwords        |
| SQL injection                      | Social engineering                        |
| Data exposure of other users' data | Third-party services (Cloudflare, GitHub) |
| SSRF / RCE in ingest workers       | Denial-of-service against the free tier   |

## Safe-harbour

We won't pursue legal action against researchers who act in good faith, do not
access or modify other users' data, and coordinate disclosure with us before
publishing findings.
