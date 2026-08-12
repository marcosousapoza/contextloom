import pytest
from django.urls import reverse

from contextloom.knowledge.exceptions import KnowledgeError
from contextloom.knowledge.models import Archive, Category, Memory
from contextloom.knowledge.services import archive_category, restore_archive, save_category


@pytest.mark.django_db
def test_web_objects_are_tenant_isolated(client, user, other_user):
    foreign_category = Category.objects.create(owner=other_user, name="Foreign")
    foreign_memory = Memory.objects.create(
        owner=other_user, category=foreign_category, content="Secret", priority=5
    )
    client.force_login(user)
    assert (
        client.get(reverse("knowledge:category_edit", args=[foreign_category.pk])).status_code
        == 404
    )
    assert client.get(reverse("knowledge:memory_edit", args=[foreign_memory.pk])).status_code == 404
    assert (
        client.post(reverse("knowledge:category_archive", args=[foreign_category.pk])).status_code
        == 404
    )
    assert (
        client.post(reverse("knowledge:memory_delete", args=[foreign_memory.pk])).status_code == 404
    )
    assert Category.objects.filter(pk=foreign_category.pk).exists()
    assert Memory.objects.filter(pk=foreign_memory.pk).exists()


@pytest.mark.django_db
def test_service_rejects_cross_owner_parent(user, other_user):
    parent = Category.objects.create(owner=other_user, name="Foreign")
    with pytest.raises(KnowledgeError):
        save_category(owner=user, name="Child", parent=parent)


@pytest.mark.django_db
def test_category_archive_is_complete_and_restorable(user):
    parent = Category.objects.create(owner=user, name="Parent", description="Root")
    child = Category.objects.create(owner=user, parent=parent, name="Child")
    Memory.objects.create(owner=user, category=child, content="Line one\nLine two", priority=4)
    archived = archive_category(owner=user, category_id=parent.pk)
    assert not Category.objects.filter(owner=user).exists()
    assert len(archived.snapshot["categories"]) == 2
    assert len(archived.snapshot["memories"]) == 1
    restore_archive(owner=user, archive_id=archived.pk)
    restored = Category.objects.get(owner=user, name="Child")
    assert restored.parent.name == "Parent"
    assert restored.memories.get().content == "Line one\nLine two"
    assert not Archive.objects.filter(owner=user).exists()
