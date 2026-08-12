from django.urls import path

from contextloom.knowledge import import_export, views

app_name = "knowledge"
urlpatterns = [
    path("", views.home, name="home"),
    path("categories/new/", views.category_edit, name="category_create"),
    path("categories/<int:category_id>/edit/", views.category_edit, name="category_edit"),
    path("categories/<int:category_id>/archive/", views.category_archive, name="category_archive"),
    path("memories/new/", views.memory_edit, name="memory_create"),
    path("memories/<int:memory_id>/edit/", views.memory_edit, name="memory_edit"),
    path("memories/<int:memory_id>/delete/", views.memory_delete, name="memory_delete"),
    path("archives/", views.archives, name="archives"),
    path("archives/<int:archive_id>/restore/", views.archive_restore, name="archive_restore"),
    path("archives/<int:archive_id>/delete/", views.archive_delete, name="archive_delete"),
    path("data/export/", import_export.export_data, name="export"),
    path("data/import/", import_export.import_upload, name="import"),
    path("data/import/<uuid:job_id>/confirm/", import_export.import_confirm, name="import_confirm"),
]
