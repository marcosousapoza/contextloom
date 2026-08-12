import pytest
from django.contrib import admin
from django.contrib.auth.models import Permission
from django.core.management import call_command
from django.test import Client
from django.urls import reverse

from contextloom.accounts.models import PersonalAccessToken
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
def test_public_registration_does_not_exist(client):
    assert client.get("/accounts/register/").status_code == 404


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


@pytest.mark.django_db
def test_bootstrap_admin_must_change_default_password(client):
    call_command("create_initial_admin")
    response = client.post(reverse("accounts:login"), {"username": "admin", "password": "admin"})
    assert response.status_code == 302
    assert response.url == reverse("accounts:password_change")
    assert client.get(reverse("knowledge:home")).url == reverse("accounts:password_change")
    assert client.get(reverse("admin:index")).url == reverse("accounts:password_change")

    response = client.post(
        reverse("accounts:password_change"),
        {
            "old_password": "admin",
            "new_password1": "a-new-long-random-password-42",
            "new_password2": "a-new-long-random-password-42",
        },
    )
    assert response.status_code == 302
    assert response.url == reverse("knowledge:home")
    user = client.session.get("_auth_user_id")
    assert user
    from contextloom.accounts.models import User

    administrator = User.objects.get(pk=user)
    assert administrator.password_change_required is False
    assert administrator.check_password("a-new-long-random-password-42")


@pytest.mark.django_db
def test_bootstrap_admin_creation_is_idempotent(capsys):
    call_command("create_initial_admin")
    call_command("create_initial_admin")
    assert "Administrator already exists" in capsys.readouterr().out


@pytest.mark.django_db
def test_admin_created_user_requires_password_change(client):
    from contextloom.accounts.admin import ContextLoomUserAdmin
    from contextloom.accounts.models import User

    administrator = User.objects.create_superuser(
        username="admin", email="admin@example.com", password="administrator-password"
    )
    request = type("Request", (), {"user": administrator})()
    account = User(username="new-user", email="new-user@example.com")
    account.set_password("assigned-password")
    ContextLoomUserAdmin(User, admin.site).save_model(request, account, form=None, change=False)
    assert account.password_change_required is True

    response = client.post(
        reverse("accounts:login"),
        {"username": account.username, "password": "assigned-password"},
    )
    assert response.url == reverse("accounts:password_change")
