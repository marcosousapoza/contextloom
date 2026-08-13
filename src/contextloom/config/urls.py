from django.contrib import admin
from django.urls import include, path
from oauth2_provider.urls import dcr_urlpatterns, metadata_urlpatterns

from contextloom.config.views import health, ready

urlpatterns = [
    path("health", health, name="health"),
    path("ready", ready, name="ready"),
    path("accounts/", include("contextloom.accounts.urls")),
    path("admin/", admin.site.urls),
    path("", include("contextloom.knowledge.urls")),
    path("o/", include("oauth2_provider.urls")),
]

urlpatterns += [
    path("", include((metadata_urlpatterns, "oauth2_provider"), namespace="oauth2_metadata")),
    path("", include((dcr_urlpatterns, "oauth2_provider"), namespace="oauth2_dcr")),
]
