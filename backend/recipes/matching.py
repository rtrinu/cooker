"""Match a recipe card's ingredient name to a USDA food.

Card names and USDA names are written from opposite ends. A card says
``"Fresh granny smith apples, peeled, cored, cubed"`` -- preparation first,
food last -- while USDA writes ``"Apples, granny smith, with skin, raw"`` --
food first, attributes after. Nothing here trusts a single wording: the
strategies run cheapest and most certain first (exact, casefold, alias) and
only fall back on token overlap when those miss.

Only ingredients that carry nutrition are worth *fuzzy*-matching. A
nutritionless row would resolve a line to nothing useful, so the fuzzy
strategies draw candidates from nutrition-bearing rows alone; the exact and
alias checks still see every row so a re-import reuses what it created.
"""

import re
from collections import namedtuple

from .models import Ingredient

# Words a card uses that never help identify the food. Preparation verbs and
# presentation adjectives belong here; words that name a *form* of the food
# ("ground", "whole", "part-skim") do not, because confusing ground chicken
# with chicken breast would corrupt the nutrition rather than merely miss it.
STOPWORDS = frozenset({
    "fresh", "frozen", "canned", "dried", "raw", "cooked", "prepared",
    "chopped", "diced", "sliced", "minced", "shredded", "peeled", "cored",
    "cubed", "grated", "crushed", "halved", "quartered", "rinsed",
    "drained", "seeded", "trimmed", "patted", "thawed", "softened", "melted",
    "and", "or", "with", "without", "of", "the", "a", "an", "plus", "for",
    "to", "in", "on", "into", "cut", "bite", "size", "strip", "strips",
    "floret", "florets", "leaf", "leaves", "optional", "finely", "coarsely",
    "thinly", "roughly", "well", "lightly", "about", "into",
})

Token = re.compile(r"[a-z0-9]+")

Match = namedtuple("Match", ("ingredient", "strategy", "score"))


def tokenize(text):
    """Lowercase word tokens, footnotes and punctuation dropped."""
    return Token.findall(str(text or "").casefold())


def significant(tokens):
    """Tokens minus preparation/qualifier noise, keeping order and repeats."""
    return [token for token in tokens if token not in STOPWORDS]


def head_noun(name):
    """The food word USDA puts first: ``"Apples, gala, raw"`` -> ``"apples"``."""
    tokens = significant(tokenize(name))
    return tokens[0] if tokens else ""


def usda_reversed(name):
    """USDA's ``"Apples, gala, with skin, raw"`` as ``"apples gala raw"``.

    Both sides of a comma run keep their order; the significance filter trims
    the preparation words on both.
    """
    return " ".join(significant(tokenize(name)))


def jaccard(left, right):
    """Overlap of two token sets, 0.0 when either is empty."""
    if not left or not right:
        return 0.0
    union = left | right
    return len(left & right) / len(union) if union else 0.0


class IngredientIndex:
    """Ingredient names indexed for the match strategies.

    Exact, casefold and alias lookup covers every row; the token and head-noun
    pools cover only nutrition-bearing rows. Building the index costs a few
    queries and a token pass per ingredient, so one index serves a whole
    import run.
    """

    def __init__(self, ingredients=None):
        if ingredients is None:
            ingredients = Ingredient.objects.all().prefetch_related("nutrition")
        self.ingredients = list(ingredients)
        self.by_name = {}
        self.by_casefold = {}
        self.by_alias = {}
        self.by_head = {}
        self.token_sets = {}
        self.nutrition_ids = set()
        for ingredient in self.ingredients:
            name = ingredient.name
            self.by_name.setdefault(name, ingredient)
            self.by_casefold.setdefault(name.casefold(), ingredient)
            for alias in ingredient.aliases or []:
                self.by_alias.setdefault(str(alias).casefold(), ingredient)
            # Only ingredients with nutrition are worth fuzzy-matching: a
            # nutritionless row resolves a line to nothing useful, so the
            # fuzzy pools below are built from nutrition-bearing rows alone.
            if not ingredient.nutrition.all():
                continue
            self.nutrition_ids.add(ingredient.pk)
            head = head_noun(name)
            if head:
                self.by_head.setdefault(head, []).append(ingredient)
            self.token_sets[ingredient.pk] = set(significant(tokenize(name)))

        self.fuzzy = [i for i in self.ingredients if i.pk in self.nutrition_ids]

    def match(self, name, threshold=0.6):
        """Best ``Match`` for ``name``, or None when nothing is close enough.

        Strategies run in order and the first hit wins: a certain match is
        never overridden by a fuzzy one, because a wrong ingredient quietly
        poisons the per-serving nutrition while a miss is visible.
        """
        normalized = " ".join(str(name or "").split())
        if not normalized:
            return None

        found = self.by_name.get(normalized)
        if found is not None:
            return Match(found, "exact", 1.0)

        found = self.by_casefold.get(normalized.casefold())
        if found is not None:
            return Match(found, "casefold", 1.0)

        found = self.by_alias.get(normalized.casefold())
        if found is not None:
            return Match(found, "alias", 1.0)

        card_tokens = significant(tokenize(normalized))
        card_set = set(card_tokens)
        if not card_set:
            return None

        # Token set: every significant card token appears in the candidate.
        # This is stronger than Jaccard and picks "Apples, gala, raw" over the
        # many apple rows a fuzzy score would tie.
        head = head_noun(normalized)
        candidates = self.by_head.get(head, self.fuzzy)
        best = None
        for ingredient in candidates:
            candidate_tokens = self.token_sets[ingredient.pk]
            if not candidate_tokens:
                continue
            if card_set <= candidate_tokens:
                # A generic card ("cooked diced chicken") is contained in many
                # rows; the head noun has to be one of them or the match is a
                # guess at the food's form rather than its identity.
                if head and head not in candidate_tokens:
                    continue
                score = len(card_set) / len(candidate_tokens)
                if best is None or score > best.score:
                    best = Match(ingredient, "token-set", score)
        if best is not None and best.score >= threshold:
            return best

        # USDA reversed: compare the card's significant tokens with USDA's,
        # reading both food-first. Catches reorderings like "garbanzo beans
        # canned" against "chickpeas (garbanzo beans), canned".
        card_phrase = usda_reversed(normalized)
        best = None
        for ingredient in candidates:
            candidate_phrase = usda_reversed(ingredient.name)
            if candidate_phrase == card_phrase:
                return Match(ingredient, "usda-reversed", 1.0)
            score = jaccard(card_set, self.token_sets[ingredient.pk])
            if best is None or score > best.score:
                best = Match(ingredient, "jaccard", score)
        if best is not None and best.score >= threshold:
            return best
        return None

    def suggest(self, name, limit=3, threshold=0.3):
        """Top ``limit`` fuzzy candidates for ``name``, best first.

        Used only by ``--report``: an unresolved line is one :meth:`match`
        declined, so the suggestions are shown to a human who can decide
        whether to seed an alias, never applied automatically.
        """
        normalized = " ".join(str(name or "").split())
        card_set = set(significant(tokenize(normalized)))
        if not card_set:
            return []
        scored = []
        for ingredient in self.fuzzy:
            candidate_tokens = self.token_sets.get(ingredient.pk)
            if not candidate_tokens:
                continue
            score = jaccard(card_set, candidate_tokens)
            if score >= threshold:
                scored.append(Match(ingredient, "suggest", score))
        scored.sort(key=lambda match: match.score, reverse=True)
        return scored[:limit]
