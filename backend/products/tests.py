import json

from django.conf import settings as django_settings
from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User
from products.classifier import (
    ClassificationResult,
    TriggeredIngredient,
    Verdict,
    classify,
    parse_ingredients,
)
from products.models import Certification, Ingredient, Product


# =============================================================================
# Classifier unit tests
# =============================================================================


class IngredientParserTest(TestCase):
    """Unit tests for the raw-text parser — no DB needed."""

    def test_simple_comma_separated(self):
        self.assertEqual(parse_ingredients("Water, Sugar, Salt"), ["Water", "Sugar", "Salt"])

    def test_strips_ingredients_label_prefix(self):
        result = parse_ingredients("INGREDIENTS: Water, Sugar")
        self.assertIn("Water", result)
        self.assertIn("Sugar", result)

    def test_strips_trailing_period(self):
        result = parse_ingredients("Water, Sugar.")
        self.assertNotIn("Sugar.", result)
        self.assertIn("Sugar", result)

    def test_extracts_parenthetical_sub_ingredients(self):
        result = parse_ingredients("Enriched Flour (Wheat Flour, Niacin, Iron), Sugar")
        self.assertIn("Enriched Flour", result)
        self.assertIn("Wheat Flour", result)
        self.assertIn("Niacin", result)
        self.assertIn("Iron", result)
        self.assertIn("Sugar", result)

    def test_nested_parens_handled(self):
        result = parse_ingredients("Sauce (Water, Salt (Sea Salt)), Sugar")
        self.assertIn("Sauce", result)
        self.assertIn("Water", result)
        self.assertIn("Sugar", result)

    def test_empty_string_returns_empty_list(self):
        self.assertEqual(parse_ingredients(""), [])

    def test_whitespace_only_returns_empty_list(self):
        self.assertEqual(parse_ingredients("   "), [])


