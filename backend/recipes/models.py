from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

# The five nutrients recipe totals have always used. Keeping aggregation on
# this tuple means adding a stored nutrient cannot silently change an existing
# calorie or macro figure.
NUTRIENT_FIELDS = ("kcal", "protein_g", "carbs_g", "fat_g", "fiber_g")
# Nutrients stored per ingredient but not yet rolled into recipe panels.
EXTENDED_NUTRIENT_FIELDS = ("saturated_fat_g", "sugar_g", "sodium_mg")
INGREDIENT_NUTRIENT_FIELDS = NUTRIENT_FIELDS + EXTENDED_NUTRIENT_FIELDS

VERIFICATION_STATUSES = (
    ("unverified", "unverified"),
    ("estimated", "estimated"),
    ("verified", "verified"),
)

PROCESSING_STATUSES = (
    ("pending", "pending"),
    ("processing", "processing"),
    ("matched", "matched"),
    ("needs_review", "needs review"),
    ("unavailable", "unavailable"),
    ("failed", "failed"),
)

MEASUREMENT_SYSTEMS = (
    ("us", "US customary"),
    ("metric", "metric"),
    ("imperial", "imperial"),
    ("unspecified", "unspecified"),
)


def nonnegative_or_null(field):
    """Constraint helper: a value is fine as long as it is not negative."""
    return models.Q(**{f"{field}__isnull": True}) | models.Q(**{f"{field}__gte": 0})


def confidence_or_null(field):
    """Constraint helper: confidence, when present, is a 0..1 score."""
    return models.Q(**{f"{field}__isnull": True}) | (
        models.Q(**{f"{field}__gte": 0}) & models.Q(**{f"{field}__lte": 1})
    )


class Ingredient(models.Model):
    name = models.CharField(max_length=255, unique=True)
    aliases = models.JSONField(default=list, blank=True)
    category = models.CharField(max_length=50, blank=True)
    # State of the automated nutrition lookup for this ingredient. A row with
    # an explicit nutrition record is ``matched``; a failure stays visible
    # rather than looking like an ingredient with no data.
    processing_status = models.CharField(
        max_length=20, choices=PROCESSING_STATUSES, default="pending", db_index=True
    )
    processing_error = models.TextField(blank=True)
    processed_at = models.DateTimeField(null=True, blank=True)

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
    saturated_fat_g = models.FloatField(
        null=True, blank=True, validators=[MinValueValidator(0)]
    )
    sugar_g = models.FloatField(null=True, blank=True, validators=[MinValueValidator(0)])
    sodium_mg = models.FloatField(null=True, blank=True, validators=[MinValueValidator(0)])
    serving_size_g = models.FloatField(validators=[MinValueValidator(0)])
    source = models.CharField(max_length=200)
    source_id = models.CharField(max_length=200)
    publication_date = models.DateField(null=True, blank=True)
    # How sure the automated matcher is that this record describes the
    # ingredient, kept separate from measurement-conversion confidence.
    confidence = models.FloatField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(1)],
    )
    verification_status = models.CharField(
        max_length=20, choices=VERIFICATION_STATUSES, default="unverified"
    )
    retrieved_at = models.DateTimeField(null=True, blank=True)
    # Licence terms travel with the record so a commercial deployment can
    # show attribution and know which obligations apply to each source.
    license = models.CharField(max_length=100, blank=True)
    attribution = models.TextField(blank=True)

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
                & nonnegative_or_null("fiber_g")
                & nonnegative_or_null("saturated_fat_g")
                & nonnegative_or_null("sugar_g")
                & nonnegative_or_null("sodium_mg")
                & (confidence_or_null("confidence")),
                name="ingredient_nutrition_valid_values",
            ),
        ]


