from django.urls import path

from . import api

urlpatterns = [
    path("auth/session/", api.session, name="auth-session"),
    path("auth/login/", api.login_view, name="auth-login"),
    path("auth/logout/", api.logout_view, name="auth-logout"),
]