class ClassifierTest(TestCase):
    """
    Integration tests for classify().

    Seeded ingredients (from migration 0002) are available throughout.
    We additionally create HALAL test ingredients (Water, Sugar) since
    the seed data only covers Haram and Doubtful categories — any ingredient
    absent from the DB is treated as Doubtful (safe failure mode).
    """

    def setUp(self):
        # These already exist via the seed migration — fetch, don't re-create.
        self.pork_gelatin = Ingredient.objects.get(name="Pork Gelatin")  # HARAM
        self.gelatin = Ingredient.objects.get(name="Gelatin")            # DOUBTFUL
        self.natural_flavors = Ingredient.objects.get(name="Natural Flavors")  # DOUBTFUL

        # HALAL entries not in the seed data — needed for "clean product" tests.
        self.water = Ingredient.objects.create(
            name="Test-Water",
            e_number="",
            aliases=["water", "purified water", "filtered water"],
            category=Ingredient.Category.HALAL,
            reason="Water is halal.",
        )
        self.sugar = Ingredient.objects.create(
            name="Test-Sugar",
            e_number="",
            aliases=["sugar", "cane sugar", "sucrose"],
            category=Ingredient.Category.HALAL,
            reason="Plant-derived sweetener — halal.",
        )
        self.salt = Ingredient.objects.create(
            name="Test-Salt",
            e_number="",
            aliases=["salt", "sea salt", "sodium chloride"],
            category=Ingredient.Category.HALAL,
            reason="Mineral — halal.",
        )

    def test_haram_ingredient_returns_haram(self):
        result = classify("Water, Sugar, Pork Gelatin")
        self.assertEqual(result.verdict, Verdict.HARAM)
        self.assertEqual(len(result.triggers), 1)
        self.assertEqual(result.triggers[0].name, "Pork Gelatin")
        self.assertIn("pig", result.triggers[0].reason.lower())

    def test_haram_matched_via_alias(self):
        result = classify("Water, Sugar, Gelatin (Pork)")
        self.assertEqual(result.verdict, Verdict.HARAM)

    def test_haram_short_circuits_on_first_match(self):
        result = classify("Natural Flavors, Pork Gelatin, Gelatin")
        self.assertEqual(result.verdict, Verdict.HARAM)
        self.assertEqual(len(result.triggers), 1)

    def test_haram_case_insensitive(self):
        result = classify("WATER, SUGAR, PORK GELATIN")
        self.assertEqual(result.verdict, Verdict.HARAM)

    def test_doubtful_ingredient_no_cert_returns_doubtful(self):
        result = classify("Water, Sugar, Gelatin")
        self.assertEqual(result.verdict, Verdict.DOUBTFUL)
        names = [t.name for t in result.triggers]
        self.assertIn("Gelatin", names)

    def test_multiple_doubtful_ingredients_all_reported(self):
        result = classify("Water, Gelatin, Natural Flavors, Sugar")
        self.assertEqual(result.verdict, Verdict.DOUBTFUL)
        names = [t.name for t in result.triggers]
        self.assertIn("Gelatin", names)
        self.assertIn("Natural Flavors", names)

    def test_doubtful_triggers_include_reason_text(self):
        result = classify("Water, Gelatin")
        self.assertEqual(result.verdict, Verdict.DOUBTFUL)
        gelatin_trigger = next(t for t in result.triggers if t.name == "Gelatin")
        self.assertTrue(len(gelatin_trigger.reason) > 10)

    def test_repeated_doubtful_ingredient_deduplicated(self):
        result = classify("Gelatin, Gelatin, Gelatin")
        self.assertEqual(result.verdict, Verdict.DOUBTFUL)
        self.assertEqual(len(result.triggers), 1)

    def test_active_cert_overrides_doubtful(self):
        Certification.objects.create(
            brand="GoodBrand",
            certifying_body=Certification.CertifyingBody.IFANCA,
            certified=True,
        )
        result = classify("Water, Sugar, Gelatin", brand="GoodBrand")
        self.assertEqual(result.verdict, Verdict.HALAL)
        self.assertIsNotNone(result.certifying_body)
        self.assertIn("IFANCA", result.certifying_body)

    def test_cert_match_is_case_insensitive(self):
        Certification.objects.create(
            brand="goodbrand",
            certifying_body=Certification.CertifyingBody.IFANCA,
            certified=True,
        )
        result = classify("Water, Gelatin", brand="GOODBRAND")
        self.assertEqual(result.verdict, Verdict.HALAL)

    def test_inactive_cert_does_not_override_doubtful(self):
        Certification.objects.create(
            brand="ExpiredBrand",
            certifying_body=Certification.CertifyingBody.IFANCA,
            certified=False,
        )
        result = classify("Water, Gelatin", brand="ExpiredBrand")
        self.assertEqual(result.verdict, Verdict.DOUBTFUL)

    def test_cert_for_different_brand_does_not_apply(self):
        Certification.objects.create(
            brand="OtherBrand",
            certifying_body=Certification.CertifyingBody.IFANCA,
            certified=True,
        )
        result = classify("Water, Gelatin", brand="ThisBrand")
        self.assertEqual(result.verdict, Verdict.DOUBTFUL)

    def test_certification_never_overrides_haram(self):
        Certification.objects.create(
            brand="CertifiedBrand",
            certifying_body=Certification.CertifyingBody.IFANCA,
            certified=True,
        )
        result = classify("Water, Pork Gelatin", brand="CertifiedBrand")
        self.assertEqual(result.verdict, Verdict.HARAM)

    def test_all_halal_ingredients_returns_halal(self):
        result = classify("Water, Sugar, Salt")
        self.assertEqual(result.verdict, Verdict.HALAL)
        self.assertEqual(result.triggers, [])
        self.assertIsNone(result.certifying_body)

    def test_empty_ingredient_text_returns_doubtful(self):
        result = classify("")
        self.assertEqual(result.verdict, Verdict.DOUBTFUL)
        self.assertEqual(len(result.triggers), 1)
        self.assertFalse(result.triggers[0].matched)
        self.assertIn("not available", result.triggers[0].reason)

    def test_unrecognised_ingredient_returns_doubtful(self):
        result = classify("Water, Sugar, Xanthoflavorex-9000")
        self.assertEqual(result.verdict, Verdict.DOUBTFUL)

    def test_unrecognised_ingredient_is_named_in_triggers(self):
        result = classify("Water, Sugar, Xanthoflavorex-9000")
        names = [t.name for t in result.triggers]
        self.assertIn("Xanthoflavorex-9000", names)

    def test_unrecognised_ingredient_marked_as_unmatched(self):
        result = classify("Water, Sugar, Xanthoflavorex-9000")
        unmatched = [t for t in result.triggers if not t.matched]
        self.assertEqual(len(unmatched), 1)
        self.assertIn("not yet classified", unmatched[0].reason)

    def test_unrecognised_alongside_doubtful_both_reported(self):
        result = classify("Water, Gelatin, MysteryIngredient-X")
        self.assertEqual(result.verdict, Verdict.DOUBTFUL)
        names = [t.name for t in result.triggers]
        self.assertIn("Gelatin", names)
        self.assertIn("MysteryIngredient-X", names)

    def test_unrecognised_not_overridden_by_cert(self):
        Certification.objects.create(
            brand="CertBrand2",
            certifying_body=Certification.CertifyingBody.JAKIM,
            certified=True,
        )
        result = classify("Water, MysteryIngredient-X", brand="CertBrand2")
        self.assertEqual(result.verdict, Verdict.HALAL)

    def test_halal_result_has_empty_triggers(self):
        result = classify("Water, Sugar")
        self.assertIsInstance(result, ClassificationResult)
        self.assertEqual(result.triggers, [])

    def test_haram_result_trigger_is_triggered_ingredient(self):
        result = classify("Pork Gelatin")
        self.assertIsInstance(result.triggers[0], TriggeredIngredient)
        self.assertTrue(result.triggers[0].matched)

    def test_no_brand_supplied_no_cert_lookup(self):
        result = classify("Water, Gelatin", brand="")
        self.assertEqual(result.verdict, Verdict.DOUBTFUL)
        self.assertIsNone(result.certifying_body)


