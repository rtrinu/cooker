from django.test import TestCase
from ninja.testing import TestClient

from .api import api
from .models import Ingredient, Nutrition, Recipe, RecipeIngredient


class ApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.flour = Ingredient.objects.create(
            name="Flour", category="baking", aliases=["all-purpose flour"]
        )
        cls.sugar = Ingredient.objects.create(name="Sugar", category="baking")

        cls.recipe = Recipe.objects.create(
            slug="test-cake",
            name="Test Cake",
            description="A cake for tests.",
            servings=8,
            category="dessert",
            tags=["cake", "sweet"],
            directions="Mix and bake.",
            collection="test-collection",
        )
        RecipeIngredient.objects.create(
            recipe=cls.recipe,
            ingredient=cls.flour,
            quantity_text="2 cups",
            position=1,
        )
        RecipeIngredient.objects.create(
            recipe=cls.recipe,
            ingredient=cls.sugar,
            quantity_text="1 cup",
            position=2,
        )
        Nutrition.objects.create(
            recipe=cls.recipe,
            kcal=250,
            protein_g=3,
            carbs_g=40,
            fat_g=9,
            fiber_g=1,
        )

    def setUp(self):
        self.client = TestClient(api)

    def test_health(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"ok": True})

    def test_list_recipes(self):
        response = self.client.get("/recipes/")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["items"][0]["name"], "Test Cake")

    def test_filter_recipes(self):
        response = self.client.get("/recipes/", query_params={"q": "cake"})
        self.assertEqual(response.json()["count"], 1)

        response = self.client.get("/recipes/", query_params={"q": "nothing"})
        self.assertEqual(response.json()["count"], 0)

    def test_recipe_detail(self):
        response = self.client.get(f"/recipes/{self.recipe.id}")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["name"], "Test Cake")
        self.assertEqual(len(payload["ingredients"]), 2)
        self.assertEqual(payload["ingredients"][0]["ingredient"]["name"], "Flour")
        self.assertEqual(payload["nutrition"]["kcal"], 250)

    def test_recipe_detail_missing(self):
        response = self.client.get("/recipes/999999")
        self.assertEqual(response.status_code, 404)

    def test_recipe_detail_by_slug(self):
        response = self.client.get("/recipes/slug/test-cake")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["name"], "Test Cake")

    def test_stats(self):
        response = self.client.get("/stats")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["recipes"], 1)
        self.assertEqual(payload["ingredients"], 2)
        self.assertEqual(payload["collections"], 1)
        self.assertEqual(payload["categories"], [{"category": "dessert", "count": 1}])

    def test_list_ingredients(self):
        response = self.client.get("/ingredients/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 2)

    def test_ingredient_detail(self):
        response = self.client.get(f"/ingredients/{self.flour.id}")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["name"], "Flour")
        self.assertEqual(payload["aliases"], ["all-purpose flour"])
