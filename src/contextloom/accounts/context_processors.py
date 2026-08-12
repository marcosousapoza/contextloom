from django.conf import settings
from django.db import DatabaseError

from contextloom.accounts.models import ApplicationSettings


def application_settings(request):
    enabled = settings.CONTEXTLOOM_REGISTRATION_ENABLED
    try:
        enabled = ApplicationSettings.load().registration_enabled
    except DatabaseError:
        pass
    return {"registration_enabled": enabled, "contextloom_version": settings.CONTEXTLOOM_VERSION}
