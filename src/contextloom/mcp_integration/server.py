import hashlib

from asgiref.sync import sync_to_async
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import connections
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import AccessToken
from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from contextloom.accounts.services import authenticate_token
from contextloom.knowledge.exceptions import KnowledgeError
from contextloom.knowledge.models import Category, Memory
from contextloom.knowledge.services import (
    archive_category as archive_category_service,
)
from contextloom.knowledge.services import (
    save_category,
    save_memory,
)


class CombinedTokenVerifier:
    """
    Accept either ContextLoom PATs (clm_...) or OAuth2 access tokens.
    PATs are checked first to preserve backward compatibility.
    OAuth tokens are validated by checksum and must have the /mcp resource.
    """

    async def verify_token(self, raw_token):
        if not raw_token:
            return None

        # Try PAT authentication first
        if raw_token.startswith("clm_"):
            token = await _run_sync(lambda: authenticate_token(raw_token))
            if token is None:
                return None
            return AccessToken(
                token=token.prefix,
                client_id=f"contextloom-token-{token.pk}",
                subject=str(token.owner_id),
                scopes=token.scopes,
                expires_at=int(token.expires_at.timestamp()) if token.expires_at else None,
            )

        # Try OAuth2 access token authentication
        return await _run_sync(lambda: self._verify_oauth_token(raw_token))

    def _verify_oauth_token(self, raw_token):
        from oauth2_provider.models import AccessToken as OAuthAccessToken

        token_checksum = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        oauth_token = (
            OAuthAccessToken.objects.select_related("application", "user")
            .filter(token_checksum=token_checksum)
            .first()
        )

        if not oauth_token or not oauth_token.is_valid():
            return None

        # Validate audience/resource: token must be for /mcp
        resources = oauth_token.resource
        mcp_resource = f"{settings.CONTEXTLOOM_PUBLIC_URL.rstrip('/')}/mcp"
        if mcp_resource not in resources:
            return None

        if not oauth_token.user or not oauth_token.user.is_active:
            return None

        return AccessToken(
            token=oauth_token.token[:12] if oauth_token.token else f"oauth-{oauth_token.pk}",
            client_id=(
                oauth_token.application.client_id if oauth_token.application else "oauth-client"
            ),
            subject=str(oauth_token.user_id),
            scopes=oauth_token.scope.split() if oauth_token.scope else [],
            expires_at=int(oauth_token.expires.timestamp()) if oauth_token.expires else None,
        )


async def _run_sync(operation):
    def wrapped():
        connections.close_all()
        try:
            return operation()
        finally:
            connections.close_all()

    return await sync_to_async(wrapped, thread_sensitive=True)()


def _create_mcp_server():
    return FastMCP(
        "ContextLoom",
        instructions="Manage the authenticated user's categorized knowledge.",
        streamable_http_path="/mcp",
        stateless_http=True,
        json_response=True,
        max_request_body_size=1_000_000,
        token_verifier=CombinedTokenVerifier(),
        auth=AuthSettings(
            issuer_url=settings.CONTEXTLOOM_PUBLIC_URL,
            resource_server_url=f"{settings.CONTEXTLOOM_PUBLIC_URL}/mcp",
            required_scopes=[],
        ),
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=settings.CONTEXTLOOM_MCP_ALLOWED_HOSTS,
            allowed_origins=settings.CONTEXTLOOM_MCP_ALLOWED_ORIGINS,
        ),
    )


mcp = _create_mcp_server()


def _identity(required_scope):
    access = get_access_token()
    if not access or not access.subject or required_scope not in access.scopes:
        raise ValueError(f"This token requires the {required_scope} scope.")
    try:
        owner_id = int(access.subject)
    except ValueError as exc:
        raise ValueError("The authenticated identity is invalid.") from exc
    user_model = get_user_model()
    owner = user_model.objects.filter(pk=owner_id, is_active=True).first()
    if owner is None:
        raise ValueError("The authenticated account is unavailable.")
    return owner


def _category(owner, category_id):
    category = Category.objects.filter(owner=owner, pk=category_id).first()
    if category is None:
        raise ValueError("Category not found.")
    return category


