from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from contextloom.knowledge.exceptions import KnowledgeError
from contextloom.knowledge.forms import CategoryForm, MemoryForm
from contextloom.knowledge.models import Archive, Category, Memory
from contextloom.knowledge.services import (
    archive_category,
    archives_for,
    categories_for,
    memories_for,
    restore_archive,
    save_category,
    save_memory,
)


@login_required
def home(request):
    categories = list(categories_for(request.user).annotate(direct_memory_count=Count("memories")))
    categories_by_id = {category.pk: category for category in categories}
    children_by_parent = {}
    for category in categories:
        parent_id = category.parent_id if category.parent_id in categories_by_id else None
        children_by_parent.setdefault(parent_id, []).append(category)

    def prepare_category(category, path=()):
        category.category_path = (*path, category.name)
        category.tree_children = children_by_parent.get(category.pk, [])
        category.branch_memory_count = category.direct_memory_count + sum(
            prepare_category(child, category.category_path) for child in category.tree_children
        )
        return category.branch_memory_count

    root_categories = children_by_parent.get(None, [])
    for category in root_categories:
        category.tree_open = True
        prepare_category(category)

    selected_category = None
    category_id = request.GET.get("category")
    if category_id:
        try:
            selected_category = categories_by_id[int(category_id)]
        except (KeyError, TypeError, ValueError) as exc:
            raise Http404 from exc
        selected_category.is_selected = True
        current = selected_category
        while current:
            current.tree_open = True
            current = categories_by_id.get(current.parent_id)

    query = request.GET.get("q", "").strip()
    search_scope = request.GET.get("scope", "all")
    memory_query = memories_for(request.user).order_by("-updated_at", "-id")

    if selected_category and (not query or search_scope == "category"):
        branch_ids = []
        pending = [selected_category]
        while pending:
            category = pending.pop()
            branch_ids.append(category.pk)
            pending.extend(category.tree_children)
        memory_query = memory_query.filter(category_id__in=branch_ids)

    if query:
        memory_query = memory_query.filter(content__icontains=query)
        view_mode = "search"
    elif selected_category:
        view_mode = "category"
    elif request.GET.get("view") == "all":
        view_mode = "all"
    else:
        view_mode = "recent"

    page_obj = None
    if view_mode == "recent":
        displayed_memories = list(memory_query[:8])
    else:
        page_obj = Paginator(memory_query, 20).get_page(request.GET.get("page"))
        displayed_memories = list(page_obj.object_list)

    for memory in displayed_memories:
        category = categories_by_id.get(memory.category_id)
        memory.category_path = (
            " / ".join(category.category_path) if category else memory.category.name
        )

    query_parameters = request.GET.copy()
    query_parameters.pop("page", None)
    pagination_query = query_parameters.urlencode()

    return render(
        request,
        "knowledge/home.html",
        {
            "categories": categories,
            "root_categories": root_categories,
            "selected_category": selected_category,
            "memories": displayed_memories,
            "page_obj": page_obj,
            "pagination_query": pagination_query,
            "query": query,
            "search_scope": search_scope,
            "view_mode": view_mode,
            "total_memory_count": sum(category.direct_memory_count for category in categories),
        },
    )


@login_required
def category_edit(request, category_id=None):
    category = None
    if category_id:
        category = get_object_or_404(Category, owner=request.user, pk=category_id)
    initial = {"parent": request.GET.get("parent")} if not category else None
    form = CategoryForm(
        request.POST or None, instance=category, owner=request.user, initial=initial
    )
    if request.method == "POST" and form.is_valid():
        try:
            save_category(owner=request.user, category=category, **form.cleaned_data)
        except KnowledgeError as exc:
            form.add_error(None, str(exc))
        else:
            messages.success(request, "Category saved.")
            return redirect("knowledge:home")
    return render(request, "knowledge/form.html", {"form": form, "title": "Category"})


@login_required
@require_POST
def category_archive(request, category_id):
    try:
        archive_category(owner=request.user, category_id=category_id)
    except Category.DoesNotExist as exc:
        raise Http404 from exc
    messages.success(request, "Category archived.")
    return redirect("knowledge:home")


@login_required
def memory_edit(request, memory_id=None):
    memory = None
    if memory_id:
        memory = get_object_or_404(Memory, owner=request.user, pk=memory_id)
    initial = {"category": request.GET.get("category")} if not memory else None
    form = MemoryForm(request.POST or None, instance=memory, owner=request.user, initial=initial)
    if request.method == "POST" and form.is_valid():
        try:
            save_memory(owner=request.user, memory=memory, **form.cleaned_data)
        except KnowledgeError as exc:
            form.add_error(None, str(exc))
        else:
            messages.success(request, "Memory saved.")
            return redirect("knowledge:home")
    return render(request, "knowledge/form.html", {"form": form, "title": "Memory"})


@login_required
@require_POST
def memory_delete(request, memory_id):
    deleted, _ = Memory.objects.filter(owner=request.user, pk=memory_id).delete()
    if not deleted:
        raise Http404
    messages.success(request, "Memory deleted.")
    return redirect("knowledge:home")


@login_required
def archives(request):
    return render(request, "knowledge/archives.html", {"archives": archives_for(request.user)})


@login_required
@require_POST
def archive_restore(request, archive_id):
    try:
        restore_archive(owner=request.user, archive_id=archive_id)
    except Archive.DoesNotExist as exc:
        raise Http404 from exc
    messages.success(request, "Archive restored.")
    return redirect("knowledge:archives")


@login_required
@require_POST
def archive_delete(request, archive_id):
    deleted, _ = archives_for(request.user).filter(pk=archive_id).delete()
    if not deleted:
        raise Http404
    messages.success(request, "Archive permanently deleted.")
    return redirect("knowledge:archives")
