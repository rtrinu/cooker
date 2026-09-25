from django.contrib import admin
from .models import (
    Ingredient,
    IngredientNutrition,
    Nutrition,
    Recipe,
    RecipeIngredient,
    Substitution,
)


@admin.register(Ingredient)
class IngredientAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "aliases")
    list_filter = ("category",)
    search_fields = ("name",)


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


class NutritionInline(admin.TabularInline):
    model = Nutrition
    max_num = 1
    extra = 1
    fields = ("kcal", "protein_g", "carbs_g", "fat_g", "fiber_g")


@admin.register(Substitution)
class SubstitutionAdmin(admin.ModelAdmin):
    list_display = ("from_ingredient", "to_ingredient", "swap_note")
    search_fields = ("from_ingredient__name", "to_ingredient__name")
    autocomplete_fields = ("from_ingredient", "to_ingredient")


@admin.register(Recipe)
class RecipeAdmin(admin.ModelAdmin):
    list_display = ("name", "servings", "total_time", "kcal", "protein_g", "tag_list")
    search_fields = ("name",)
    inlines = [RecipeIngredientInline, NutritionInline]

    @admin.display(description="total time")
    def total_time(self, obj):
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
