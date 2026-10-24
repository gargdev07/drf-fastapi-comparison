from django.test import TestCase, override_settings
from rest_framework.test import APIClient

@override_settings(DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}})
class ProductApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_crud_and_validation(self):
        root = self.client.get("/", follow=True)
        self.assertEqual(root.status_code, 200)
        self.assertIn("swagger-ui", root.request["PATH_INFO"])
        self.assertEqual(self.client.get("/api/schema/").status_code, 200)
        self.assertEqual(self.client.get("/api/schema/swagger-ui/").status_code, 200)
        self.assertEqual(self.client.get("/api/v1/health").data["data"]["framework"], "Django REST Framework")
        created = self.client.post("/api/v1/products", {"title": "Test item", "price": 5, "category": "Test"}, format="json")
        self.assertEqual(created.status_code, 201)
        product_id = created.data["data"]["id"]
        self.assertEqual(self.client.get(f"/api/v1/products/{product_id}").status_code, 200)
        self.assertEqual(self.client.patch(f"/api/v1/products/{product_id}", {"stock": 4}, format="json").data["data"]["stock"], 4)
        self.assertTrue(self.client.delete(f"/api/v1/products/{product_id}").data["data"]["deleted"])
        invalid = self.client.post("/api/v1/products", {"title": "x", "price": -1, "category": "Test"}, format="json")
        self.assertEqual(invalid.status_code, 422)
        self.assertIsInstance(invalid.data["detail"], list)
        self.assertTrue({issue["loc"][-1] for issue in invalid.data["detail"]} >= {"title", "price"})
