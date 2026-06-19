from unittest.mock import patch

import jwt as pyjwt
from django.conf import settings as django_settings
from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.models import Scan, User
from products.models import Ingredient, Product


def _make_user(apple_user_id="test_apple_user"):
    return User.objects.create_user(apple_user_id=apple_user_id)


def _auth_client(user):
    """Return an APIClient with a valid JWT for the given user."""
    client = APIClient()
    refresh = RefreshToken.for_user(user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {str(refresh.access_token)}")
    return client


# =============================================================================
# POST /api/auth/apple/
# =============================================================================


class AppleAuthViewTest(TestCase):
    """Tests for Apple Sign In token exchange."""

    def setUp(self):
        self.client = APIClient()
        cache.clear()

    def _fake_claims(self, sub="apple_uid_123", email="user@example.com"):
        return {
            "sub": sub,
            "email": email,
            "aud": "com.placeholder.halalify",
            "iss": "https://appleid.apple.com",
        }

    # ---- Reachability without an existing token ----

    def test_endpoint_is_reachable_without_bearer_token(self):
        # AllowAny — should not return 403 (Forbidden).
        # Will return 400 (missing field) or 401 (bad token), never 403.
        response = self.client.post("/api/auth/apple/", {})
        self.assertNotEqual(response.status_code, 403)

    def test_missing_identity_token_field_returns_400(self):
        response = self.client.post("/api/auth/apple/", {})
        self.assertEqual(response.status_code, 400)

    # ---- Happy path ----

    @patch("accounts.views.verify_apple_token")
    def test_valid_token_returns_jwt_pair(self, mock_verify):
        mock_verify.return_value = self._fake_claims()
        response = self.client.post(
            "/api/auth/apple/", {"identity_token": "valid.apple.token"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)

    @patch("accounts.views.verify_apple_token")
    def test_valid_token_creates_user_on_first_auth(self, mock_verify):
        mock_verify.return_value = self._fake_claims(sub="new_apple_user")
        self.assertEqual(User.objects.filter(apple_user_id="new_apple_user").count(), 0)
        self.client.post("/api/auth/apple/", {"identity_token": "token"})
        self.assertEqual(User.objects.filter(apple_user_id="new_apple_user").count(), 1)

    @patch("accounts.views.verify_apple_token")
    def test_second_auth_reuses_existing_user(self, mock_verify):
        User.objects.create_user(apple_user_id="existing_apple_user")
        mock_verify.return_value = self._fake_claims(sub="existing_apple_user")
        count_before = User.objects.count()
        self.client.post("/api/auth/apple/", {"identity_token": "token"})
        self.assertEqual(User.objects.count(), count_before)

    # ---- Rejection of bad / forged / expired tokens ----

    @patch("accounts.views.verify_apple_token")
    def test_invalid_token_returns_401(self, mock_verify):
        mock_verify.side_effect = pyjwt.InvalidSignatureError("bad signature")
        response = self.client.post(
            "/api/auth/apple/", {"identity_token": "forged.token.here"}
        )
        self.assertEqual(response.status_code, 401)

    @patch("accounts.views.verify_apple_token")
    def test_expired_token_returns_401(self, mock_verify):
        mock_verify.side_effect = pyjwt.ExpiredSignatureError("token expired")
        response = self.client.post(
            "/api/auth/apple/", {"identity_token": "expired.token.here"}
        )
        self.assertEqual(response.status_code, 401)

    @patch("accounts.views.verify_apple_token")
    def test_invalid_token_does_not_create_user(self, mock_verify):
        mock_verify.side_effect = pyjwt.PyJWTError("verification failed")
        count_before = User.objects.count()
        self.client.post("/api/auth/apple/", {"identity_token": "forged"})
        self.assertEqual(User.objects.count(), count_before)

    @patch("accounts.views.verify_apple_token")
    def test_401_response_body_contains_no_internal_details(self, mock_verify):
        mock_verify.side_effect = pyjwt.PyJWTError("internal error")
        response = self.client.post("/api/auth/apple/", {"identity_token": "bad"})
        self.assertEqual(response.status_code, 401)
        body = response.content.decode()
        self.assertNotIn("Traceback", body)
        self.assertNotIn("PyJWTError", body)
        self.assertNotIn("apple_auth", body)
        # Generic message only
        self.assertEqual(response.data["error"], "Authentication failed.")

    # ---- Throttle enforcement ----

    @patch("accounts.views.verify_apple_token")
    def test_apple_auth_throttle_returns_429(self, mock_verify):
        mock_verify.side_effect = pyjwt.PyJWTError("bad")
        base = dict(django_settings.REST_FRAMEWORK)
        base["DEFAULT_THROTTLE_RATES"] = {
            **base["DEFAULT_THROTTLE_RATES"],
            "apple_auth": "3/minute",
        }
        cache.clear()
        with self.settings(REST_FRAMEWORK=base):
            cache.clear()
            for _ in range(3):
                self.client.post("/api/auth/apple/", {"identity_token": "t"})
            response = self.client.post("/api/auth/apple/", {"identity_token": "t"})
        self.assertEqual(response.status_code, 429)


# =============================================================================
# POST /api/scans/
# =============================================================================


class ScanCreateViewTest(TestCase):
    """Tests for POST /api/scans/"""

    def setUp(self):
        self.user = _make_user("scan_creator")
        self.authed_client = _auth_client(self.user)
        self.anon_client = APIClient()
        self.product = Product.objects.create(
            barcode="012345678905",
            name="Test Product",
            brand="Brand",
            ingredients_text="Water",
        )
        # Ensure a halal ingredient exists so classify doesn't flag everything doubtful
        Ingredient.objects.create(
            name="Scan-Water",
            aliases=["water"],
            category=Ingredient.Category.HALAL,
            reason="Halal.",
        )

    def test_unauthenticated_request_returns_401(self):
        response = self.anon_client.post(
            "/api/scans/", {"barcode": self.product.barcode}
        )
        self.assertIn(response.status_code, [401, 403])

    def test_authenticated_scan_creates_record(self):
        count_before = Scan.objects.count()
        response = self.authed_client.post(
            "/api/scans/", {"barcode": self.product.barcode}
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Scan.objects.count(), count_before + 1)

    def test_authenticated_scan_response_shape(self):
        response = self.authed_client.post(
            "/api/scans/", {"barcode": self.product.barcode}
        )
        self.assertEqual(response.status_code, 201)
        self.assertIn("id", response.data)
        self.assertIn("barcode", response.data)
        self.assertIn("product_name", response.data)
        self.assertIn("scanned_at", response.data)

    def test_scan_is_linked_to_authenticated_user(self):
        self.authed_client.post("/api/scans/", {"barcode": self.product.barcode})
        scan = Scan.objects.get(product=self.product)
        self.assertEqual(scan.user, self.user)

    def test_nonexistent_barcode_returns_404(self):
        response = self.authed_client.post("/api/scans/", {"barcode": "999999999999"})
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.data["error"], "Product not found.")

    def test_invalid_barcode_format_returns_400(self):
        response = self.authed_client.post("/api/scans/", {"barcode": "ABCDEF"})
        self.assertEqual(response.status_code, 400)

    def test_barcode_too_short_returns_400(self):
        response = self.authed_client.post("/api/scans/", {"barcode": "123"})
        self.assertEqual(response.status_code, 400)

    def test_missing_barcode_field_returns_400(self):
        response = self.authed_client.post("/api/scans/", {})
        self.assertEqual(response.status_code, 400)

    def test_404_response_contains_no_internal_details(self):
        response = self.authed_client.post("/api/scans/", {"barcode": "999999999999"})
        body = response.content.decode()
        self.assertNotIn("Traceback", body)
        self.assertNotIn("DoesNotExist", body)


# =============================================================================
# GET /api/scans/history/
# =============================================================================


class ScanHistoryViewTest(TestCase):
    """Tests for GET /api/scans/history/"""

    def setUp(self):
        self.user1 = _make_user("history_user_1")
        self.user2 = _make_user("history_user_2")
        self.client1 = _auth_client(self.user1)
        self.client2 = _auth_client(self.user2)
        self.anon_client = APIClient()

        self.product = Product.objects.create(
            barcode="012345678905",
            name="History Product",
            brand="Brand",
            ingredients_text="Water",
        )
        # user1: 3 scans, user2: 2 scans
        for _ in range(3):
            Scan.objects.create(user=self.user1, product=self.product)
        for _ in range(2):
            Scan.objects.create(user=self.user2, product=self.product)

    def test_unauthenticated_request_returns_401(self):
        response = self.anon_client.get("/api/scans/history/")
        self.assertIn(response.status_code, [401, 403])

    def test_returns_200_for_authenticated_user(self):
        response = self.client1.get("/api/scans/history/")
        self.assertEqual(response.status_code, 200)

    def test_response_is_paginated(self):
        response = self.client1.get("/api/scans/history/")
        self.assertIn("count", response.data)
        self.assertIn("results", response.data)

    # ---- Critical: data isolation ----

    def test_user1_sees_only_their_own_scans(self):
        response = self.client1.get("/api/scans/history/")
        self.assertEqual(response.status_code, 200)
        # user1 has 3 scans, user2 has 2; total is 5 but user1 must see exactly 3
        self.assertEqual(response.data["count"], 3)

    def test_user2_sees_only_their_own_scans(self):
        response = self.client2.get("/api/scans/history/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 2)

    def test_cross_user_data_isolation_explicit(self):
        # Authenticate as user1, verify user2's scan count is NOT returned.
        r1 = self.client1.get("/api/scans/history/")
        r2 = self.client2.get("/api/scans/history/")
        self.assertNotEqual(r1.data["count"], r2.data["count"])
        # Combined total is 5; if isolation fails, at least one would show 5.
        self.assertLess(r1.data["count"], 5)
        self.assertLess(r2.data["count"], 5)

    def test_response_items_have_expected_fields(self):
        response = self.client1.get("/api/scans/history/")
        item = response.data["results"][0]
        self.assertIn("id", item)
        self.assertIn("barcode", item)
        self.assertIn("product_name", item)
        self.assertIn("scanned_at", item)

    def test_history_ordered_newest_first(self):
        response = self.client1.get("/api/scans/history/")
        timestamps = [item["scanned_at"] for item in response.data["results"]]
        self.assertEqual(timestamps, sorted(timestamps, reverse=True))
