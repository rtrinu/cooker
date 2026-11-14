from datetime import date, datetime

from ninja import Schema


class IngredientOut(Schema):
    id: int
    name: str
    category: str
    processing_status: str


class IngredientMeasureOut(Schema):
    id: int
    measure: str
    source_label: str
    amount: float
    gram_weight: float
    sequence: int
    measurement_system: str
    preparation_state: str
    conversion_source: str
    confidence: float | None = None


class IngredientNutritionOut(Schema):
    id: int
    kcal: float | None = None
    protein_g: float | None = None
    carbs_g: float | None = None
    fat_g: float | None = None
    fiber_g: float | None = None
    saturated_fat_g: float | None = None
    sugar_g: float | None = None
    sodium_mg: float | None = None
    serving_size_g: float
    source: str
    source_id: str
    publication_date: date | None = None
    confidence: float | None = None
    verification_status: str
    retrieved_at: datetime | None = None
    license: str
    attribution: str


class IngredientDetailOut(IngredientOut):
    aliases: list[str]
    processing_error: str
    processed_at: datetime | None = None
    measures: list[IngredientMeasureOut]
    nutrition: list[IngredientNutritionOut]


class RecipeIngredientOut(Schema):
    id: int
    ingredient: IngredientOut
    quantity_text: str
    raw_text: str
    position: int


class NutritionOut(Schema):
    kcal: float
    protein_g: float
    carbs_g: float
    fat_g: float
    fiber_g: float
    method: str
    lines_used: int = 0
    lines_total: int = 0


class RecipeListOut(Schema):
    id: int
    slug: str | None = None
    name: str
    description: str
    servings: int | None = None
    serving_size: str
    prep_mins: int | None = None
    cook_mins: int | None = None
    tags: list[str]
    category: str
    cuisine: str
    contributor: str
    source: str
    source_url: str
    source_title: str
    source_year: str
    collection: str
    license: str
    nutrition: NutritionOut | None = None


class RecipeDetailOut(RecipeListOut):
    directions: str
    attribution: str
    ingredients: list[RecipeIngredientOut]


class FinderRecipeOut(Schema):
    recipe: RecipeListOut
    matched: list[str]
    missing: list[str]
    matched_ingredients: int
    total_ingredients: int
    pantry_coverage: float


class FinderOut(Schema):
    count: int
    ingredients: list[str]
    unmatched: list[str]
    items: list[FinderRecipeOut]


class CategoryCountOut(Schema):
    category: str
    count: int


class CuisineCountOut(Schema):
    cuisine: str
    count: int


class StatsOut(Schema):
    recipes: int
    ingredients: int
    ingredients_total: int
    collections: int
    categories: list[CategoryCountOut]
    cuisines: list[CuisineCountOut]
