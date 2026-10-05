from django.core.validators import MinValueValidator
from django.db import models

NUTRIENT_FIELDS = ("kcal", "protein_g", "carbs_g", "fat_g", "fiber_g")


def nonnegative_or_null(field):
    """Constraint helper: a value is fine as long as it is not negative."""
    return models.Q(**{f"{field}__isnull": True}) | models.Q(**{f"{field}__gte": 0})


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
    kcal = models.FloatField(null=True, blank=True, validators=[MinValueValidator(0)])
    protein_g = models.FloatField(null=True, blank=True, validators=[MinValueValidator(0)])
    carbs_g = models.FloatField(null=True, blank=True, validators=[MinValueValidator(0)])
    fat_g = models.FloatField(null=True, blank=True, validators=[MinValueValidator(0)])
    fiber_g = models.FloatField(null=True, blank=True, validators=[MinValueValidator(0)])
    serving_size_g = models.FloatField(validators=[MinValueValidator(0)])
    source = models.CharField(max_length=200)
    source_id = models.CharField(max_length=200)
    publication_date = models.DateField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("ingredient", "source", "source_id"),
                name="unique_ingredient_nutrition_source",
            ),
            models.CheckConstraint(
                condition=models.Q(serving_size_g__gt=0)
                & nonnegative_or_null("kcal")
                & nonnegative_or_null("protein_g")
                & nonnegative_or_null("carbs_g")
                & nonnegative_or_null("fat_g")
                & nonnegative_or_null("fiber_g"),
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
