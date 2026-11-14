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
        self.assertEqual(payload["items"][0]["nutrition"]["kcal"], 250)

    def test_finder_ranks_partial_matches(self):
        response = self.client.get(
            "/recipes/finder", query_params={"ingredients": "flour, salt"}
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["count"], 1)
        hit = payload["items"][0]
        self.assertEqual(hit["recipe"]["name"], "Test Cake")
        self.assertEqual(hit["matched"], ["flour"])
        self.assertEqual(hit["missing"], ["Sugar"])
        self.assertEqual(hit["matched_ingredients"], 1)
        self.assertEqual(hit["total_ingredients"], 2)
        self.assertEqual(payload["unmatched"], ["salt"])

    def test_finder_returns_nothing_for_unknown_ingredient(self):
        response = self.client.get(
            "/recipes/finder", query_params={"ingredients": "dragonfruit"}
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["count"], 0)
        self.assertEqual(payload["unmatched"], ["dragonfruit"])

    def test_ingredient_suggestions_only_include_used_ingredients(self):
        Ingredient.objects.create(name="Flour, unused", category="baking")
        response = self.client.get(
            "/ingredients/suggestions", query_params={"q": "flour"}
        )
        self.assertEqual(response.status_code, 200)
        names = [item["name"] for item in response.json()]
        self.assertEqual(names, ["Flour"])

    def test_filter_recipes(self):
        response = self.client.get("/recipes/", query_params={"q": "cake"})
        self.assertEqual(response.json()["count"], 1)

        response = self.client.get("/recipes/", query_params={"q": "nothing"})
        self.assertEqual(response.json()["count"], 0)

    def test_filter_recipes_by_nutrition(self):
        lean = Recipe.objects.create(name="Lean Salad", servings=1)
        Nutrition.objects.create(
            recipe=lean,
            kcal=180,
            protein_g=22,
            carbs_g=10,
            fat_g=5,
            fiber_g=3,
        )
        Recipe.objects.create(name="Unrated Soup", servings=1)

        response = self.client.get(
            "/recipes/", query_params={"kcal_max": 300, "protein_min": 20}
        )
        names = [item["name"] for item in response.json()["items"]]
        self.assertEqual(names, ["Lean Salad"])

        # Recipes without a nutrition row drop out once a bound is applied.
        response = self.client.get(
            "/recipes/", query_params={"kcal_max": 5000, "protein_min": 0}
        )
        names = [item["name"] for item in response.json()["items"]]
        self.assertEqual(names, ["Lean Salad", "Test Cake"])

    def test_filter_recipes_by_nutrition_boundaries(self):
        response = self.client.get(
            "/recipes/",
            query_params={
                "kcal_min": 250,
                "kcal_max": 250,
                "protein_min": 3,
                "protein_max": 3,
            },
        )
        self.assertEqual(response.json()["count"], 1)
        self.assertEqual(response.json()["items"][0]["name"], "Test Cake")

        response = self.client.get("/recipes/", query_params={"kcal_max": 100})
        self.assertEqual(response.json()["count"], 0)

        response = self.client.get("/recipes/", query_params={"protein_min": 50})
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
        self.assertEqual(payload["ingredients_total"], 2)
        self.assertEqual(payload["collections"], 1)
        self.assertEqual(payload["categories"], [{"category": "dessert", "count": 1}])

    def test_list_ingredients(self):
        response = self.client.get("/ingredients/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 2)

    def test_list_ingredients_excludes_unused_by_default(self):
        Ingredient.objects.create(name="Unused flour", category="baking")

        response = self.client.get("/ingredients/")
        names = [item["name"] for item in response.json()["items"]]
        self.assertEqual(response.json()["count"], 2)
        self.assertNotIn("Unused flour", names)

        response = self.client.get(
            "/ingredients/", query_params={"include_unused": "true"}
        )
        self.assertEqual(response.json()["count"], 3)

    def test_ingredient_detail(self):
        response = self.client.get(f"/ingredients/{self.flour.id}")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["name"], "Flour")
        self.assertEqual(payload["aliases"], ["all-purpose flour"])
