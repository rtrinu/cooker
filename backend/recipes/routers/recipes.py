from ninja import Router
from ninja.errors import HttpError
from ninja.pagination import PageNumberPagination, paginate

from ..finder import find_recipes, pantry_terms
from ..models import Recipe
from ..schemas import FinderOut, RecipeDetailOut, RecipeListOut

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
    cuisine: str | None = None,
    contributor: str | None = None,
    tag: str | None = None,
    kcal_min: float | None = None,
    kcal_max: float | None = None,
    protein_min: float | None = None,
    protein_max: float | None = None,
):
    recipes = Recipe.objects.select_related("nutrition").order_by("name")
    if q:
        recipes = recipes.filter(name__icontains=q)
    if category:
        recipes = recipes.filter(category=category)
    if cuisine:
        recipes = recipes.filter(cuisine=cuisine)
    if contributor:
        recipes = recipes.filter(contributor__icontains=contributor)
    if tag:
        # JSONField containment is not supported on SQLite, so fall back to a
        # text match against the serialized list. Good enough for filtering.
        recipes = recipes.filter(tags__icontains=tag)
    if kcal_min is not None:
        recipes = recipes.filter(nutrition__kcal__gte=kcal_min)
    if kcal_max is not None:
        recipes = recipes.filter(nutrition__kcal__lte=kcal_max)
    if protein_min is not None:
        recipes = recipes.filter(nutrition__protein_g__gte=protein_min)
    if protein_max is not None:
        recipes = recipes.filter(nutrition__protein_g__lte=protein_max)
    return recipes


@router.get("/finder", response=FinderOut)
def find_by_ingredients(
    request,
    ingredients: str,
    page: int = 1,
    page_size: int = 20,
):
    recipes = Recipe.objects.select_related("nutrition").prefetch_related(
        "ingredients__ingredient"
    )
    count, _, hits, unmatched = find_recipes(
        recipes, ingredients, page=page, page_size=page_size
    )
    return {
        "count": count,
        "ingredients": [term.display for term in pantry_terms(ingredients)],
        "unmatched": unmatched,
        "items": [
            {
                "recipe": hit.recipe,
                "matched": hit.matched,
                "missing": hit.missing,
                "matched_ingredients": hit.matched_ingredients,
                "total_ingredients": hit.total_ingredients,
                "pantry_coverage": hit.pantry_coverage,
            }
            for hit in hits
        ],
    }


@router.get("/slug/{slug}", response=RecipeDetailOut)
def get_recipe_by_slug(request, slug: str):
    return get_recipe_or_404(slug=slug)


@router.get("/{recipe_id}", response=RecipeDetailOut)
def get_recipe(request, recipe_id: int):
    return get_recipe_or_404(id=recipe_id)
