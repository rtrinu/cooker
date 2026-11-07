"""Cuisine taxonomy for imported recipe collections.

A recipe has two independent descriptors: ``category`` records which corpus
it came from (Classic or Modern), and ``cuisine`` records what kind of cooking
it is. Keeping them separate means a modern Spanish recipe and a historical
American one can both be filtered without pretending the source years are
comparable.

The Public Domain Recipes source tags dishes inconsistently (``Spanish`` and
``spanish``, ``Asian`` and ``asian``), so tags are lowercased and mapped
through an ordered table. More specific tags win over broader ones: a dish
tagged both ``indian`` and ``asian`` is South Asian, not East Asian.
"""

# Specific regional tags first; broad fallbacks last. The first tag found in a
# recipe's tag list determines its cuisine.
CUISINE_TAGS = (
    # East and South Asia before the generic "asian".
    ("chinese", "east-asian"),
    ("japanese", "east-asian"),
    ("korean", "east-asian"),
    ("taiwanese", "east-asian"),
    ("indian", "south-asian"),
    ("pakistani", "south-asian"),
    ("bangladeshi", "south-asian"),
    ("sri lankan", "south-asian"),
    ("sri-lankan", "south-asian"),
    ("nepali", "south-asian"),
    ("thai", "southeast-asian"),
    ("vietnamese", "southeast-asian"),
    ("filipino", "southeast-asian"),
    ("indonesian", "southeast-asian"),
    ("malaysian", "southeast-asian"),
    ("singaporean", "southeast-asian"),
    ("burmese", "southeast-asian"),
    ("cambodian", "southeast-asian"),
    ("laotian", "southeast-asian"),
    ("asian", "east-asian"),
    # Europe.
    ("italian", "italian"),
    ("french", "french"),
    ("spanish", "spanish"),
    ("portuguese", "portuguese"),
    ("greek", "greek"),
    ("english", "british"),
    ("british", "british"),
    ("scottish", "british"),
    ("welsh", "british"),
    ("irish", "irish"),
    ("german", "german"),
    ("austrian", "austrian"),
    ("swiss", "swiss"),
    ("dutch", "dutch"),
    ("belgian", "belgian"),
    ("swedish", "nordic"),
    ("norwegian", "nordic"),
    ("danish", "nordic"),
    ("finnish", "nordic"),
    ("icelandic", "nordic"),
    ("russian", "eastern-european"),
    ("ukrainian", "eastern-european"),
    ("polish", "eastern-european"),
    ("czech", "eastern-european"),
    ("slovak", "eastern-european"),
    ("hungarian", "eastern-european"),
    ("romanian", "eastern-european"),
    ("bulgarian", "eastern-european"),
    ("serbian", "eastern-european"),
    ("croatian", "eastern-european"),
    ("balkan", "eastern-european"),
    # Middle East, Africa, Central Asia.
    ("turkish", "middle-eastern"),
    ("lebanese", "middle-eastern"),
    ("israeli", "middle-eastern"),
    ("persian", "middle-eastern"),
    ("iranian", "middle-eastern"),
    ("arab", "middle-eastern"),
    ("moroccan", "african"),
    ("ethiopian", "african"),
    ("nigerian", "african"),
    ("south african", "african"),
    ("egyptian", "african"),
    ("african", "african"),
    ("georgian", "central-asian"),
    ("uzbek", "central-asian"),
    ("kazakh", "central-asian"),
    ("afghan", "central-asian"),
    # The Americas and Oceania.
    ("mexican", "mexican"),
    ("tex-mex", "mexican"),
    ("brazilian", "latin-american"),
    ("peruvian", "latin-american"),
    ("argentinian", "latin-american"),
    ("colombian", "latin-american"),
    ("chilean", "latin-american"),
    ("cuban", "caribbean"),
    ("jamaican", "caribbean"),
    ("puerto rican", "caribbean"),
    ("haitian", "caribbean"),
    ("caribbean", "caribbean"),
    ("cajun", "american"),
    ("creole", "american"),
    ("southern", "american"),
    ("pennsylvania", "american"),
    ("american", "american"),
    ("australian", "oceania"),
    ("new zealand", "oceania"),
    ("pacific", "oceania"),
    # Broad culinary traditions.
    ("mediterranean", "mediterranean"),
    ("global", "global"),
)

CUISINE_LABELS = {
    "italian": "Italian",
    "french": "French",
    "spanish": "Spanish",
    "portuguese": "Portuguese",
    "greek": "Greek",
    "british": "British",
    "irish": "Irish",
    "german": "German",
    "austrian": "Austrian",
    "swiss": "Swiss",
    "dutch": "Dutch",
    "belgian": "Belgian",
    "nordic": "Nordic",
    "eastern-european": "Eastern European",
    "middle-eastern": "Middle Eastern",
    "african": "African",
    "east-asian": "East Asian",
    "south-asian": "South Asian",
    "southeast-asian": "Southeast Asian",
    "central-asian": "Central Asian",
    "mexican": "Mexican",
    "latin-american": "Latin American",
    "caribbean": "Caribbean",
    "american": "American",
    "mediterranean": "Mediterranean",
    "oceania": "Oceania",
    "global": "Global",
}


def normalize_tags(tags):
    return [str(tag).strip().casefold() for tag in tags or [] if str(tag).strip()]


def cuisine_for_tags(tags):
    """Return the cuisine slug for a recipe's tags, or ``""`` when unknown."""
    normalized = set(normalize_tags(tags))
    for tag, cuisine in CUISINE_TAGS:
        if tag in normalized:
            return cuisine
    return ""


def cuisine_label(slug):
    return CUISINE_LABELS.get(slug, str(slug or "").replace("-", " ").title())
