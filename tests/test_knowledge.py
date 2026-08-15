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


@pytest.mark.django_db
def test_home_builds_recursive_branch_counts_and_limits_recent_memories(client, user):
    root = Category.objects.create(owner=user, name="Root")
    child = Category.objects.create(owner=user, parent=root, name="Child")
    grandchild = Category.objects.create(owner=user, parent=child, name="Grandchild")
    Memory.objects.create(owner=user, category=root, content="At root")
    Memory.objects.create(owner=user, category=child, content="At child")
    for index in range(9):
        Memory.objects.create(owner=user, category=grandchild, content=f"Recent {index}")

    client.force_login(user)
    response = client.get(reverse("knowledge:home"))

    assert response.status_code == 200
    root_context = response.context["root_categories"][0]
    assert root_context.branch_memory_count == 11
    assert root_context.direct_memory_count == 1
    assert root_context.tree_children[0].tree_children[0] == grandchild
    assert len(response.context["memories"]) == 8
    assert response.context["view_mode"] == "recent"


@pytest.mark.django_db
def test_category_branch_is_paginated_and_includes_all_descendants(client, user):
    root = Category.objects.create(owner=user, name="Root")
    child = Category.objects.create(owner=user, parent=root, name="Child")
    sibling = Category.objects.create(owner=user, name="Sibling")
    Memory.objects.create(owner=user, category=root, content="Direct memory")
    for index in range(22):
        Memory.objects.create(owner=user, category=child, content=f"Child memory {index}")
    Memory.objects.create(owner=user, category=sibling, content="Outside branch")

    client.force_login(user)
    response = client.get(reverse("knowledge:home"), {"category": root.pk})

    assert response.status_code == 200
    assert response.context["page_obj"].paginator.count == 23
    assert len(response.context["memories"]) == 20
    assert all(memory.category_id != sibling.pk for memory in response.context["memories"])


@pytest.mark.django_db
def test_memory_search_is_owner_scoped_and_can_be_limited_to_a_branch(client, user, other_user):
    selected = Category.objects.create(owner=user, name="Selected")
    elsewhere = Category.objects.create(owner=user, name="Elsewhere")
    foreign = Category.objects.create(owner=other_user, name="Foreign")
    Memory.objects.create(owner=user, category=selected, content="A searchable branch memory")
    Memory.objects.create(owner=user, category=elsewhere, content="A searchable global memory")
    Memory.objects.create(owner=other_user, category=foreign, content="A searchable secret")

    client.force_login(user)
    global_response = client.get(reverse("knowledge:home"), {"q": "searchable"})
    branch_response = client.get(
        reverse("knowledge:home"),
        {"q": "searchable", "category": selected.pk, "scope": "category"},
    )

    assert global_response.context["page_obj"].paginator.count == 2
    assert branch_response.context["page_obj"].paginator.count == 1
    assert branch_response.context["memories"][0].category == selected
