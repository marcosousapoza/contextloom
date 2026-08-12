import pytest

from contextloom.accounts.models import User


@pytest.fixture
def user(db):
    return User.objects.create_user(
        username="alice", email="alice@example.com", password="correct horse battery staple"
    )


@pytest.fixture
def other_user(db):
    return User.objects.create_user(
        username="bob", email="bob@example.com", password="correct horse battery staple"
    )


@pytest.fixture(autouse=True)
def collected_static_root(tmp_path, settings):
    static_root = tmp_path / "static"
    static_root.mkdir()
    settings.STATIC_ROOT = static_root
