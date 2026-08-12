# Security Policy

## Supported Versions

Security fixes are applied to the latest released ContextLoom version.

## Reporting

Do not open a public issue for a suspected vulnerability. Send a private report to the
maintainer through the repository's security advisory feature. Include affected versions,
reproduction steps, impact, and any suggested mitigation. Allow reasonable time for a fix
before public disclosure.

## Deployment Responsibilities

ContextLoom provides authentication, CSRF protection, scoped hashed tokens, tenant-scoped
queries, bounded imports, and a non-root container. Operators remain responsible for TLS,
reverse-proxy security, host updates, secret management, PostgreSQL access and backups,
network filtering, monitoring, and timely ContextLoom upgrades.

Rotate `CONTEXTLOOM_SECRET_KEY` only with care: rotation invalidates existing browser
sessions and all personal access tokens because it participates in token hashing. Never send
database URLs, password values, secret keys, token values, exports, or database dumps in a
security report.
