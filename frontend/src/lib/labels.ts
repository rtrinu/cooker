const LABELS: Record<string, string> = {
  'american-historical': 'Classic',
  'ye-old-american': 'Classic',
  modern: 'Modern',
}

const INGREDIENT_LABELS: Record<string, string> = {
  'American Indian/Alaska Native Foods': 'Indigenous foods',
}

export function taxonomyLabel(value: string) {
  return LABELS[value] ?? value.replaceAll('-', ' ')
}

export function ingredientCategoryLabel(value: string) {
  return INGREDIENT_LABELS[value] ?? value
}
