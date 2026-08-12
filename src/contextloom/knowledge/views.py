from django.contrib import messages
from django.contrib.auth.decorators import login_required
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
    categories = categories_for(request.user)
    return render(
        request,
        "knowledge/home.html",
        {
            "categories": categories,
            "root_categories": categories.filter(parent__isnull=True),
            "memories": memories_for(request.user),
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
