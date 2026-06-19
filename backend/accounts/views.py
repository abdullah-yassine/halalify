import logging

import jwt as pyjwt
from django.conf import settings
from rest_framework import generics
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.apple_auth import verify_apple_token
from accounts.models import Scan, User
from accounts.serializers import (
    AppleAuthInputSerializer,
    ScanCreateInputSerializer,
    ScanItemSerializer,
)
from config.throttles import AppleAuthThrottle, ScanCreateThrottle, ScanHistoryThrottle
from products.models import Product

logger = logging.getLogger(__name__)


class AppleAuthView(APIView):
    """
    POST /api/auth/apple/

    Exchanges a client-supplied Apple identity token for our own JWT pair.

    AllowAny is intentional and required — this is the endpoint through which
    a user obtains a token in the first place. Every other endpoint in the app
    uses the global IsAuthenticated default. This override must not be mistaken
    for an oversight or removed without understanding that removing it would lock
    all users out of authentication.
    """

    permission_classes = [AllowAny]
    throttle_classes = [AppleAuthThrottle]

    def post(self, request):
        serializer = AppleAuthInputSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({"error": "Invalid request."}, status=400)

        identity_token = serializer.validated_data["identity_token"]

        try:
            claims = verify_apple_token(identity_token, settings.APPLE_APP_BUNDLE_ID)
        except pyjwt.PyJWTError as exc:
            # Log error TYPE only — never the token or any claim from it.
            logger.warning("Apple token verification failed: %s", type(exc).__name__)
            return Response({"error": "Authentication failed."}, status=401)
        except Exception as exc:
            logger.error(
                "Unexpected error during Apple token verification: %s",
                type(exc).__name__,
            )
            return Response({"error": "Authentication failed."}, status=401)

        apple_user_id = claims.get("sub")
        if not apple_user_id:
            # Should be impossible after successful verification, but defend anyway.
            return Response({"error": "Authentication failed."}, status=401)

        # get_or_create by Apple subject (sub) only — email is not a stable identifier
        # and may not always be present (Apple hides email after first sign-in).
        user, _ = User.objects.get_or_create(
            apple_user_id=apple_user_id,
            defaults={"email": claims.get("email", "")},
        )

        refresh = RefreshToken.for_user(user)
        return Response({
            "access": str(refresh.access_token),
            "refresh": str(refresh),
        })


class ScanCreateView(APIView):
    """POST /api/scans/ — log a product scan to the authenticated user's history."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [ScanCreateThrottle]

    def post(self, request):
        serializer = ScanCreateInputSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"error": serializer.errors},
                status=400,
            )

        barcode = serializer.validated_data["barcode"]

        try:
            product = Product.objects.get(barcode=barcode)
        except Product.DoesNotExist:
            return Response({"error": "Product not found."}, status=404)

        scan = Scan.objects.create(user=request.user, product=product)

        return Response(
            {
                "id": scan.id,
                "barcode": product.barcode,
                "product_name": product.name,
                "scanned_at": scan.scanned_at,
            },
            status=201,
        )


class ScanHistoryPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class ScanHistoryView(generics.ListAPIView):
    """
    GET /api/scans/history/ — paginated list of the authenticated user's scans.

    Data isolation is structural, not conventional: get_queryset() is always
    filtered by request.user and never accepts a user ID from the client.
    It is impossible for this view to return another user's scan records.
    """

    permission_classes = [IsAuthenticated]
    throttle_classes = [ScanHistoryThrottle]
    serializer_class = ScanItemSerializer
    pagination_class = ScanHistoryPagination

    def get_queryset(self):
        # Hard isolation: scoped to request.user, no client-supplied filter.
        return (
            Scan.objects.filter(user=self.request.user)
            .select_related("product")
            .order_by("-scanned_at")
        )
