import hashlib

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from contextloom.accounts.models import LoginAttempt, PersonalAccessToken


def login_throttle_key(request, identifier):
    address = request.META.get("REMOTE_ADDR", "unknown")
    return hashlib.sha256(f"{address}:{identifier.lower()}".encode()).hexdigest()


def login_is_throttled(key):
    cutoff = timezone.now() - timezone.timedelta(seconds=settings.CONTEXTLOOM_LOGIN_WINDOW_SECONDS)
    LoginAttempt.objects.filter(attempted_at__lt=cutoff).delete()
    return (
        LoginAttempt.objects.filter(key=key, attempted_at__gte=cutoff).count()
        >= settings.CONTEXTLOOM_LOGIN_ATTEMPTS
    )


def record_login_failure(key):
    LoginAttempt.objects.create(key=key)


def clear_login_failures(key):
    LoginAttempt.objects.filter(key=key).delete()


@transaction.atomic
def authenticate_token(raw_token, required_scopes=()):
    if not raw_token or len(raw_token) > 200:
        return None
    digest = PersonalAccessToken.hash_token(raw_token)
    token = (
        PersonalAccessToken.objects.select_related("owner")
        .select_for_update()
        .filter(token_hash=digest)
        .first()
    )
    if not token or not token.is_valid or not set(required_scopes).issubset(token.scopes):
        return None
    token.last_used_at = timezone.now()
    token.save(update_fields=["last_used_at"])
    return token
