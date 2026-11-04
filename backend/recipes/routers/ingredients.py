from ninja import Router
from ninja.errors import HttpError
from ninja.pagination import PageNumberPagination, paginate

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
