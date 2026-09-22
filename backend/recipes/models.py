from django.db import models


class Ingredient(models.Model):
    name = models.CharField(max_length=100, unique=True)
    aliases = models.JSONField(default=list, blank=True)
    category = models.CharField(max_length=50, blank=True)

    def __str__(self):
        return self.name


class Recipe(models.Model):
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    servings = models.PositiveIntegerField(default=1)
    prep_mins = models.PositiveIntegerField()
    cook_mins = models.PositiveIntegerField()
    tags = models.JSONField(default=list, blank=True)


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
