from django.db import IntegrityError, transaction
from django.db.models import Prefetch

from contextloom.knowledge.exceptions import KnowledgeError
from contextloom.knowledge.models import Archive, Category, Memory


def categories_for(owner):
    return Category.objects.filter(owner=owner).select_related("parent")


def memories_for(owner):
    return Memory.objects.filter(owner=owner).select_related("category")


def archives_for(owner):
    return Archive.objects.filter(owner=owner)


def _check_parent(owner, parent, category=None):
    if parent is None:
        return
    if parent.owner_id != owner.id:
        raise KnowledgeError("The selected parent category is not available.")
    current = parent
    seen = set()
    while current:
        if current.pk in seen:
            raise KnowledgeError("The category hierarchy is invalid.")
        seen.add(current.pk)
        if category and current.pk == category.pk:
            raise KnowledgeError("A category cannot be moved inside itself.")
        current = current.parent


def save_category(*, owner, name, description="", parent=None, category=None):
    _check_parent(owner, parent, category)
    name = name.strip()
    if not name or len(name) > 200:
        raise KnowledgeError("Category names must contain 1 to 200 characters.")
    target = category or Category(owner=owner)
    if target.owner_id != owner.id:
        raise KnowledgeError("Category not found.")
    target.name = name
    target.description = description
    target.parent = parent
    try:
        with transaction.atomic():
            target.save()
    except IntegrityError as exc:
        raise KnowledgeError("A category with this name already exists here.") from exc
    return target


def save_memory(*, owner, category, content, priority, memory=None):
    if category.owner_id != owner.id:
        raise KnowledgeError("The selected category is not available.")
    if not isinstance(content, str) or not content.strip():
        raise KnowledgeError("Memory content cannot be empty.")
    if not isinstance(priority, int) or not 1 <= priority <= 5:
        raise KnowledgeError("Memory priority must be between 1 and 5.")
    target = memory or Memory(owner=owner)
    if target.owner_id != owner.id:
        raise KnowledgeError("Memory not found.")
    target.category = category
    target.content = content
    target.priority = priority
    target.save()
    return target


def _snapshot_category(category):
    categories = []
    memories = []

    def visit(item, parent_key=None):
        key = str(item.pk)
        categories.append(
            {
                "key": key,
                "parent_key": parent_key,
                "name": item.name,
                "description": item.description,
                "created_at": item.created_at.isoformat(),
                "updated_at": item.updated_at.isoformat(),
            }
        )
        for memory in item.memories.all():
            memories.append(
                {
                    "category_key": key,
                    "content": memory.content,
                    "priority": memory.priority,
                    "created_at": memory.created_at.isoformat(),
                    "updated_at": memory.updated_at.isoformat(),
                }
            )
        for child in item.children.all():
            visit(child, key)

    visit(category)
    return {"version": 1, "categories": categories, "memories": memories}


@transaction.atomic
def archive_category(*, owner, category_id):
    category = (
        Category.objects.filter(owner=owner)
        .prefetch_related(
            Prefetch("children", queryset=Category.objects.order_by("name")), "memories"
        )
        .get(pk=category_id)
    )
    archive = Archive.objects.create(
        owner=owner, name=category.name, snapshot=_snapshot_category(category)
    )
    category.delete()
    return archive


def _available_name(owner, parent, name):
    candidate = name
    number = 2
    while Category.objects.filter(owner=owner, parent=parent, name=candidate).exists():
        candidate = f"{name} ({number})"
        number += 1
    return candidate


@transaction.atomic
def restore_archive(*, owner, archive_id):
    archive = Archive.objects.select_for_update().get(owner=owner, pk=archive_id)
    snapshot = archive.snapshot
    created = {}
    pending = list(snapshot["categories"])
    while pending:
        progress = False
        for row in pending[:]:
            parent_key = row.get("parent_key")
            if parent_key and parent_key not in created:
                continue
            parent = created.get(parent_key)
            name = _available_name(owner, parent, row["name"])
            created[row["key"]] = Category.objects.create(
                owner=owner, parent=parent, name=name, description=row.get("description", "")
            )
            pending.remove(row)
            progress = True
        if not progress:
            raise KnowledgeError("This archive contains an invalid category hierarchy.")
    restored_memories = Memory.objects.bulk_create(
        [
            Memory(
                owner=owner,
                category=created[row["category_key"]],
                content=row["content"],
                priority=row["priority"],
            )
            for row in snapshot["memories"]
        ]
    )
    for memory, row in zip(restored_memories, snapshot["memories"], strict=True):
        Memory.objects.filter(pk=memory.pk).update(
            created_at=row["created_at"], updated_at=row["updated_at"]
        )
    archive.delete()