class IngredientMeasure(models.Model):
    """One household measure of an ingredient, from the USDA foodPortions table.

    ``amount`` of ``measure`` weighs ``gram_weight`` grams, so a recipe asking
    for 2 cups converts with ``2 * gram_weight / amount``. Derived from the
    dataset and replaced wholesale on re-import.
    """

    ingredient = models.ForeignKey(
        Ingredient, on_delete=models.CASCADE, related_name="measures"
    )
    measure = models.CharField(max_length=50)
    source_label = models.CharField(max_length=100, blank=True)
    amount = models.FloatField()
    gram_weight = models.FloatField()
    sequence = models.PositiveIntegerField(default=1)
    measurement_system = models.CharField(
        max_length=20, choices=MEASUREMENT_SYSTEMS, default="unspecified"
    )
    preparation_state = models.CharField(max_length=50, blank=True)
    conversion_source = models.CharField(max_length=100, blank=True)
    # Confidence in this gram conversion, separate from nutrition confidence.
    confidence = models.FloatField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(1)],
    )

    class Meta:
        ordering = ("ingredient", "sequence")
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gt=0)
                & models.Q(gram_weight__gt=0)
                & (confidence_or_null("confidence")),
                name="ingredient_measure_valid_values",
            ),
        ]

    def __str__(self):
        label = self.source_label or self.measure
        return f"{self.amount:g} {label} = {self.gram_weight:g} g"


class Recipe(models.Model):
    slug = models.CharField(max_length=200, unique=True, null=True, blank=True)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    servings = models.PositiveIntegerField(default=1, null=True, blank=True)
    serving_size = models.CharField(max_length=100, blank=True)
    prep_mins = models.PositiveIntegerField(null=True, blank=True)
    cook_mins = models.PositiveIntegerField(null=True, blank=True)
    tags = models.JSONField(default=list, blank=True)
    category = models.CharField(max_length=50, blank=True)
    cuisine = models.CharField(max_length=50, blank=True, db_index=True)
    contributor = models.CharField(max_length=100, blank=True)
    source_url = models.URLField(blank=True)
    directions = models.TextField(blank=True)

    # Provenance for imported corpora. ``source`` and ``source_id`` identify a
    # recipe in the source system, so re-imports update instead of duplicating.
    # Both stay blank for recipes that were entered by hand or came from a PDF.
    source = models.CharField(max_length=50, blank=True, db_index=True)
    source_id = models.CharField(max_length=200, blank=True)
    source_title = models.CharField(max_length=300, blank=True)
    source_year = models.CharField(max_length=20, blank=True)
    license = models.CharField(max_length=50, blank=True)
    attribution = models.TextField(blank=True)
    collection = models.CharField(max_length=100, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("source", "source_id"),
                condition=~models.Q(source="") & ~models.Q(source_id=""),
                name="unique_recipe_source_id",
            ),
        ]

    def __str__(self):
        return self.name


class RecipeIngredient(models.Model):
    recipe = models.ForeignKey(
        Recipe, on_delete=models.CASCADE, related_name="ingredients"
    )
    ingredient = models.ForeignKey(Ingredient, on_delete=models.PROTECT)
    quantity_text = models.CharField(max_length=50)
    raw_text = models.TextField(blank=True)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("position",)


class Nutrition(models.Model):
    recipe = models.OneToOneField(
        Recipe, on_delete=models.CASCADE, related_name="nutrition"
    )
    kcal = models.FloatField()
    protein_g = models.FloatField()
    carbs_g = models.FloatField()
    fat_g = models.FloatField()
    fiber_g = models.FloatField(default=0)
    method = models.CharField(
        max_length=20,
        choices=(("computed", "computed"), ("source", "source")),
        default="source",
    )
    # How many ingredient lines the computation actually resolved. Source
    # panels cover the whole recipe, so they leave both at zero and the UI
    # reads the method instead of a ratio.
    lines_used = models.PositiveIntegerField(default=0)
    lines_total = models.PositiveIntegerField(default=0)


class Substitution(models.Model):
    from_ingredient = models.ForeignKey(
        Ingredient, on_delete=models.CASCADE, related_name="subs_out"
    )
    to_ingredient = models.ForeignKey(
        Ingredient, on_delete=models.CASCADE, related_name="subs_in"
    )
    swap_note = models.CharField(max_length=200, blank=True)
