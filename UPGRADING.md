# Upgrading ContextLoom

## From Retain or SQLite-Based Installations

ContextLoom replaces the local SQLite architecture with a multi-user PostgreSQL modular
monolith. It does not silently read or migrate Retain SQLite databases. Direct SQLite
migration is outside this release.

Use the documented versioned CSV/ZIP portability workflow where an export is available.
Every imported record receives a new internal database ID and is assigned only to the user
performing the import. Validate with merge mode first when preserving existing data.

## ContextLoom Releases

Before every upgrade:

1. Make and verify an administrator-managed PostgreSQL backup.
2. Review release notes for configuration and format changes.
3. Build or pull the target image using its exact version tag.
4. Run `contextloom migrate` using the target image.
5. Recreate the pod, then verify `/health`, `/ready`, login, and an MCP request.

Do not run an older application version against a database after its migrations have been
applied unless that release explicitly documents rollback support.
