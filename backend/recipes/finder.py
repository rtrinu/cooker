"""Rank recipes by how much of a pantry the user already has.

The matcher here is deliberately broader than the import matcher. Import has
to be certain because a wrong match poisons nutrition; the finder only has to
decide whether a recipe uses something the user typed. A pantry term counts
when its significant tokens are a subset of an ingredient's tokens or the
other way round, so ``sugar`` finds ``white sugar`` and ``chicken breast``
finds ``chicken``.
"""

from dataclasses import dataclass, field

from .matching import significant, tokenize


@dataclass(frozen=True)
class PantryTerm:
    display: str
    tokens: frozenset[str]


@dataclass
class FinderHit:
    recipe: object
    matched: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    matched_ingredients: int = 0
    total_ingredients: int = 0

    @property
    def pantry_coverage(self):
        if not self.total_ingredients:
            return 0.0
        return self.matched_ingredients / self.total_ingredients


def pantry_terms(raw):
    """Split a comma-separated pantry into de-duplicated token sets."""
    terms = []
    seen = set()
    for chunk in str(raw or "").split(","):
        display = " ".join(chunk.split())
        tokens = frozenset(significant(tokenize(display)))
        if not tokens:
            continue
        key = tuple(sorted(tokens))
        if key in seen:
            continue
        seen.add(key)
        terms.append(PantryTerm(display, tokens))
    return terms


def ingredient_tokens(ingredient):
    """Significant tokens for an ingredient name and every alias it carries."""
    tokens = set(significant(tokenize(ingredient.name)))
    for alias in ingredient.aliases or []:
        tokens.update(significant(tokenize(alias)))
    return frozenset(tokens)


def terms_touch(left, right):
    """True when either token set describes the other, ignoring empty sets."""
    if not left or not right:
        return False
    return left <= right or right <= left


def find_recipes(recipes, raw_ingredients, page=1, page_size=20):
    """Return ``(result_count, total_recipes, items, unmatched)`` for a pantry.

    ``recipes`` is an iterable of ``Recipe`` objects with ``nutrition`` and
    ``ingredients__ingredient`` selected. Results are ranked by pantry terms
    matched first, then by the share of the recipe's distinct ingredients those
    terms cover, then by recipes that actually carry nutrition, so the macro
    cards at the top are the most useful ones.
    """
    terms = pantry_terms(raw_ingredients)
    if not terms:
        return 0, 0, [], []

    all_ingredient_tokens = {}
    matched_terms_seen = set()
    hits = []

    for recipe in recipes:
        lines = list(recipe.ingredients.all())
        matched = []
        recipe_token_sets = []
        ingredient_ids = set()
        for line in lines:
            ingredient_ids.add(line.ingredient_id)
            tokens = all_ingredient_tokens.get(line.ingredient_id)
            if tokens is None:
                tokens = ingredient_tokens(line.ingredient)
                all_ingredient_tokens[line.ingredient_id] = tokens
            recipe_token_sets.append((line, tokens))

        matched_ingredient_ids = set()
        missing = []
        missing_seen = set()
        for line, tokens in recipe_token_sets:
            line_matched = False
            for term in terms:
                if terms_touch(term.tokens, tokens):
                    line_matched = True
                    if term.display not in matched:
                        matched.append(term.display)
                    matched_terms_seen.add(term.display)
                    break
            if line_matched:
                matched_ingredient_ids.add(line.ingredient_id)
            else:
                key = line.ingredient.name.casefold()
                if key not in missing_seen:
                    missing_seen.add(key)
                    missing.append(line.ingredient.name)

        if matched_ingredient_ids:
            hits.append(
                FinderHit(
                    recipe=recipe,
                    matched=matched,
                    missing=missing,
                    matched_ingredients=len(matched_ingredient_ids),
                    total_ingredients=len(ingredient_ids),
                )
            )

    hits.sort(
        key=lambda hit: (
            -len(hit.matched),
            not hasattr(hit.recipe, "nutrition"),
            -hit.pantry_coverage,
            hit.recipe.name.casefold(),
        )
    )

    unmatched = [
        term.display for term in terms if term.display not in matched_terms_seen
    ]

    page = max(1, int(page or 1))
    page_size = min(50, max(1, int(page_size or 20)))
    start = (page - 1) * page_size
    return len(hits), len(recipes), hits[start : start + page_size], unmatched
