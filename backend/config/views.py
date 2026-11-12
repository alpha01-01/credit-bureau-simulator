"""Infrastructure endpoints that sit outside any business module."""

from django.db import connection
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response


@api_view(["GET"])
@permission_classes([AllowAny])
def health(request: Request) -> Response:
    """Report that the API is up and can reach the database."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_setting('server_version')")
        row = cursor.fetchone()
    return Response(
        {
            "status": "ok",
            "service": "simb-api",
            "database": {"vendor": connection.vendor, "server_version": row[0] if row else None},
        }
    )
