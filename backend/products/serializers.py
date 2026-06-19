from rest_framework import serializers


class TriggeredIngredientSerializer(serializers.Serializer):
    name = serializers.CharField()
    reason = serializers.CharField()
    matched = serializers.BooleanField()


class ProductVerdictSerializer(serializers.Serializer):
    """Output shape for GET /api/products/{barcode}/"""

    barcode = serializers.CharField()
    name = serializers.CharField()
    brand = serializers.CharField(allow_blank=True)
    verdict = serializers.CharField()
    certifying_body = serializers.CharField(allow_null=True)
    triggers = TriggeredIngredientSerializer(many=True)
