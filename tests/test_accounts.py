import pytest
from django.contrib import admin
from django.contrib.auth.models import Permission
from django.test import Client
from django.urls import reverse

from contextloom.accounts.models import ApplicationSettings, PersonalAccessToken
from contextloom.accounts.services import authenticate_token
from contextloom.knowledge.models import Archive, Category, ImportJob, Memory


@pytest.mark.django_db
def test_login_accepts_email_and_uses_argon2(user):
    response = Client().post(
        reverse("accounts:login"),
        {"username": user.email, "password": "correct horse battery staple"},
    )
    assert response.status_code == 302
    user.refresh_from_db()
    assert user.password.startswith("argon2$")


@pytest.mark.django_db
def test_state_changing_form_requires_csrf(user):
    client = Client(enforce_csrf_checks=True)
    client.force_login(user)
    response = client.post(reverse("knowledge:category_create"), {"name": "Private"})
    assert response.status_code == 403
    assert not Category.objects.exists()


@pytest.mark.django_db
def test_registration_is_database_configurable(client):
    assert client.get(reverse("accounts:register")).status_code == 404
    settings = ApplicationSettings.load()
    settings.registration_enabled = True
    settings.save()
    assert client.get(reverse("accounts:register")).status_code == 200


@pytest.mark.django_db
def test_login_throttling(user, settings):
    settings.CONTEXTLOOM_LOGIN_ATTEMPTS = 2
    client = Client()
    url = reverse("accounts:login")
    for _ in range(2):
        client.post(url, {"username": user.username, "password": "wrong"})
    response = client.post(
        url, {"username": user.username, "password": "correct horse battery staple"}
    )
    assert response.status_code == 200
    assert "Too many login attempts" in response.content.decode()


@pytest.mark.django_db
def test_tokens_are_hashed_scoped_and_disabled_with_owner(user):
    token, raw = PersonalAccessToken.issue(owner=user, name="MCP", scopes=["categories:read"])
    assert raw not in token.token_hash
    assert authenticate_token(raw, ["categories:read"]) == token
    assert authenticate_token(raw, ["categories:write"]) is None
    user.is_active = False
    user.save()
    assert authenticate_token(raw) is None


def test_admin_does_not_register_user_content():
    registered = admin.site._registry
    assert Category not in registered
    assert Memory not in registered
    assert Archive not in registered
    assert ImportJob not in registered
    assert PersonalAccessToken not in registered


@pytest.mark.django_db
def test_non_staff_cannot_access_admin(client, user):
    client.force_login(user)
    response = client.get(reverse("admin:index"))
    assert response.status_code == 302
    assert response.url.startswith(reverse("admin:login"))


@pytest.mark.django_db
def test_staff_requires_explicit_account_permissions(client, user):
    user.is_staff = True
    user.save()
    client.force_login(user)
    assert client.get(reverse("admin:index")).status_code == 200
    assert client.get(reverse("admin:accounts_user_changelist")).status_code == 403

    user.user_permissions.add(Permission.objects.get(codename="view_user"))
    assert client.get(reverse("admin:accounts_user_changelist")).status_code == 200


@pytest.mark.django_db
def test_superuser_can_manage_accounts_but_not_content(client):
    from contextloom.accounts.models import User

    administrator = User.objects.create_superuser(
        username="admin", email="admin@example.com", password="administrator-password"
    )
    client.force_login(administrator)
    response = client.get(reverse("admin:accounts_user_changelist"))
    assert response.status_code == 200
    body = client.get(reverse("admin:index")).content.decode()
    assert "Categories" not in body
    assert "Memories" not in body
    assert "Archives" not in body
