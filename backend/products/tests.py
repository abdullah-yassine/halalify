from django.test import TestCase

from products.classifier import (
    ClassificationResult,
    TriggeredIngredient,
    Verdict,
    classify,
    parse_ingredients,
)
from products.models import Certification, Ingredient


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

    # ------------------------------------------------------------------
    # 1. Clear HARAM ingredient
    # ------------------------------------------------------------------

    def test_haram_ingredient_returns_haram(self):
        result = classify("Water, Sugar, Pork Gelatin")
        self.assertEqual(result.verdict, Verdict.HARAM)
        self.assertEqual(len(result.triggers), 1)
        self.assertEqual(result.triggers[0].name, "Pork Gelatin")
        self.assertIn("pig", result.triggers[0].reason.lower())

    def test_haram_matched_via_alias(self):
        # "Gelatin (Pork)" should match the "Pork Gelatin" ingredient via alias.
        result = classify("Water, Sugar, Gelatin (Pork)")
        self.assertEqual(result.verdict, Verdict.HARAM)

    def test_haram_short_circuits_on_first_match(self):
        # Doubtful ingredients before and after the haram one shouldn't appear
        # in triggers — we short-circuit immediately.
        result = classify("Natural Flavors, Pork Gelatin, Gelatin")
        self.assertEqual(result.verdict, Verdict.HARAM)
        self.assertEqual(len(result.triggers), 1)

    def test_haram_case_insensitive(self):
        result = classify("WATER, SUGAR, PORK GELATIN")
        self.assertEqual(result.verdict, Verdict.HARAM)

    # ------------------------------------------------------------------
    # 2. DOUBTFUL ingredient, no certification
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # 3. DOUBTFUL ingredient + active certification → HALAL
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # 4. Certification does NOT override HARAM (critical safety check)
    # ------------------------------------------------------------------

    def test_certification_never_overrides_haram(self):
        Certification.objects.create(
            brand="CertifiedBrand",
            certifying_body=Certification.CertifyingBody.IFANCA,
            certified=True,
        )
        result = classify("Water, Pork Gelatin", brand="CertifiedBrand")
        self.assertEqual(result.verdict, Verdict.HARAM)

    # ------------------------------------------------------------------
    # 5. All recognised halal ingredients → HALAL
    # ------------------------------------------------------------------

    def test_all_halal_ingredients_returns_halal(self):
        result = classify("Water, Sugar, Salt")
        self.assertEqual(result.verdict, Verdict.HALAL)
        self.assertEqual(result.triggers, [])
        self.assertIsNone(result.certifying_body)

    def test_empty_ingredient_text_returns_halal(self):
        result = classify("")
        self.assertEqual(result.verdict, Verdict.HALAL)

    # ------------------------------------------------------------------
    # 6. Unrecognised ingredient → DOUBTFUL (safe failure mode)
    # ------------------------------------------------------------------

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
        # A certified brand with an unrecognised ingredient: cert wins over
        # unrecognised (same logic as it wins over Doubtful — cert resolves all
        # non-haram ambiguity).
        Certification.objects.create(
            brand="CertBrand2",
            certifying_body=Certification.CertifyingBody.JAKIM,
            certified=True,
        )
        result = classify("Water, MysteryIngredient-X", brand="CertBrand2")
        self.assertEqual(result.verdict, Verdict.HALAL)

    # ------------------------------------------------------------------
    # 7. Result structure correctness
    # ------------------------------------------------------------------

    def test_halal_result_has_empty_triggers(self):
        result = classify("Water, Sugar")
        self.assertIsInstance(result, ClassificationResult)
        self.assertEqual(result.triggers, [])

    def test_haram_result_trigger_is_triggered_ingredient(self):
        result = classify("Pork Gelatin")
        self.assertIsInstance(result.triggers[0], TriggeredIngredient)
        self.assertTrue(result.triggers[0].matched)

    def test_no_brand_supplied_no_cert_lookup(self):
        # brand='' should skip DB lookup and go straight to verdict.
        result = classify("Water, Gelatin", brand="")
        self.assertEqual(result.verdict, Verdict.DOUBTFUL)
        self.assertIsNone(result.certifying_body)
