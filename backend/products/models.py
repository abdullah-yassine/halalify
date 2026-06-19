from django.db import models


class Ingredient(models.Model):
    class Category(models.TextChoices):
        HARAM = "haram", "Haram"
        HALAL = "halal", "Halal"
        DOUBTFUL = "doubtful", "Doubtful"

    name = models.CharField(max_length=255, unique=True)
    e_number = models.CharField(max_length=20, blank=True)
    # Alternative names/spellings the classifier uses when scanning ingredient text.
    aliases = models.JSONField(default=list, blank=True)
    category = models.CharField(max_length=10, choices=Category)
    reason = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "products_ingredient"
        indexes = [models.Index(fields=["category"])]

    def __str__(self):
        return f"{self.name} ({self.get_category_display()})"


class Certification(models.Model):
    class CertifyingBody(models.TextChoices):
        IFANCA = "IFANCA", "IFANCA"
        HMS = "HMS", "HMS (Halal Monitoring Services)"
        HFSAA = "HFSAA", "HFSAA (Halal Food Standards Alliance of America)"
        JAKIM = "JAKIM", "JAKIM"
        OTHER = "OTHER", "Other"

    brand = models.CharField(max_length=255, db_index=True)
    certifying_body = models.CharField(max_length=10, choices=CertifyingBody)
    certified = models.BooleanField(default=True)
    source_url = models.URLField(blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "products_certification"
        unique_together = ("brand", "certifying_body")

    def __str__(self):
        status = "certified" if self.certified else "not certified"
        return f"{self.brand} — {self.certifying_body} ({status})"


class Product(models.Model):
    # barcode is the primary lookup key — must be fast. unique=True creates the index.
    barcode = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=500)
    brand = models.CharField(max_length=255, blank=True)
    # Raw ingredient string from Open Food Facts, e.g. "Water, Sugar, Salt, Natural Flavors"
    ingredients_text = models.TextField(blank=True)
    ingredients = models.ManyToManyField(
        Ingredient,
        through="ProductIngredient",
        blank=True,
        related_name="products",
    )
    # Open Food Facts internal ID for future re-sync reference
    off_id = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "products_product"

    def __str__(self):
        return f"{self.name} ({self.barcode})"


class ProductIngredient(models.Model):
    """Through table linking a scanned product to the known ingredients identified in it."""
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="product_ingredients",
    )
    ingredient = models.ForeignKey(
        Ingredient,
        on_delete=models.CASCADE,
        related_name="product_ingredients",
    )

    class Meta:
        db_table = "products_productingredient"
        unique_together = ("product", "ingredient")
