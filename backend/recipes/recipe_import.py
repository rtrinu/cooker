"""Persist recipes extracted from Team Nutrition PDFs.

:func:`recipes.pdf.parse_pdf` returns plain dictionaries; this module is the
only place that turns them into rows. A recipe's slug is its identity key, so
re-importing the same card updates the recipe instead of duplicating it.

Ingredient names go through :mod:`recipes.matching` against the nutrition-
bearing part of the USDA import. A card name that matches an existing
ingredient is folded into that ingredient's ``aliases`` so the next import is
an exact hit; a card name that matches nothing is created on its own, because a
recipe is more useful with an unresolved nutrition line than with a missing
ingredient.

Nutrition comes from the card's printed "Nutrients Per Serving" panel when the
card has one, and only falls back to recomputing from USDA measures when it
does not.
"""

from collections import namedtuple

from django.db import transaction
from django.utils.text import slugify

from .matching import IngredientIndex
from .models import NUTRIENT_FIELDS, Ingredient, Nutrition, Recipe, RecipeIngredient
from .nutrition import compute
from .pdf import split_quantity

NAME_MAX_LENGTH = Ingredient._meta.get_field("name").max_length
QUANTITY_MAX_LENGTH = RecipeIngredient._meta.get_field("quantity_text").max_length

RecipeResult = namedtuple(
    "RecipeResult",
    ("created", "name", "slug", "ingredients", "unresolved", "unmatched"),
)


def slug_for(title):
    """Slug for ``title``, keeping distinct titles with the same slug apart.

    A slug already used by a recipe with the same title is *that* recipe, so a
    re-import lands on the same row. Only a slug claimed by a different title
    gets a numeric suffix.
    """
    base = slugify(title) or "recipe"
    slug = base
    index = 2
    while Recipe.objects.filter(slug=slug).exclude(name=title).exists():
        slug = f"{base}-{index}"
        index += 1
    return slug


def normalize_name(name):
    """Ingredient name with USDA's footnote marker and stray spacing removed."""
    text = " ".join(str(name or "").split())
    text = text.lstrip("*").strip()
    return text[:NAME_MAX_LENGTH].rstrip()


def _add_alias(ingredient, alias):
    """Append ``alias`` to an ingredient's alias list if it is new.

    Card names are recorded so a later import of the same card is an exact
    match, which is how the curated alias list grows without a hand-edited
    file.
    """
    alias = normalize_name(alias)
    if not alias or alias == ingredient.name:
        return
    aliases = list(ingredient.aliases or [])
    if any(str(existing).casefold() == alias.casefold() for existing in aliases):
        return
    aliases.append(alias)
    ingredient.aliases = aliases
    ingredient.save(update_fields=["aliases"])


def _resolve(name, index):
    """Return ``(ingredient, matched)`` for a card ``name``.

    A match against an existing ingredient records the card wording as an
    alias and reports ``matched`` True. A name with no match is created fresh
    and reported False so the caller can list it for a human to alias.
    """
    normalized = normalize_name(name)
    if not normalized:
        return None, True
    match = index.match(normalized)
    if match is not None:
        _add_alias(match.ingredient, normalized)
        return match.ingredient, True
    ingredient = Ingredient.objects.create(name=normalized)
    return ingredient, False


def _ingredient_lines(data):
    """Yield ``(quantity_text, name)`` for each extracted ingredient line."""
    for line in data.get("ingredients") or []:
        text = " ".join(str(line).split())
        if not text:
            continue
        quantity, name = split_quantity(text)
        if not name:
            quantity, name = "", text
        yield quantity[:QUANTITY_MAX_LENGTH], name


def _source_nutrition(data):
    """The printed panel as a Nutrition-ready dict, or None when absent.

    Only the five tracked fields are read; a card with no calorie line is
    treated as having no panel, because calories are the anchor of the panel.
    """
    nutrients = data.get("nutrients") or {}
    if "kcal" not in nutrients:
        return None
    values = {field: float(nutrients.get(field) or 0.0) for field in NUTRIENT_FIELDS}
    values["method"] = "source"
    return values


def save_recipe(data, slug=None, dry_run=False):
    """Create or update the recipe described by a ``parse_pdf`` dictionary."""
    title = " ".join(str(data.get("title") or "").split()) or "Untitled recipe"
    recipe_slug = slugify(slug) if slug else slug_for(title)
    recipe_slug = recipe_slug or "recipe"
    servings = data.get("servings") or 1
    serving_size = " ".join(str(data.get("serving_size") or "").split())
    directions = "\n".join(data.get("directions") or [])
    lines = list(_ingredient_lines(data))
    source_nutrition = _source_nutrition(data)

    if dry_run:
        return RecipeResult(
            not Recipe.objects.filter(slug=recipe_slug).exists(),
            title,
            recipe_slug,
            len(lines),
            [],
            [],
        )

    index = IngredientIndex()
    with transaction.atomic():
        recipe, created = Recipe.objects.get_or_create(
            slug=recipe_slug,
            defaults={"name": title},
        )
        recipe.name = title
        recipe.servings = servings
        recipe.serving_size = serving_size
        recipe.prep_mins = data.get("prep_mins")
        recipe.cook_mins = data.get("cook_mins")
        recipe.directions = directions
        recipe.save()

        RecipeIngredient.objects.filter(recipe=recipe).delete()
        pairs = []
        unmatched = []
        for position, (quantity, name) in enumerate(lines, start=1):
            ingredient, matched = _resolve(name, index)
            if ingredient is None:
                continue
            if not matched:
                unmatched.append((normalize_name(name), quantity))
            RecipeIngredient.objects.create(
                recipe=recipe,
                ingredient=ingredient,
                quantity_text=quantity,
                position=position,
            )
            pairs.append((ingredient, quantity))

        computed = compute(pairs, servings)
        if source_nutrition is not None:
            Nutrition.objects.update_or_create(
                recipe=recipe, defaults=source_nutrition
            )
        elif computed.lines_used:
            Nutrition.objects.update_or_create(
                recipe=recipe,
                defaults={**computed.per_serving, "method": "computed"},
            )
        else:
            Nutrition.objects.filter(recipe=recipe).delete()

    return RecipeResult(
        created,
        title,
        recipe_slug,
        len(lines),
        computed.unresolved,
        unmatched,
    )


def load_aliases(mapping):
    """Attach ``{card_name: usda_name}`` entries as ingredient aliases.

    The value names an existing USDA ingredient; the key is the card wording
    to fold into its alias list. A value that matches no ingredient is
    returned so the caller can report it rather than fail silently.
    """
    missing = []
    for card_name, usda_name in mapping.items():
        target = Ingredient.objects.filter(name=usda_name).first()
        if target is None:
            missing.append(usda_name)
            continue
        _add_alias(target, card_name)
    return missing


def reset_recipes():
    """Delete imported recipes and the junk ingredients they created.

    USDA rows are kept: an ingredient that carries nutrition is the import's
    ground truth. Only nutritionless, measureless ingredients -- the ones a
    card import invented for a name it could not match -- are removed, and
    only once no recipe refers to them.
    """
    Recipe.objects.all().delete()
    junk = (
        Ingredient.objects.filter(nutrition__isnull=True, measures__isnull=True)
        .filter(recipeingredient__isnull=True)
        .distinct()
    )
    removed = junk.count()
    junk.delete()
    return removed
