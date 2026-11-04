from ninja import Router
from ninja.errors import HttpError
from ninja.pagination import PageNumberPagination, paginate

from ..models import Recipe
from ..schemas import RecipeDetailOut, RecipeListOut

router = Router(tags=["recipes"])


def get_recipe_or_404(**lookup):
    recipe = (
        Recipe.objects.select_related("nutrition")
        .prefetch_related("ingredients__ingredient")
        .filter(**lookup)
        .first()
    )
    if recipe is None:
        raise HttpError(404, "Recipe not found")
    return recipe


@router.get("/", response=list[RecipeListOut])
@paginate(PageNumberPagination, page_size=20)
def list_recipes(
    request,
    q: str | None = None,
    category: str | None = None,
    contributor: str | None = None,
    tag: str | None = None,
):
    recipes = Recipe.objects.order_by("name")
    if q:
        recipes = recipes.filter(name__icontains=q)
    if category:
        recipes = recipes.filter(category=category)
    if contributor:
        recipes = recipes.filter(contributor__icontains=contributor)
    if tag:
        # JSONField containment is not supported on SQLite, so fall back to a
        # text match against the serialized list. Good enough for filtering.
        recipes = recipes.filter(tags__icontains=tag)
    return recipes


@router.get("/slug/{slug}", response=RecipeDetailOut)
def get_recipe_by_slug(request, slug: str):
    return get_recipe_or_404(slug=slug)


@router.get("/{recipe_id}", response=RecipeDetailOut)
def get_recipe(request, recipe_id: int):
    return get_recipe_or_404(id=recipe_id)