# =============================================================================
# Product API integration tests
# =============================================================================


class ProductLookupAPITest(TestCase):
    """Integration tests for GET /api/products/{barcode}/"""

    def setUp(self):
        self.client = APIClient()
        # Halal ingredients for the test product
        Ingredient.objects.create(
            name="API-Water", aliases=["water"],
            category=Ingredient.Category.HALAL, reason="Halal.",
        )
        Ingredient.objects.create(
            name="API-Sugar", aliases=["sugar"],
            category=Ingredient.Category.HALAL, reason="Halal.",
        )
        self.product = Product.objects.create(
            barcode="012345678905",
            name="Clean Test Product",
            brand="SafeBrand",
            ingredients_text="Water, Sugar",
        )
        self.haram_product = Product.objects.create(
            barcode="012345678912",
            name="Haram Test Product",
            brand="HaramBrand",
            ingredients_text="Water, Lard",
        )

    def test_valid_barcode_returns_200_with_verdict(self):
        response = self.client.get("/api/products/012345678905/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("verdict", response.data)
        self.assertIn("barcode", response.data)
        self.assertIn("triggers", response.data)

    def test_verdict_correct_for_halal_product(self):
        response = self.client.get("/api/products/012345678905/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["verdict"], "halal")

    def test_verdict_correct_for_haram_product(self):
        response = self.client.get("/api/products/012345678912/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["verdict"], "haram")
        self.assertEqual(len(response.data["triggers"]), 1)
        self.assertEqual(response.data["triggers"][0]["name"], "Lard")

    # ---- Input validation: barcode format ----

    def test_letters_in_barcode_returns_400(self):
        response = self.client.get("/api/products/ABCDEF123456/")
        self.assertEqual(response.status_code, 400)

    def test_barcode_too_short_returns_400(self):
        response = self.client.get("/api/products/123/")
        self.assertEqual(response.status_code, 400)

    def test_barcode_too_long_returns_400(self):
        response = self.client.get("/api/products/123456789012345/")
        self.assertEqual(response.status_code, 400)

    def test_barcode_with_special_chars_returns_400(self):
        response = self.client.get("/api/products/0123-5678-9012/")
        self.assertEqual(response.status_code, 400)

    def test_400_response_contains_no_internal_details(self):
        response = self.client.get("/api/products/INVALID/")
        self.assertEqual(response.status_code, 400)
        body = response.content.decode()
        self.assertNotIn("Traceback", body)
        self.assertNotIn("DoesNotExist", body)
        self.assertNotIn("models.py", body)
        self.assertNotIn("settings", body)

    def test_missing_product_returns_404(self):
        response = self.client.get("/api/products/999999999999/")
        self.assertEqual(response.status_code, 404)

    def test_404_response_is_generic(self):
        response = self.client.get("/api/products/999999999999/")
        body = response.content.decode()
        self.assertNotIn("DoesNotExist", body)
        self.assertNotIn("Traceback", body)
        self.assertNotIn("models.py", body)
        self.assertEqual(response.data["error"], "Product not found.")

    # ---- Throttle enforcement ----

    def test_product_lookup_throttle_returns_429_for_anon(self):
        # Override to a very low rate to confirm 429 is actually returned.
        base = dict(django_settings.REST_FRAMEWORK)
        base["DEFAULT_THROTTLE_RATES"] = {
            **base["DEFAULT_THROTTLE_RATES"],
            "product_lookup_anon": "3/minute",
        }
        cache.clear()
        with self.settings(REST_FRAMEWORK=base):
            cache.clear()
            for _ in range(3):
                self.client.get("/api/products/012345678905/")
            response = self.client.get("/api/products/012345678905/")
        self.assertEqual(response.status_code, 429)
