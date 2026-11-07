from ninja import Router
from ninja.errors import HttpError
from ninja.pagination import PageNumberPagination, paginate

from django.db.models.functions import Length

from ..models import Ingredient
from ..schemas import IngredientDetailOut, IngredientOut

router = Router(tags=["ingredients"])


@router.get("/", response=list[IngredientOut])
@paginate(PageNumberPagination, page_size=20)
def list_ingredients(
    request,
    q: str | None = None,
    category: str | None = None,
):
    ingredients = Ingredient.objects.order_by("name")
    if q:
        ingredients = ingredients.filter(name__icontains=q)
    if category:
        ingredients = ingredients.filter(category=category)
    return ingredients


@router.get("/suggestions", response=list[IngredientOut])
def suggest_ingredients(request, q: str = "", limit: int = 12):
    """Autocomplete limited to ingredients some recipe actually uses.

    The USDA import adds thousands of foods nobody can cook with on their own
    (babyfood, restaurant items); sending those to the pantry input would make
    the suggestion list useless.
    """
    text = " ".join(q.split())
    if not text:
        return []
    limit = max(1, min(20, limit))
    rows = list(
        Ingredient.objects.filter(
            recipeingredient__isnull=False, name__icontains=text
        )
        .annotate(name_length=Length("name"))
        .order_by("name_length", "name")
        .distinct()[: limit * 4]
    )
    # Recipe cards often carry compound lines ("sugar and butter each"); they
    # are useful in a recipe but not in a pantry autocomplete.
    return [
        ingredient
        for ingredient in rows
        if not any(
            marker in ingredient.name.casefold()
            for marker in (" and ", " or ", " each", " with ")
        )
    ][:limit]


@router.get("/{ingredient_id}", response=IngredientDetailOut)
def get_ingredient(request, ingredient_id: int):
    ingredient = (
        Ingredient.objects.prefetch_related("measures", "nutrition")
        .filter(id=ingredient_id)
        .first()
    )
    if ingredient is None:
        raise HttpError(404, "Ingredient not found")
    return ingredient
