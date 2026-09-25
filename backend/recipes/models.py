from django.core.validators import MinValueValidator
from django.db import models


class Ingredient(models.Model):
    name = models.CharField(max_length=255, unique=True)
    aliases = models.JSONField(default=list, blank=True)
    category = models.CharField(max_length=50, blank=True)

    def __str__(self):
        return self.name


class IngredientNutrition(models.Model):
    ingredient = models.ForeignKey(
        Ingredient, on_delete=models.CASCADE, related_name="nutrition"
    )
    kcal = models.FloatField(validators=[MinValueValidator(0)])
    protein_g = models.FloatField(validators=[MinValueValidator(0)])
    carbs_g = models.FloatField(validators=[MinValueValidator(0)])
    fat_g = models.FloatField(validators=[MinValueValidator(0)])
    fiber_g = models.FloatField(default=0, validators=[MinValueValidator(0)])
    serving_size_g = models.FloatField(validators=[MinValueValidator(0)])
    source = models.CharField(max_length=200)
    source_id = models.CharField(max_length=200)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("ingredient", "source", "source_id"),
                name="unique_ingredient_nutrition_source",
            ),
            models.CheckConstraint(
                condition=models.Q(kcal__gte=0)
                & models.Q(protein_g__gte=0)
                & models.Q(carbs_g__gte=0)
                & models.Q(fat_g__gte=0)
                & models.Q(fiber_g__gte=0)
                & models.Q(serving_size_g__gt=0),
                name="ingredient_nutrition_valid_values",
            ),
        ]


class Recipe(models.Model):
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    servings = models.PositiveIntegerField(default=1)
    prep_mins = models.PositiveIntegerField()
    cook_mins = models.PositiveIntegerField()
    tags = models.JSONField(default=list, blank=True)

    def __str__(self):
        return self.name


class RecipeIngredient(models.Model):
    recipe = models.ForeignKey(
        Recipe, on_delete=models.CASCADE, related_name="ingredients"
    )
    ingredient = models.ForeignKey(Ingredient, on_delete=models.PROTECT)
    quantity_text = models.CharField(max_length=50)


class Nutrition(models.Model):
    recipe = models.OneToOneField(
        Recipe, on_delete=models.CASCADE, related_name="nutrition"
    )
    kcal = models.FloatField()
    protein_g = models.FloatField()
    carbs_g = models.FloatField()
    fat_g = models.FloatField()
    fiber_g = models.FloatField(default=0)


class Substitution(models.Model):
    from_ingredient = models.ForeignKey(
        Ingredient, on_delete=models.CASCADE, related_name="subs_out"
    )
    to_ingredient = models.ForeignKey(
        Ingredient, on_delete=models.CASCADE, related_name="subs_in"
    )
    swap_note = models.CharField(max_length=200, blank=True)
