from django.contrib import admin
from .models import (
    Ingredient,
    IngredientMeasure,
    IngredientNutrition,
    Nutrition,
    Recipe,
    RecipeIngredient,
    Substitution,
)


class IngredientMeasureInline(admin.TabularInline):
    model = IngredientMeasure
    extra = 0
    fields = ("measure", "source_label", "amount", "gram_weight", "sequence")


@admin.register(Ingredient)
class IngredientAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "aliases")
    list_filter = ("category",)
    search_fields = ("name",)
    inlines = [IngredientMeasureInline]


@admin.register(IngredientMeasure)
class IngredientMeasureAdmin(admin.ModelAdmin):
    list_display = ("ingredient", "measure", "amount", "gram_weight", "sequence")
    search_fields = ("ingredient__name", "source_label")


@admin.register(IngredientNutrition)
class IngredientNutritionAdmin(admin.ModelAdmin):
    list_display = (
        "ingredient",
        "serving_size_g",
        "kcal",
        "protein_g",
        "carbs_g",
        "fat_g",
        "fiber_g",
        "source",
        "source_id",
    )
    list_filter = ("source",)
    search_fields = ("ingredient__name", "source_id")


class RecipeIngredientInline(admin.TabularInline):
    model = RecipeIngredient
    extra = 1
    autocomplete_fields = ("ingredient",)
    fields = ("ingredient", "quantity_text", "position")


class NutritionInline(admin.TabularInline):
    model = Nutrition
    max_num = 1
    extra = 1
    fields = ("kcal", "protein_g", "carbs_g", "fat_g", "fiber_g", "method")


@admin.register(Substitution)
class SubstitutionAdmin(admin.ModelAdmin):
    list_display = ("from_ingredient", "to_ingredient", "swap_note")
    search_fields = ("from_ingredient__name", "to_ingredient__name")
    autocomplete_fields = ("from_ingredient", "to_ingredient")


@admin.register(Recipe)
class RecipeAdmin(admin.ModelAdmin):
    list_display = ("name", "servings", "total_time", "kcal", "protein_g", "tag_list")
    list_filter = ("category",)
    search_fields = ("name", "slug")
    inlines = [RecipeIngredientInline, NutritionInline]

    @admin.display(description="total time")
    def total_time(self, obj):
        if obj.prep_mins is None or obj.cook_mins is None:
            return "\u2014"
        return f"{obj.prep_mins + obj.cook_mins} min"

    @admin.display(description="kcal")
    def kcal(self, obj):
        n = getattr(obj, "nutrition", None)
        return n.kcal if n else "\u2014"

    @admin.display(description="protein g")
    def protein_g(self, obj):
        n = getattr(obj, "nutrition", None)
        return n.protein_g if n else "\u2014"

    @admin.display(description="tags")
    def tag_list(self, obj):
        return ", ".join(obj.tags)
