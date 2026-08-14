import json

import pytest
from starlette.testclient import TestClient

from contextloom.accounts.models import PersonalAccessToken
from contextloom.knowledge.models import Category, Memory
from contextloom.mcp_integration.server import create_mcp_application

INITIALIZE = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "test", "version": "1"},
    },
}


def _call_tool(client, token, name, arguments):
    return client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 10,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        },
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json, text/event-stream",
        },
    )


@pytest.mark.django_db(transaction=True)
def test_mcp_streamable_http_auth_scopes_and_tenant_isolation(user, other_user):
    _, read_token = PersonalAccessToken.issue(owner=user, name="reader", scopes=["categories:read"])
    _, write_token = PersonalAccessToken.issue(
        owner=user, name="writer", scopes=["categories:write"]
    )
    Category.objects.create(owner=other_user, name="Foreign secret")
    with TestClient(create_mcp_application(), base_url="http://localhost") as client:
        unauthorized = client.post(
            "/mcp", json=INITIALIZE, headers={"Accept": "application/json, text/event-stream"}
        )
        response = client.post(
            "/mcp",
            json=INITIALIZE,
            headers={
                "Authorization": f"Bearer {read_token}",
                "Accept": "application/json, text/event-stream",
            },
        )
        forbidden = client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "create_category",
                    "arguments": {"name": "Not allowed"},
                },
            },
            headers={
                "Authorization": f"Bearer {read_token}",
                "Accept": "application/json, text/event-stream",
            },
        )
        created = client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "create_category",
                    "arguments": {"name": "Created through MCP"},
                },
            },
            headers={
                "Authorization": f"Bearer {write_token}",
                "Accept": "application/json, text/event-stream",
            },
        )
        listed = client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {"name": "list_categories", "arguments": {}},
            },
            headers={
                "Authorization": f"Bearer {read_token}",
                "Accept": "application/json, text/event-stream",
            },
        )
    assert unauthorized.status_code == 401
    assert response.status_code == 200
    assert response.json()["result"]["serverInfo"]["name"] == "ContextLoom"
    assert forbidden.status_code == 200
    assert forbidden.json()["result"]["isError"] is True
    assert created.status_code == 200
    assert created.json()["result"]["isError"] is False
    assert listed.status_code == 200
    listed_body = json.dumps(listed.json())
    assert "Created through MCP" in listed_body
    assert "Foreign secret" not in listed_body


@pytest.mark.django_db(transaction=True)
def test_mcp_edit_category_preserves_fields_and_moves_subtree(user, other_user):
    _, token = PersonalAccessToken.issue(
        owner=user, name="category editor", scopes=["categories:write"]
    )
    _, read_token = PersonalAccessToken.issue(
        owner=user, name="category reader", scopes=["categories:read"]
    )
    parent = Category.objects.create(owner=user, name="Parent")
    destination = Category.objects.create(owner=user, name="Destination")
    category = Category.objects.create(
        owner=user, parent=parent, name="Original", description="Keep this"
    )
    child = Category.objects.create(owner=user, parent=category, name="Child")
    foreign = Category.objects.create(owner=other_user, name="Foreign")

    with TestClient(create_mcp_application(), base_url="http://localhost") as client:
        renamed = _call_tool(
            client,
            token,
            "edit_category",
            {"category_id": category.pk, "name": "Renamed"},
        )
        moved = _call_tool(
            client,
            token,
            "edit_category",
            {"category_id": category.pk, "parent_id": destination.pk},
        )
        moved_to_root = _call_tool(
            client,
            token,
            "edit_category",
            {"category_id": category.pk, "move_to_root": True},
        )
        empty = _call_tool(client, token, "edit_category", {"category_id": category.pk})
        conflicting_move = _call_tool(
            client,
            token,
            "edit_category",
            {
                "category_id": category.pk,
                "parent_id": destination.pk,
                "move_to_root": True,
            },
        )
        cycle = _call_tool(
            client,
            token,
            "edit_category",
            {"category_id": category.pk, "parent_id": child.pk},
        )
        foreign_move = _call_tool(
            client,
            token,
            "edit_category",
            {"category_id": category.pk, "parent_id": foreign.pk},
        )
        foreign_edit = _call_tool(
            client,
            token,
            "edit_category",
            {"category_id": foreign.pk, "name": "Exposed"},
        )
        forbidden = _call_tool(
            client,
            read_token,
            "edit_category",
            {"category_id": category.pk, "name": "Not allowed"},
        )

    assert renamed.json()["result"]["isError"] is False
    assert moved.json()["result"]["isError"] is False
    assert moved_to_root.json()["result"]["isError"] is False
    assert empty.json()["result"]["isError"] is True
    assert conflicting_move.json()["result"]["isError"] is True
    assert cycle.json()["result"]["isError"] is True
    assert foreign_move.json()["result"]["isError"] is True
    assert foreign_edit.json()["result"]["isError"] is True
    assert forbidden.json()["result"]["isError"] is True
    category.refresh_from_db()
    child.refresh_from_db()
    foreign.refresh_from_db()
    assert category.name == "Renamed"
    assert category.description == "Keep this"
    assert category.parent is None
    assert child.parent == category
    assert foreign.name == "Foreign"


