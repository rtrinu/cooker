"""Ingredient naming and cleanup shared by the import commands.

USDA descriptions are written for a database, not a pantry: ``Alcoholic
Beverage, wine, table, red, Barbera`` is a red wine, and its category is
``Beverages``. This module rewrites those names into the item-first form the
finder and the ingredient list use, and identifies the USDA categories that
are not cooking ingredients at all.
"""

import re

UNWANTED_CATEGORIES = frozenset({"Restaurant Foods", "Fast Foods", "Baby Foods"})
ALCOHOLIC_CATEGORY = "Alcoholic Beverage"
ALCOHOLIC_PREFIX = re.compile(r"^alcoholic beverages?\s*,?\s*", re.I)
PROOF = re.compile(r"\b(?P<proof>\d+)\s*proof\b", re.I)


def should_skip_category(category):
    return str(category or "").strip() in UNWANTED_CATEGORIES


def _title(value):
    text = " ".join(str(value or "").split())
    if not text:
        return ""
    # Keep already-mixed-case variety names such as "Pinot Gris (Grigio)"
    # readable without shouting all-caps USDA brand entries.
    if text.isupper():
        text = text.title()
    return text[:1].upper() + text[1:]


def _proof(parts):
    match = PROOF.search(", ".join(parts))
    return f"{match.group('proof')} proof" if match else ""


def _wine(parts):
    rest = [part for part in parts if part.casefold() not in {"wine", "table"}]
    night = [part.casefold() for part in rest]
    if "rose" in night:
        return "Rose wine"
    if "cooking" in night:
        return "Cooking wine"
    if "light" in night:
        return "Light wine"
    if "dessert" in night:
        return "Sweet dessert wine" if "sweet" in night else (
            "Dry dessert wine" if "dry" in night else "Dessert wine"
        )
    color = next((part for part in rest if part.casefold() in {"red", "white"}), "")
    if not color:
        if "all" in night:
            return "Table wine"
        return "Wine"
    variety = [
        part
        for part in rest
        if part.casefold() not in {"red", "white", "all", "late harvest"}
    ]
    name = " ".join(_title(part) for part in variety).strip()
    if "late harvest" in night:
        name = f"Late harvest {name}".strip()
    if name:
        return f"{name} ({color.casefold()} wine)"
    return f"{color.title()} wine"


def _beer(parts):
    rest = [part for part in parts if part.casefold() != "beer"]
    night = [part.casefold() for part in rest]
    if any("hard lemonade" in part for part in night):
        return "Hard lemonade"
    brand = [
        part
        for part in rest
        if part.casefold() not in {"light", "regular", "all", "higher alcohol", "low carb"}
    ]
    name = " ".join(_title(part) for part in brand).strip()
    if "light" in night:
        if name:
            return f"{name} (light beer)"
        if "higher alcohol" in night:
            return "High-alcohol light beer"
        if "low carb" in night:
            return "Low-carb light beer"
        return "Light beer"
    if "higher alcohol" in night:
        return f"{name} (higher alcohol)".strip() if name else "Beer (higher alcohol)"
    if name:
        return f"{name} (beer)"
    return "Beer"


def _distilled(parts):
    proof = _proof(parts)
    rest = [part for part in parts if part.casefold() != "distilled"]
    spirit = next(
        (
            part
            for part in rest
            if part.casefold() in {"rum", "vodka", "whiskey", "whisky", "gin"}
        ),
        "",
    )
    if spirit:
        name = f"{_title(spirit)}"
    else:
        name = "Distilled spirits"
    return f"{name} ({proof})" if proof else name


def _liqueur(parts):
    proof = _proof(parts)
    rest = [part for part in parts if part.casefold() != "liqueur"]
    flavour = ", ".join(part for part in rest if not PROOF.search(part))
    if "coffee with cream" in flavour.casefold():
        name = "Coffee cream liqueur"
    elif "coffee" in flavour.casefold():
        name = "Coffee liqueur"
    else:
        name = f"{_title(flavour)} liqueur".strip()
    return f"{name} ({proof})" if proof else name


def _cocktail(parts, name):
    suffix = " ".join(parts[1:]).casefold()
    if "canned" in suffix:
        return f"Canned {name}"
    return name


def normalize_alcoholic_name(name):
    """Return the item-first name for a USDA alcoholic description.

    Non-alcoholic descriptions are returned unchanged. The replacements cover
    the USDA shapes present in the dataset; an unrecognised suffix keeps its
    words after the item instead of being dropped.
    """
    text = " ".join(str(name or "").split())
    match = ALCOHOLIC_PREFIX.match(text)
    if not match:
        return text
    body = text[match.end():].strip(" ,")
    if not body:
        return text
    parts = [part.strip() for part in body.split(",") if part.strip()]
    if not parts:
        return text
    head = parts[0].casefold()
    if head == "wine":
        return _wine(parts)
    if head == "beer":
        return _beer(parts)
    if head == "distilled":
        return _distilled(parts)
    if head == "liqueur":
        return _liqueur(parts)
    if head.startswith("rice") and "sake" in body.casefold():
        return "Sake"
    if head == "daiquiri":
        return _cocktail(parts, "Daiquiri")
    if head == "pina colada":
        return _cocktail(parts, "Pina colada")
    if head == "tequila sunrise":
        return _cocktail(parts, "Tequila sunrise")
    if head == "whiskey sour":
        return "Whiskey sour"
    if head == "malt beer":
        return "Hard lemonade" if "lemonade" in body.casefold() else "Malt beer"
    proof = _proof(parts)
    if proof:
        return f"{_title(' '.join(parts[:-1]))} ({proof})"
    suffix = ", ".join(_title(part) for part in parts[1:])
    return f"{_title(parts[0])} ({suffix})" if suffix else _title(parts[0])


def normalize_ingredient(name, category=""):
    """Return ``(name, category)`` with alcoholic rows made item-first."""
    text = " ".join(str(name or "").split())
    normalized = normalize_alcoholic_name(text)
    if normalized != text:
        return normalized, ALCOHOLIC_CATEGORY
    lowered = text.casefold()
    if lowered == "beverages, amber, hard cider":
        return "Hard cider", ALCOHOLIC_CATEGORY
    if lowered == "rice (sake)":
        return "Sake", ALCOHOLIC_CATEGORY
    if lowered == "beverages, malt liquor beverage":
        return "Malt liquor", ALCOHOLIC_CATEGORY
    if lowered == "beverages, wine, non-alcoholic":
        return "Non-alcoholic wine", category
    if lowered.startswith("beverages, whiskey sour mix"):
        if lowered.endswith("bottled"):
            return "Whiskey sour mix (bottled)", category
        if lowered.endswith("powder"):
            return "Whiskey sour mix (powder)", category
    return text, category
