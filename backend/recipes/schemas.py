from datetime import date

from ninja import Schema


class IngredientOut(Schema):
    id: int
    name: str
    category: str


class IngredientMeasureOut(Schema):
    id: int
    measure: str
    source_label: str
    amount: float
    gram_weight: float
    sequence: int


class IngredientNutritionOut(Schema):
    id: int
    kcal: float | None = None
    protein_g: float | None = None
    carbs_g: float | None = None
    fat_g: float | None = None
    fiber_g: float | None = None
    serving_size_g: float
    source: str
    source_id: str
    publication_date: date | None = None


class IngredientDetailOut(IngredientOut):
    aliases: list[str]
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
    contributor: str
    source: str
    source_url: str
    source_title: str
    source_year: str
    collection: str
    license: str


class RecipeDetailOut(RecipeListOut):
    directions: str
    attribution: str
    ingredients: list[RecipeIngredientOut]
    nutrition: NutritionOut | None = None


class CategoryCountOut(Schema):
    category: str
    count: int


class StatsOut(Schema):
    recipes: int
    ingredients: int
    collections: int
    categories: list[CategoryCountOut]
