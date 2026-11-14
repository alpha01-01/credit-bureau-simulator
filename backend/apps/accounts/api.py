"""Sign-in for the game UI (session authentication with CSRF protection).

GET  /api/v1/auth/session/   who is signed in (and sets the CSRF cookie)
POST /api/v1/auth/login/     {"username", "password"}
POST /api/v1/auth/logout/
"""

from __future__ import annotations

from django.contrib.auth import authenticate, login, logout
from django.http import HttpResponse
from django.middleware.csrf import CsrfViewMiddleware
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response


def _me(request: Request) -> dict[str, object]:
    user = request.user
    if not user.is_authenticated:
        return {"authenticated": False}
    return {"authenticated": True, "username": user.get_username()}


@api_view(["GET"])
@permission_classes([AllowAny])
@ensure_csrf_cookie
def session(request: Request) -> Response:
    return Response(_me(request))


def _csrf_failure(request: Request) -> HttpResponse | None:
    """Enforce CSRF for an anonymous request (DRF only checks it for signed-in users)."""

    def view(_request: object) -> HttpResponse:
        return HttpResponse()

    check = CsrfViewMiddleware(view)
    check.process_request(request._request)
    return check.process_view(request._request, view, (), {})


@api_view(["POST"])
@permission_classes([AllowAny])
def login_view(request: Request) -> Response:
    if _csrf_failure(request) is not None:
        return Response({"detail": "CSRF check failed."}, status=status.HTTP_403_FORBIDDEN)
    user = authenticate(
        request,
        username=str(request.data.get("username", "")),
        password=str(request.data.get("password", "")),
    )
    if user is None:
        return Response(
            {"detail": "Wrong username or password."}, status=status.HTTP_400_BAD_REQUEST
        )
    login(request._request, user)
    # DRF's request.user was resolved before the login, so describe the user directly.
    return Response({"authenticated": True, "username": user.get_username()})


@api_view(["POST"])
def logout_view(request: Request) -> Response:
    logout(request._request)
    return Response({"authenticated": False})
