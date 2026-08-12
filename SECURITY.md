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

The zero-input bootstrap account uses `admin` / `admin` and is forced through a password
change before any application or Admin access. The default deployment binds HTTP to
`127.0.0.1`; change the password before altering that binding or exposing the service. The
default PostgreSQL trust mode is acceptable only while port 5432 remains unpublished inside
the single-application pod.

Rotate `CONTEXTLOOM_SECRET_KEY` only with care: rotation invalidates existing browser
sessions and all personal access tokens because it participates in token hashing. Never send
database URLs, password values, secret keys, token values, exports, or database dumps in a
security report.

The Podman deployment stores the Django key as a Podman secret containing a serialized
Kubernetes Secret and injects it through `secretKeyRef`. ContextLoom does not create a
plaintext secret file. Podman's default `file` secret driver uses read-protected host storage;
operators may configure another supported driver according to their security policy. Podman
kube environment expansion also exposes the resolved value to host administrators through
`podman inspect`; restrict Podman access accordingly.
