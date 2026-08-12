from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.http import Http404
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from contextloom.accounts.forms import LoginForm, ProfileForm, RegistrationForm, TokenForm
from contextloom.accounts.models import ApplicationSettings, PersonalAccessToken
from contextloom.accounts.services import (
    clear_login_failures,
    login_is_throttled,
    login_throttle_key,
    record_login_failure,
)


class ThrottledLoginView(LoginView):
    authentication_form = LoginForm
    template_name = "accounts/login.html"

    def post(self, request, *args, **kwargs):
        identifier = request.POST.get("username", "")
        self.throttle_key = login_throttle_key(request, identifier)
        if login_is_throttled(self.throttle_key):
            form = self.get_form()
            form.add_error(None, "Too many login attempts. Try again later.")
            return self.form_invalid(form)
        return super().post(request, *args, **kwargs)

    def form_invalid(self, form):
        record_login_failure(self.throttle_key)
        return super().form_invalid(form)

    def form_valid(self, form):
        clear_login_failures(self.throttle_key)
        return super().form_valid(form)


def register(request):
    if not ApplicationSettings.load().registration_enabled:
        raise Http404
    form = RegistrationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        return redirect("knowledge:home")
    return render(request, "accounts/register.html", {"form": form})


@login_required
def settings_view(request):
    profile_form = ProfileForm(request.POST or None, instance=request.user)
    token_form = TokenForm(prefix="token")
    if request.method == "POST" and "save_profile" in request.POST and profile_form.is_valid():
        profile_form.save()
        messages.success(request, "Profile updated.")
        return redirect("accounts:settings")
    return render(
        request,
        "accounts/settings.html",
        {
            "profile_form": profile_form,
            "token_form": token_form,
            "tokens": request.user.personalaccesstoken_set.all(),
        },
    )


@login_required
@require_POST
def create_token(request):
    form = TokenForm(request.POST, prefix="token")
    if form.is_valid():
        _, raw_token = PersonalAccessToken.issue(owner=request.user, **form.cleaned_data)
        return render(request, "accounts/token_created.html", {"raw_token": raw_token})
    profile_form = ProfileForm(instance=request.user)
    return render(
        request,
        "accounts/settings.html",
        {
            "profile_form": profile_form,
            "token_form": form,
            "tokens": request.user.personalaccesstoken_set.all(),
        },
        status=400,
    )


@login_required
@require_POST
def revoke_token(request, token_id):
    updated = PersonalAccessToken.objects.filter(
        id=token_id, owner=request.user, revoked_at__isnull=True
    ).update(revoked_at=timezone.now())
    if not updated:
        raise Http404
    messages.success(request, "Token revoked.")
    return redirect("accounts:settings")
