from ninja import NinjaAPI

from django.db.models import Count

from .models import Ingredient, Recipe
from .routers import ingredients, recipes
from .schemas import StatsOut

api = NinjaAPI(
    title="Cooker API",
    version="1.0.0",
    description="Read-only API for the recipe archive.",
)

api.add_router("/recipes", recipes.router)
api.add_router("/ingredients", ingredients.router)


@api.get("/health", tags=["meta"])
def health(request):
    return {"ok": True}


@api.get("/stats", response=StatsOut, tags=["meta"])
def stats(request):
    return {
        "recipes": Recipe.objects.count(),
        "ingredients": Ingredient.objects.count(),
        "collections": Recipe.objects.exclude(collection="")
        .values("collection")
        .distinct()
        .count(),
        "categories": list(
            Recipe.objects.exclude(category="")
            .values("category")
            .annotate(count=Count("id"))
            .order_by("-count", "category")
        ),
    }
