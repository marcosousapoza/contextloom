from django.contrib import admin
from django.urls import include, path

from contextloom.config.views import health, ready

urlpatterns = [
    path("health", health, name="health"),
    path("ready", ready, name="ready"),
    path("accounts/", include("contextloom.accounts.urls")),
    path("admin/", admin.site.urls),
    path("", include("contextloom.knowledge.urls")),
]
