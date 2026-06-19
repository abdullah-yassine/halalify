import logging
import re

from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from config.throttles import ProductLookupAnonThrottle, ProductLookupUserThrottle
from products.classifier import classify
from products.models import Product
from products.serializers import ProductVerdictSerializer

logger = logging.getLogger(__name__)

# UPC-A (12), UPC-E (8), EAN-13 (13), EAN-8 (8), GTIN-14 (14)
_BARCODE_RE = re.compile(r"^\d{8,14}$")


class ProductLookupView(APIView):
    """
    GET /api/products/{barcode}/

    Open to anonymous and authenticated requests — scanning doesn't require
    sign-in per v1 spec. Anonymous and authenticated callers are throttled
    separately (20/min vs 100/min) via the two throttle classes below.
    """

    # AllowAny: scanning is a core v1 feature that must work before sign-in.
    permission_classes = [AllowAny]
    throttle_classes = [ProductLookupAnonThrottle, ProductLookupUserThrottle]

    def get(self, request, barcode: str):
        # ----------------------------------------------------------------
        # 1. Strict barcode validation at the edge — defense-in-depth even
        #    though the ORM prevents injection. Malformed input never reaches
        #    the DB layer regardless.
        # ----------------------------------------------------------------
        if not _BARCODE_RE.match(barcode):
            return Response({"error": "Invalid barcode format."}, status=400)

        # ----------------------------------------------------------------
        # 2. Product lookup — 404 with no internal details on miss.
        # ----------------------------------------------------------------
        try:
            product = Product.objects.get(barcode=barcode)
        except Product.DoesNotExist:
            return Response({"error": "Product not found."}, status=404)

        # ----------------------------------------------------------------
        # 3. Classify and return.
        # ----------------------------------------------------------------
        result = classify(product.ingredients_text, brand=product.brand)

        serializer = ProductVerdictSerializer({
            "barcode": product.barcode,
            "name": product.name,
            "brand": product.brand,
            "verdict": result.verdict.value,
            "certifying_body": result.certifying_body,
            "triggers": [
                {"name": t.name, "reason": t.reason, "matched": t.matched}
                for t in result.triggers
            ],
        })
        return Response(serializer.data)
