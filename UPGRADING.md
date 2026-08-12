# Upgrading ContextLoom

## From Retain or SQLite-Based Installations

ContextLoom replaces the local SQLite architecture with a multi-user PostgreSQL modular
monolith. It does not silently read or migrate Retain SQLite databases. Direct SQLite
migration is outside this release.

Use the documented versioned CSV/ZIP portability workflow where an export is available.
Every imported record receives a new internal database ID and is assigned only to the user
performing the import. Validate with merge mode first when preserving existing data.

## ContextLoom Releases

Pushes to `main` do not publish containers. A `vX.Y.Z` release tag publishes one image under
the exact `X.Y.Z` tag, the `X.Y` series alias, and `latest`. Version-tagged deployment
manifests pin the exact image rather than following `latest`.

Before every upgrade:

1. Make and verify an administrator-managed PostgreSQL backup.
2. Review release notes for configuration and format changes.
3. Build or pull the target image using its exact version tag.
4. Recreate the pod. The target image waits for PostgreSQL and applies migrations before
   starting the server.
5. Verify `/health`, `/ready`, login, and an MCP request.

Do not run an older application version against a database after its migrations have been
applied unless that release explicitly documents rollback support.
