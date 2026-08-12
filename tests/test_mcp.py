import json

import pytest
from starlette.testclient import TestClient

from contextloom.accounts.models import PersonalAccessToken
from contextloom.knowledge.models import Category
from contextloom.mcp_integration.server import mcp_application

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


@pytest.mark.django_db(transaction=True)
def test_mcp_streamable_http_auth_scopes_and_tenant_isolation(user, other_user):
    _, read_token = PersonalAccessToken.issue(owner=user, name="reader", scopes=["categories:read"])
    _, write_token = PersonalAccessToken.issue(
        owner=user, name="writer", scopes=["categories:write"]
    )
    Category.objects.create(owner=other_user, name="Foreign secret")
    with TestClient(mcp_application, base_url="http://localhost") as client:
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
