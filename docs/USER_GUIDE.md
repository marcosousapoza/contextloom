# User Guide

ContextLoom organizes private knowledge into nested categories and memories. Every account
has an isolated workspace; users cannot browse or modify another user's records.

## Sign In

Open the URL supplied by the administrator and sign in with either your username or email
address and password. Public registration appears only when an administrator enables it.

If repeated login attempts fail, ContextLoom temporarily throttles further attempts. A
disabled account cannot sign in or use existing personal access tokens.

If an administrator created your account or assigned its initial password, ContextLoom opens
the password-change page immediately after login. No other page is available until you choose
a private password. You can change it again later from **Settings**.

## Categories

Select **New category** to create a top-level category or choose a parent to nest it. Names
must be unique under the same parent. A category can be renamed, described, or moved below
another category.

Archiving a category removes the complete subtree and all its memories from the active
workspace. Open **Archives** to restore it later. If a restored name conflicts with an
active category, ContextLoom adds a numeric suffix instead of overwriting data. Deleting an
archive is permanent.

## Memories

Select **New memory**, choose a category, enter the content, and assign a priority from 1 to
5. Memories can later be edited, moved to another category, or permanently deleted.

## Personal Access Tokens

Open **Settings** to create a token for an MCP client. Give each token a descriptive name,
an optional expiration, and only the scopes it needs:

- `categories:read` lists categories.
- `categories:write` creates, updates, and archives categories.
- `memories:read` lists memories.
- `memories:write` creates, updates, and deletes memories.

The token value is displayed once. Store it in the MCP client's secret storage and never
put it in source control or screenshots. Revoke a token immediately if it may be exposed.

## Export

Open **Settings** and select **Export my data**. The download contains categories, memories,
archives, hierarchy, priorities, and timestamps. It excludes passwords, sessions, tokens,
and administrator privileges.

Exports are personal portability files. They are not a replacement for administrator-run
PostgreSQL backups.

## Import

Open **Import**, select a ContextLoom ZIP export, and choose a mode:

- **Merge** keeps existing data and adds imported records. Name conflicts receive numeric
  suffixes.
- **Replace** atomically removes your current categories, memories, and archives before
  importing. It never changes another account.

ContextLoom validates the full archive and presents a dry-run summary first. Review the
counts and conflicts, then confirm. A rejected or failed import makes no database changes.
