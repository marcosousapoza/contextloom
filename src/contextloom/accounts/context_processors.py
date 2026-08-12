from django.conf import settings


def application_settings(request):
    return {"contextloom_version": settings.CONTEXTLOOM_VERSION}
