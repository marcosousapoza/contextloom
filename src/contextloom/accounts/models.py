import hashlib
import secrets

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.validators import RegexValidator
from django.db import models
from django.db.models.functions import Lower
from django.utils import timezone


class User(AbstractUser):
    email = models.EmailField("email address", unique=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(Lower("email"), name="unique_user_email_case_insensitive")
        ]

    def save(self, *args, **kwargs):
        self.email = self.email.strip().lower()
        super().save(*args, **kwargs)


class ApplicationSettings(models.Model):
    registration_enabled = models.BooleanField(default=False)

    class Meta:
        verbose_name_plural = "application settings"

    def __str__(self):
        return "Application settings"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        return cls.objects.get_or_create(
            pk=1,
            defaults={"registration_enabled": settings.CONTEXTLOOM_REGISTRATION_ENABLED},
        )[0]


class LoginAttempt(models.Model):
    key = models.CharField(max_length=64, db_index=True)
    attempted_at = models.DateTimeField(default=timezone.now, db_index=True)

    def __str__(self):
        return self.key


class PersonalAccessToken(models.Model):
    SCOPE_CHOICES = [
        ("categories:read", "Read categories"),
        ("categories:write", "Write categories"),
        ("memories:read", "Read memories"),
        ("memories:write", "Write memories"),
    ]

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    prefix = models.CharField(max_length=12, db_index=True)
    token_hash = models.CharField(
        max_length=64,
        unique=True,
        validators=[RegexValidator(r"^[0-9a-f]{64}$")],
    )
    scopes = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name

    @staticmethod
    def hash_token(raw_token):
        value = f"{settings.SECRET_KEY}:{raw_token}".encode()
        return hashlib.sha256(value).hexdigest()

    @classmethod
    def issue(cls, *, owner, name, scopes, expires_at=None):
        raw_token = f"clm_{secrets.token_urlsafe(32)}"
        token = cls.objects.create(
            owner=owner,
            name=name,
            prefix=raw_token[:12],
            token_hash=cls.hash_token(raw_token),
            scopes=sorted(set(scopes)),
            expires_at=expires_at,
        )
        return token, raw_token

    @property
    def is_valid(self):
        return (
            self.owner.is_active
            and self.revoked_at is None
            and (self.expires_at is None or self.expires_at > timezone.now())
        )
