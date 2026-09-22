from django.contrib import admin
from .models import Recipe, Ingredient, RecipeIngredient, Nutrition, Substitution

admin.site.register([Recipe, Ingredient, Nutrition, Substitution])