def _memory(owner, memory_id):
    memory = Memory.objects.filter(owner=owner, pk=memory_id).first()
    if memory is None:
        raise ValueError("Memory not found.")
    return memory


@mcp.tool()
async def list_categories() -> list[dict]:
    """List all categories owned by the authenticated user."""

    def operation():
        owner = _identity("categories:read")
        return list(
            Category.objects.filter(owner=owner)
            .order_by("name", "id")
            .values("id", "parent_id", "name", "description")
        )

    return await _run_sync(operation)


@mcp.tool()
async def create_category(name: str, description: str = "", parent_id: int | None = None) -> dict:
    """Create a category, optionally nested below another owned category."""

    def operation():
        owner = _identity("categories:write")
        parent = _category(owner, parent_id) if parent_id is not None else None
        try:
            category = save_category(owner=owner, name=name, description=description, parent=parent)
        except KnowledgeError as exc:
            raise ValueError(str(exc)) from exc
        return {"id": category.id, "parent_id": category.parent_id, "name": category.name}

    return await _run_sync(operation)


@mcp.tool()
async def update_category(
    category_id: int,
    name: str,
    description: str = "",
    parent_id: int | None = None,
) -> dict:
    """Rename, describe, or move an owned category."""

    def operation():
        owner = _identity("categories:write")
        category = _category(owner, category_id)
        parent = _category(owner, parent_id) if parent_id is not None else None
        try:
            category = save_category(
                owner=owner,
                category=category,
                name=name,
                description=description,
                parent=parent,
            )
        except KnowledgeError as exc:
            raise ValueError(str(exc)) from exc
        return {"id": category.id, "parent_id": category.parent_id, "name": category.name}

    return await _run_sync(operation)


@mcp.tool()
async def archive_category(category_id: int) -> dict:
    """Archive an owned category and all of its descendants and memories."""

    def operation():
        owner = _identity("categories:write")
        try:
            archive = archive_category_service(owner=owner, category_id=category_id)
        except Category.DoesNotExist as exc:
            raise ValueError("Category not found.") from exc
        return {"archive_id": archive.id, "name": archive.name}

    return await _run_sync(operation)


@mcp.tool()
async def list_memories(category_id: int | None = None) -> list[dict]:
    """List owned memories, optionally restricted to one owned category."""

    def operation():
        owner = _identity("memories:read")
        query = Memory.objects.filter(owner=owner)
        if category_id is not None:
            _category(owner, category_id)
            query = query.filter(category_id=category_id)
        return list(query.values("id", "category_id", "content", "priority", "updated_at"))

    return await _run_sync(operation)


@mcp.tool()
async def create_memory(category_id: int, content: str, priority: int = 3) -> dict:
    """Create a memory in an owned category."""

    def operation():
        owner = _identity("memories:write")
        category = _category(owner, category_id)
        memory = save_memory(owner=owner, category=category, content=content, priority=priority)
        return {"id": memory.id, "category_id": memory.category_id, "priority": memory.priority}

    return await _run_sync(operation)


@mcp.tool()
async def update_memory(memory_id: int, category_id: int, content: str, priority: int = 3) -> dict:
    """Edit or move an owned memory."""

    def operation():
        owner = _identity("memories:write")
        memory = _memory(owner, memory_id)
        category = _category(owner, category_id)
        memory = save_memory(
            owner=owner,
            memory=memory,
            category=category,
            content=content,
            priority=priority,
        )
        return {"id": memory.id, "category_id": memory.category_id, "priority": memory.priority}

    return await _run_sync(operation)


@mcp.tool()
async def delete_memory(memory_id: int) -> dict:
    """Permanently delete an owned memory."""

    def operation():
        owner = _identity("memories:write")
        memory = _memory(owner, memory_id)
        memory.delete()
        return {"deleted": True, "id": memory_id}

    return await _run_sync(operation)


def create_mcp_application():
    server = _create_mcp_server()
    for tool in (
        list_categories,
        create_category,
        update_category,
        archive_category,
        list_memories,
        create_memory,
        update_memory,
        delete_memory,
    ):
        server.tool()(tool)
    return server.streamable_http_app()


mcp_application = mcp.streamable_http_app()
