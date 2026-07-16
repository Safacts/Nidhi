"""
API tests (DRF) — TESTING_STRATEGY #13.

The Rubix IdP auth (api/authentication.py) is NEVER exercised here: the test
settings set REST_FRAMEWORK.DEFAULT_AUTHENTICATION_CLASSES = [] so no live
`requests.post` to the IdP happens. Tests use DRF force_authenticate instead.

Covers:
  * /api/heartbeat/ returns ok for a valid app key + matching fingerprint, and
    401 when the key is missing.
  * A protected endpoint (/api/me/) requires authentication.
"""
from django.contrib.auth.models import User
from django.test import override_settings
from rest_framework.test import APITestCase

from api.models import DatabaseServer, DatabaseInstance, Product
from api.views import compute_db_fingerprint


@override_settings(NIDHI_APP_API_KEY="test-api-key")
class HeartbeatAPITests(APITestCase):
    def _seed_instance(self):
        server = DatabaseServer.objects.create(
            name="hb-srv", host="10.0.0.5", port=5432, root_user="postgres",
            root_password="x", environment_type="production", is_active=True,
        )
        product = Product.objects.create(name="hb-product")
        inst = DatabaseInstance.objects.create(
            server=server, product=product, db_name="hb_db", db_user="hb_db_user",
            db_password_temp="pw", created_by_sso_id="t", status="available",
        )
        return server, inst

    def test_heartbeat_ok(self):
        server, inst = self._seed_instance()
        fp = compute_db_fingerprint(server.host, server.port, inst.db_name)
        resp = self.client.post(
            "/api/heartbeat/",
            {
                "project_slug": "hb-product",
                "environment": "production",
                "database_fingerprint": fp,
            },
            format="json",
            HTTP_AUTHORIZATION="Bearer test-api-key",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "ok")
        self.assertTrue(resp.json()["valid"])

    def test_heartbeat_unauthorized_without_key(self):
        resp = self.client.post(
            "/api/heartbeat/",
            {"project_slug": "x", "environment": "production",
             "database_fingerprint": "abc"},
            format="json",
        )
        self.assertEqual(resp.status_code, 401)


class ProtectedEndpointTests(APITestCase):
    def test_me_requires_auth(self):
        # With REST_FRAMEWORK.DEFAULT_AUTHENTICATION_CLASSES = [] (test settings),
        # an unauthenticated request has no auth scheme -> DRF IsAuthenticated
        # returns 403. This proves the endpoint is protected (no live IdP call).
        resp = self.client.get("/api/me/")
        self.assertIn(resp.status_code, (401, 403))

    def test_me_authenticated(self):
        user = User.objects.create_user(username="fe1", password="pw")
        self.client.force_authenticate(user=user)
        resp = self.client.get("/api/me/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["username"], "fe1")
