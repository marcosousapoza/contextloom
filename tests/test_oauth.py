import base64
import hashlib
import json
import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import pytest
from django.urls import reverse
from oauth2_provider.models import AccessToken as OAuthAccessToken
from oauth2_provider.models import Application
from starlette.testclient import TestClient

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
MCP_RESOURCE = "http://localhost:8000/mcp"


def _pkce_challenge(verifier):
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


@pytest.mark.django_db(transaction=True)
class TestOAuthDiscovery:
    def test_authorization_server_metadata(self, client):
        response = client.get("/.well-known/oauth-authorization-server")
        assert response.status_code == 200
        data = response.json()
        assert "issuer" in data
        assert data["issuer"].endswith("/mcp") is False
        assert "authorization_endpoint" in data
        assert "token_endpoint" in data
        assert "registration_endpoint" in data
        assert "code" in data["response_types_supported"]
        assert "authorization_code" in data["grant_types_supported"]
        assert "S256" in data["code_challenge_methods_supported"]
        assert "implicit" not in data["grant_types_supported"]
        assert "password" not in data["grant_types_supported"]

    def test_protected_resource_metadata(self, client):
        response = client.get("/.well-known/oauth-protected-resource/mcp")
        assert response.status_code == 200
        data = response.json()
        assert data["resource"].endswith("/mcp")
        assert "authorization_servers" in data
        assert "bearer_methods_supported" in data


@pytest.mark.django_db(transaction=True)
class TestDynamicClientRegistration:
    def test_dcr_create_public_client(self, client):
        response = client.post(
            "/register/",
            content_type="application/json",
            data=json.dumps(
                {
                    "client_name": "Test MCP Client",
                    "redirect_uris": ["http://192.168.1.20:8080/callback"],
                    "grant_types": ["authorization_code"],
                    "token_endpoint_auth_method": "none",
                }
            ),
        )
        assert response.status_code == 201
        data = response.json()
        assert "client_id" in data
        assert data["client_name"] == "Test MCP Client"
        assert data["token_endpoint_auth_method"] == "none"
        assert "registration_access_token" in data

    def test_dcr_requires_redirect_uris(self, client):
        response = client.post(
            "/register/",
            content_type="application/json",
            data=json.dumps(
                {
                    "client_name": "Bad Client",
                    "grant_types": ["authorization_code"],
                }
            ),
        )
        assert response.status_code == 400


@pytest.mark.django_db(transaction=True)
class TestAuthorizationCodeFlow:
    @pytest.fixture
    def oauth_client(self, user):
        return Application.objects.create(
            name="Test Client",
            user=user,
            client_type=Application.CLIENT_PUBLIC,
            authorization_grant_type=Application.GRANT_AUTHORIZATION_CODE,
            redirect_uris="http://127.0.0.1:8080/callback",
        )

    def test_authorization_request_requires_login(self, client, oauth_client):
        verifier = secrets.token_urlsafe(48)
        response = client.get(
            "/o/authorize/",
            {
                "client_id": oauth_client.client_id,
                "response_type": "code",
                "redirect_uri": "http://127.0.0.1:8080/callback",
                "scope": "categories:read memories:read",
                "code_challenge": _pkce_challenge(verifier),
                "code_challenge_method": "S256",
                "resource": MCP_RESOURCE,
            },
        )
        assert response.status_code == 302
        assert response.url.startswith(reverse("accounts:login"))

    def test_full_pkce_flow_issues_token_for_mcp(self, user, client, oauth_client):
        client.force_login(user)
        verifier = secrets.token_urlsafe(48)
        authorization = {
            "client_id": oauth_client.client_id,
            "response_type": "code",
            "redirect_uri": "http://127.0.0.1:8080/callback",
            "scope": "categories:read memories:read",
            "code_challenge": _pkce_challenge(verifier),
            "code_challenge_method": "S256",
            "resource": MCP_RESOURCE,
        }

        consent_response = client.get("/o/authorize/", authorization)
        assert consent_response.status_code == 200
        assert "Test Client" in consent_response.content.decode()
        assert "categories:read" in consent_response.content.decode()

        authorization["allow"] = "Authorize"
        authorization_response = client.post("/o/authorize/", authorization)
        assert authorization_response.status_code == 302
        code = parse_qs(urlparse(authorization_response.url).query)["code"][0]

        token_response = client.post(
            "/o/token/",
            {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": "http://127.0.0.1:8080/callback",
                "client_id": oauth_client.client_id,
                "code_verifier": verifier,
                "resource": MCP_RESOURCE,
            },
        )
        assert token_response.status_code == 200
        access_token = token_response.json()["access_token"]
        stored_token = OAuthAccessToken.objects.get(application=oauth_client)
        assert stored_token.resource == [MCP_RESOURCE]

        with TestClient(create_mcp_application(), base_url="http://localhost") as mcp_client:
            response = mcp_client.post(
                "/mcp",
                json=INITIALIZE,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/json, text/event-stream",
                },
            )
        assert response.status_code == 200
        assert response.json()["result"]["serverInfo"]["name"] == "ContextLoom"

    def test_token_exchange_rejects_wrong_verifier(self, user, client, oauth_client):
        client.force_login(user)
        verifier = secrets.token_urlsafe(48)
        authorization = {
            "client_id": oauth_client.client_id,
            "response_type": "code",
            "redirect_uri": "http://127.0.0.1:8080/callback",
            "scope": "categories:read",
            "code_challenge": _pkce_challenge(verifier),
            "code_challenge_method": "S256",
            "resource": MCP_RESOURCE,
            "allow": "Authorize",
        }
        authorization_response = client.post("/o/authorize/", authorization)
        code = parse_qs(urlparse(authorization_response.url).query)["code"][0]

        token_response = client.post(
            "/o/token/",
            {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": "http://127.0.0.1:8080/callback",
                "client_id": oauth_client.client_id,
                "code_verifier": secrets.token_urlsafe(48),
                "resource": MCP_RESOURCE,
            },
        )
        assert token_response.status_code == 400
        assert token_response.json()["error"] == "invalid_grant"


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("resources", [[], ["http://localhost:8000/other"]])
def test_mcp_rejects_token_without_exact_resource(user, resources):
    app = Application.objects.create(
        name="MCP Test Client",
        user=user,
        client_type=Application.CLIENT_PUBLIC,
        authorization_grant_type=Application.GRANT_AUTHORIZATION_CODE,
        redirect_uris="http://127.0.0.1:8080/callback",
    )
    token_value = "oauth_test_token_" + secrets.token_urlsafe(16)
    token = OAuthAccessToken.objects.create(
        user=user,
        application=app,
        token=token_value,
        expires=datetime.now(UTC) + timedelta(hours=1),
        scope="categories:read",
        resource=resources,
    )
    assert token.resource == resources

    with TestClient(create_mcp_application(), base_url="http://localhost") as mcp_client:
        response = mcp_client.post(
            "/mcp",
            json=INITIALIZE,
            headers={
                "Authorization": f"Bearer {token_value}",
                "Accept": "application/json, text/event-stream",
            },
        )
    assert response.status_code == 401
