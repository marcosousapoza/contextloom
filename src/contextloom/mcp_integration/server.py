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


class PersonalTokenVerifier:
    async def verify_token(self, raw_token):
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


async def _run_sync(operation):
    def wrapped():
        connections.close_all()
        try:
            return operation()
        finally:
            connections.close_all()

    return await sync_to_async(wrapped, thread_sensitive=True)()


mcp = FastMCP(
    "ContextLoom",
    instructions="Manage the authenticated user's categorized knowledge.",
    streamable_http_path="/mcp",
    stateless_http=True,
    json_response=True,
    max_request_body_size=1_000_000,
    token_verifier=PersonalTokenVerifier(),
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


mcp_application = mcp.streamable_http_app()
