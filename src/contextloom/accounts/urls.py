from django.contrib.auth.views import LogoutView
from django.urls import path

from contextloom.accounts import views

app_name = "accounts"
urlpatterns = [
    path("login/", views.ThrottledLoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("register/", views.register, name="register"),
    path(
        "password-change/",
        views.RequiredPasswordChangeView.as_view(),
        name="password_change",
    ),
    path("settings/", views.settings_view, name="settings"),
    path("tokens/create/", views.create_token, name="create_token"),
    path("tokens/<int:token_id>/revoke/", views.revoke_token, name="revoke_token"),
]
