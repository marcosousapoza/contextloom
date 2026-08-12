from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.utils import timezone

from contextloom.accounts.models import PersonalAccessToken, User


class LoginForm(AuthenticationForm):
    username = forms.CharField(label="Username or email", max_length=254)


class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ("email", "first_name", "last_name")


class TokenForm(forms.Form):
    name = forms.CharField(max_length=100)
    scopes = forms.MultipleChoiceField(
        choices=PersonalAccessToken.SCOPE_CHOICES,
        widget=forms.CheckboxSelectMultiple,
    )
    expires_at = forms.DateTimeField(
        required=False,
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}),
        help_text="Optional. Times are interpreted as UTC.",
    )

    def clean_expires_at(self):
        value = self.cleaned_data.get("expires_at")
        if value and value <= timezone.now():
            raise forms.ValidationError("Expiration must be in the future.")
        return value
