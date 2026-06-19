import re

from rest_framework import serializers

# UPC-A (12), UPC-E (8), EAN-13 (13), EAN-8 (8), GTIN-14 (14)
BARCODE_RE = re.compile(r"^\d{8,14}$")


class AppleAuthInputSerializer(serializers.Serializer):
    identity_token = serializers.CharField(max_length=4096)


class ScanCreateInputSerializer(serializers.Serializer):
    barcode = serializers.CharField(max_length=14, min_length=8)

    def validate_barcode(self, value):
        if not BARCODE_RE.match(value):
            raise serializers.ValidationError(
                "Barcode must be 8–14 digits (numeric only)."
            )
        return value


class ScanItemSerializer(serializers.Serializer):
    """Output shape for individual items in GET /api/scans/history/"""

    id = serializers.IntegerField()
    barcode = serializers.CharField(source="product.barcode")
    product_name = serializers.CharField(source="product.name")
    brand = serializers.CharField(source="product.brand", allow_blank=True)
    scanned_at = serializers.DateTimeField()