@pytest.mark.django_db(transaction=True)
def test_mcp_edit_memory_preserves_fields_and_enforces_scope_and_ownership(user, other_user):
    _, token = PersonalAccessToken.issue(
        owner=user, name="memory editor", scopes=["memories:write"]
    )
    _, read_token = PersonalAccessToken.issue(
        owner=user, name="memory reader", scopes=["memories:read"]
    )
    source = Category.objects.create(owner=user, name="Source")
    destination = Category.objects.create(owner=user, name="Destination")
    foreign = Category.objects.create(owner=other_user, name="Foreign")
    memory = Memory.objects.create(
        owner=user, category=source, content="Original content", priority=5
    )
    foreign_memory = Memory.objects.create(
        owner=other_user, category=foreign, content="Foreign content", priority=3
    )

    with TestClient(create_mcp_application(), base_url="http://localhost") as client:
        edited = _call_tool(
            client,
            token,
            "edit_memory",
            {"memory_id": memory.pk, "content": "Edited content"},
        )
        moved = _call_tool(
            client,
            token,
            "edit_memory",
            {"memory_id": memory.pk, "category_id": destination.pk},
        )
        empty = _call_tool(client, token, "edit_memory", {"memory_id": memory.pk})
        invalid_priority = _call_tool(
            client,
            token,
            "edit_memory",
            {"memory_id": memory.pk, "priority": 6},
        )
        foreign_move = _call_tool(
            client,
            token,
            "edit_memory",
            {"memory_id": memory.pk, "category_id": foreign.pk},
        )
        forbidden = _call_tool(
            client,
            read_token,
            "edit_memory",
            {"memory_id": memory.pk, "priority": 2},
        )
        foreign_edit = _call_tool(
            client,
            token,
            "edit_memory",
            {"memory_id": foreign_memory.pk, "content": "Exposed"},
        )

    assert edited.json()["result"]["isError"] is False
    assert moved.json()["result"]["isError"] is False
    assert empty.json()["result"]["isError"] is True
    assert invalid_priority.json()["result"]["isError"] is True
    assert foreign_move.json()["result"]["isError"] is True
    assert forbidden.json()["result"]["isError"] is True
    assert foreign_edit.json()["result"]["isError"] is True
    memory.refresh_from_db()
    foreign_memory.refresh_from_db()
    assert memory.content == "Edited content"
    assert memory.priority == 5
    assert memory.category == destination
    assert foreign_memory.content == "Foreign content"


@pytest.mark.django_db(transaction=True)
def test_mcp_lists_edit_tools(user):
    _, token = PersonalAccessToken.issue(owner=user, name="reader", scopes=["categories:read"])
    with TestClient(create_mcp_application(), base_url="http://localhost") as client:
        response = client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 11, "method": "tools/list", "params": {}},
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json, text/event-stream",
            },
        )

    assert response.status_code == 200
    tools = {tool["name"]: tool for tool in response.json()["result"]["tools"]}
    assert "edit_category" in tools
    assert "edit_memory" in tools
    assert "update_category" in tools
    assert "update_memory" in tools
    assert tools["edit_category"]["inputSchema"]["required"] == ["category_id"]
    assert tools["edit_memory"]["inputSchema"]["required"] == ["memory_id"]
